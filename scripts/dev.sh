#!/usr/bin/env bash
# Start the backend (:8181) and frontend dev server (:5173) together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/backend/.venv/bin/python" -m uvicorn studio.main:app --reload --app-dir "$ROOT/backend" --port 8181 &
API_PID=$!

(cd "$ROOT/frontend" && npm run dev) &
WEB_PID=$!

trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' INT TERM EXIT
wait
