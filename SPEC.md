# FrankensteinCentral v2: Build Specification

Owner: Anthony
Spec date: October 20, 2026
Audience: Claude Code, working in a brand new, empty repository
Goal: build the entire dashboard from this one document, tonight, with no follow up questions

## 0. Read this first (instructions for Claude)

You are building **FrankensteinCentral**, a self-hosted personal life dashboard. This file is the single source of truth. Read the whole thing before writing any code.

Operating rules:

1. **Do not stop to ask questions.** When something is ambiguous, pick the option this spec marks as DEFAULT. If the spec is silent, pick the simplest option that satisfies the acceptance criteria, write one line about it in `DECISIONS.md`, and keep going.
2. **Mock mode first.** Every integration must work with `MOCK_MODE=true` using fixture data in `backend/app/fixtures/`. Build and verify the full UI against mocks before wiring real services. This guarantees a working dashboard even if a real service is unreachable from where you are running.
3. **Build in the phases in Section 13.** Commit at the end of each phase with a clear message. Do not start a phase until the previous phase's acceptance checklist passes.
4. **Every widget is independent.** One integration failing must never break the page or another widget. Failed widgets show their last good data with a "stale" badge, or a clear error card.
5. **Secrets never reach the browser.** All third party calls happen in the backend. The frontend only talks to this app's own `/api/*` routes. Never log tokens, URLs containing tokens, or full Google iCal secret URLs.
6. **Writing style for all UI copy, README, and docs:** American English spelling (color, behavior, canceled, labeled, optimize). Never use em dashes or double hyphens as punctuation anywhere in UI text or docs. Use commas, colons, or parentheses instead.
7. Create a short `CLAUDE.md` in the repo root at the start that summarizes the stack, commands, and the rules above, so future sessions keep the conventions.
8. When you finish, write `README.md` with setup steps (Section 14) and a "what is real vs mocked" status table.

Definition of done for tonight:

* `docker compose up -d` (after `docker compose build`) starts the app and the socket proxy.
* With `MOCK_MODE=true`, every widget renders realistic data.
* With real credentials in `.env`, each integration that has credentials switches to live data; integrations without credentials show a friendly "not configured" card instead of an error.
* The Amex benefits engine passes every scenario test in Section 12.2.
* Login works, and a read-only kiosk view works.

## 1. What this dashboard is

A single screen that answers "what do I need to know right now?" for Anthony's life:

| Module | What it shows | Data source |
|-|-|-|
| Attention strip | The few things that need action now, pulled from every module | All modules |
| Weather | Now, next 12 hours, 7 day outlook, official alerts | Open-Meteo + National Weather Service |
| Calendar | Today, next 7 days, month glance, "next event in X min" | Google Calendar via secret iCal feeds |
| Finances | Net worth, balances, month-to-date spend vs pace, categories, budgets, bills, recent transactions, data freshness | Firefly III API |
| Amex cards | Balances and cycle spend for Platinum and Gold | Firefly III |
| Amex benefits tracker | Every statement credit: used, remaining, pending, expiring, fee offset | Firefly III transactions + rules engine in this app |
| Media (Plex) | Server status, now playing, recently added, on deck, one click open | Plex Media Server API |
| Password vault | Vaultwarden health, version, one click open | Vaultwarden endpoints |
| Containers | Every Docker container: state, health, uptime, restarts, quick links | Docker API through a read-only socket proxy |

There is also a full-screen **kiosk mode** for an always-on display (Anthony plans to repurpose a laptop as a dedicated dashboard screen).

## 2. Environment facts (what Anthony already runs)

* Homelab host: Dell OptiPlex on Ubuntu, running Docker and Portainer. Remote access through Tailscale.
* Firefly III is self-hosted, with the Firefly III Data Importer pulling Amex and Discover transactions from **SimpleFIN** (paid bridge) so there are no manual CSV uploads.
* Vaultwarden is self-hosted.
* Plex Media Server is self-hosted.
* Time zone: `America/New_York`. Default weather location: Toms River, NJ (lat 39.9537, lon -74.1979). Locations must be configurable because Anthony expects to move to the NYC/Hoboken area.
* Cards: **Amex Platinum** (consumer) and **Amex Gold** (consumer). Note: both are charge cards with no preset spending limit, so "utilization percent" is not meaningful. Show balance and cycle spend instead.
* Anthony's languages: C#/.NET and Python. He dislikes recurring manual friction: anything that needs repeated manual steps will be abandoned. Design for zero maintenance.
* Hostnames, IPs, and ports are unknown to this spec. Everything is configured through `.env` and `config/*.yaml`.

## 3. Architecture

### 3.1 Stack (DEFAULT, do not substitute)

Backend:
* Python 3.12, FastAPI, Uvicorn
* httpx (async) for all outbound calls
* Pydantic v2 + pydantic-settings for config and response models
* SQLite (file at `data/frankenstein.db`) via SQLModel or plain `sqlite3`; keep it simple
* `icalendar` + `recurring-ical-events` for calendar parsing and recurrence expansion
* `python-dateutil`, `PyYAML`, `tzdata`
* Background refresh with asyncio tasks (or APScheduler AsyncIOScheduler)
* Auth: `itsdangerous` signed cookies, `bcrypt` (or `argon2-cffi`) password hash
* Tests: `pytest`, `pytest-asyncio`, `respx` (httpx mocking), `freezegun` or `time-machine`
* Dependency management: `uv` with `pyproject.toml` (pip fallback is fine)

Frontend:
* React + Vite + TypeScript
* Tailwind CSS
* TanStack Query for data fetching and polling
* Recharts for charts
* lucide-react for icons
* date-fns (with `date-fns-tz`) for dates

Why this stack: Python has the best iCal recurrence handling and the least boilerplate for an aggregation backend; a single container serves both API and the built SPA.

### 3.2 Data flow

* Browser loads the SPA from FrankensteinCentral.
* SPA polls `/api/*` routes on module specific intervals.
* Backend never calls a third party on the request path when it can avoid it. Background refreshers fetch from each source on a schedule and write results to an in-memory cache, mirrored to SQLite so the dashboard survives restarts with last known data.
* `/api/*` handlers return the cached envelope immediately.
* Docker data comes from `tecnativa/docker-socket-proxy` on an internal network; the app never mounts the Docker socket itself.

### 3.3 Standard response envelope

Every module route returns:

```json
{
  "module": "weather",
  "status": "ok",
  "configured": true,
  "fetched_at": "2026-10-20T04:40:00Z",
  "stale": false,
  "error": null,
  "data": {}
}
```

* `status`: one of `ok`, `degraded` (partial data), `error`, `disabled` (not configured).
* `stale`: true when the last successful fetch is older than 3x that module's refresh interval.
* `error`: short human message, never containing secrets.

### 3.4 Refresh intervals (backend) and polling (frontend)

| Source | Backend refresh | Frontend poll |
|-|-|-|
| Open-Meteo forecast | 15 min | 5 min |
| NWS alerts | 5 min | 2 min |
| Google iCal feeds | 5 min | 2 min |
| Firefly summary, accounts, transactions | 10 min | 5 min |
| Benefits engine | recompute after each Firefly refresh | 5 min |
| Plex sessions | 30 s | 30 s |
| Plex recently added, on deck | 15 min | 5 min |
| Vaultwarden health | 60 s | 60 s |
| Docker container list | 15 s | 15 s |
| Docker restart counts (inspect) | 5 min | with list |

Use exponential backoff on failures (cap at 10 min) and jitter so sources are not hit in lockstep.

## 4. Repository layout

```
frankenstein-central/
  CLAUDE.md
  SPEC.md                 (this file)
  DECISIONS.md
  README.md
  .env.example
  .gitignore              (must ignore .env, data/, node_modules/, dist/)
  docker-compose.yml
  Dockerfile              (multi-stage: node build, then python runtime)
  config/
    dashboard.yaml        (locations, calendars, links, health probes, UI options)
    benefits.yaml         (Amex benefit catalog, Section 8.5 and Appendix A)
  data/                   (SQLite, gitignored)
  backend/
    pyproject.toml
    app/
      main.py             (FastAPI app, static file serving, startup tasks)
      settings.py         (pydantic-settings, reads .env)
      config_loader.py    (loads and validates YAML)
      auth.py
      cache.py            (in-memory + SQLite mirror, envelope helpers)
      scheduler.py        (background refresh loops)
      db.py
      integrations/
        base.py           (Integration protocol: name, interval, fetch(), mock())
        weather.py
        calendar_ics.py
        firefly.py
        plex.py
        vaultwarden.py
        docker_proxy.py
        probes.py         (generic HTTP health probes)
      services/
        benefits/
          catalog.py      (load benefits.yaml into models)
          periods.py      (period math: monthly, quarterly, semiannual, annual, special)
          classify.py     (transaction classification)
          match.py        (credit to purchase matching)
          engine.py       (per benefit per period results)
        attention.py      (builds the attention strip)
        finance.py        (derived finance metrics)
      routes/
        weather.py calendar.py finance.py cards.py benefits.py
        plex.py vault.py containers.py attention.py auth.py health.py
      fixtures/           (mock JSON and .ics files for every integration)
    tests/
  frontend/
    package.json
    vite.config.ts
    index.html
    src/
      main.tsx App.tsx
      api/                (typed fetchers, TanStack Query hooks)
      components/         (Card, StatusBadge, StaleBadge, Money, Sparkline, etc.)
      widgets/            (Attention, Weather, Calendar, Finance, Cards, Benefits,
                           Plex, Vault, Containers)
      pages/              (Dashboard, Kiosk, Benefits, Settings, Login)
      lib/                (formatters, weather code map, privacy blur)
```

