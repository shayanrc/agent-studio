"""FastAPI app for Agent Studio — branching chat + coding agent + spec/plan/task
workflow + workspace/command runner, all behind one server."""
import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import ops, seed, store, workflow, workspace
from .agent import run_agent, summarize_messages
from .config import SYSTEM_PROMPT, capability_infos, provider_infos
from .models import (
    Conversation,
    Phase,
    Plan,
    Spec,
    Task,
    ToolEvent,
    dump,
)
from .tools import ToolContext

load_dotenv()

# Pending file changes from review-mode chat turns (in-memory; lost on restart).
PENDING_CHANGES: dict[str, dict] = {}


def _json(payload, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status)


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _conv_or_404(conversation_id: str):
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return _json({"error": "conversation not found"}, 404)
    return conv


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.load()
    if not os.environ.get("STUDIO_NO_SEED"):
        seed.ensure_seed()
    yield


app = FastAPI(title="agent-studio", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/api/meta")
def meta():
    return _json({
        "providers": provider_infos(),
        "capabilities": capability_infos(),
        "systemPromptTokens": ops.estimate_tokens(SYSTEM_PROMPT),
    })


# ---------------------------------------------------------------------------
# Conversations (branching chat)
# ---------------------------------------------------------------------------

@app.get("/api/conversations")
def list_conversations():
    return _json([dump(ops.to_summary(c)) for c in store.list_conversations()])


@app.post("/api/conversations")
def create_conversation():
    return _json(dump(store.create_conversation()))


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    return _json(dump(conv))


@app.patch("/api/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    title = str(body.get("title") or "").strip()[:80]
    if title:
        conv.title = title
    store.touch(conv)
    return _json(dump(conv))


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    if not store.delete_conversation(conversation_id):
        return _json({"error": "conversation not found"}, 404)
    return _json({"ok": True})


@app.post("/api/conversations/{conversation_id}/activate")
async def activate(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    branch = ops.get_branch(conv, body.get("branchId"))
    if branch is None:
        return _json({"error": "branch not found"}, 404)
    conv.active_branch_id = branch.id
    store.touch(conv)
    return _json(dump(conv))


@app.post("/api/conversations/{conversation_id}/branch")
async def branch(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    from_branch = ops.get_branch(conv, body.get("branchId") or conv.active_branch_id)
    if from_branch is None:
        return _json({"error": "branch not found"}, 404)
    new_branch = ops.fork_branch(
        conv, from_branch, body.get("messageId"), body.get("name") or ops.next_name(conv, "Branch")
    )
    conv.active_branch_id = new_branch.id
    store.touch(conv)
    return _json(dump(conv))


@app.post("/api/conversations/{conversation_id}/rewind")
async def rewind(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    from_branch = ops.get_branch(conv, body.get("branchId"))
    if from_branch is None:
        return _json({"error": "branch not found"}, 404)
    new_branch = ops.fork_branch(
        conv, from_branch, body.get("messageId"), ops.next_name(conv, "Rewind")
    )
    conv.active_branch_id = new_branch.id
    store.touch(conv)
    return _json(dump(conv))


@app.post("/api/conversations/{conversation_id}/combine")
async def combine(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    try:
        ops.combine_branches(conv, body.get("sourceBranchId"), body.get("targetBranchId"))
    except ValueError:
        return _json({"error": "bad branches"}, 400)
    store.touch(conv)
    return _json(dump(conv))


@app.post("/api/conversations/{conversation_id}/summarize")
async def summarize(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    branch = ops.get_branch(conv, body.get("branchId"))
    if branch is None:
        return _json({"error": "branch not found"}, 404)
    ids = [m.id for m in branch.messages]
    from_id, to_id = body.get("fromId"), body.get("toId")
    if from_id not in ids or to_id not in ids or ids.index(from_id) > ids.index(to_id):
        return _json({"error": "bad range"}, 400)
    lo, hi = ids.index(from_id), ids.index(to_id)
    content = await summarize_messages(
        body.get("provider"), body.get("model"), branch.messages[lo : hi + 1], body.get("apiKeys") or {}
    )
    ops.splice_summary(branch, from_id, to_id, content)
    store.touch(conv)
    return _json(dump(conv))


@app.post("/api/conversations/{conversation_id}/chat")
async def chat(conversation_id: str, request: Request):
    conv = _conv_or_404(conversation_id)
    if isinstance(conv, JSONResponse):
        return conv
    body = await request.json()
    branch = ops.get_branch(conv, body.get("branchId") or conv.active_branch_id)
    if branch is None:
        return _json({"error": "branch not found"}, 404)
    content = body.get("content") or ""
    provider = body.get("provider") or "deepseek"
    model = body.get("model") or "deepseek-chat"
    capabilities = body.get("capabilities") or []
    api_keys = body.get("apiKeys") or {}
    review = bool(body.get("review"))
    project_id = body.get("projectId")
    task_id = body.get("taskId")

    project = store.get_project(project_id) if project_id else None
    task = next((t for t in project.tasks if t.id == task_id), None) if (project and task_id) else None
    prev_status = task.status if task else None
    if project is not None and task is not None:
        task.status = "in-progress"
        task.updated_at = ops.now_ms()
        store.touch_project(project)
    system_extra = workflow.context_text(project, task_id) if project else ""
    ctx = ToolContext(review=review, pending=PENDING_CHANGES, docs=workflow.docs(project) if project else None)

    async def gen():
        user_msg = ops.make_msg("user", content)
        branch.messages.append(user_msg)
        if conv.title == "New chat":
            conv.title = content[:48] + ("…" if len(content) > 48 else "")
        store.touch(conv)
        yield _line({"type": "user", "message": dump(user_msg)})

        assistant = ops.make_msg("assistant", "")
        assistant.tool_events = []
        try:
            async for ev in run_agent(provider, model, branch.messages, api_keys, ctx, capabilities, system_extra):
                if ev["type"] == "delta":
                    assistant.content += ev["text"]
                else:
                    assistant.tool_events.append(ToolEvent.model_validate(ev["event"]))
                yield _line(ev)
            if not assistant.content.strip():
                assistant.content = "(no response)"
            branch.messages.append(assistant)
            store.touch(conv)
            if project is not None and task is not None:
                task.status = "done"
                task.result = assistant.content[:500]
                task.updated_at = ops.now_ms()
                workflow.write_docs(project)
                store.touch_project(project)
            yield _line({"type": "done", "conversation": dump(conv)})
            if project is not None:
                yield _line({"type": "project", "project": dump(project)})
        except asyncio.CancelledError:
            if assistant.content.strip():
                assistant.content += "\n\n*(generation interrupted)*"
                branch.messages.append(assistant)
            store.touch(conv)
            raise
        except Exception as err:  # noqa: BLE001 — surface provider failures to the client
            # nothing was generated → revert the task we just marked in-progress
            if not assistant.content.strip() and project is not None and task is not None:
                task.status = prev_status or "pending"
                task.updated_at = ops.now_ms()
                store.touch_project(project)
            if assistant.content.strip():
                assistant.content += "\n\n*(generation interrupted)*"
                branch.messages.append(assistant)
            store.touch(conv)
            yield _line({"type": "error", "message": str(err)})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Projects + spec/plan/task workflow
# ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    return _json([dump(p) for p in store.list_projects()])


@app.post("/api/projects")
async def create_project(request: Request):
    body = await request.json()
    name = str(body.get("name") or "New project").strip()[:80] or "New project"
    root = str(body.get("root") or "").strip()
    if not root:
        root = re.sub(r"[^A-Za-z0-9._-]+", "-", name.lower()).strip(".-/") or "project"
    root = re.sub(r"[^A-Za-z0-9._-]+", "-", root).strip(".-/") or "project"
    workspace.ensure_dir(root)
    proj = store.create_project(name, root)
    workflow.write_docs(proj)
    return _json(dump(proj))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    return _json(dump(proj))


@app.patch("/api/projects/{project_id}")
async def rename_project(project_id: str, request: Request):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    body = await request.json()
    if body.get("name"):
        proj.name = str(body["name"]).strip()[:80]
    store.touch_project(proj)
    return _json(dump(proj))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if not store.delete_project(project_id):
        return _json({"error": "project not found"}, 404)
    return _json({"ok": True})


@app.put("/api/projects/{project_id}/spec")
async def put_spec(project_id: str, request: Request):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    body = await request.json()
    proj.spec = Spec(
        title=str(body.get("title") or ""),
        goal=str(body.get("goal") or ""),
        requirements=[str(r) for r in (body.get("requirements") or [])],
        constraints=[str(c) for c in (body.get("constraints") or [])],
        assumptions=[str(a) for a in (body.get("assumptions") or [])],
        updated_at=ops.now_ms(),
    )
    workflow.write_docs(proj)
    store.touch_project(proj)
    return _json(dump(proj))


@app.put("/api/projects/{project_id}/plan")
async def put_plan(project_id: str, request: Request):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    body = await request.json()
    phases = []
    for ph in (body.get("phases") or []):
        phases.append(Phase(
            id=str(ph.get("id") or uuid.uuid4()),
            name=str(ph.get("name") or "Phase"),
            goal=str(ph.get("goal") or ""),
        ))
    proj.plan = Plan(overview=str(body.get("overview") or ""), phases=phases, updated_at=ops.now_ms())
    workflow.write_docs(proj)
    store.touch_project(proj)
    return _json(dump(proj))


@app.put("/api/projects/{project_id}/tasks")
async def put_tasks(project_id: str, request: Request):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    body = await request.json()
    tasks = []
    for t in (body.get("tasks") or []):
        d = dict(t)
        d.setdefault("id", str(uuid.uuid4()))
        d.setdefault("title", "Untitled task")
        tasks.append(Task.model_validate(d))
    proj.tasks = tasks
    workflow.write_docs(proj)
    store.touch_project(proj)
    return _json(dump(proj))


@app.patch("/api/projects/{project_id}/tasks/{task_id}")
async def patch_task(project_id: str, task_id: str, request: Request):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    task = next((t for t in proj.tasks if t.id == task_id), None)
    if task is None:
        return _json({"error": "task not found"}, 404)
    body = await request.json()
    if "status" in body:
        task.status = body["status"]
    for field in ("title", "description", "phase", "result"):
        if field in body:
            setattr(task, field, body[field])
    if "acceptance" in body:
        task.acceptance = [str(a) for a in body["acceptance"]]
    if "dependsOn" in body:
        task.depends_on = [str(d) for d in body["dependsOn"]]
    task.updated_at = ops.now_ms()
    workflow.write_docs(proj)
    store.touch_project(proj)
    return _json(dump(proj))


@app.post("/api/projects/{project_id}/docs")
def generate_docs(project_id: str):
    proj = store.get_project(project_id)
    if proj is None:
        return _json({"error": "project not found"}, 404)
    workflow.write_docs(proj)
    store.touch_project(proj)
    return _json(dump(proj))


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@app.get("/api/workspace/tree")
def workspace_tree(path: str = ""):
    try:
        return _json({"tree": workspace.tree(path)})
    except (OSError, ValueError) as e:
        return _json({"error": str(e)}, 400)


@app.get("/api/workspace/file")
def workspace_file(path: str):
    try:
        content = workspace.read_file(path)
        return _json({"path": path, "content": content, "size": len(content)})
    except (OSError, ValueError) as e:
        return _json({"error": str(e)}, 404)


# ---------------------------------------------------------------------------
# Review-mode change approval
# ---------------------------------------------------------------------------

@app.post("/api/changes/apply")
async def apply_changes(request: Request):
    body = await request.json()
    ids = body.get("changeIds") or []
    applied = []
    for cid in ids:
        ch = PENDING_CHANGES.pop(cid, None)
        if ch:
            workspace.write_file(ch["path"], ch["content"])
            applied.append(ch["path"])
    return _json({"ok": True, "applied": applied})


@app.post("/api/changes/discard")
async def discard_changes(request: Request):
    body = await request.json()
    ids = body.get("changeIds") or []
    for cid in ids:
        PENDING_CHANGES.pop(cid, None)
    return _json({"ok": True})


# ---------------------------------------------------------------------------
# Command runner (streaming)
# ---------------------------------------------------------------------------

@app.post("/api/run")
async def run_command(request: Request):
    body = await request.json()
    command = body.get("command") or ""
    cwd = body.get("cwd") or ""
    if not command.strip():
        return _json({"error": "empty command"}, 400)
    try:
        root = workspace.resolve(cwd)
    except ValueError as e:
        return _json({"error": str(e)}, 400)

    async def gen():
        proc = await asyncio.create_subprocess_shell(
            command, cwd=root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        q: asyncio.Queue = asyncio.Queue()

        async def reader(stream, kind):
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                await q.put({"type": kind, "text": chunk.decode("utf-8", "replace")})

        readers = [
            asyncio.create_task(reader(proc.stdout, "stdout")),
            asyncio.create_task(reader(proc.stderr, "stderr")),
        ]

        async def waiter():
            code = await proc.wait()
            for r in readers:
                await r
            await q.put({"type": "exit", "code": code})
            await q.put(None)

        w = asyncio.create_task(waiter())
        while True:
            item = await q.get()
            if item is None:
                break
            yield _line(item)
        await w

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Production: serve the built frontend
# ---------------------------------------------------------------------------

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = _DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
