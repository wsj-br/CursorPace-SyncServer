# CursorPace Sync Server

Lightweight server letting multiple CursorPace desktop instances share usage data.

## First run

1. Set env vars (see below), then:
   ```bash
   docker compose up --build -d
   ```
2. Open `http://server:8080/login`, sign in with `ADMIN_PASSWORD`.
3. Go to **Tokens** → create a token per machine (raw token is shown once).
4. In each CursorPace app Settings, set the sync URL to `http://server:8080`
   and paste that machine's token.

Or run locally:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ADMIN_PASSWORD=change-me SECRET_KEY=dev-secret DATA_DIR=./data PORT=8080 \
  uvicorn app.main:app --reload
```

## Env vars

| Var | Required | Default | Meaning |
|---|---|---|---|
| `ADMIN_PASSWORD` | yes (first boot) | — | Seeds the admin password hash if none stored. |
| `SECRET_KEY` | no | random per boot (warn) | Signs admin session cookies; set for stable logins. |
| `DATA_DIR` | no | `/data` | SQLite file `sync.db` lives here; keep as a volume. |
| `PORT` | no | `8080` | Listen port. |

## API summary

- `GET /healthz` → `{"status": "ok"}` (no auth).
- `POST /api/v1/push` with `Authorization: Bearer <token>` merges samples +
  cycle bounds (spec §6.3). Max 50,000 samples per request.
- `GET /api/v1/pull` with `Authorization: Bearer <token>` returns the full
  canonical state (spec §6.4).

## Token flow

**Tokens** page → enter machine name → **Generate token** → copy the raw token
once → paste into that machine's app. **Revoke** deletes the token row
(pushed samples stay); revoked tokens get `401` immediately.

## Backup / restore

**Backup** page → **Export** downloads `cursorpace-backup-<stamp>.zip`
(`manifest.json`, `settings.json`, `usage-samples.json`).
**Import** accepts app- or server-produced zips and replaces the canonical
dataset in one transaction.
