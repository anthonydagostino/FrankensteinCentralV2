#!/usr/bin/env bash
# Browser integration test for the glance view: starts the backend in mock mode on a spare port against the
# built frontend, runs frontend/e2e/glance.mjs with Playwright, and stops the server. Needs a built frontend
# (npm run build) and Playwright with Chromium available to node (npx playwright install chromium once).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${E2E_PORT:-8777}"
DATA="$(mktemp -d)"
cd "$ROOT/backend"
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
MOCK_MODE=true SECRET_KEY=e2e-secret-key-0123456789abcdef KIOSK_TOKEN=e2e-kiosk-token-0123456789 DASHBOARD_PASSWORD_HASH='' \
  DATA_DIR="$DATA" APP_PORT="$PORT" "$PY" run.py > "$DATA/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; rm -rf "$DATA"' EXIT
for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1; done
# wait for the first refresh of every module the glance view shows, so the check sees data rather than the warm-up state
COOKIES="$DATA/cookies"
curl -sf -c "$COOKIES" -H 'content-type: application/json' -d '{"password":"anything"}' "http://127.0.0.1:$PORT/api/auth/login" >/dev/null
for _ in $(seq 1 60); do
  ready=1
  for m in weather calendar finance/summary lockin transit benefits plex vault containers; do
    curl -sf -b "$COOKIES" "http://127.0.0.1:$PORT/api/$m" | grep -q '"status":"ok"' || ready=0
  done
  [ "$ready" = 1 ] && break
  sleep 1
done
cd "$ROOT/frontend"
BASE_URL="http://127.0.0.1:$PORT" PASSWORD=anything node e2e/glance.mjs
