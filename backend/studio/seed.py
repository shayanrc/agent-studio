"""Seed a demo project + workspace files on first run so the app is operable
immediately (skipped when STUDIO_NO_SEED=1, e.g. in tests)."""
import uuid

from . import store, workflow, workspace
from .models import Phase, Plan, Spec, Task
from .ops import now_ms

DEMO_FILES = {
    "demo-app/main.py": (
        'def greet(name: str = "world") -> str:\n'
        '    return f"Hello, {name}!"\n\n\n'
        'if __name__ == "__main__":\n'
        '    import sys\n'
        '    who = sys.argv[1] if len(sys.argv) > 1 else "world"\n'
        '    print(greet(who))\n'
    ),
    "demo-app/test_main.py": (
        "from main import greet\n\n\n"
        "def test_greet():\n"
        '    assert greet() == "Hello, world!"\n'
        '    assert greet("Ada") == "Hello, Ada!"\n'
    ),
    "demo-app/data.csv": (
        "month,revenue,expenses\n"
        "Jan,120,80\nFeb,150,90\nMar,110,70\nApr,180,100\nMay,200,120\nJun,170,95\n"
    ),
    "demo-app/README.md": (
        "# demo-app\n\n"
        "A tiny greeting CLI used to exercise Agent Studio.\n\n"
        "Run it:\n\n```bash\npython main.py Ada\n```\n\n"
        "Test it:\n\n```bash\npython -m pytest\n```\n"
    ),
}


def ensure_seed() -> None:
    for rel, content in DEMO_FILES.items():
        if not workspace.exists(rel):
            try:
                workspace.write_file(rel, content)
            except ValueError:
                continue
    if store.list_projects():
        return
    proj = store.create_project("Demo: Greeting CLI", "demo-app")
    now = now_ms()
    proj.spec = Spec(
        title="Greeting CLI",
        goal="A tiny CLI that prints a personalized greeting.",
        requirements=[
            "greet(name) returns 'Hello, <name>!'",
            "CLI prints the greeting to stdout",
        ],
        constraints=["Python 3.11+"],
        assumptions=["pytest is available"],
        updated_at=now,
    )
    phase = Phase(id=str(uuid.uuid4()), name="Core", goal="Implement and test greet()")
    proj.plan = Plan(
        overview="Build the CLI in a single phase, then verify with tests.",
        phases=[phase],
        updated_at=now,
    )
    proj.tasks = [
        Task(
            id=str(uuid.uuid4()),
            title="Implement greet()",
            description="Add a greet(name) function that returns 'Hello, <name>!'.",
            status="done",
            phase=phase.id,
            acceptance=["greet() == 'Hello, world!'"],
            created_at=now,
            updated_at=now,
        ),
        Task(
            id=str(uuid.uuid4()),
            title="Add CLI entrypoint",
            description="Read an optional name from sys.argv and print the greeting.",
            status="pending",
            phase=phase.id,
            acceptance=["python main.py Ada prints 'Hello, Ada!'"],
            created_at=now,
            updated_at=now,
        ),
    ]
    store.touch_project(proj)
    workflow.write_docs(proj)