## 5. Configuration

### 5.1 `.env.example` (create exactly this, with comments)

```
# Core
APP_PORT=8000
TZ=America/New_York
MOCK_MODE=true
SECRET_KEY=change-me-to-a-long-random-string
DASHBOARD_PASSWORD_HASH=           # bcrypt hash; README explains how to generate
KIOSK_TOKEN=                       # long random string; enables /kiosk?token=...
SESSION_DAYS=30

# Weather
NWS_USER_AGENT=(FrankensteinCentral, your-email@example.com)

# Google Calendar (one or more secret iCal URLs, defined in config/dashboard.yaml by env var name)
GCAL_ICS_PRIMARY=
GCAL_ICS_SECOND=

# Firefly III
FIREFLY_URL=http://firefly:8080     # base URL reachable FROM INSIDE this container
FIREFLY_VANITY_URL=                 # URL Anthony uses in his browser, for "open in Firefly" links
FIREFLY_TOKEN=                      # Personal Access Token
FIREFLY_WRITEBACK_TAGS=false        # if true, tag classified Amex credits in Firefly
FIREFLY_IMPORTER_URL=               # optional: data importer base URL for "Sync now"
FIREFLY_IMPORTER_SECRET=            # optional: AUTO_IMPORT_SECRET of the importer
FIREFLY_IMPORTER_DIR=/import        # optional: import directory configured on the importer

# Plex
PLEX_URL=http://plex-host:32400
PLEX_TOKEN=
PLEX_PUBLIC_URL=https://app.plex.tv/desktop

# Vaultwarden
VAULTWARDEN_URL=http://vaultwarden:80
VAULTWARDEN_PUBLIC_URL=             # URL Anthony opens in the browser
VAULTWARDEN_BACKUP_DIR=             # optional, read-only mount; enables "last backup age"

# Docker
DOCKER_HOST=tcp://socket-proxy:2375
DOCKER_ALLOW_RESTART=false          # requires socket proxy POST=1 and ALLOW_RESTARTS=1
PORTAINER_URL=
```

Settings rules:
* An integration is "configured" only when its required variables are non-empty. Unconfigured integrations return `status: "disabled"` and the UI shows a setup hint card (which variables to set), not an error.
* `MOCK_MODE=true` forces fixture data for every integration regardless of credentials.
* Add a per integration override: `MOCK_WEATHER`, `MOCK_CALENDAR`, `MOCK_FIREFLY`, `MOCK_PLEX`, `MOCK_VAULT`, `MOCK_DOCKER` (each `true`/`false`, default follows `MOCK_MODE`). This lets Anthony go live one service at a time.

### 5.2 `config/dashboard.yaml`

```yaml
owner_name: Anthony
timezone: America/New_York

weather:
  locations:
    - name: Toms River
      lat: 39.9537
      lon: -74.1979
      default: true
  units: imperial            # imperial or metric

calendar:
  lookahead_days: 30
  feeds:
    - name: Personal
      env: GCAL_ICS_PRIMARY
      color: "#4ade80"
    - name: Second
      env: GCAL_ICS_SECOND
      color: "#60a5fa"

finance:
  currency: USD
  hide_amounts_by_default: false     # privacy blur default on the main dashboard
  kiosk_hide_amounts: true           # amounts blurred on kiosk unless toggled
  stale_after_hours: 48              # warn when newest imported transaction is older
  net_worth_include_types: [asset, liabilities]

cards:
  - id: amex_platinum
    label: Amex Platinum
    firefly_account_match: "(?i)platinum"   # regex on Firefly account name
    firefly_account_id: null                # set to pin an exact account id
    annual_fee: 895
  - id: amex_gold
    label: Amex Gold
    firefly_account_match: "(?i)gold"
    firefly_account_id: null
    annual_fee: 325

links:                     # quick launch tiles
  - { name: Firefly III, env_url: FIREFLY_VANITY_URL, icon: wallet }
  - { name: Plex, env_url: PLEX_PUBLIC_URL, icon: tv }
  - { name: Vaultwarden, env_url: VAULTWARDEN_PUBLIC_URL, icon: key-round }
  - { name: Portainer, env_url: PORTAINER_URL, icon: container }

probes:                    # generic HTTP checks shown in the service health row
  - { name: Firefly III, url_env: FIREFLY_URL, path: /api/v1/about, auth: firefly, expect: 200 }
  - { name: Vaultwarden, url_env: VAULTWARDEN_URL, path: /alive, expect: 200 }
  - { name: Plex, url_env: PLEX_URL, path: /identity, expect: 200 }

ui:
  theme: dark
  accent: "#4ade80"        # "Frankenstein green"
  kiosk_rotate_seconds: 0  # 0 means no page rotation
```

Validate both YAML files at startup with Pydantic models and fail fast with a readable error that names the bad key.

## 6. Backend core

### 6.1 Integration contract

```python
class Integration(Protocol):
    name: str                      # "weather", "calendar", ...
    interval_seconds: int
    def is_configured(self) -> bool: ...
    async def fetch(self) -> dict: ...   # live data, raises on failure
    def mock(self) -> dict: ...          # fixture data, same shape as fetch()
```

The scheduler runs each configured integration on its interval, stores the result in the cache with `fetched_at`, and on failure keeps the last good data, sets `status` to `error` or `degraded`, and records a sanitized error message.

### 6.2 SQLite tables

| Table | Purpose |
|-|-|
| `cache(key TEXT PK, payload TEXT, fetched_at TEXT, status TEXT, error TEXT)` | Last good data per module so restarts are instant |
| `benefit_overrides(id, firefly_journal_id UNIQUE, classification, benefit_id, period_key, note, created_at)` | Manual corrections from the UI |
| `benefit_manual_usage(id, benefit_id, period_key, amount, note, created_at)` | Usage for benefits that never touch the card (Uber Cash) |
| `benefit_snapshots(benefit_id, period_key, cap, used, pending, remaining, computed_at)` | History; one row per benefit per period, upserted |
| `settings(key PK, value)` | UI preferences (privacy blur, selected location) |

### 6.3 Routes

| Method | Route | Notes |
|-|-|-|
| GET | `/api/health` | App liveness, no auth, used by Docker healthcheck |
| POST | `/api/auth/login` | `{password}` sets signed cookie |
| POST | `/api/auth/logout` | |
| GET | `/api/config/public` | Non-secret UI config: locations, link tiles (resolved URLs), feature flags |
| GET | `/api/attention` | Attention strip items |
| GET | `/api/weather?location=Toms%20River` | |
| GET | `/api/calendar?days=7` | |
| GET | `/api/finance/summary` | |
| GET | `/api/finance/transactions?limit=15` | |
| POST | `/api/finance/sync` | Optional; triggers data importer auto import |
| GET | `/api/cards` | Card balances and cycle spend |
| GET | `/api/benefits?year=2026` | Full benefits state |
| GET | `/api/benefits/unclassified` | Card deposits the engine could not classify, last 120 days |
| POST | `/api/benefits/overrides` | Create or update a classification override |
| DELETE | `/api/benefits/overrides/{id}` | |
| POST | `/api/benefits/manual` | Record manual usage for a manual benefit and period |
| GET | `/api/plex` | |
| GET | `/api/plex/image?path=...&w=300&h=450` | Backend proxies Plex artwork so the token stays server-side |
| GET | `/api/vault` | |
| GET | `/api/containers` | |
| POST | `/api/containers/{id}/restart` | Only when `DOCKER_ALLOW_RESTART=true`; otherwise 403 |
| GET | `/api/probes` | Results of generic HTTP probes |

