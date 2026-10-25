# FrankensteinCentral

A self-hosted personal life dashboard: weather, calendar, finances (Firefly III), Amex benefit tracking, Lock-In training, Plex, Vaultwarden health, and Docker containers on one dark screen, with a kiosk mode for an always-on display.

The full build specification is in `SPEC.md`. Choices the spec left open are logged in `DECISIONS.md`.

## Status: what is real and what is mocked

Every integration has a live adapter and a fixture-backed mock. `MOCK_MODE=true` (the default) uses fixtures everywhere; per integration flags (`MOCK_WEATHER`, `MOCK_CALENDAR`, `MOCK_FIREFLY`, `MOCK_PLEX`, `MOCK_VAULT`, `MOCK_DOCKER`) let you go live one service at a time.

The build environment for this repository had no outbound network access to the real services and no Docker daemon, so the live adapters were verified with recorded fixtures through `respx` rather than against Anthony's homelab. Each one is implemented end to end and only needs credentials.

| Integration | Live adapter | Verified against | Needs |
|-|-|-|-|
| Weather (Open-Meteo + NWS alerts, optional AQI) | implemented | respx with recorded responses | `NWS_USER_AGENT` with a real email (no key) |
| Calendar (Google secret iCal feeds) | implemented, conditional requests, recurrence expansion | respx plus iCal parsing tests (RRULE, EXDATE, RECURRENCE-ID, all-day, TZID, UTC, canceled) | `GCAL_ICS_*` URLs |
| Firefly III (accounts, summary, transactions, insights, budgets, bills) | implemented with pagination | respx (pagination, token rejection, degraded) | `FIREFLY_URL`, `FIREFLY_TOKEN` |
| Amex cards and benefits engine | implemented | 18 scenario tests from SPEC section 12.2 plus extras | Firefly |
| Plex (plex.tv discovery for owned or shared servers, identity, sessions, recently added, on deck, libraries, image proxy) | implemented | respx | `PLEX_URL`, `PLEX_TOKEN` |
| Vaultwarden (alive, version, backup age) | implemented | respx | `VAULTWARDEN_URL` |
| Docker (socket proxy, inspect, restart counts) | implemented | respx | compose socket proxy (no extra config) |
| Lock-In training tracker (summary, week squares, weight trend) | implemented | respx plus unit tests | `LOCKIN_URL`, `LOCKIN_TOKEN` |
| HTTP probes | implemented | mock | `probes` in `config/dashboard.yaml` |
| Recurring charge detector | implemented | 10 unit tests plus an API test on mock data | Firefly |
| Firefly "Sync now" (data importer) | implemented | manual only | `FIREFLY_IMPORTER_URL`, `FIREFLY_IMPORTER_SECRET` |
| Firefly tag write back | implemented behind `FIREFLY_WRITEBACK_TAGS` | respx | off by default |
| Container restart | implemented behind `DOCKER_ALLOW_RESTART` | API test (403 by default) | proxy `POST=1`, `ALLOW_RESTARTS=1` |

Test suite: 83 backend tests (`pytest`) and 9 frontend tests (`vitest`); `scripts/test.sh` runs everything, and the GitHub Actions workflow in `.github/workflows/ci.yml` runs it on every push and pull request.

## Setup

1. Copy `.env.example` to `.env`. The `data/` folder ships with the repository and is mounted into the container for the SQLite database; it must be writable by uid 1000 (the first user on Ubuntu). If the container logs "unable to open database file", run `sudo chown -R 1000:1000 data` once.
2. Generate secrets.
   * Password hash: `docker compose run --rm frankenstein python -m app.hash_password` (or `docker compose exec frankenstein python -m app.hash_password` once the stack is up). Paste the printed bcrypt hash into `DASHBOARD_PASSWORD_HASH` wrapped in single quotes, for example `DASHBOARD_PASSWORD_HASH='$2b$12$...'`. Docker Compose treats a bare `$` in `.env` as a variable reference and would blank out parts of the hash, which makes every login fail. (If you ever paste the hash directly into `docker-compose.yml`, write each `$` as `$$` instead.)
   * `SECRET_KEY` and `KIOSK_TOKEN`: `python -c "import secrets; print(secrets.token_urlsafe(48))"` (run twice).
   * Until a hash is set, the login page accepts any password and the log prints a warning. Set it before exposing the dashboard beyond your own machine.
