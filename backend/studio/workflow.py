"""Spec → plan → tasks: markdown generation + agent context text."""
from . import workspace
from .models import Project


def spec_md(p: Project) -> str:
    s = p.spec
    lines = [f"# SPEC — {s.title or p.name}", ""]
    if s.goal:
        lines += ["## Goal", "", s.goal, ""]
    if s.requirements:
        lines += ["## Requirements", ""] + [f"- {r}" for r in s.requirements] + [""]
    if s.constraints:
        lines += ["## Constraints", ""] + [f"- {c}" for c in s.constraints] + [""]
    if s.assumptions:
        lines += ["## Assumptions", ""] + [f"- {a}" for a in s.assumptions] + [""]
    return "\n".join(lines).rstrip() + "\n"


def plan_md(p: Project) -> str:
    lines = ["# PLAN", ""]
    if p.plan.overview:
        lines += [p.plan.overview, ""]
    phase_ids = {ph.id for ph in p.plan.phases}
    for i, ph in enumerate(p.plan.phases, 1):
        lines.append(f"### {i}. {ph.name}")
        if ph.goal:
            lines += ["", ph.goal]
        tasks = [t for t in p.tasks if t.phase == ph.id]
        if tasks:
            lines += ["", "Tasks:"]
            lines += [f"- [ ] {t.title}" for t in tasks]
        lines.append("")
    unassigned = [t for t in p.tasks if t.phase is None or t.phase not in phase_ids]
    if unassigned:
        lines += ["### Unassigned", ""] + [f"- [ ] {t.title}" for t in unassigned] + [""]
    return "\n".join(lines).rstrip() + "\n"


def tasks_md(p: Project) -> str:
    lines = ["# TASKS", ""]
    box = {"done": "x", "pending": " ", "in-progress": "~", "blocked": "!"}
    for t in p.tasks:
        lines.append(f"- [{box.get(t.status, ' ')}] {t.title}  `{t.status}`")
        if t.description:
            lines.append(f"  - {t.description}")
        if t.acceptance:
            lines.append("  - Acceptance:")
            lines += [f"    - {a}" for a in t.acceptance]
        if t.result:
            lines.append(f"  - Result: {t.result}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def docs(p: Project) -> dict[str, str]:
    return {"SPEC.md": spec_md(p), "PLAN.md": plan_md(p), "TASKS.md": tasks_md(p)}


def write_docs(p: Project) -> None:
    for name, text in docs(p).items():
        workspace.write_file(f"{p.root}/{name}", text)


def context_text(p: Project, task_id: str | None = None) -> str:
    parts = [f"\n\n# Active project: {p.name}\n"]
    parts.append(spec_md(p))
    if task_id:
        task = next((t for t in p.tasks if t.id == task_id), None)
        if task:
            parts.append("\n# Current task (implement this now)\n")
            parts.append(f"## {task.title}\n")
            if task.description:
                parts.append(task.description + "\n")
            if task.acceptance:
                parts.append("Acceptance criteria:")
                parts += [f"- {a}" for a in task.acceptance]
                parts.append("")
            deps = [t for t in p.tasks if t.id in task.depends_on]
            if deps:
                parts.append("Depends on:")
                parts += [f"- {t.title} ({t.status})" for t in deps]
                parts.append("")
    else:
        parts.append(plan_md(p))
        parts.append(tasks_md(p))
    return "\n".join(parts)
