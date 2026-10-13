#!/usr/bin/env bash
# One-shot setup: install backend (uv), frontend (npm) and root (concurrently) deps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"

echo "==> Backend (uv sync)"
(cd "$ROOT/backend" && uv sync)

echo "==> Frontend (npm install)"
(cd "$ROOT/frontend" && npm install)

echo "==> Root (npm install)"
(cd "$ROOT" && npm install)

echo ""
echo "Done. Run: npm run dev   →  http://localhost:5173"
