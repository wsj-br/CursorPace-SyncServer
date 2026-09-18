# Development guide — CursorPace Sync Server

How to go from a clean `git clone` to a running server, tests, and Docker image.

## Prerequisites

- Python 3.12+
- Docker + Docker Compose plugin (for container steps only)
- Normal internet access (PyPI + Docker Hub)

## 1. Clone and set up the virtualenv

```bash
git clone <repo-url> CursorPace-SyncServer
cd CursorPace-SyncServer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run the server locally

```bash
ADMIN_PASSWORD=change-me SECRET_KEY=dev-secret DATA_DIR=./data PORT=8080 \
  uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8080/login` and sign in with password `change-me`.

| Env var | Meaning |
|---|---|
| `ADMIN_PASSWORD` | Seeds the admin password on first boot (required) |
| `SECRET_KEY` | Signs admin session cookies; set it or logins reset on restart |
| `DATA_DIR` | Directory holding `sync.db` (default `/data`) |
| `PORT` | Listen port (default `8080`) |

To simulate a second machine, create a token per machine under **Tokens** and
use each token as `Authorization: Bearer <token>` against `/api/v1/push` and
`/api/v1/pull`.

## 3. Run the tests

```bash
source .venv/bin/activate
pytest -q
```

What the suite covers:

- `tests/test_merge.py` — timestamp/decimal normalization, cycle-winner and
  history-union rules (spec §6)
- `tests/test_api.py` — 401s, two-machine convergence, idempotent re-push,
  newer-cycle-wins (spec §8, §12)
- `tests/test_backup.py` — zip round-trip, app-style import, bad
  manifest/product rejection (spec §7)

A fast syntax-only check without dependencies:

```bash
python3 -m py_compile app/*.py tests/*.py
```

## 4. Manual web-UI checklist

Automated tests don't cover the UI; verify by hand:

1. Wrong password on `/login` re-renders with an error.
2. **Tokens** → generate → raw token shown once → paste into a push call.
3. **Machines** shows the device as Active after a push/pull.
4. **Data** shows bounds, counts, and the last-20 table.
5. **Backup** → export, unzip (expect exactly `manifest.json`,
   `settings.json`, `usage-samples.json`), then re-import and confirm the
   summary counts.

## 5. Build and run the Docker container

```bash
docker build -t cursorpace-sync .
docker run --rm -p 8080:8080 \
  -e ADMIN_PASSWORD=change-me \
  -e SECRET_KEY=long-random-string \
  -v sync-data:/data \
  cursorpace-sync
```

Verify:

```bash
curl http://127.0.0.1:8080/healthz   # {"status":"ok"}
docker inspect --format='{{json .State.Health.Status}}' <container>
```

Persistence check: push data, `docker stop` + `docker start` (same volume),
pull again — samples, cycles, and tokens must survive.

Or use Compose (see `docker-compose.yml`):

```bash
docker compose up --build -d
docker compose logs -f sync
```

## Troubleshooting

- `No module named pip` on minimal Ubuntu images: `apt-get install -y python3-venv python3-pip`,
  or create the venv with `python3 -m venv --without-pip` and bootstrap via
  `https://bootstrap.pypa.io/get-pip.py`.
- `401 {"detail": "Invalid or missing API token"}`: wrong/revoked token or
  missing `Authorization: Bearer` header. Tokens are `sha256`-hashed at rest;
  revocation takes effect immediately.
- Sessions lost on restart: you didn't set `SECRET_KEY` (a random one is
  generated per boot with a warning).
- `curl` of `/` returns 303: expected — unauthenticated browsers
  redirect to `/login`.
