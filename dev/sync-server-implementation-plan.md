# CursorPace Sync Server — Implementation Plan (Part A)

Self-contained build spec for an AI agent working in a **new, empty repo** (suggested name: `CursorPace-SyncServer`).
No access to the CursorPace app repo is assumed; all cross-repo contracts are defined below.

## 1. Goal

Build a lightweight server that lets multiple CursorPace desktop instances share usage data:

- Each app instance pushes its usage samples plus billing-cycle bounds and pulls the merged canonical state.
- A web UI manages per-machine API tokens, shows machines and sync status, and supports backup export/import.
- Ships as a single Docker container on a trusted LAN (plain HTTP, no TLS in scope).

Non-goals: user accounts beyond one admin password, live presence sockets, TLS termination, multi-tenant datasets (one shared dataset per server).

## 2. Tech choices (fixed)

- Language: Python 3.12+.
- Web: FastAPI + uvicorn.
- DB: SQLite via aiosqlite, plain SQL, no ORM.
- Web UI: server-rendered Jinja2 templates plus minimal vanilla JS; no SPA build step.
- Sessions: signed cookie via `itsdangerous` (bundled approach, no extra session store).
- Password hashing: stdlib `hashlib.scrypt` (no passlib/bcrypt dependency).
- Tests: pytest with httpx `TestClient` (or FastAPI `TestClient`).

## 3. Repository layout to create

```
.
├── Dockerfile
├── docker-compose.yml        # example deployment with /data volume
├── README.md                 # setup, env vars, API summary
├── requirements.txt          # pinned: fastapi, uvicorn, aiosqlite, jinja2, itsdangerous, httpx, pytest
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, route wiring, startup (migrate + seed admin)
│   ├── config.py             # env parsing: DATA_DIR, PORT; session secret in $DATA_DIR/.secret_key
│   ├── db.py                 # sqlite connect, migrate/DDL, query helpers
│   ├── merge.py              # pure merge functions (samples union, cycle winner, history union)
│   ├── backup.py             # export/import of the app backup zip format (section 7)
│   ├── auth.py               # token hashing/verification, admin password check, session helpers
│   └── templates/            # login.html, dashboard.html, tokens.html, machines.html, data.html, backup.html
│   └── static/               # one small styles.css (no framework needed)
└── tests/
    ├── test_merge.py
    ├── test_api.py
    └── test_backup.py
```

## 4. Configuration

| Env var | Required | Default | Meaning |
|---|---|---|---|
| `DATA_DIR` | no | `/data` | SQLite file `sync.db` and session secret `.secret_key` live here; must be a Docker volume. |
| `PORT` | no | `7050` | Listen port. |

Startup behavior: run DDL migrations, create `$DATA_DIR/.secret_key` (mode `0600`) if missing, seed the default admin password `cursorpace01` if the `meta` key `admin_hash` is absent, then serve. First admin login with that default must choose a new password before the rest of the UI is available.

## 5. Database schema (SQLite, file `sync.db`)

```sql
CREATE TABLE IF NOT EXISTS samples (
    ts TEXT PRIMARY KEY,        -- normalized UTC instant, format %Y-%m-%dT%H:%M:%S.%fZ (see 6.1)
    cursor TEXT NOT NULL,       -- decimal as string, e.g. "12.50"
    other TEXT NOT NULL,        -- decimal as string
    source_machine TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- meta keys: admin_hash, cycle_start_utc, active_cycle (JSON), cycle_history (JSON)
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,   -- sha256 hex of raw token
    token_prefix TEXT NOT NULL,        -- first 8 chars of raw token, for display
    created_utc TEXT NOT NULL,
    last_seen_utc TEXT,                -- updated on every authenticated push/pull
    last_sample_count INTEGER NOT NULL DEFAULT 0,  -- canonical sample count at last contact
    last_push_count INTEGER NOT NULL DEFAULT 0
);
```

`active_cycle` JSON shape: `{"cycle_start": "<local ISO>", "next_renewal": "<local ISO>"}` (local wall-clock ISO without offset, e.g. `2026-08-15T01:00:00`).
`cycle_history` JSON shape: array of the same objects.
`cycle_start_utc`: UTC ISO instant string.

## 6. Sync semantics (must implement exactly)

### 6.1 Timestamp normalization

