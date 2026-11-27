# FrankensteinCentral

Self-hosted personal life dashboard for Anthony. `SPEC.md` is the source of truth; `DECISIONS.md` records choices the spec left open.

## Stack
- Backend: Python 3.12, FastAPI, Uvicorn, httpx, Pydantic v2, SQLite, icalendar + recurring-ical-events. Lives in `backend/` (package `app`).
- Frontend: React + Vite + TypeScript, Tailwind CSS, TanStack Query, Recharts, lucide-react, date-fns. Lives in `frontend/`.
- One container serves the API (`/api/*`) and the built SPA. Docker access only through `tecnativa/docker-socket-proxy`.

## Commands
- Backend dev: `cd backend && uv sync && uv run python run.py` (or `pip install -e .[dev]`).
- Backend checks: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app`.
- Backend tests: `cd backend && uv run pytest`.
- Frontend dev: `cd frontend && npm install && npm run dev` (proxies `/api` to port 8000).
- Frontend checks: `cd frontend && npx prettier --check . && npx eslint . --max-warnings 0`.
- Frontend build and tests: `cd frontend && npm run build && npm test`.
- Everything (same as CI): `scripts/test.sh`. Keep ruff, mypy, and both test suites clean before every commit.
- Browser integration test for the glance view: `scripts/e2e.sh` (builds nothing itself: run `npm run build` first; needs Playwright with Chromium).
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

## Interaction rules (UI)
Apply these to every screen; they come from Anthony and are not optional.
1. Pulse to confirm: a control the user pressed gives one short beat (`.confirm-pulse`), never a spinner for a local change.
2. Expand the same element: a detail opens in place from the thing that was clicked, not in a new box somewhere else.
3. Crossfade icons with blur: an icon that swaps state arrives from a soft blur (`.icon-in`, keyed so it re-mounts).
4. Rubber band past the edge: scrolling lists keep native overscroll; never `overscroll-behavior: none` on a list.
5. Reveal with masks: showing hidden content (the privacy blur) transitions over about 200ms rather than snapping.
6. Stage the focus: on first paint, panels arrive top to bottom with a 60ms stagger (`.rise-in` with `animationDelay`).
7. Fitts: every click target is at least 40 by 40px; icon-only buttons use `h-10 w-10`.
8. Hick: at most a handful of actions per view; the glance view keeps one toggle and one link.
9. Doherty: every interaction responds within 400ms. Local state flips on the click, animations stay under 250ms, and data shows cached values first.
10. All motion sits under `prefers-reduced-motion: no-preference` in `index.css`; with reduced motion the UI still works, just without the movement.

