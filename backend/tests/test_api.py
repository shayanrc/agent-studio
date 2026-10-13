import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["STUDIO_WORKSPACE"] = os.path.join(_tmp, "ws")
os.environ["STUDIO_DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["STUDIO_NO_SEED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from studio.main import app  # noqa: E402


def _client():
    return TestClient(app)


def test_meta():
    with _client() as c:
        r = c.get("/api/meta")
        assert r.status_code == 200
        data = r.json()
        assert any(p["id"] == "deepseek" for p in data["providers"])


def test_conversation_crud_and_branch():
    with _client() as c:
        conv = c.post("/api/conversations").json()
        cid = conv["id"]
        main = conv["activeBranchId"]

        r = c.post(f"/api/conversations/{cid}/branch", json={"branchId": main})
        assert r.status_code == 200
        assert len(r.json()["branches"]) == 2

        # rename
        r = c.patch(f"/api/conversations/{cid}", json={"title": "Hello"})
        assert r.json()["title"] == "Hello"


def test_project_workflow_and_docs():
    with _client() as c:
        r = c.post("/api/projects", json={"name": "Test App", "root": "test-app"})
        assert r.status_code == 200
        pid = r.json()["id"]

        r = c.put(
            f"/api/projects/{pid}/spec",
            json={"title": "T", "goal": "g", "requirements": ["a", "b"]},
        )
        assert r.json()["spec"]["requirements"] == ["a", "b"]

        r = c.put(
            f"/api/projects/{pid}/tasks",
            json={"tasks": [{"title": "t1", "status": "pending"}]},
        )
        assert len(r.json()["tasks"]) == 1

        # docs written into the workspace
        r = c.get("/api/workspace/file", params={"path": "test-app/SPEC.md"})
        assert r.status_code == 200
        assert "# SPEC" in r.json()["content"]


def test_workspace_safety():
    with _client() as c:
        r = c.get("/api/workspace/file", params={"path": "../secret"})
        assert r.status_code in (400, 404)


def test_run_command():
    with _client() as c:
        r = c.post("/api/run", json={"command": "echo hello"})
        assert r.status_code == 200
        body = r.text
        assert "hello" in body
        assert '"exit"' in body


def test_chat_without_key_streams_error(monkeypatch):
    for key in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with _client() as c:
        cid = c.post("/api/conversations").json()["id"]
        with c.stream(
            "POST",
            f"/api/conversations/{cid}/chat",
            json={
                "content": "hi",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "apiKeys": {},
                "review": False,
            },
        ) as resp:
            body = "".join(resp.iter_text())
        assert '"type": "user"' in body
        assert '"type": "error"' in body