- Parse any ISO-8601 `ts` (with `Z` or numeric offset) to a UTC instant.
- Canonical form: UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ` (microseconds always present, e.g. `2026-09-01T10:00:00.000000Z`).
- Samples merge on this canonical string. Reject unparseable timestamps with HTTP 400 naming the index.

### 6.2 Decimal precision

- `cursor` / `other` are percentages as decimal strings. Validate with a decimal parser (max 4 fractional digits accepted, non-negative); store the normalized plain string (strip exponent, keep value).
- Never convert through float.

### 6.3 Push merge rules

Given an authenticated `POST /api/v1/push` body (schema in 8.1):

1. Samples: `INSERT OR IGNORE` each normalized sample; first writer wins per timestamp (values for the same instant are identical in practice since all machines read the same Cursor account).
2. `cycle_start_utc`: keep the latest instant (max) of stored vs pushed.
3. `active_cycle`: newest wins — compare `cycle_start` as an instant (parse local ISO as-is for ordering; all machines share one Cursor account so wall clocks agree to the minute); later start wins; tie-break by later `next_renewal`; final tie-break keeps the stored value.
4. `cycle_history`: union by `cycle_start` date part; on duplicate start date keep the entry with the later `next_renewal`.
5. Update the calling device row: `name` (from body `machine_name`), `last_seen_utc = now`, `last_push_count`, `last_sample_count = canonical total`.
6. Response: `{accepted: <new rows>, duplicates: <ignored>, total_samples: <canonical total>, server_time: <utc iso>}`.

### 6.4 Pull

`GET /api/v1/pull` returns the full canonical state (no deltas; sample volume is small — tens of rows per cycle):

```json
{
  "cycle_start_utc": "2026-08-15T00:00:00.000000Z",
  "active_cycle": {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"},
  "cycle_history": [],
  "samples": [{"ts": "2026-09-01T10:00:00.000000Z", "cursor": "12.50", "other": "3.25"}],
  "server_time": "2026-09-18T10:00:00.000000Z"
}
```

Empty server returns `cycle_start_utc: null`, `active_cycle: null`, `cycle_history: []`, `samples: []`.
Pull also updates the calling device's `last_seen_utc` and `last_sample_count`.

### 6.5 Presence status (web UI derivation, not stored)

- Active: last seen within 15 minutes.
- Recent: within 24 hours.
- Stale: older than 24 hours.
- Never: null.

## 7. Backup export/import format (app-compatible)

The server export MUST be restorable by the desktop app, and server import MUST accept app-produced backups. The zip contains exactly three entries:

### 7.1 `manifest.json`

```json
{"formatVersion": 1, "product": "CursorPace", "createdUtc": "2026-09-18T10:00:00.000000Z"}
```

- On import: `product` must equal `CursorPace` (case-sensitive); reject `formatVersion` greater than 1.

### 7.2 `settings.json`

```json
{
  "version": 2,
  "activeCycle": {"renewalDay": 15, "cycleStart": "2026-08-15T01:00:00", "nextRenewal": "2026-09-15T01:00:00"},
  "cycleHistory": [{"renewalDay": 15, "cycleStart": "2026-07-15T01:00:00", "nextRenewal": "2026-08-15T01:00:00"}],
  "cursorAccountConnected": true
}
```

- Export: build from canonical `active_cycle` / `cycle_history`; `renewalDay` is the start-date day number; include `cursorAccountConnected: true` only when an active cycle exists; omit all other app keys.
- Import: read `activeCycle` / `cycleHistory` bounds only; ignore every other key (including legacy `renewalDay` / `edits` / `days`); validate `nextRenewal > cycleStart`, skip invalid entries.

### 7.3 `usage-samples.json`

```json
{
  "version": 1,
  "cycleStartUtc": "2026-08-15T00:00:00.000000Z",
  "samples": [{"ts": "2026-09-01T10:00:00.000000Z", "cursor": 12.50, "other": 3.25}]
}
```

- Export: `cycleStartUtc` from canonical meta; samples sorted ascending by `ts`; numbers may be JSON numbers.
- Import: accept numbers or numeric strings for `cursor`/`other`; normalize timestamps per 6.1; sort ascending.

### 7.4 Import behavior

- Replaces the entire canonical dataset (samples + cycle meta) inside one SQLite transaction.
- Missing `usage-samples.json` in the zip means empty samples (do not fail).
- Missing `manifest.json` is allowed (old backups); when present, validate per 7.1.

## 8. HTTP API specification

Base path `/api/v1`. Auth: `Authorization: Bearer <raw-token>` where `sha256(raw-token)` matches a `devices.token_hash`. Missing/invalid token yields 401 JSON `{"detail": "Invalid or missing API token"}`.

### 8.1 `POST /api/v1/push`

Request:

```json
{
  "machine_name": "dev-laptop",
  "cycle_start_utc": "2026-08-15T00:00:00.000000Z",
  "active_cycle": {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"},
  "cycle_history": [{"cycle_start": "2026-07-15T01:00:00", "next_renewal": "2026-08-15T01:00:00"}],
  "samples": [{"ts": "2026-09-01T10:00:00.000000Z", "cursor": "12.50", "other": "3.25"}]
}
```

- `machine_name`: required, 1-64 chars.
- `active_cycle`: nullable; when present both fields required local ISO datetimes.
- `samples`: array, max 50,000 entries per request (else 413); each entry requires `ts`, `cursor`, `other`.
- Merge per 6.3. Response 200: `{accepted, duplicates, total_samples, server_time}`.

### 8.2 `GET /api/v1/pull`

- Response 200 per 6.4. Updates device presence.

### 8.3 `GET /healthz`

- No auth. Response 200 `{"status": "ok"}`. Used by Docker healthcheck.

## 9. Web UI specification (admin password)

- `GET /login`: password form. First boot uses default password `cursorpace01` and shows that on the form. `POST /login`: verify scrypt hash, set signed session cookie. If the password is still the default, redirect to `/change-password`; otherwise redirect `/`. Wrong password re-renders with an error (no account lockout in scope).
- `GET`/`POST /change-password`: required after first login with the default password. New password must differ from the default, be at least 8 characters, and match confirmation. Other admin routes redirect here until it succeeds.
- `POST /logout`: clear session. All routes below require a valid session that has completed password setup, else redirect to `/login` or `/change-password`.
- `GET /` dashboard: cards for device count, total samples, active cycle range, last push time; quick links.
- `GET /tokens`: table of devices (name, prefix, created, last seen, status); `POST /tokens` with `name` generates a token, stores only its hash, and shows the raw token once on a confirmation page; `POST /tokens/{id}/delete` revokes (delete row; pushed samples stay).
- `GET /machines`: same device data focused on sync status (last seen, status chip per 6.5, last sample count, last push size). May share the tokens table implementation with different columns.
- `GET /data`: active cycle bounds, history count, sample count, earliest/latest sample ts, last 20 samples table.
- `GET /backup`: export button (`GET /backup/export` streams the zip download `cursorpace-backup-<utc-stamp>.zip`) and import form (`POST /backup/import` multipart file, validates per 7.4, shows summary or errors).
- Token generation: `secrets.token_urlsafe(32)`; store `sha256` hex; display prefix is the first 8 raw chars.

## 10. Docker and deployment

Dockerfile (single stage is fine):

- Base `python:3.12-slim`, `WORKDIR /app`, copy requirements then source, `EXPOSE 7050`.
- Run `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7050}`.
- `HEALTHCHECK` against `http://127.0.0.1:${PORT:-7050}/healthz`.
- Declare `VOLUME /data`.

`docker-compose.yml` example:

```yaml
services:
  sync:
    image: ghcr.io/wsj-br/cursorpace-syncserver:latest
    build: .
    ports: ["7050:7050"]
    volumes:
      - sync-data:/data
volumes:
  sync-data:
```

Releases: `./scripts/upgrade-deps` (or `--alerts`) refreshes `requirements.txt` pins, then `./scripts/release.sh` tags `v<VERSION>` from `app/version.py`. `.github/workflows/release.yml` publishes `linux/amd64` and `linux/arm64` images to `ghcr.io/<owner>/<repo>` and creates the GitHub Release from `release-notes/RELEASE_NOTES_<version>.md`.

README must document: first-run steps, the GHCR image, env vars, LAN URL for app Settings (e.g. `http://server:7050`), token creation flow, and backup/restore.

## 11. Implementation order

1. Scaffold repo layout, requirements, config, DB module with DDL.
2. `merge.py` pure functions plus `tests/test_merge.py`.
3. API routes push/pull/healthz plus `tests/test_api.py` (auth failures, merge convergence, idempotent re-push).
4. `backup.py` export/import plus `tests/test_backup.py` (round-trip; import of a hand-written app-style zip; rejection of bad manifest/product and newer formatVersion).
5. Web UI templates and session auth (manual check: login, create token, revoke, export, import).
6. Dockerfile, compose file, README; verify container boots, persists across restart, healthcheck passes.

## 12. Acceptance criteria

- Two sequential pushes from different machine names with overlapping samples converge to one canonical set with no duplicates.
- Re-pushing identical data returns `accepted: 0` and is idempotent.
- Newer `active_cycle` wins; history union keeps one entry per start date.
- Invalid token yields 401; revoked token stops working immediately.
- Exported zip unzips to the three entries in section 7 and imports back with zero diff.
- Container restart with the same `/data` volume preserves samples, cycles, and tokens.
- `pytest` passes; `GET /healthz` returns ok.
