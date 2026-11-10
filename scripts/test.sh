#!/usr/bin/env bash
# Runs every check: backend tests, frontend typecheck and build, frontend unit tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== backend lint, format, types"
cd "$ROOT/backend"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python
"$PY" -m ruff check .
"$PY" -m ruff format --check .
"$PY" -m mypy app

echo "== backend tests"
"$PY" -m pytest -q

echo "== frontend build (tsc + vite)"
cd "$ROOT/frontend"
npm run build

echo "== frontend unit tests"
npm test

echo "All checks passed."