3. Weather: set `NWS_USER_AGENT` to something like `(FrankensteinCentral, you@example.com)`; the National Weather Service requires a contact. Adjust `weather.locations` in `config/dashboard.yaml` (several locations are allowed, the dashboard has a switcher).
4. Google Calendar: in Google Calendar on the web open Settings, pick the calendar under "Settings for my calendars", scroll to "Integrate calendar", and copy "Secret address in iCal format". Paste it into `GCAL_ICS_PRIMARY` (and `GCAL_ICS_SECOND`, or add more feeds under `calendar.feeds` with any env var name). The URL is a credential: anyone with it can read the calendar, and Google lets you reset it.
5. Firefly III: create a Personal Access Token (Options, Profile, OAuth, Personal Access Tokens, Create new token) and put it in `FIREFLY_TOKEN`. Set `FIREFLY_URL` to an address reachable from inside the container (see networking below) and `FIREFLY_VANITY_URL` to the address you use in the browser, so amounts link into Firefly. Make sure the SimpleFIN imports run on a schedule; the dashboard flags finance data older than `finance.stale_after_hours` (48 by default).
6. Amex: enroll every benefit in the Amex app, otherwise credits never post. After the first sync open `/benefits`, review the Unclassified deposits list, label anything the engine missed, and paste the suggested regex patterns into `config/benefits.yaml`. Verify the catalog against the Benefits page in the Amex app once a quarter and bump `last_verified`.
7. Plex: set `PLEX_TOKEN` to your account token. The quickest way to get it: open `app.plex.tv` in a desktop browser, press F12, open the Console tab, run `localStorage.getItem("myPlexAccessToken")`, and copy the value without the quotes. (On a server you own, View XML under Get Info also shows it in the URL.) Then either:
   * leave `PLEX_URL` empty, and Frankenstein asks plex.tv which servers your account can see, including servers friends have shared with you, picks the owned one or the first shared one (or `PLEX_SERVER_NAME`), and connects through the server's public address or the Plex relay using the server specific token plex.tv issues; or
   * set `PLEX_URL` to a direct address such as `http://192.168.1.50:32400` when the server is on your own network.
   `PLEX_PUBLIC_URL` is where "Open Plex" links go. The health probe for Plex only runs when `PLEX_URL` is set.
8. Vaultwarden: set `VAULTWARDEN_URL` (internal) and `VAULTWARDEN_PUBLIC_URL` (browser). Optional: mount your backup folder read-only and set `VAULTWARDEN_BACKUP_DIR` to show backup age and warn after 48 hours.
9. Lock-In (your training tracker): set `LOCKIN_TOKEN` to the same value as `LOCKIN_TOKEN` in the Lock-In `.env`, `LOCKIN_URL` to an address the container can reach (the Lock-In compose binds `127.0.0.1:8090`, so either join its Docker network and use `http://lockin:8080`, or publish it on the host IP), and `LOCKIN_PUBLIC_URL` to the Tailscale HTTPS address the phone uses, for the "Open Lock-In" button. Frankenstein only reads `/api/health`, `/api/summary`, and `/api/export`; it never writes.
10. Docker: nothing beyond compose. Optional labels on any container: `frankenstein.url` (launch link), `frankenstein.name` (display name), `frankenstein.hide=true`, `frankenstein.critical=true` (non-running becomes a critical attention item).
11. Set `MOCK_MODE=false` (or flip the per integration flags one at a time), then:

```
docker compose build
docker compose up -d
```

Open `http://<host>:8088`. The kiosk view is `http://<host>:8088/kiosk?token=<KIOSK_TOKEN>` (open it once per device; it sets a read-only cookie and drops the token from the URL).

### Docker networking

Inside a container, `localhost` is the container itself. `FIREFLY_URL`, `PLEX_URL`, and `VAULTWARDEN_URL` must point at something the container can reach:

* the host's LAN IP or Tailscale name, for example `http://100.x.y.z:8080`, or
* the other container's name on a shared Docker network. To join Firefly's existing network, add it to `docker-compose.yml`:

```yaml
services:
  frankenstein:
    networks:
      - frankenstein
      - socket
      - firefly_default        # whatever `docker network ls` shows for Firefly
networks:
  firefly_default:
    external: true
```

Then `FIREFLY_URL=http://<firefly-container-name>:8080`.

### Keep it off the public internet

The dashboard is meant for the LAN and your tailnet only. Pick one:

* Bind the published port to the host's Tailscale IP: change `ports` to `"100.x.y.z:8088:8000"`.
* Do not publish a port at all and run `tailscale serve --bg 8088` (or `tailscale serve https / http://127.0.0.1:8088`) on the host to expose it inside the tailnet with HTTPS. When served over HTTPS the session cookie is marked `Secure` automatically.

### Optional features

