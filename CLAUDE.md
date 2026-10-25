# FrankensteinCentral

Self-hosted personal life dashboard for Anthony. `SPEC.md` is the source of truth; `DECISIONS.md` records choices the spec left open.

## Stack
- Backend: Python 3.12, FastAPI, Uvicorn, httpx, Pydantic v2, SQLite, icalendar + recurring-ical-events. Lives in `backend/` (package `app`).
- Frontend: React + Vite + TypeScript, Tailwind CSS, TanStack Query, Recharts, lucide-react, date-fns. Lives in `frontend/`.
- One container serves the API (`/api/*`) and the built SPA. Docker access only through `tecnativa/docker-socket-proxy`.

## Commands
- Backend dev: `cd backend && uv sync && uv run python run.py` (or `pip install -e .[dev]`).
- Backend tests: `cd backend && uv run pytest`.
- Frontend dev: `cd frontend && npm install && npm run dev` (proxies `/api` to port 8000).
- Frontend build and tests: `cd frontend && npm run build && npm test`.
- Everything: `scripts/test.sh`.
- Production: `docker compose build && docker compose up -d`.

## Rules
1. Never stop to ask questions. Pick the spec DEFAULT, or the simplest option that meets acceptance, and log it in `DECISIONS.md`.
2. Mock mode first. Every integration works with `MOCK_MODE=true` from fixtures in `backend/app/fixtures/`. Per integration overrides: `MOCK_WEATHER`, `MOCK_CALENDAR`, `MOCK_FIREFLY`, `MOCK_PLEX`, `MOCK_VAULT`, `MOCK_DOCKER`, `MOCK_LOCKIN`.
3. Every widget is independent. One failing integration never breaks the page. Failed widgets show last good data with a stale badge or an error card.
4. Secrets never reach the browser. All third party calls happen in the backend. Never log tokens, URLs containing tokens, or iCal secret URLs. The logging filter redacts them.
5. Money is `Decimal` end to end; serialize as strings with two decimals. Direction comes from Firefly `type` and source/destination, never from the sign of `amount`.
6. All backend time math uses aware datetimes. Store UTC, display `America/New_York`.
7. UI copy, README and docs use American English. Never use em dashes or double hyphens as punctuation. Use commas, colons, or parentheses.
8. Every module route returns the standard envelope: `module, status, configured, fetched_at, stale, error, data`.
