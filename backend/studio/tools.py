"""LangChain tools for the coding agent + optional capability tools (ported from
deku-chat). File tools read/write through the workspace module and, in review mode,
stage changes in the ToolContext overlay instead of touching disk."""
import ast
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from . import workspace
from .models import ToolEvent


@dataclass
class ToolContext:
    """Per-turn state shared by the file tools and the agent loop."""
    review: bool = False
    staged: dict[str, str] = field(default_factory=dict)     # rel path -> staged content
    pending: dict[str, dict] = field(default_factory=dict)   # changeId -> {path, content}
    events: list[ToolEvent] = field(default_factory=list)    # rich events, FIFO per turn
    docs: dict[str, str] | None = None                       # {SPEC.md: ..., PLAN.md: ...}


def _emit(ctx: ToolContext, ev: ToolEvent, message: str) -> str:
    ctx.events.append(ev)
    return message


def _current(ctx: ToolContext, rel: str) -> str:
    if ctx.review and rel in ctx.staged:
        return ctx.staged[rel]
    try:
        return workspace.read_file(rel)
    except (OSError, ValueError):
        return ""


def _exists(ctx: ToolContext, rel: str) -> bool:
    if ctx.review and rel in ctx.staged:
        return True
    return workspace.exists(rel)


def make_file_tools(ctx: ToolContext):
    class _Path(BaseModel):
        path: str = Field(description="Workspace-relative path ('' for root)")

    @tool(args_schema=_Path)
    def list_directory(path: str) -> str:
        """List files and subdirectories at a workspace-relative path."""
        try:
            entries = workspace.list_dir(path)
        except (OSError, ValueError) as e:
            return f"ERROR: {e}"
        if not entries:
            return "(empty directory)"
        return "\n".join(
            f"{'[dir] ' if e['type'] == 'dir' else '      '}{e['path']}" for e in entries
        )

    class _Read(BaseModel):
        path: str = Field(description="Workspace-relative file path to read")

    @tool(args_schema=_Read)
    def read_file(path: str) -> str:
        """Read the contents of a file in the workspace."""
        try:
            return _current(ctx, path)
        except (OSError, ValueError) as e:
            return f"ERROR: {e}"

    class _Write(BaseModel):
        path: str = Field(description="Workspace-relative path to create or overwrite")
        content: str = Field(description="Full file content to write")

    @tool(args_schema=_Write)
    def write_file(path: str, content: str) -> str:
        """Create a new file or overwrite an existing file with the given content."""
        existed = _exists(ctx, path)
        old = _current(ctx, path)
        if ctx.review:
            cid = str(uuid.uuid4())
            ctx.staged[path] = content
            ctx.pending[cid] = {"path": path, "content": content}
            diff = workspace.unified_diff(old, content, path)
            ev = ToolEvent(
                kind="file",
                label=f"Propose {'edit' if existed else 'create'} {path}",
                detail=f"{'Edit' if existed else 'Create'} {path} — awaiting approval",
                path=path,
                action="edit" if existed else "create",
                diff=diff,
                change_id=cid,
                applied=False,
            )
            return _emit(ctx, ev, f"Proposed {'edit to' if existed else 'create of'} {path}.")
        workspace.write_file(path, content)
        diff = workspace.unified_diff(old, content, path)
        ev = ToolEvent(
            kind="file",
            label=f"{'Edit' if existed else 'Create'} {path}",
            detail=f"{'Edited' if existed else 'Created'} {path}",
            path=path,
            action="edit" if existed else "create",
            diff=diff,
            applied=True,
        )
        return _emit(ctx, ev, f"{'Updated' if existed else 'Created'} {path}.")

    class _Edit(BaseModel):
        path: str = Field(description="Workspace-relative path to edit")
        old_string: str = Field(description="Exact snippet to find")
        new_string: str = Field(description="Replacement snippet")

    @tool(args_schema=_Edit)
    def edit_file(path: str, old_string: str, new_string: str) -> str:
        """Replace the first occurrence of old_string with new_string in a file."""
        cur = _current(ctx, path)
        if old_string not in cur:
            return f"ERROR: old_string not found in {path}. No change made."
        new_content = cur.replace(old_string, new_string, 1)
        if ctx.review:
            cid = str(uuid.uuid4())
            ctx.staged[path] = new_content
            ctx.pending[cid] = {"path": path, "content": new_content}
            diff = workspace.unified_diff(cur, new_content, path)
            ev = ToolEvent(
                kind="file",
                label=f"Propose edit {path}",
                detail=f"Edit {path} — awaiting approval",
                path=path,
                action="edit",
                diff=diff,
                change_id=cid,
                applied=False,
            )
            return _emit(ctx, ev, f"Proposed edit to {path}.")
        workspace.write_file(path, new_content)
        diff = workspace.unified_diff(cur, new_content, path)
        ev = ToolEvent(
            kind="file",
            label=f"Edit {path}",
            detail=f"Edited {path}",
            path=path,
            action="edit",
            diff=diff,
            applied=True,
        )
        return _emit(ctx, ev, f"Edited {path}.")

    class _Run(BaseModel):
        command: str = Field(description="Shell command to run inside the workspace")
        cwd: str = Field(default="", description="Workspace-relative working directory")

    @tool(args_schema=_Run)
    def run_command(command: str, cwd: str = "") -> str:
        """Run a shell command inside the workspace; returns stdout/stderr and exit code."""
        try:
            root = workspace.resolve(cwd)
        except ValueError as e:
            return f"ERROR: {e}"
        try:
            proc = subprocess.run(
                command, shell=True, cwd=root, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired:
            ev = ToolEvent(kind="run", label=f"$ {command}", detail="timed out")
            return _emit(ctx, ev, f"Command timed out: {command}")
        out, err = proc.stdout or "", proc.stderr or ""
        detail = (out + err).strip()[:200]
        ev = ToolEvent(
            kind="run",
            label=f"$ {command}",
            detail=detail,
            exit_code=proc.returncode,
            stdout=out[:2000],
            stderr=err[:1000],
        )
        summary = out[:3000] + (("\n[stderr]\n" + err[:1500]) if err else "") + f"\n[exit {proc.returncode}]"
        return _emit(ctx, ev, summary)

    @tool
    def read_project_docs() -> str:
        """Read the active project's SPEC, PLAN and TASKS markdown documents."""
        if not ctx.docs:
            return "No active project."
        return "\n\n".join(f"# {name}\n{text}" for name, text in ctx.docs.items())

    return [list_directory, read_file, write_file, edit_file, run_command, read_project_docs]


# ---------------------------------------------------------------------------
# Optional capability tools (calculator / clock / web search), ported from deku
# ---------------------------------------------------------------------------

_CALC_RE = re.compile(r"^[\d+\-*/().%\s^eE,]+$")

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
)


