## Approach
- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

## Project
Lightweight FastAPI server that lets multiple CursorPace desktop instances share one canonical usage dataset. Each machine pushes samples plus billing-cycle bounds and pulls the merged state. A signed-cookie admin UI issues per-machine Bearer tokens, shows devices and data, and exports or imports the desktop app backup zip plus a full sync-server snapshot (`sync.db` and the session secret).

Stack: Python 3.12+ / FastAPI / uvicorn / aiosqlite / Jinja2. One admin password, one shared dataset per process. Ships as a single Docker container for a trusted LAN (plain HTTP; TLS is out of scope). No extra user accounts, no live presence sockets, no multi-tenant datasets.

Treat `app/` and the tests as truth. Spec details live in `dev/sync-server-implementation-plan.md`; do not drift from sections 4 through 8 without updating that file and the tests. When you change operator-facing behavior, update `README.md` and `dev/DEVEL.md` in the same session unless the user says docs are out of scope. Do not invent features in docs.

## Layout

| Path | Role |
|---|---|
| `app/main.py` | FastAPI app, lifespan (migrate + seed admin), API and HTML routes, presence chips. |
| `app/config.py` | `DATA_DIR`, `PORT`; session secret in `$DATA_DIR/.secret_key`. |
| `app/db.py` | SQLite connect, DDL, query helpers. No ORM. |
| `app/merge.py` | Pure merge: timestamp/decimal normalize, cycle winner, history union. No I/O. |
| `app/auth.py` | Token hash/verify, scrypt admin password, signed session cookie. |
| `app/backup.py` | App-compatible zip and sync-server zip export/import (`sync.db` + session secret). |
| `app/ui.py` | View-only timestamp and number formatting. No I/O, no merge rules. |
| `app/version.py` | `VERSION`, `BUILD_TIMESTAMP`, GitHub and license URLs shown in the footer. |
| `app/templates/` | Server-rendered pages: login, change-password, dashboard, tokens, machines, data, backup. |
| `app/static/` | CSS, JS, icons. No SPA build step. |
| `tests/` | pytest. |
| `dev/` | `CHANGELOG.md`, `DEVEL.md`, implementation plan, release-notes prompt. |
| `scripts/dev.sh` | Local uvicorn `--reload` using `DATA_DIR` / `PORT` (or `.env` / `.env.local`). |
| `scripts/clean.sh` | Remove bytecode, pytest leftovers, and optional local `data/` / `.venv`. |
| `scripts/set-version` | Print or set `VERSION` and refresh `BUILD_TIMESTAMP` in `app/version.py`. |
| `scripts/upgrade-deps` | CLI for `scripts/upgrade_deps.py`: bump pins from PyPI, `--alerts`, or `--set`. |
| `scripts/release.sh` | Tag `v<VERSION>` at HEAD and trigger `.github/workflows/release.yml`. |
| `.github/workflows/release.yml` | Tests, multi-arch image to GHCR, GitHub Release from notes. |
| `Dockerfile` | `python:3.12-slim`, volume `/data`, healthcheck `/healthz`. |
| `docker-compose.yml` | Example service on port 7050 with a named volume. |

Do not add an ORM, a frontend bundler, or a second dataset. Put new tests under `tests/`.

## Architecture
Construct the app with `create_app(settings)`. Tests pass a temp `Settings(data_dir=..., secret_key=...)`. Production lifespan creates `$DATA_DIR`, writes `.secret_key` (mode `0600`) if missing, runs DDL, and seeds `meta.admin_hash` from `DEFAULT_ADMIN_PASSWORD` (`cursorpace01`) when that key is absent.

