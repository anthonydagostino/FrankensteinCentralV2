#!/usr/bin/env bash
# Runs every check: backend tests, frontend typecheck and build, frontend unit tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== backend tests"
cd "$ROOT/backend"
if command -v uv >/dev/null 2>&1; then
  uv run --python .venv/bin/python pytest -q 2>/dev/null || .venv/bin/python -m pytest -q
else
  python -m pytest -q
fi

echo "== frontend build (tsc + vite)"
cd "$ROOT/frontend"
npm run build

echo "== frontend unit tests"
npm test

echo "All checks passed."