def _safe_eval(expression: str) -> float:
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("Only arithmetic expressions are supported")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("Only arithmetic expressions are supported")
    return eval(compile(tree, "<calculator>", "eval"))  # noqa: S307 — AST-whitelisted


class CalculatorInput(BaseModel):
    expression: str = Field(description="e.g. (1234 * 5678) / 9")


@tool(args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression exactly. Supports + - * / % ^ and parentheses."""
    if not _CALC_RE.match(expression):
        raise ValueError("Only arithmetic expressions are supported")
    value = _safe_eval(expression)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


@tool
def clock() -> str:
    """Get the current date and time."""
    now = datetime.now().astimezone()
    return now.strftime("%a %b %d %Y %H:%M:%S GMT%z (%Z)")


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")


def make_web_search(tavily_key: str):
    @tool(args_schema=WebSearchInput)
    async def web_search(query: str) -> str:
        """Search the web for current information."""
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": 5, "include_answer": True},
            )
        if res.status_code != 200:
            raise RuntimeError(f"Tavily search failed: {res.status_code}")
        data = res.json()
        hits = "\n".join(
            f"- {r['title']} ({r['url']})\n  {r['content'][:300]}" for r in data.get("results", [])
        )
        answer = data.get("answer")
        return f"{f'Answer: {answer}\n\n' if answer else ''}Results:\n{hits}"

    return web_search


def tools_for_capabilities(capabilities: list[str], api_keys: dict[str, str]):
    tools = []
    tavily_key = api_keys.get("TAVILY_API_KEY") or os.environ.get("TAVILY_API_KEY")
    if "web_search" in capabilities and tavily_key:
        tools.append(make_web_search(tavily_key))
    if "calculator" in capabilities:
        tools.append(calculator)
    if "clock" in capabilities:
        tools.append(clock)
    return tools


_KINDS = {"web_search": "web", "calculator": "code", "clock": "tool"}
_LABELS = {"web_search": "Web search", "calculator": "Calculator", "clock": "Clock"}


def tool_event_for(name: str, tool_input, output: str | None = None) -> ToolEvent:
    if isinstance(tool_input, dict) and "input" in tool_input and len(tool_input) == 1:
        tool_input = tool_input["input"]
    tool_input = tool_input or {}
    if name == "web_search":
        detail = f"Searched “{tool_input.get('query', '')}”"
    elif name == "calculator":
        expr = tool_input.get("expression", "")
        detail = f"{expr} = {output}" if output else f"Evaluated {expr}"
    elif name == "clock":
        detail = f"Read the clock — {output[:33]}" if output else "Read the clock"
    else:
        import json as _json

        detail = _json.dumps(tool_input)[:120]
    return ToolEvent(kind=_KINDS.get(name, "tool"), label=_LABELS.get(name, name), detail=detail)