All `/api/*` routes except health and login require the session cookie, or a valid `KIOSK_TOKEN` for read-only GET routes. Kiosk token can never call POST/DELETE routes.

## 7. Security

* Access: the app is meant to be reachable only on the LAN and Tailscale. README must recommend one of: (a) bind the published port to the host's Tailscale IP in compose, or (b) do not publish a port and use `tailscale serve` to expose it inside the tailnet with HTTPS. Never expose it to the public internet.
* Auth: single user password, stored only as a hash in `.env`. Signed, `HttpOnly`, `SameSite=Lax` cookie; `Secure` when served over HTTPS. Rate limit login (5 attempts per minute per IP).
* Kiosk: `/kiosk?token=...` sets a separate read-only kiosk cookie; dollar amounts blurred by default on kiosk.
* Docker: only through `tecnativa/docker-socket-proxy` with `CONTAINERS=1`, `INFO=1`, `POST=0` by default. The proxy lives on an `internal: true` network shared only with this app.
* Plex token, Firefly token, iCal URLs: backend only. Plex images are proxied through `/api/plex/image`. Validate that the `path` parameter starts with `/library/` to prevent the proxy from becoming an open relay.
* Logs: a logging filter must redact anything matching `X-Plex-Token=`, `Authorization`, `/calendar/ical/`, and the literal values of every secret env var.
* Vaultwarden is never embedded and never asked for vault contents. The dashboard only checks health and links out.

## 8. Module specifications

### 8.1 Weather

Sources:
* **Open-Meteo forecast API** (free, no API key, no account):
  `https://api.open-meteo.com/v1/forecast`
  Parameters:
  * `latitude`, `longitude`
  * `current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,precipitation,wind_speed_10m,wind_gusts_10m`
  * `hourly=temperature_2m,precipitation_probability,weather_code,wind_speed_10m`
  * `daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,sunrise,sunset,uv_index_max,wind_speed_10m_max`
  * `temperature_unit=fahrenheit`, `wind_speed_unit=mph`, `precipitation_unit=inch` (when units are imperial)
  * `timezone=America/New_York`, `forecast_days=7`
* **National Weather Service alerts** (official US alerts, free, no key):
  `https://api.weather.gov/alerts/active?point={lat},{lon}`
  A `User-Agent` header identifying the app and a contact email is required. Use `NWS_USER_AGENT`. Response is GeoJSON; read `features[].properties` (`event`, `severity`, `urgency`, `headline`, `description`, `instruction`, `effective`, `expires`, `areaDesc`).
* Optional, nice to have: Open-Meteo air quality `https://air-quality-api.open-meteo.com/v1/air-quality` with `current=us_aqi`. Show AQI only when it is 101 or higher.

Backend output `data`:
```json
{
  "location": "Toms River",
  "current": {"temp": 58, "feels_like": 55, "humidity": 71, "code": 3, "label": "Overcast",
              "icon": "cloud", "is_day": true, "wind_mph": 9, "gust_mph": 18, "precip_in": 0},
  "next_12h": [{"time": "...", "temp": 57, "pop": 10, "code": 3}],
  "daily": [{"date": "2026-10-20", "hi": 63, "lo": 48, "pop": 20, "code": 2,
             "sunrise": "...", "sunset": "...", "uv": 3}],
  "alerts": [{"event": "Wind Advisory", "severity": "Moderate", "headline": "...",
              "expires": "...", "instruction": "..."}],
  "badges": ["umbrella"]
}
```

Logic:
* Map WMO `weather_code` to label and icon (Appendix B). Use day/night icon variants with `is_day`.
* Badges: `umbrella` if any hourly precipitation probability in the next 12 hours is 50 or higher; `wind` if gusts 35 mph or higher; `freeze` if tonight's low is 32 F or lower; `uv` if today's UV max is 7 or higher.
* Location switcher: all locations from config; selection saved in `settings`.

UI: big current temp and condition with icon, feels like, wind; a 12 hour strip (temp line plus rain probability bars); 7 day row; alerts rendered as a colored banner (Extreme/Severe red, Moderate amber, Minor blue) that expands to show the description.

Acceptance:
* Renders with mocks; with live data it shows the correct local times in America/New_York.
* An active NWS alert appears in both the weather widget and the attention strip.
* NWS failure does not break the Open-Meteo forecast (status becomes `degraded`).

### 8.2 Calendar (Google Calendar sync)

**DEFAULT approach: Google's "Secret address in iCal format" feed per calendar.** It is read-only, needs no Google Cloud project, no OAuth consent screen, and no refresh tokens. This avoids the most common failure in self-hosted Google Calendar integrations: OAuth apps left in "Testing" mode have their refresh tokens expire after 7 days, which silently breaks sync every week.

The secret URL is a credential (anyone with it can read that calendar). Treat it like a password; Google lets Anthony reset it if it leaks.

How Anthony gets it (put this in README): Google Calendar on the web, Settings, under "Settings for my calendars" pick the calendar, scroll to "Integrate calendar", copy "Secret address in iCal format". Repeat per calendar.

Parsing requirements:
* Fetch each feed with httpx (timeout 20 s). Support conditional requests: send `If-None-Match` / `If-Modified-Since` when the server provided `ETag` / `Last-Modified`.
* Parse with `icalendar`; expand recurring events with `recurring-ical-events` over the window `[start of yesterday, now + lookahead_days]`. This correctly handles RRULE, EXDATE, and modified single instances (RECURRENCE-ID).
* Correctly handle all-day events (DATE values, end date is exclusive), timed events with TZID, and UTC times. Convert everything to America/New_York for display.
* Skip canceled events (iCal `STATUS` property). Show tentative events with a dashed outline.
* De-duplicate events that appear in multiple feeds (same UID and same start).
* Extract `location`, `description` (strip HTML), and the first URL found in location or description (Zoom, Meet, Teams) as `join_url`.
* Multi-day events appear on every day they span.

Backend output `data`:
```json
{
  "now": "...",
  "next_event": {"title": "...", "start": "...", "minutes_until": 42, "calendar": "Personal"},
  "days": [
    {"date": "2026-10-20", "label": "Today",
     "events": [{"id": "...", "title": "...", "start": "...", "end": "...", "all_day": false,
                 "calendar": "Personal", "color": "#4ade80", "location": "...",
                 "join_url": null, "tentative": false}]}
  ],
  "month_density": {"2026-10-21": 3, "2026-10-24": 1}
}
```

UI:
* Header line: "Next: {title} in {X} min" (or "at 3:30 PM" if more than 2 hours away; "Now: {title}" if in progress).
* Today column with a timeline (all-day events pinned on top), then a compact list for the next 6 days.
* Mini month grid with dots sized by `month_density`.
* Clicking an event opens a small popover with time, location, description, and join link.

Acceptance:
* A weekly recurring event shows on every correct day; an excluded instance does not show.
* All-day events show on the right dates (no off by one).
* A feed that fails leaves the other feeds working (status `degraded`).

Phase 2 (do NOT build tonight, document in README as a future option): Google Calendar API with OAuth for write access. If ever built, the OAuth consent screen must be published to Production, not left in Testing, or refresh tokens expire after 7 days.

### 8.3 Finances (Firefly III)

Auth: Firefly III **Personal Access Token**, sent as `Authorization: Bearer {FIREFLY_TOKEN}` with `Accept: application/vnd.api+json` (fall back to `application/json`). Base path `{FIREFLY_URL}/api/v1`. Anthony creates it in Firefly: Options, Profile, OAuth tab, Personal Access Tokens, Create new token.

Docker networking gotcha (put in README): inside a container, `localhost` refers to that container. `FIREFLY_URL` must be the Firefly container name on a shared Docker network, the host's LAN IP, or its Tailscale name.

On startup call `GET /api/v1/about` and log the Firefly version. Verify every endpoint below against the instance's OpenAPI docs (`https://api-docs.firefly-iii.org`) for that version and adapt field names if they differ; record any differences in `DECISIONS.md`.

Endpoints to use:

