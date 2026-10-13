"""Branching conversation ops + project helpers. Ported from deku-chat's ops.py."""
import math
import time
import uuid

from .models import (
    Branch,
    Conversation,
    ConversationSummary,
    ForkOf,
    Msg,
    Plan,
    Project,
    Spec,
)


def now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid.uuid4())


def estimate_tokens(text: str) -> int:
    """rough universal token estimate: ~4 chars per token"""
    return math.ceil(len(text) / 4)


def message_tokens(m: Msg) -> int:
    tools = sum(estimate_tokens(t.label + t.detail) for t in (m.tool_events or []))
    return estimate_tokens(m.content) + tools + 4


def make_msg(role: str, content: str, id: str | None = None) -> Msg:
    return Msg(id=id or _uuid(), role=role, kind="message", content=content, created_at=now_ms())


def new_conversation(id: str | None = None) -> Conversation:
    now = now_ms()
    main = Branch(id=_uuid(), name="Main", fork_of=None, messages=[], created_at=now)
    return Conversation(
        id=id or _uuid(),
        title="New chat",
        branches=[main],
        active_branch_id=main.id,
        created_at=now,
        updated_at=now,
    )


def touch(conv: Conversation) -> None:
    conv.updated_at = now_ms()


def get_branch(conv: Conversation, branch_id: str | None) -> Branch | None:
    if branch_id is None:
        return None
    return next((b for b in conv.branches if b.id == branch_id), None)


def fork_branch(conv: Conversation, from_branch: Branch, message_id: str | None, name: str) -> Branch:
    """New branch with from_branch's messages up to and including message_id.
    message_id None = full copy (plain Branch); forkOf.messageId is then the tip."""
    prefix = from_branch.messages
    if message_id is not None:
        idx = next((i for i, m in enumerate(from_branch.messages) if m.id == message_id), -1)
        if idx == -1:
            raise ValueError("message not found in branch")
        prefix = from_branch.messages[: idx + 1]
    tip = from_branch.messages[-1].id if from_branch.messages else None
    branch = Branch(
        id=_uuid(),
        name=name,
        fork_of=ForkOf(
            branch_id=from_branch.id,
            message_id=message_id if message_id is not None else tip,
        ),
        messages=[m.model_copy(deep=True) for m in prefix],
        created_at=now_ms(),
    )
    conv.branches.append(branch)
    return branch


def next_name(conv: Conversation, base: str) -> str:
    n = len([b for b in conv.branches if b.name.startswith(base)]) + 1
    return f"{base} {n}"


def combine_branches(conv: Conversation, source_branch_id: str, target_branch_id: str) -> None:
    """Append source's messages target lacks (by id), re-point source's children
    at target, delete source, activate target."""
    source = get_branch(conv, source_branch_id)
    target = get_branch(conv, target_branch_id)
    if source is None or target is None or source.id == target.id:
        raise ValueError("bad branches")
    target_ids = {m.id for m in target.messages}
    target.messages.extend(m.model_copy(deep=True) for m in source.messages if m.id not in target_ids)
    for b in conv.branches:
        if b.fork_of is not None and b.fork_of.branch_id == source.id:
            b.fork_of.branch_id = target.id
    conv.branches = [b for b in conv.branches if b.id != source.id]
    conv.active_branch_id = target.id


def splice_summary(branch: Branch, from_id: str, to_id: str, summary_text: str) -> Msg:
    """Replace [from_id..to_id] with a summary node keeping the originals and the
    freed-token estimate (floored at 0)."""
    lo = next((i for i, m in enumerate(branch.messages) if m.id == from_id), -1)
    hi = next((i for i, m in enumerate(branch.messages) if m.id == to_id), -1)
    if lo == -1 or hi == -1 or lo > hi:
        raise ValueError("bad range")
    originals = branch.messages[lo : hi + 1]
    freed = sum(message_tokens(m) for m in originals) - estimate_tokens(summary_text)
    base = make_msg("assistant", summary_text)
    summary = base.model_copy(
        update={"kind": "summary", "summary_of": originals, "freed_tokens": max(freed, 0)}
    )
    branch.messages[lo : hi + 1] = [summary]
    return summary


def summary_fallback(msgs: list[Msg]) -> str:
    def first_line(s: str) -> str:
        return s.split("\n")[0][:90]

    return f"{first_line(msgs[0].content)} → {first_line(msgs[-1].content)}"


def to_summary(c: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=c.id, title=c.title, branch_count=len(c.branches), updated_at=c.updated_at
    )


# --- projects ---

def new_project(name: str, root: str, id: str | None = None) -> Project:
    now = now_ms()
    return Project(
        id=id or _uuid(),
        name=name,
        root=root,
        spec=Spec(updated_at=now),
        plan=Plan(updated_at=now),
        tasks=[],
        created_at=now,
        updated_at=now,
    )
