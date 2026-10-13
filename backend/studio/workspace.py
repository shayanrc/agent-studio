"""Constrained filesystem access to the shared workspace directory. Every path is
workspace-relative; absolute paths and `..` traversal are rejected."""
import difflib
import os
from pathlib import Path

WORKSPACE_ROOT = Path(
    os.environ.get(
        "STUDIO_WORKSPACE",
        Path(__file__).resolve().parent.parent.parent / "workspace",
    )
).resolve()


def resolve(rel_path: str) -> Path:
    rel_path = (rel_path or "").strip() or "."
    abs_path = (WORKSPACE_ROOT / rel_path).resolve()
    try:
        abs_path.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise ValueError(f"path escapes workspace: {rel_path}") from None
    return abs_path


def list_dir(rel_path: str = "") -> list[dict]:
    d = resolve(rel_path)
    if not d.is_dir():
        raise FileNotFoundError(f"not a directory: {rel_path}")
    entries = []
    for p in sorted(d.iterdir()):
        if p.name.startswith("."):
            continue
        is_dir = p.is_dir()
        entries.append(
            {
                "name": p.name,
                "path": str(p.relative_to(WORKSPACE_ROOT)),
                "type": "dir" if is_dir else "file",
                "size": None if is_dir else p.stat().st_size,
            }
        )
    return entries


def read_file(rel_path: str) -> str:
    p = resolve(rel_path)
    if not p.is_file():
        raise FileNotFoundError(f"not a file: {rel_path}")
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(rel_path: str, content: str) -> Path:
    p = resolve(rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def ensure_dir(rel_path: str) -> Path:
    p = resolve(rel_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def exists(rel_path: str) -> bool:
    try:
        return resolve(rel_path).is_file()
    except ValueError:
        return False


def unified_diff(old: str, new: str, rel_path: str) -> str:
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )
    return diff or "(no changes)"


def tree(rel_path: str = "") -> dict:
    """Recursive tree of the workspace under rel_path."""
    root = resolve(rel_path)
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {rel_path}")

    def walk(d: Path) -> dict:
        children = []
        for p in sorted(d.iterdir()):
            if p.name.startswith("."):
                continue
            if p.is_dir():
                children.append({"name": p.name, "path": str(p.relative_to(WORKSPACE_ROOT)), "type": "dir", "children": walk(p)["children"]})
            else:
                children.append({"name": p.name, "path": str(p.relative_to(WORKSPACE_ROOT)), "type": "file", "size": p.stat().st_size})
        return {"children": children}

    if root == WORKSPACE_ROOT:
        return {"name": "", "path": "", "type": "dir", "children": walk(root)["children"]}
    return {"name": root.name, "path": str(root.relative_to(WORKSPACE_ROOT)), "type": "dir", "children": walk(root)["children"]}