| Purpose | Endpoint |
|-|-|
| Version and health | `GET /api/v1/about` |
| Accounts with balances | `GET /api/v1/accounts?type=asset` and `GET /api/v1/accounts?type=liabilities` |
| Headline numbers | `GET /api/v1/summary/basic?start=YYYY-MM-DD&end=YYYY-MM-DD` (keys like `net-worth-in-USD`, `spent-in-USD`, `earned-in-USD`, `bills-unpaid-in-USD`, `left-to-spend-in-USD`; read `monetary_value` / `value_parsed`) |
| Transactions in range | `GET /api/v1/transactions?start=...&end=...&type=all&limit=100&page=N` |
| Transactions for one account | `GET /api/v1/accounts/{id}/transactions?start=...&end=...&limit=100&page=N` |
| Search | `GET /api/v1/search/transactions?query=...&limit=100&page=N` |
| Spend by category | `GET /api/v1/insight/expense/category?start=...&end=...` |
| Spend by merchant (expense account) | `GET /api/v1/insight/expense/expense?start=...&end=...` |
| Budgets and limits | `GET /api/v1/budgets` and `GET /api/v1/budgets/{id}/limits?start=...&end=...` |
| Bills / subscriptions | `GET /api/v1/bills?start=...&end=...` (newer Firefly UI calls these Subscriptions; verify path) |

Data model notes (important):
* Transactions come back as transaction **groups**; the real rows are `data[].attributes.transactions[]` (splits). Work at the split level and key everything by `transaction_journal_id`.
* Each split has `type` (`withdrawal`, `deposit`, `transfer`), `date`, `amount` (a string, always positive), `description`, `source_id`, `source_name`, `destination_id`, `destination_name`, `category_name`, `budget_name`, `tags`, `notes`, `external_id`, `currency_code`.
* Direction comes from `type` and source/destination, never from the sign of `amount`. Parse amounts with `Decimal`, never float.
* Paginate with `meta.pagination.total_pages`. Cap any single sync at 50 pages and log if hit.
* Credit card payments from checking are `transfer`s and must be excluded from spending.
* SimpleFIN-imported descriptions can be uppercase, abbreviated, or truncated. All matching is case-insensitive and considers `description`, `destination_name`, `source_name`, and `notes`.

Derived metrics (compute in `services/finance.py`):
* Net worth: from summary basic; fallback to sum of asset balances minus liability balances.
* Month-to-date spend (withdrawals, excluding transfers) vs last month's spend through the same day number: show "pace" as ahead/behind with percent.
* Daily spend for the last 30 days (sparkline).
* Top 6 categories this month with amounts and share.
* Budgets this month: spent vs limit with progress bars, red at 100 percent and amber at 85 percent.
* Upcoming bills in the next 14 days.
* Recent 15 transactions (date, description, amount, account, category).
* Data freshness: newest transaction date per SimpleFIN-fed account. If the newest is older than `stale_after_hours`, raise an attention item "Finance data looks stale, check SimpleFIN import".

Optional "Sync now" (build in the optional phase): if `FIREFLY_IMPORTER_URL` and `FIREFLY_IMPORTER_SECRET` are set, `POST /api/finance/sync` calls the data importer's auto import endpoint: `POST {FIREFLY_IMPORTER_URL}/autoimport?directory={FIREFLY_IMPORTER_DIR}&secret={FIREFLY_IMPORTER_SECRET}` with header `Accept: application/json`. The importer must have `AUTO_IMPORT_SECRET`, `CAN_POST_AUTOIMPORT=true`, and `IMPORT_DIR_ALLOWLIST` configured, plus a saved SimpleFIN import config JSON in that directory. After triggering, schedule a Firefly refresh 90 seconds later. Document the importer side setup in README; do not attempt to modify Anthony's importer.

UI: headline tiles (net worth, MTD spend with pace arrow, left to spend), a balances list grouped Assets / Credit cards / Liabilities, category donut or bar, budgets bars, upcoming bills list, recent transactions table, freshness chip ("Updated from bank 6 h ago"). A global eye icon toggles privacy blur on all dollar amounts (CSS blur, persisted in `settings`). Every amount links to the matching page in Firefly using `FIREFLY_VANITY_URL` when set.

Acceptance:
* Transfers never count as spending.
* Amounts are exact to the cent (Decimal end to end; serialize as strings or fixed 2 decimal numbers).
* Unconfigured Firefly shows the setup card; the benefits widget then shows the same setup hint.

### 8.4 Amex cards

For each card in `dashboard.yaml`:
* Resolve the Firefly account: use `firefly_account_id` if set, else the first account (asset or liability) whose name matches `firefly_account_match`. Expose the resolved account id and name on the Settings page with a dropdown to pin a different account (saved in `settings`).
* Show: current balance (amount owed), spend this calendar month, spend last 30 days, largest purchase this month, last statement credit received (date and amount), and benefits value captured year to date versus `annual_fee` ("fee offset" bar: captured / fee, can exceed 100 percent).
* No utilization percent (charge cards). If the account has a credit limit configured in Firefly (virtual balance), it may optionally be shown as "limit set in Firefly", nothing more.

### 8.5 Amex benefits tracker (the most important custom logic)

#### 8.5.1 What it must answer

For every benefit, for the current period and for every period this calendar year:
* **Cap**: maximum credit for the period.
* **Used**: statement credits actually received for purchases in that period.
* **Pending**: eligible purchases already made that should produce a credit that has not posted yet.
* **Remaining**: cap minus used minus pending (never below zero).
* **Status**: `used`, `partial`, `pending`, `unused`, `expired_unused`, `expired_partial`, `manual`.
* **Days left** in the period and an **expiring soon** flag (remaining above zero and 14 or fewer days left).

Anthony's example, which is the core case: he spends $X at lululemon on the Platinum card, then later the card shows money coming back that mentions lululemon. The engine must recognize that as the quarterly lululemon credit, mark the credit amount as used for the quarter of the purchase, and show what is left. It must also tell a real merchant refund apart from a statement credit.

#### 8.5.2 Facts about how Amex credits behave (encode these)

