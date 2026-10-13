"""JSON-file persistence for conversations + projects. Single-process in-memory
cache (run uvicorn with one worker), saved on every mutation."""
import json
import os
from pathlib import Path

from . import ops
from .models import Conversation, Project

DATA_DIR = Path(os.environ.get("STUDIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "db.json"

_conversations: list[Conversation] = []
_projects: list[Project] = []


def load() -> None:
    global _conversations, _projects
    try:
        raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
        _conversations = [Conversation.model_validate(c) for c in raw.get("conversations", [])]
        _projects = [Project.model_validate(p) for p in raw.get("projects", [])]
    except (OSError, ValueError, KeyError):
        _conversations = []
        _projects = []


def save() -> None:
    from .models import dump

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "conversations": [dump(c) for c in _conversations],
        "projects": [dump(p) for p in _projects],
    }
    DB_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# --- conversations ---

def list_conversations() -> list[Conversation]:
    return sorted(_conversations, key=lambda c: c.updated_at, reverse=True)


def get_conversation(conversation_id: str) -> Conversation | None:
    return next((c for c in _conversations if c.id == conversation_id), None)


def create_conversation() -> Conversation:
    conv = ops.new_conversation()
    _conversations.append(conv)
    save()
    return conv


def delete_conversation(conversation_id: str) -> bool:
    global _conversations
    before = len(_conversations)
    _conversations = [c for c in _conversations if c.id != conversation_id]
    save()
    return len(_conversations) < before


def touch(conv: Conversation) -> None:
    ops.touch(conv)
    save()


# --- projects ---

def list_projects() -> list[Project]:
    return sorted(_projects, key=lambda p: p.updated_at, reverse=True)


def get_project(project_id: str) -> Project | None:
    return next((p for p in _projects if p.id == project_id), None)


def create_project(name: str, root: str) -> Project:
    proj = ops.new_project(name, root)
    _projects.append(proj)
    save()
    return proj


def delete_project(project_id: str) -> bool:
    global _projects
    before = len(_projects)
    _projects = [p for p in _projects if p.id != project_id]
    save()
    return len(_projects) < before


def touch_project(proj: Project) -> None:
    proj.updated_at = ops.now_ms()
    save()
