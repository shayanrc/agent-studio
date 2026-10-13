# Agent Studio ⚡

A greenfield **fullstack** app that combines two tools into one operable workspace:

- **Agent-driven development** — a coding agent that reads, writes, and edits files in a
  shared workspace and runs shell commands to verify its work (inspired by `deepseek-engineer`).
- **Deku chat** — agentic chat with git-like **branching conversations** (branch / rewind /
  combine / summarize) and multi-provider streaming (inspired by `deku-chat`).

On top of both sits a **spec → plan → task** workflow that stays in sync as structured records
in the UI *and* as `SPEC.md` / `PLAN.md` / `TASKS.md` files written into the workspace. You
operate and test the whole thing from one web UI.

![stack](https://img.shields.io/badge/FastAPI-Python-009688)
![stack](https://img.shields.io/badge/React_18-TypeScript-61DAFB)
![stack](https://img.shields.io/badge/LangGraph-ReAct_agent-1C3C3C)
![providers](https://img.shields.io/badge/LLM_providers-8-9184d9)

## What you get

| View | What it does |
| --- | --- |
| **Chat** | Branching agentic chat. The agent has file + shell tools. Toggle **Review** to have file changes proposed as diffs you approve/discard, or leave it off to apply immediately. |
| **Board** | Project list + editable **Spec / Plan / Tasks**. Each task has an **⚡ Implement** button that scopes the agent to that task and marks it in-progress → done. |
| **Files** | The live workspace file tree + file viewer (markdown rendered, everything else as text). |
| **Run** | A streaming shell runner with live stdout/stderr and exit code. |
| **Data** | Load a `.csv` / `.json` from the workspace and visualize it as a table + bar/line chart. |

## Features

### Branching conversations (from deku-chat)
Conversations are trees: **branch** (full copy), **rewind** to any message, **combine** one
branch onto another (active branch is the source), and **summarize** a message into a compact
node that keeps the original behind "Show original". The same ops are implemented and tested
on the backend (`backend/studio/ops.py`).

### Coding agent (from deepseek-engineer)
Tools exposed to the model: `list_directory`, `read_file`, `write_file`, `edit_file`
(targeted string replace), `run_command`, and `read_project_docs`. File changes stream back to
the UI as **unified diffs**. In **Review** mode they are staged (not written) and each diff gets
**Apply / Discard**; reads during the turn see the staged content.

### Spec → plan → task workflow
Structured records (spec, plan with phases, tasks with acceptance criteria + status) drive the
Board, and every mutation regenerates `SPEC.md`, `PLAN.md`, and `TASKS.md` inside the project's
workspace directory — so the docs and the UI never drift.

### Multi-provider
DeepSeek, Anthropic, OpenAI, Google, Mistral, Groq, Cohere, xAI. Keys are held in the browser
(localStorage) and sent per-request, with server `.env` as a fallback. Same provider registry as
deku-chat.

## Architecture

```
agent-studio/
├── backend/            # FastAPI + LangGraph (Python, uv)
│   ├── studio/
│   │   ├── main.py     # all routes (chat, projects, workspace, changes, run)
│   │   ├── agent.py    # create_react_agent streaming
│   │   ├── tools.py    # file tools + calculator/clock/web_search
│   │   ├── ops.py      # branching ops (pure, tested)
│   │   ├── workflow.py # spec/plan/tasks → markdown + agent context
│   │   ├── workspace.py# path-confined file access to ./workspace
│   │   ├── store.py    # JSON persistence (data/db.json)
│   │   └── seed.py     # demo project + workspace on first run
│   └── tests/          # pytest (ops + API smoke)
├── frontend/           # Vite + React 18 + TypeScript
│   └── src/
│       ├── App.tsx     # shell + nav + API-keys modal
│       ├── ChatView.tsx
│       ├── BoardView.tsx
│       ├── FilesView.tsx
│       ├── RunView.tsx
│       └── DataView.tsx
├── workspace/          # where the agent reads/writes (gitignored, seeded at runtime)
├── data/               # db.json (gitignored, created at runtime)
└── scripts/            # setup.sh, dev.sh
```

## Setup

Prereqs: Node 20+, Python 3.11+, [`uv`](https://docs.astral.sh/uv/).

```bash
bash scripts/setup.sh     # backend uv sync + frontend npm install + root npm install
```

Or manually:

```bash
cd backend && uv sync
cd ../frontend && npm install
cd .. && npm install
```

> If your `uv`/`npm` cache lives on a read-only mount, point them at a writable dir first:
> `export UV_CACHE_DIR=./.uv-cache` and `npm install --cache ./.npm-cache`.

## Run

```bash
npm run dev
# backend  : http://localhost:8181  (FastAPI + uvicorn --reload)
# frontend : http://localhost:5173  (Vite, proxies /api → :8181)
```

Open http://localhost:5173. Add a provider key via **⚙️ → API keys…** (or copy
`backend/.env.example` to `backend/.env`).

On first run a demo project **"Demo: Greeting CLI"** is seeded under `workspace/demo-app/`,
so you can immediately: run `python main.py Ada` (Run view), implement its pending task
(Board → ⚡ Implement), review the diff, and visualize `demo-app/data.csv` (Data view).

## Test & verify

```bash
npm test                 # backend pytest (ops + API smoke)
npm run typecheck        # frontend tsc
npm run build            # frontend production build (then backend serves it on :8181)
```

## API surface

- `GET /api/meta` — providers, capabilities, system-prompt tokens
- `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/{id}`
- `POST /api/conversations/{id}/activate|branch|rewind|combine|summarize`
- `POST /api/conversations/{id}/chat` — NDJSON stream (`delta`/`tool`/`done`/`project`/`error`);
  accepts `review`, `projectId`, `taskId`
- `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}`
- `PUT /api/projects/{id}/spec|plan|tasks`, `PATCH /api/projects/{id}/tasks/{taskId}`,
  `POST /api/projects/{id}/docs`
- `GET /api/workspace/tree?path=`, `GET /api/workspace/file?path=`
- `POST /api/changes/apply|discard` — review-mode approval
- `POST /api/run` — streaming command runner

## Notes & limits

- **Review-mode changes are held in memory** (`PENDING_CHANGES`) and are lost on server restart;
  they are meant to be applied/discarded in the same session.
- `run_command` is a convenience for a local dev workspace — it is confined to `workspace/` as
  its working directory but is **not** a hardened sandbox.
- Backend is single-worker (in-memory JSON store); run uvicorn with one worker.
