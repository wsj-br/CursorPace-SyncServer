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
./scripts/dev.sh
```

`scripts/dev.sh` uses `$DATA_DIR` and `$PORT` from the environment (or
`.env` / `.env.local`), defaulting to `./data` and `7050`, and enables
uvicorn `--reload`.

To change the version shown in the UI footer:

```bash
./scripts/set-version          # current version and build timestamp
./scripts/set-version 1.2.3
```

Then open `http://127.0.0.1:7050/login` and sign in with `cursorpace01`.
The first login asks you to choose a new admin password.

| Env var | Meaning |
|---|---|
| `DATA_DIR` | Directory holding `sync.db` and `.secret_key` (default `/data`) |
| `PORT` | Listen port (default `7050`) |

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
2. First login with `cursorpace01` redirects to `/change-password`; the rest of
   the UI stays blocked until a new password is saved.
3. **Tokens** → generate → raw token shown once → paste into a push call.
4. **Machines** shows the device as Active after a push/pull.
5. **Data** shows bounds, counts, and the last-20 table.
6. **Backup** → export, unzip (expect exactly `manifest.json`,
   `settings.json`, `usage-samples.json`), then re-import and confirm the
   summary counts.

## 5. Build and run the Docker container

```bash
docker build -t cursorpace-sync .
docker run --rm -p 7050:7050 \
  -v sync-data:/data \
  cursorpace-sync
```

Verify:

```bash
curl http://127.0.0.1:7050/healthz   # {"status":"ok"}
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
- Sessions lost on restart: `$DATA_DIR/.secret_key` was deleted. A new key is
  created on the next boot and existing admin cookies no longer verify.
- `curl` of `/` returns 303: expected — unauthenticated browsers
  redirect to `/login`.