- Config: `DATA_DIR` defaults to `/data` (Compose volume) and `./data` under `scripts/dev.sh`. `PORT` defaults to `7050`. Do not store the session secret in env; persist it next to `sync.db`.
- Time: merge and API timestamps are UTC canonical `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Cycle bounds in the API are local wall-clock ISO without offset. `app/ui.py` must not convert cycle bounds to the viewer's timezone.
- Persistence: SQLite file `$DATA_DIR/sync.db`. Tables `samples`, `meta`, `devices` (spec §5). `meta` keys: `admin_hash`, `cycle_start_utc`, `active_cycle` (JSON), `cycle_history` (JSON).
- Merge: keep `merge.py` pure. Samples union by canonical `ts`; first writer wins (`INSERT OR IGNORE`). `cycle_start_utc` keeps the later instant. `active_cycle` newest-wins (later `cycle_start`, then later `next_renewal`, else keep stored). `cycle_history` unions by `cycle_start` date part; duplicate dates keep the later `next_renewal`. Never convert percentages through `float` in merge or storage; use `Decimal` and store plain strings (max 4 fractional digits, non-negative).
- Auth (API): `Authorization: Bearer <raw-token>`; `sha256` hex compared to `devices.token_hash`. Missing or revoked token is `401` `{"detail": "Invalid or missing API token"}`. Tokens are `secrets.token_urlsafe(32)`; store only the hash and an 8-character display prefix. Revoke deletes the device row; samples stay.
- Auth (admin): stdlib `hashlib.scrypt`. Session cookie `cursorpace_session` via `itsdangerous`. First login with the default password must complete `/change-password` (min 8 chars, not the default, confirm match) before any other admin page. No account lockout.
- Backup: two zip products. App zip `CursorPace` `formatVersion` 1; import replaces samples + cycle meta unless merge is checked (then union per `merge.py` / push). Accept app-produced zips; reject `product` other than `CursorPace` and `formatVersion` greater than 1. Missing `manifest.json` is allowed (old backups). Missing `usage-samples.json` means empty samples. Sync-server zip `CursorPaceSyncServer` contains `sync.db` and `secret_key`; import replaces the database and `$DATA_DIR/.secret_key` (mode `0600`) and re-issues the admin session. Cross-upload of the wrong zip kind is rejected.
- Web UI: Jinja2 plus minimal vanilla JS. Routes: `/login`, `/change-password`, `/logout`, `/`, `/tokens`, `/machines`, `/data`, `/backup` (dataset and sync-server export/import). Footer shows version, UTC build stamp, copyright, and the GitHub link from `app/version.py`.
- Presence: derived, not stored. Active: last seen within 15 minutes. Recent: within 24 hours. Stale: older. Never: null. Push and pull both update `last_seen_utc`.
- Version: `./scripts/set-version` rewrites `VERSION` and `BUILD_TIMESTAMP` in `app/version.py`. Docker may also write `app/BUILD_TIMESTAMP` at image build. `APP_VERSION` / `BUILD_TIMESTAMP` env vars override display only.

## Sync contract
Base path `/api/v1`. Max 50,000 samples per push (else 413). Unparseable timestamps are HTTP 400 naming the index.

`POST /api/v1/push` body: `machine_name` (1-64 chars), optional `cycle_start_utc`, optional `active_cycle` (`cycle_start` + `next_renewal` local ISO), `cycle_history`, `samples` (`ts`, `cursor`, `other`). Merge per spec §6.3. Response `{accepted, duplicates, total_samples, server_time}`.

`GET /api/v1/pull` returns the full canonical state (no deltas): `cycle_start_utc`, `active_cycle`, `cycle_history`, `samples`, `server_time`. Empty server uses null / `[]`. Updates device presence.

`GET /healthz` is unauthenticated `{"status": "ok"}` (Docker healthcheck).

This server never talks to Cursor. Desktop clients fetch usage themselves and replicate samples plus cycle bounds/history only.

If you change timestamp/decimal rules or cycle-winner / history-union, update and run `tests/test_merge.py`. If you change push/pull/auth HTTP behavior, update `tests/test_api.py`. If you change the zip format or import transaction, update `tests/test_backup.py`. If you change admin login, password gate, pages, or footer metadata, update `tests/test_web.py`. If you change display formatting or presence chips, update `tests/test_ui.py`. If you change `.secret_key` path or mode, update `tests/test_config.py`. If you change `VERSION` assignment shape or `scripts/set-version`, update `tests/test_version.py`. If you change pin-upgrade selection or `scripts/upgrade-deps`, update `tests/test_upgrade_deps.py`.

## Commands
```
source .venv/bin/activate
pip install -r requirements.txt
./scripts/dev.sh
./scripts/clean.sh
pytest -q
python3 -m py_compile app/*.py tests/*.py
./scripts/set-version
./scripts/set-version 1.2.3
./scripts/upgrade-deps --dry-run
./scripts/upgrade-deps --alerts
./scripts/upgrade-deps
./scripts/release.sh
./scripts/release.sh --dry-run
docker compose up --build -d
docker build -t cursorpace-sync .
```

Do not add a frontend toolchain or switch SQLite to another engine unless asked.

## Changelog
After any behavioral change, bug fix, settings/schema change, or dependency update, add a bullet under `## [Unreleased]` in `dev/CHANGELOG.md` in the same edit session as the code.

Format: `- **{Type}**: {scope} - description.` Types: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Use backticks for identifiers. One bullet per logical change. Scopes are short (`api`, `merge`, `backup`, `auth`, `web`, `docker`, `config`, `tokens`).

Skip only for documentation-only or comment-only edits with no operator-visible effect.

Do not move `[Unreleased]` into a versioned section, and do not write `release-notes/RELEASE_NOTES_*.md`, unless you are following `dev/release-new-version-prompt.md`.

## When changing code
- Match existing naming and file placement. Keep merge and UI formatting free of I/O.
- Prefer editing an existing module over new layers.
- Keep templates thin; put merge and persistence in `merge.py` / `db.py` / `backup.py`.
- After merge, API, backup, auth, or version changes: `pytest -q`.
- After web UI changes: run `./scripts/dev.sh` and walk login, change-password, tokens, machines, data, and backup if those paths were touched. Automated tests do not replace that checklist in `dev/DEVEL.md`.
- Log operator-visible work in `dev/CHANGELOG.md` (see Changelog above).
- Do not commit `.venv/`, `__pycache__/`, `data/`, `.secret_key`, `.env*`, `*.db`, or `app/BUILD_TIMESTAMP` (gitignored).
- Do not commit unless asked.