* Credits post as a **separate positive transaction** (a deposit on the card account in Firefly), typically a few days after the purchase, but Amex says it can take up to 8 weeks.
* Amex assigns the credit to the benefit period of the **purchase's transaction date as reported by the merchant**, not the date the credit posts. A purchase on December 30 whose credit posts January 3 counts toward Q4.
* The credit amount is the lower of the purchase amount and the remaining cap for that period.
* Returning a credited purchase can **claw back** the statement credit (appears as a negative or reversing transaction).
* Benefits require one-time enrollment in the Amex account; if eligible purchases never produce credits, likely causes are missing enrollment or an ineligible purchase.
* lululemon specifics: eligible at U.S. lululemon stores and lululemon.com/app; outlets and some channels are excluded. As of early October 2026, lululemon **gift card** purchases reportedly stopped triggering the credit. The engine should treat lululemon gift card purchases (description containing "gift card" or "GC") as ineligible.
* Some credits are not visible on the card at all: **Uber Cash** is deposited into the Uber account, not the card statement. These are `manual` benefits with a checkbox or amount entry in the UI.
* For some benefits the purchase merchant name is unpredictable (Resy restaurants show the restaurant's own name, airline incidentals show the airline, hotel credits show Amex Travel). For these, track by **credits only** (`tracking: credits_only`).

#### 8.5.3 The catalog file: `config/benefits.yaml`

Each benefit:

```yaml
- id: plat_lululemon
  card: amex_platinum
  name: lululemon
  cap: 75.00
  period: quarterly          # monthly | quarterly | semiannual | annual | multi_year
  period_caps: {}            # optional per-period overrides, e.g. {"12": 35.00} for December Uber Cash
  tracking: matched          # matched | credits_only | manual
  enrollment_required: true
  active_from: 2025-09-18    # inclusive; omit for always
  active_until: null         # inclusive; set when Amex retires a benefit
  purchase_patterns:         # regex, case-insensitive, matched against description/destination/notes
    - "lululemon"
    - "lulu ?lemon"
  purchase_exclude_patterns:
    - "gift ?card"
    - "\\bGC\\b"
    - "outlet"
  credit_patterns:           # how the statement credit itself is described
    - "lululemon.*credit"
    - "credit.*lululemon"
    - "platinum.*lululemon"
  notes: "Up to $75 per calendar quarter. Gift cards stopped triggering in Oct 2026."
```

The full starting catalog (current as of October 2026, with sources) is in **Appendix A**. Put all of it in `benefits.yaml`. Values and merchant lists change, so the README must say "verify against the Benefits page in the Amex app once a quarter" and the Settings page must show the catalog's `last_verified` date (top level key in the YAML).

Important: the exact wording Amex and SimpleFIN use for statement credit descriptions is not known in advance. The `credit_patterns` above are starting guesses. That is why the Discovery screen (8.5.7) and overrides exist. The system must be useful on day one even when the patterns are wrong.

#### 8.5.4 Period math (`periods.py`)

Calendar based, in America/New_York:
* monthly: key `2026-M10`, Oct 1 to Oct 31
* quarterly: key `2026-Q4`, Q1 Jan to Mar, Q2 Apr to Jun, Q3 Jul to Sep, Q4 Oct to Dec
* semiannual: key `2026-H2`, H1 Jan to Jun, H2 Jul to Dec
* annual: key `2026`
* multi_year (Global Entry / TSA PreCheck): track last used date and show "next eligible" date; no remaining math.
* `period_caps` override caps by month number or period key (Platinum Uber Cash: $15 per month, $35 in December).
* A benefit only produces periods that overlap `[active_from, active_until]`.

#### 8.5.5 Classification (`classify.py`)

Input: every split on each Amex card account for the window `[Jan 1 of the selected year minus 60 days, today]`.

For each split decide one of:
* `purchase` (withdrawal from the card) that is **eligible** for benefit B: matches B's `purchase_patterns`, does not match `purchase_exclude_patterns`, date within B's active range.
* `merchant_refund` (deposit to the card) whose text matches B's `purchase_patterns` and does not look like a statement credit (see rules below).
* `statement_credit` for benefit B (deposit to the card).
* `credit_clawback` for benefit B: a withdrawal whose text matches B's `credit_patterns`, or a transaction whose text contains "reversal" or "adjustment" plus B's merchant.
* `payment` (transfer into the card): ignore.
* `other`: ignore for benefits.
* `unclassified_deposit`: a deposit to the card that is not a payment and matched nothing. These feed the Discovery screen.

Statement credit vs merchant refund, applied in this order:
1. An override in `benefit_overrides` for this `transaction_journal_id` always wins.
2. Text matches a `credit_patterns` entry, or contains generic credit markers (`credit`, `stmt cr`, `statement credit`, `amex`, `american express`, `platinum`) together with B's merchant: **statement_credit**, confidence `high`.
3. Text matches B's merchant only. Find eligible purchases for B from 0 to 60 days before this deposit:
   * If the deposit amount exactly equals one prior purchase amount AND that amount is greater than B's cap: **merchant_refund**, confidence `high`.
   * Else if the deposit amount is less than or equal to B's cap AND less than or equal to the matched purchase amount AND it posted 0 to 21 days after the purchase: **statement_credit**, confidence `medium`.
   * Else if the deposit exactly equals a prior purchase amount that is less than or equal to cap: ambiguous. Default to **statement_credit**, confidence `low`, and also list it on the Discovery screen for confirmation.
   * Else: **merchant_refund**, confidence `medium`.
4. For `credits_only` benefits only rule 1 and rule 2 apply.

Credit attribution (`match.py`), per benefit:
* Sort eligible purchases by date. For each statement credit in date order, attach it to the **earliest** purchase that has unmatched remaining amount, whose date is on or before the credit date and no more than 60 days before it, and whose remaining unmatched amount is at least the credit amount minus $0.01. Partial credits are allowed (a $75 credit against a $120 purchase leaves $45 of that purchase unmatched, which can never earn more credit in that period once the cap is hit).
* The credit's `period_key` is the matched purchase's period. If no purchase matches (or the benefit is `credits_only`), use the period containing `credit_date minus 3 days` and set `attribution: "by_credit_date"` so the UI can show a small info icon. An override can set `period_key` explicitly.
* Merchant refunds reduce the matched purchase's eligible amount (attach to the earliest purchase with an equal or larger amount within 120 days before the refund).
* Clawbacks subtract from `used` in the period of the credit they reverse (match by amount and benefit, most recent prior credit).

#### 8.5.6 Engine output (`engine.py`)

For benefit B and period P:
* `credits = sum(statement credits attributed to P) minus sum(clawbacks attributed to P)`
* `used = min(cap_P, max(0, credits))`, plus manual usage rows for manual benefits
* `net_eligible_spend = sum(eligible purchases in P) minus refunds attached to them`
* `pending = 0` if `tracking != matched`; else `min(cap_P minus used, max(0, unmatched eligible spend in P from purchases made within the last 60 days))`
* `remaining = max(0, cap_P minus used minus pending)`
* `missing_credit` flag: an eligible purchase older than 14 days with no credit while the period still had cap available. Message: "No credit yet for $X at {merchant} on {date}. Check that the benefit is enrolled." After 60 days, raise it as an attention item.
* Status rules:
  * Period ended: `expired_unused` if used == 0; `expired_partial` if 0 < used < cap; `used` if used == cap.
  * Period active: `used` if used == cap; `pending` if pending > 0 and used + pending >= cap; `partial` if used > 0 or pending > 0; else `unused`.
  * `manual` for manual benefits with no entry this period.
* Year totals per card: `captured_ytd = sum(used across all benefits and periods this year)`; `fee_offset = captured_ytd / annual_fee`; `left_on_table_ytd = sum(cap minus used for ended periods)`; `still_available = sum(remaining for current periods)`.

`GET /api/benefits` response:
```json
{
  "year": 2026,
  "catalog_last_verified": "2026-10-20",
  "cards": [
    {
      "card": "amex_platinum", "label": "Amex Platinum", "annual_fee": 895,
      "captured_ytd": "1234.56", "fee_offset": 1.38,
      "left_on_table_ytd": "410.00", "still_available": "215.00",
      "benefits": [
        {
          "id": "plat_lululemon", "name": "lululemon", "tracking": "matched",
          "current": {"period_key": "2026-Q4", "start": "2026-10-01", "end": "2026-12-31",
                       "days_left": 72, "cap": "75.00", "used": "75.00", "pending": "0.00",
                       "remaining": "0.00", "status": "used", "expiring_soon": false,
                       "missing_credit": null},
          "history": [{"period_key": "2026-Q1", "cap": "75.00", "used": "75.00", "status": "used"}],
          "evidence": [
            {"journal_id": 812, "date": "2026-10-03", "kind": "purchase", "amount": "120.00",
             "description": "LULULEMON ATHLETICA", "period_key": "2026-Q4"},
            {"journal_id": 840, "date": "2026-10-06", "kind": "statement_credit", "amount": "75.00",
             "description": "PLATINUM LULULEMON CREDIT", "confidence": "high",
             "matched_purchase": 812, "period_key": "2026-Q4"}
          ]
        }
      ]
    }
  ],
  "expiring_soon": [{"card": "amex_gold", "id": "gold_dining", "remaining": "10.00", "days_left": 11}]
}
```

#### 8.5.7 Discovery screen and overrides

Route `/benefits` (full page) with three parts:
1. **Benefit grid** grouped by card. Each benefit is a tile: name, period label ("Q4: Oct to Dec"), a progress bar split into used (solid green), pending (striped amber), remaining (gray), dollar labels, days left, status chip. Clicking a tile opens the evidence drawer listing every transaction that fed the number, with confidence badges and a "this is wrong" button.
2. **Unclassified deposits**: table of `unclassified_deposit` and `low` confidence items from the last 120 days (date, amount, description, account). For each row: dropdown "This is: statement credit for [benefit] / merchant refund / payment / ignore". Saving writes `benefit_overrides`. Also offer "Suggest pattern": generate a regex from the description (escape it, collapse digits and long numbers to `\d+`) and show it so Anthony can paste it into `benefits.yaml`. Never edit the YAML automatically.
3. **Manual benefits**: for `manual` benefits (Uber Cash), a per period checkbox "Used" plus optional amount. Writes `benefit_manual_usage`.

Optional write back: when `FIREFLY_WRITEBACK_TAGS=true`, after an override or a `high` confidence classification, add a tag to the Firefly transaction like `amex-credit` and `benefit:plat_lululemon:2026-Q4` via `PUT /api/v1/transactions/{group_id}` (send the full split array back with the new tags; never drop existing tags or splits). Default is false; implement it behind the flag and test it with respx only.

#### 8.5.8 Benefits widget on the main dashboard

Compact view: one row per card with the fee offset bar, then the current period benefits sorted by: expiring soon first, then pending, then unused, then partial, then used (collapsed). Each row: name, mini progress bar, "$X left, Y days". A "View all" link goes to `/benefits`.

### 8.6 Media: Plex

Auth: `X-Plex-Token` header (never as a query parameter in browser-visible URLs). Always send `Accept: application/json` (Plex defaults to XML). Also send `X-Plex-Product: FrankensteinCentral` and a stable `X-Plex-Client-Identifier` (generate once, store in `settings`).

How Anthony finds the token (README): in Plex Web, open any library item, choose the three dot menu, Get Info, View XML; the URL of the XML page contains `X-Plex-Token=...`.

Endpoints:
| Purpose | Endpoint |
|-|-|
| Reachability and version (no auth needed) | `GET /identity` (machineIdentifier, version) |
| Now playing | `GET /status/sessions` (each item: title, grandparentTitle, parentIndex, index, type, thumb, viewOffset, duration, User.title, Player.title, Player.state, presence of TranscodeSession) |
| Recently added | `GET /library/recentlyAdded` with headers `X-Plex-Container-Start: 0`, `X-Plex-Container-Size: 12` |
| On deck / continue watching | `GET /library/onDeck` |
| Libraries and counts | `GET /library/sections` then per section `GET /library/sections/{key}/all` with container size 0 to read `totalSize` |

Images: frontend requests `/api/plex/image?path=/library/metadata/123/thumb/1699999999&w=300&h=450`; backend fetches `{PLEX_URL}/photo/:/transcode?width=..&height=..&minSize=1&upscale=1&url={path}` with the token and streams the bytes back with a 1 day cache header. Reject any `path` that does not start with `/library/`.

Open in Plex: Plex Web cannot be embedded in an iframe (it sends frame-blocking headers), so do not try. Use links:
* Server: `{PLEX_PUBLIC_URL}#!/media/{machineIdentifier}/com.plexapp.plugins.library`
* Item: `{PLEX_PUBLIC_URL}#!/server/{machineIdentifier}/details?key=%2Flibrary%2Fmetadata%2F{ratingKey}`
Open in a new tab. (Plex has changed deep link formats before; if a deep link fails in testing, fall back to the server link and note it in DECISIONS.md.)

UI: status dot plus version; now playing cards with poster, title (show name, SxxEyy), user, device, progress bar, "Direct Play" or "Transcoding" chip; a horizontal poster rail for recently added; an on deck rail; library counts; a big "Open Plex" button.

Acceptance: token never appears in any response body or browser network URL; posters load through the proxy.

### 8.7 Password vault: Vaultwarden

Vaultwarden should not be embedded (it sends frame-blocking security headers on purpose, and embedding a password manager is a bad idea anyway). The widget is a health and launch tile.

Checks:
* `GET {VAULTWARDEN_URL}/alive`: returns HTTP 200 with a JSON timestamp string when healthy. This endpoint also verifies the database connection, so a 5xx means the vault is truly unhealthy. Measure latency.
* `GET {VAULTWARDEN_URL}/api/version`: version string (optional; ignore failures).
* Optional backup freshness: if `VAULTWARDEN_BACKUP_DIR` is set (mounted read-only), find the newest file and report its age. Raise an attention item if the newest backup is older than 48 hours.

UI: shield icon with green/red state, "Online, v1.x.x, 38 ms", last backup age if available, big "Open Vault" button to `VAULTWARDEN_PUBLIC_URL`, small "Admin" link to `{VAULTWARDEN_PUBLIC_URL}/admin`.

Acceptance: vault down produces a red tile and an attention item within 2 minutes.

### 8.8 Containers (Docker)

Access only through `tecnativa/docker-socket-proxy` at `DOCKER_HOST` (strip `tcp://` and call over HTTP). Default proxy permissions: `CONTAINERS=1`, `INFO=1`, `POST=0`. Use Docker Engine API paths without a version prefix (or negotiate with `GET /version`).

Calls:
* `GET /containers/json?all=true`: list. Use `Id`, `Names`, `Image`, `State` (running, exited, restarting, paused, created, dead), `Status` (human string such as "Up 3 hours (healthy)"), `Labels`, `Created`, `Ports`.
* Health: parse `(healthy)`, `(unhealthy)`, `(health: starting)` from `Status`; if absent, health is `none`.
* `GET /containers/{id}/json` every 5 min for `RestartCount`, `State.StartedAt`, `State.ExitCode`. Use a concurrency limit of 5.
* `GET /info` for totals (`Containers`, `ContainersRunning`, `ContainersStopped`, `ServerVersion`).
* Group by label `com.docker.compose.project`; ungrouped go under "Standalone".
* Custom labels Anthony can add to any container: `frankenstein.url` (launch link), `frankenstein.name` (display name), `frankenstein.hide=true` (hide from dashboard), `frankenstein.critical=true` (any non-running state becomes an attention item).

Restart (optional): when `DOCKER_ALLOW_RESTART=true` and the proxy has `POST=1` and `ALLOW_RESTARTS=1`, show a restart button with a confirmation dialog; call `POST /containers/{id}/restart`. Off by default. README explains the tradeoff.

UI: summary chips (running / stopped / unhealthy counts), then grouped list: colored state dot, name (link if `frankenstein.url`), image tag, uptime, health chip, restart count (amber if it increased since last check). Filter box and "problems only" toggle. Link to Portainer.

Acceptance: an exited container with `frankenstein.critical=true` raises an attention item; a container restarting repeatedly shows an increasing restart count.

### 8.9 Attention strip

Built by `services/attention.py` from all modules. Each item: `severity` (critical, warning, info), `icon`, `title`, `detail`, `link` (route or URL), `source`. Max 6 shown, sorted by severity then time.

Rules:
* critical: NWS alert with severity Extreme or Severe; Vaultwarden down; critical container not running.
* warning: any unhealthy container; NWS Moderate alert; Amex benefit expiring soon with remaining above zero (one item per card, summarizing, e.g. "Gold: $10 dining and $7 Dunkin left, 11 days"); missing credit older than 60 days; finance data stale; Vaultwarden backup older than 48 h.
* info: next calendar event within 30 minutes (with join link); umbrella badge today.

UI: a slim row at the very top; collapses to a single green "All clear" pill when empty.

### 8.10 Service health row

Small row of chips from `probes` in `dashboard.yaml` (name, green/red, latency). Clicking opens the service URL.

## 9. Frontend design

Layout (desktop, 12 column grid, dark theme, accent `#4ade80`):

| Row | Left (8 cols) | Right (4 cols) |
|-|-|-|
| 0 | Attention strip (full width) | |
| 1 | Calendar (today plus week) | Weather |
| 2 | Finances | Amex cards plus Benefits compact |
| 3 | Plex | Vaultwarden tile, Service health row |
| 4 | Containers (full width) | |

Header: "FrankensteinCentral", current date and time (America/New_York, updates every second), greeting ("Good evening, Anthony"), privacy eye toggle, link to `/benefits`, `/settings`, logout.

Responsive: on phone width everything stacks in priority order: attention, calendar, weather, benefits, finance, containers, Plex, vault. No horizontal scrolling.

Shared components:
* `Card` with title, status dot, "updated X min ago" footer, and states: loading skeleton, ok, stale (amber badge with last update time), error (message plus retry button), disabled (setup hint listing env vars).
* `Money` component that respects privacy blur and formats `$1,234.56`.
* Numbers use tabular figures.

Kiosk page `/kiosk`:
* Full screen, no nav, larger type, no hover-only interactions, cursor hidden after 5 s idle.
* Shows: clock, attention strip, weather, today's calendar, benefits compact, container summary, Plex now playing.
* Dollar amounts blurred unless `kiosk_hide_amounts: false`.
* Reloads the page once every 6 hours to pick up new builds; survives backend restarts (keeps retrying).
* Optimized for a 1920x1080 landscape display.

Settings page `/settings`: resolved card accounts (with pin dropdown), weather location default, privacy defaults, integration status table (configured, mocked, last fetch, last error), benefits catalog `last_verified`.

## 10. Docker and deployment

### 10.1 Dockerfile (multi-stage)

* Stage 1 `node:22-alpine`: install frontend deps, `npm run build` into `frontend/dist`.
* Stage 2 `python:3.12-slim`: install backend with uv or pip, copy `frontend/dist` to `/app/static`, run as a non-root user, `EXPOSE 8000`, start Uvicorn from a small `backend/run.py` (`uvicorn.run("app.main:app", host="0.0.0.0", port=8000)`) so the Dockerfile CMD is just `["python", "run.py"]`.
* FastAPI serves `/api/*` and falls back to `index.html` for client routes.
* Healthcheck: `CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]`.

### 10.2 `docker-compose.yml`

```yaml
services:
  frankenstein:
    build: .
    container_name: frankenstein-central
    restart: unless-stopped
    env_file: .env
    environment:
      DOCKER_HOST: tcp://socket-proxy:2375
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      # - /path/to/vaultwarden/backups:/backups/vaultwarden:ro
    ports:
      - "8088:8000"          # README: change to "<tailscale-ip>:8088:8000" to bind to Tailscale only
    networks:
      - frankenstein
      - socket
    depends_on:
      - socket-proxy

  socket-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: frankenstein-socket-proxy
    restart: unless-stopped
    environment:
      CONTAINERS: 1
      INFO: 1
      POST: 0
      # ALLOW_RESTARTS: 1   # only with DOCKER_ALLOW_RESTART=true and POST: 1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - socket

networks:
  frankenstein: {}
  socket:
    internal: true
```

README must also explain the option of joining Firefly's existing Docker network (declare it as `external: true` and add it to the `frankenstein` service) so `FIREFLY_URL=http://<firefly-container-name>:8080` works.

## 11. Error handling and resilience checklist

* Every outbound call: timeout (10 s default, 20 s for iCal), retries with backoff for 5xx and network errors, no retry on 401/403 (report "check token").
* 401 from Firefly or Plex produces the message "Token rejected, regenerate it and update .env".
* Cache survives restarts via SQLite; the UI shows data immediately on boot with stale badges until refreshers run.
* Clock and time zone: all backend time math in aware datetimes; store UTC, display America/New_York.
* Never crash the scheduler loop on one integration's exception.

## 12. Testing

### 12.1 General

* Unit tests for period math, WMO mapping, iCal parsing (fixtures with RRULE, EXDATE, all-day multi-day, TZID, canceled), Firefly pagination and split flattening, transfer exclusion, Docker status parsing, attention rules, log redaction.
* Integration tests with `respx` for each adapter using recorded fixture JSON.
* Frontend: `npm run build` must pass with no TypeScript errors; add a few Vitest tests for formatters and the privacy blur.
* `make test` (or a `scripts/test.sh`) runs everything.

### 12.2 Benefits engine scenarios (all must pass)

Use `freezegun`/`time-machine` to fix "today". Amounts in USD. Platinum lululemon cap is $75 per quarter unless stated.

| # | Setup | Expected |
|-|-|-|
| 1 | Oct 3 purchase $120 "LULULEMON ATHLETICA"; Oct 6 deposit $75 "PLATINUM LULULEMON CREDIT"; today Oct 20 | Q4 used 75, pending 0, remaining 0, status used |
| 2 | Oct 3 purchase $40, Oct 5 credit $40; Nov 10 purchase $50, Nov 12 credit $35; today Nov 20 | Q4 used 75, remaining 0 |
| 3 | Dec 29 purchase $60; Jan 2 credit $60; evaluate on Jan 5 | Q4 used 60 (expired_partial after Dec 31); next year Q1 used 0 |
| 4 | Oct 3 purchase $100, no credit; today Oct 5 | used 0, pending 75, remaining 0, status pending |
| 5 | Oct 3 purchase $100, no credit; today Oct 20 | pending 75 and missing_credit set (older than 14 days) |
| 6 | Oct 3 purchase $100; Oct 5 credit $75; Oct 20 deposit $100 "LULULEMON" (refund); Oct 22 withdrawal $75 "LULULEMON CREDIT REVERSAL"; today Oct 25 | refund classified merchant_refund; clawback applied; used 0; remaining 75 |
| 7 | Sep 1 purchase $150; Sep 9 deposit $150 "LULULEMON.COM" (no credit words) | merchant_refund (amount equals purchase and exceeds cap) |
| 8 | Oct 1 purchase $150; Oct 3 deposit $75 "LULULEMON" (no credit words) | statement_credit, confidence medium, Q4 used 75 |
| 9 | Same as 8 but an override marks the Oct 3 deposit as merchant_refund | Q4 used 0, pending 75 (purchase 19 days old within 60 days), missing_credit set |
| 10 | Oct 2 purchase $50 "LULULEMON GIFT CARD"; no credit | not eligible; Q4 used 0, pending 0, remaining 75 |
| 11 | Digital entertainment (monthly $25): Oct 4 credit $15.99 matching its credit pattern | Oct used 15.99, remaining 9.01 |
| 12 | Uber Cash (manual, $15 monthly, December $35): manual entry Dec $35 | Dec used 35 status used; Nov with no entry status manual |
| 13 | Saks benefit with `active_until: 2026-06-30`, year 2026 | periods only for H1 2026; no current period shown after June |
| 14 | Resy (credits_only, $100 quarterly): Oct 14 deposit $100 "RESY CREDIT" style matching credit pattern, no purchase matching | Q4 used 100, attribution by_credit_date |
| 15 | Credit posts Oct 2 for a Sep 28 purchase (credit date minus 3 days is Sep 29) with purchase matched | attributed to Q3 via the matched purchase, not Q4 |
| 16 | Two credits $75 and $10 in the same quarter (over cap) | used capped at 75; extra shown in evidence with a "over cap" note |
| 17 | Payment transfer of $500 into the Platinum account | ignored entirely |
| 18 | Unrecognized deposit $12.95 "AMEX CR 88231" | appears in /api/benefits/unclassified |

## 13. Build plan (phases and acceptance)

Phase 1: Scaffold (target 45 min)
* Repo layout, CLAUDE.md, DECISIONS.md, .env.example, .gitignore, pyproject, Vite app, Tailwind, Dockerfile, compose.
* FastAPI serves the built SPA and `/api/health`.
* Settings and YAML loading with validation.
* Accept: `docker compose build` and `docker compose up -d` work; the page loads.

Phase 2: Core plumbing and mocks (45 min)
* Cache, SQLite, scheduler, envelope helpers, auth (login page, cookie, kiosk token), log redaction.
* Fixtures for every integration (realistic: 30 days of Firefly transactions including Amex purchases, credits, refunds, payments; two iCal feeds; Plex sessions; Docker list with one unhealthy and one exited container; an NWS alert).
* Accept: every `/api/*` route returns mock envelopes; unauthenticated calls get 401.

Phase 3: Frontend shell and all widgets on mocks (90 min)
* Layout, header, Card states, privacy blur, every widget, `/benefits`, `/settings`, `/kiosk`.
* Accept: whole dashboard renders on mocks at desktop and phone widths with zero console errors.

Phase 4: Benefits engine (75 min)
* catalog, periods, classify, match, engine, routes, overrides, manual usage, discovery UI wired.
* Accept: all 18 scenarios in 12.2 pass.

Phase 5: Live integrations, no-auth first (45 min)
* Weather (Open-Meteo + NWS), Vaultwarden, Docker via socket proxy, probes.
* Accept: with `MOCK_WEATHER=false`, `MOCK_VAULT=false`, `MOCK_DOCKER=false` real data appears.

Phase 6: Live integrations with credentials (60 min)
* Calendar iCal, Firefly (summary, accounts, transactions, insights, budgets, bills), Amex card resolution, benefits on real data, Plex with image proxy.
* Accept: each shows live data when its env vars are set; unset ones show setup cards.

Phase 7: Polish and docs (30 min)
* Attention strip rules verified, stale and error states verified by stopping a service, README complete, test script green.

Optional Phase 8 (only if time remains): Firefly "Sync now", Firefly tag write-back, container restart, AQI, Vaultwarden backup age.

Note for running the build: Claude Code should run on a machine on Anthony's LAN or tailnet so Phases 5 and 6 can be verified against the real services. If a real service is unreachable from the build environment, leave that integration fully implemented, tested with respx, and running on mocks, and list it in the README status table.

## 14. What Anthony needs to provide (README "Setup" section)

1. Copy `.env.example` to `.env`.
2. Generate a password hash: `docker compose exec frankenstein python -m app.hash_password` (Claude: add this tiny module; it prompts for a password with `getpass` and prints the bcrypt hash) and paste into `DASHBOARD_PASSWORD_HASH`. (Note: `$` characters in the hash must be escaped as `$$` in compose env files if the value is placed in compose directly; in `.env` it is fine.) Generate `SECRET_KEY` and `KIOSK_TOKEN` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Weather: set `NWS_USER_AGENT` with a real contact email. Adjust locations in `config/dashboard.yaml`.
4. Google Calendar: for each calendar, copy the "Secret address in iCal format" into `GCAL_ICS_*` and list it under `calendar.feeds`.
5. Firefly III: create a Personal Access Token (Options, Profile, OAuth, Personal Access Tokens). Set `FIREFLY_URL` to an address reachable from inside the container. Confirm SimpleFIN imports run on a schedule (the Data Importer supports a cron job or its auto import endpoint), otherwise the dashboard will flag stale data.
6. Amex: make sure every benefit is enrolled in the Amex app (credits never post otherwise). After the first sync, open `/benefits`, check the Unclassified list, label anything the engine missed, and paste suggested patterns into `benefits.yaml`.
7. Plex: get the token from Get Info, View XML in Plex Web; set `PLEX_URL` and `PLEX_TOKEN`.
8. Vaultwarden: set `VAULTWARDEN_URL` (internal) and `VAULTWARDEN_PUBLIC_URL` (browser).
9. Docker: nothing beyond compose; optionally add `frankenstein.*` labels to containers.
10. Set `MOCK_MODE=false` (or flip per integration flags one at a time), then `docker compose build` and `docker compose up -d`.

## 15. Future ideas (do not build tonight, list in README)

* Google Calendar OAuth write access (published to Production) for creating events from the dashboard.
* Weather at calendar event time and location ("Rain likely at your 6 PM event").
* Push notifications (ntfy or Pushover) for attention items, especially benefits expiring in 7 days.
* Discover card cashback calendar and tracking.
* Uptime history graphs per container.
* Jira (personal SCRUM board) widget.
* Monthly "credits captured vs annual fee" report.

## Appendix A: Amex benefits catalog (as of October 20, 2026)

Put this into `config/benefits.yaml` with `last_verified: 2026-10-20`. Patterns are starting points; refine through the Discovery screen.

### A.1 Platinum Card (consumer), annual fee $895

| id | Benefit | Cap and period | Tracking | Purchase patterns | Credit patterns | Notes |
|-|-|-|-|-|-|-|
| plat_lululemon | lululemon | $75 quarterly ($300/yr) | matched | `lululemon`, `lulu ?lemon` (exclude `gift ?card`, `\bGC\b`, `outlet`) | `lululemon.*credit`, `credit.*lululemon`, `platinum.*lululemon` | U.S. stores and lululemon.com/app; outlets excluded; gift cards stopped triggering around Oct 5, 2026 |
| plat_resy | Resy dining | $100 quarterly ($400/yr) | credits_only | none | `resy.*credit`, `credit.*resy`, `platinum.*resy` | Restaurant names vary, so track credits only |
| plat_digital_ent | Digital entertainment | $25 monthly ($300/yr) | matched | `disney`, `hulu`, `espn`, `peacock`, `paramount`, `new ?york ?times`, `nytimes`, `wsj`, `wall street journal`, `youtube` | `digital ent.*credit`, `entertainment credit`, `platinum.*(disney|hulu|espn|peacock|paramount|nyt|wsj|youtube).*credit` | Verify the eligible partner list in the Amex app |
| plat_uber_cash | Uber Cash | $15 monthly, $35 in December ($200/yr) | manual | none | none | Lands in the Uber app, not the card |
| plat_uber_one | Uber One membership | $120 annual | matched | `uber ?one` | `uber one.*credit`, `credit.*uber one` | Pay for Uber One with the Platinum |
| plat_hotel | Hotel (Fine Hotels + Resorts / The Hotel Collection, prepaid via Amex Travel) | $300 semiannual ($600/yr) | credits_only | none | `hotel.*credit`, `fhr`, `fine hotels`, `hotel collection`, `amex travel.*credit` | |
| plat_airline | Airline incidental fees (selected airline) | $200 annual | credits_only | none | `airline.*credit`, `airline fee`, `incidental` | |
| plat_clear | CLEAR+ | $219 annual | matched | `clear ?me`, `clear\b` | `clear.*credit` | Some third-party sites still list $209; Amex's own page lists $219 |
| plat_walmart | Walmart+ monthly membership | $12.95 plus tax monthly (set cap 14.00) | matched | `walmart\+`, `walmart plus`, `wmt plus` | `walmart.*credit` | |
| plat_equinox | Equinox / Equinox+ | $300 annual | matched | `equinox` | `equinox.*credit` | |
| plat_oura | Oura Ring (ouraring.com) | $200 annual | matched | `oura` | `oura.*credit` | |
| plat_global_entry | Global Entry or TSA PreCheck | $120 Global Entry every 4 yrs or $85 TSA PreCheck every 4.5 yrs | multi_year | `global entry`, `tsa ?pre`, `cbp`, `idemia`, `telos` | `global entry.*credit`, `tsa.*credit` | Show last used and next eligible date |
| plat_saks | Saks Fifth Avenue | $50 semiannual | matched | `saks` | `saks.*credit` | `active_until: 2026-06-30` (retired July 1, 2026 after Saks Global's bankruptcy); keep for history only |

### A.2 Gold Card (consumer), annual fee $325

| id | Benefit | Cap and period | Tracking | Purchase patterns | Credit patterns | Notes |
|-|-|-|-|-|-|-|
| gold_dining | Dining credit | $10 monthly ($120/yr) | matched | `grubhub`, `seamless`, `five guys`, `cheesecake factory`, `buffalo wild wings`, `bww`, `wonder` | `dining credit`, `gold.*dining`, `(grubhub|seamless|five guys|cheesecake|buffalo wild|wonder).*credit` | Buffalo Wild Wings and Wonder added April 2026; Goldbelly and Wine.com removed July 1, 2026 |
| gold_uber_cash | Uber Cash | $10 monthly ($120/yr) | manual | none | none | Lands in the Uber app |
| gold_resy | Resy | $50 semiannual ($100/yr) | credits_only | none | `resy.*credit`, `gold.*resy` | |
| gold_dunkin | Dunkin' | $7 monthly ($84/yr) | matched | `dunkin` | `dunkin.*credit` | U.S. Dunkin' locations |
| gold_uber_one_promo | Uber One annual membership (limited time) | up to $96 one time | matched | `uber ?one` | `uber one.*credit` | `active_until: 2026-10-30`; one-time promotional credit for the Gold's 60th anniversary |

Note on the Uber One overlap: Platinum `plat_uber_one` and Gold `gold_uber_one_promo` both match "uber one". The engine attributes a purchase to the benefit whose `card` equals the account it was charged on, so there is no conflict.

Sources used for this catalog (put these links in README):
* Amex Platinum official page: https://www.americanexpress.com/us/credit-cards/platinum
* lululemon partnership terms: https://shop.lululemon.com/about/amex-platinum-partnership
* lululemon credit posting timing: https://travelupdate.com/amex-platinum-card-how-soon-does-the-lululemon-credit-post-in-2026/
* lululemon gift card change: https://doctorofcredit.com/reports-lululemon-gift-cards-no-longer-trigger-american-express-platinum-statement-crediy
* Refund clawback behavior: https://thepointsparty.com/articles/amex-platinum-lululemon-credit-guide
* Saks retirement and 2026 changes: https://upgradedpoints.com/credit-cards/reviews/american-express-platinum-card/benefits/ and https://thriftytraveler.com/news/credit-card/amex-platinum-drops-saks-credit/
* Platinum credit list and resets: https://cardstack.money/articles/credit-card-reviews/amex-platinum-credits-list-2026
* Gold 60th anniversary changes: https://awardwallet.com/news/credit-cards/american-express-gold-card-refresh-2026/ and https://www.businesstraveller.com/news/american-express-gold-60/

## Appendix B: WMO weather code map (Open-Meteo `weather_code`)

| Code | Label | Icon (lucide) |
|-|-|-|
| 0 | Clear | sun / moon |
| 1 | Mostly clear | sun / moon |
| 2 | Partly cloudy | cloud-sun / cloud-moon |
| 3 | Overcast | cloud |
| 45, 48 | Fog | cloud-fog |
| 51, 53, 55 | Drizzle | cloud-drizzle |
| 56, 57 | Freezing drizzle | cloud-drizzle |
| 61, 63, 65 | Rain (light, moderate, heavy) | cloud-rain |
| 66, 67 | Freezing rain | cloud-hail |
| 71, 73, 75 | Snow (light, moderate, heavy) | cloud-snow |
| 77 | Snow grains | cloud-snow |
| 80, 81, 82 | Rain showers | cloud-rain-wind |
| 85, 86 | Snow showers | cloud-snow |
| 95 | Thunderstorm | cloud-lightning |
| 96, 99 | Thunderstorm with hail | cloud-lightning |

## Appendix C: Quick reference of every external call

| Service | Call | Auth |
|-|-|-|
| Open-Meteo | `GET https://api.open-meteo.com/v1/forecast?...` | none |
| NWS | `GET https://api.weather.gov/alerts/active?point=lat,lon` | `User-Agent` header with contact |
| Google Calendar | `GET <secret iCal URL>` | the URL itself |
| Firefly III | `GET {FIREFLY_URL}/api/v1/...` | `Authorization: Bearer <PAT>` |
| Firefly Data Importer (optional) | `POST {FIREFLY_IMPORTER_URL}/autoimport?directory=...&secret=...` | secret query param |
| Plex | `GET {PLEX_URL}/identity`, `/status/sessions`, `/library/recentlyAdded`, `/library/onDeck`, `/library/sections`, `/photo/:/transcode` | `X-Plex-Token` header, `Accept: application/json` |
| Vaultwarden | `GET {VAULTWARDEN_URL}/alive`, `/api/version` | none |
| Docker (via socket proxy) | `GET /containers/json?all=true`, `/containers/{id}/json`, `/info`; optional `POST /containers/{id}/restart` | none (network isolation) |

End of spec. Build it.
