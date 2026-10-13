"""ReAct agent streaming, ported from deku-chat's agent.py. Yields
{'type':'delta','text':...} and {'type':'tool','event':{...}} dicts."""
import os
from collections.abc import AsyncIterator

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from . import ops
from .config import SUMMARIZE_PROMPT, SYSTEM_PROMPT, provider_by_id
from .models import Msg, dump
from .tools import ToolContext, make_file_tools, tool_event_for, tools_for_capabilities


def build_model(provider: str, model: str, api_keys: dict[str, str]):
    d = provider_by_id(provider)
    if d is None:
        raise ValueError(f"Unknown provider: {provider}")
    key = api_keys.get(d["envKey"]) or os.environ.get(d["envKey"])
    if not key:
        raise ValueError(
            f"No API key for {d['name']} — add one via the avatar → “API keys…”."
        )
    kwargs: dict = {"api_key": key}
    if provider == "anthropic":
        kwargs["max_tokens"] = 4096
    return init_chat_model(model, model_provider=d["prefix"], **kwargs)


def to_lc_messages(history: list[Msg], system_extra: str = ""):
    out = [SystemMessage(SYSTEM_PROMPT + system_extra)]
    for m in history:
        if m.kind == "summary":
            out.append(AIMessage(f"[Summary of earlier conversation] {m.content}"))
        elif m.role == "user":
            out.append(HumanMessage(m.content))
        else:
            out.append(AIMessage(m.content))
    return out


def chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict) and c.get("type") in ("text", "text_delta"):
                parts.append(c.get("text", ""))
        return "".join(parts)
    return ""


async def run_agent(
    provider: str,
    model: str,
    history: list[Msg],
    api_keys: dict[str, str],
    ctx: ToolContext,
    capabilities: list[str] = (),
    system_extra: str = "",
) -> AsyncIterator[dict]:
    llm = build_model(provider, model, api_keys)
    tools = make_file_tools(ctx) + tools_for_capabilities(capabilities, api_keys)
    agent = create_react_agent(llm, tools)
    async for ev in agent.astream_events({"messages": to_lc_messages(history, system_extra)}, version="v2"):
        if ev["event"] == "on_chat_model_stream":
            text = chunk_text(getattr(ev["data"].get("chunk"), "content", None))
            if text:
                yield {"type": "delta", "text": text}
        elif ev["event"] == "on_tool_end":
            if ctx.events:
                yield {"type": "tool", "event": dump(ctx.events.pop(0))}
            else:
                output = ev["data"].get("output")
                output_text = (
                    output if isinstance(output, str) else chunk_text(getattr(output, "content", None))
                )
                yield {
                    "type": "tool",
                    "event": dump(tool_event_for(ev["name"], ev["data"].get("input"), output_text)),
                }


async def summarize_messages(
    provider: str, model: str, msgs: list[Msg], api_keys: dict[str, str]
) -> str:
    transcript = "\n\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in msgs
    )
    try:
        llm = build_model(provider, model, api_keys)
        res = await llm.ainvoke([SystemMessage(SUMMARIZE_PROMPT), HumanMessage(transcript)])
        return chunk_text(res.content).strip() or ops.summary_fallback(msgs)
    except Exception:
        return ops.summary_fallback(msgs)
