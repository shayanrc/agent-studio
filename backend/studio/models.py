"""Pydantic models. camelCase on the wire via the alias generator; `dump()` uses
exclude_none so absent optional fields vanish (the frontend treats missing as
null/undefined). Timestamps are epoch milliseconds."""
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ToolEvent(ApiModel):
    kind: Literal["web", "code", "mcp", "skill", "tool", "file", "run"]
    label: str
    detail: str
    # file-change payloads (write_file / edit_file)
    path: str | None = None
    action: Literal["create", "edit", "delete"] | None = None
    diff: str | None = None
    change_id: str | None = None
    applied: bool | None = None
    # run_command payloads
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None


class Msg(ApiModel):
    id: str
    role: Literal["user", "assistant"]
    kind: Literal["message", "summary"]
    content: str
    tool_events: list[ToolEvent] | None = None
    summary_of: list["Msg"] | None = None
    freed_tokens: int | None = None
    created_at: int


class ForkOf(ApiModel):
    branch_id: str
    message_id: str | None


class Branch(ApiModel):
    id: str
    name: str
    fork_of: ForkOf | None
    messages: list[Msg]
    created_at: int


class Conversation(ApiModel):
    id: str
    title: str
    branches: list[Branch]
    active_branch_id: str
    created_at: int
    updated_at: int


class ConversationSummary(ApiModel):
    id: str
    title: str
    branch_count: int
    updated_at: int


class ModelInfo(ApiModel):
    id: str
    name: str
    context_window: int


class ProviderInfo(ApiModel):
    id: str
    name: str
    env_key: str
    has_key: bool
    models: list[ModelInfo]
    unavailable_reason: str | None = None


class CapabilityInfo(ApiModel):
    id: str
    name: str
    kind: str
    available: bool
    env_key: str | None
    tokens: int
    unavailable_reason: str | None = None


class Meta(ApiModel):
    providers: list[ProviderInfo]
    capabilities: list[CapabilityInfo]
    system_prompt_tokens: int


# --- Project / spec / plan / task workflow ---

class Spec(ApiModel):
    title: str = ""
    goal: str = ""
    requirements: list[str] = []
    constraints: list[str] = []
    assumptions: list[str] = []
    updated_at: int = 0


class Phase(ApiModel):
    id: str
    name: str
    goal: str = ""


class Plan(ApiModel):
    overview: str = ""
    phases: list[Phase] = []
    updated_at: int = 0


class Task(ApiModel):
    id: str
    title: str
    description: str = ""
    status: Literal["pending", "in-progress", "done", "blocked"] = "pending"
    phase: str | None = None
    acceptance: list[str] = []
    depends_on: list[str] = []
    result: str | None = None
    created_at: int = 0
    updated_at: int = 0


class Project(ApiModel):
    id: str
    name: str
    root: str
    spec: Spec
    plan: Plan
    tasks: list[Task] = []
    created_at: int = 0
    updated_at: int = 0


def dump(model: BaseModel) -> dict:
    return model.model_dump(by_alias=True, exclude_none=True)
