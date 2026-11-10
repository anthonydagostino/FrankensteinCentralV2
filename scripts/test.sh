#!/usr/bin/env bash
# Runs every Tier 1 check locally, the same commands CI runs (see .github/workflows/ci.yml).
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
"$PY" -m pytest -q --cov=app --cov-report=xml:coverage.xml --cov-report=term

echo "== frontend format, lint"
cd "$ROOT/frontend"
npx prettier --check .
npx eslint . --max-warnings 0

echo "== frontend build (tsc + vite)"
npm run build

echo "== frontend unit tests"
npx vitest run --coverage --coverage.reporter=text --coverage.reporter=lcov

echo "All checks passed."