* **Sync now** (Finance widget): set `FIREFLY_IMPORTER_URL`, `FIREFLY_IMPORTER_SECRET`, and `FIREFLY_IMPORTER_DIR`. On the importer side set `AUTO_IMPORT_SECRET`, `CAN_POST_AUTOIMPORT=true`, and `IMPORT_DIR_ALLOWLIST` to that directory, and keep a saved SimpleFIN import configuration JSON there. The dashboard calls `POST /autoimport?directory=...&secret=...` and refreshes Firefly 90 seconds later. The dashboard never changes the importer's configuration.
* **Tag write back**: `FIREFLY_WRITEBACK_TAGS=true` tags statement credits you label on the Discovery screen with `amex-credit` and `benefit:<id>:<period>` in Firefly. Existing tags and splits are preserved. Off by default.
* **Container restart**: `DOCKER_ALLOW_RESTART=true` plus `POST: 1` and `ALLOW_RESTARTS: 1` on the socket proxy adds a restart button with a confirmation step. The tradeoff: the proxy then accepts POST requests from the dashboard container, so anyone who can log in to the dashboard can restart containers. Leave it off unless you want that.
* **Air quality**: shown automatically when the US AQI is 101 or higher.

## Using the dashboard

* **Attention strip**: critical (red), warning (amber), info (blue) items from every module, at most six. Collapses to "All clear".
* **Privacy**: the eye icon in the header blurs every dollar amount. The choice is saved per browser and in the dashboard settings. Kiosk amounts are blurred unless `finance.kiosk_hide_amounts: false`.
* **Benefits page** (`/benefits`): tiles per benefit with used (green), pending (striped amber), and remaining (gray). Click a tile for the evidence drawer and use "this is wrong" to reclassify. Manual benefits (Uber Cash) are checked off per period at the bottom.
* **Settings** (`/settings`): pin the Firefly account behind each card, pick the default weather location, see each integration's status, last fetch, last error, and whether it is mocked.
* **Lock-In** (under Weather, and on the kiosk): phase and week, streak, next workout, Monday to Sunday squares, sessions this week, latest weight, 7 day average, weekly change against the phase target, and a 60 day weight trend. The attention strip warns when the 5 session streak is at risk for the week, nudges you to log a weigh-in after 10 AM, and notes deload weeks.
* **Recurring charges** (under Finances): every withdrawal in Firefly from the last year is clustered by merchant and cadence (weekly to yearly). The widget shows the monthly and yearly total, flags price increases, new subscriptions, charges routed through Apple or PayPal (split by amount), and subscriptions that stopped. A price increase also lands in the attention strip. Click the eye icon to ignore a charge that is not a subscription; transfers and deposits never count.
* Stale data: a widget whose source has not refreshed for three refresh intervals shows an amber "stale" badge but keeps showing the last good data. Cached data survives restarts.

## Development

```
cd backend && uv sync && uv run python run.py          # API on :8000, serves frontend/dist if built
cd frontend && npm install && npm run dev               # Vite on :5173, proxies /api to :8000
cd backend && uv run pytest                             # backend tests
cd frontend && npm run build && npm test                # typecheck, build, unit tests
scripts/test.sh                                         # everything
```

Regenerate fixtures with `python -m app.fixtures.generate_firefly` and `python -m app.fixtures.generate_weather` from `backend/`. Fixtures are anchored on 2026-10-20 and shifted to today at runtime so the mock dashboard always looks current.

## Future ideas (not built)

* Google Calendar OAuth write access for creating events from the dashboard. If built, publish the OAuth consent screen to Production; apps left in Testing lose their refresh tokens after 7 days, which silently breaks sync.
* Weather at calendar event time and location ("Rain likely at your 6 PM event").
* Push notifications (ntfy or Pushover) for attention items, especially benefits expiring in 7 days.
* Discover card cashback calendar and tracking.
* Uptime history graphs per container.
* Jira (personal SCRUM board) widget.
* Monthly "credits captured vs annual fee" report.

## Benefit catalog sources (October 2026)

* Amex Platinum official page: https://www.americanexpress.com/us/credit-cards/platinum
* lululemon partnership terms: https://shop.lululemon.com/about/amex-platinum-partnership
* lululemon credit posting timing: https://travelupdate.com/amex-platinum-card-how-soon-does-the-lululemon-credit-post-in-2026/
* lululemon gift card change: https://doctorofcredit.com/reports-lululemon-gift-cards-no-longer-trigger-american-express-platinum-statement-crediy
* Refund clawback behavior: https://thepointsparty.com/articles/amex-platinum-lululemon-credit-guide
* Saks retirement and 2026 changes: https://upgradedpoints.com/credit-cards/reviews/american-express-platinum-card/benefits/ and https://thriftytraveler.com/news/credit-card/amex-platinum-drops-saks-credit/
* Platinum credit list and resets: https://cardstack.money/articles/credit-card-reviews/amex-platinum-credits-list-2026
* Gold 60th anniversary changes: https://awardwallet.com/news/credit-cards/american-express-gold-card-refresh-2026/ and https://www.businesstraveller.com/news/american-express-gold-60/
