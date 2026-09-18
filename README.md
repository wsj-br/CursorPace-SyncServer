# CursorPace Sync Server

Lightweight server letting multiple CursorPace desktop instances share usage
data.

Published image: `ghcr.io/wsj-br/cursorpace-syncserver` (version tags plus
`latest`).

## Production deployment

`production.yml` runs the published image without building locally, keeps the
SQLite database and session key in a named `/data` volume, and restarts the
container after a host or Docker restart.

From the deployment directory on the production server, download the Compose
file:

```bash
curl -fsSL https://raw.githubusercontent.com/wsj-br/CursorPace-SyncServer/main/production.yml \
  -o cursorpace-syncserver.yml
```

Optionally create `.env` in that directory to pin a release and/or change the
host port:

```dotenv
CURSORPACE_VERSION=1.2.3
SYNC_PORT=7050
```

`CURSORPACE_VERSION` defaults to `latest`; use a release tag such as `1.2.3`
for reproducible upgrades. `SYNC_PORT` is the host port and defaults to
`7050`.

Pull and start the server:

```bash
docker compose -f cursorpace-syncserver.yml pull
docker compose -f cursorpace-syncserver.yml up -d
docker compose -f cursorpace-syncserver.yml ps
```

To update an existing deployment, set the desired `CURSORPACE_VERSION` in
`.env` and run the same commands. The named volume keeps `sync.db`, tokens,
samples, cycle data, and the session secret across updates.

The server exposes plain HTTP for a trusted LAN. Open
`http://server:7050/login` (or the configured `SYNC_PORT`) and sign in with
the default password `cursorpace01`. You must choose a new admin password
immediately.

In **Tokens**, create one token per machine and copy each raw token when it is
shown. In each CursorPace app's Settings, set the sync URL to
`http://server:7050` and paste that machine's token. Use the configured port
if `SYNC_PORT` is not `7050`.

## Environment variables

| Var | Required | Default | Meaning |
|---|---|---|---|
| `CURSORPACE_VERSION` | no | `latest` | Production Compose image tag. Pin a release tag for upgrades. |
| `SYNC_PORT` | no | `7050` | Production Compose host port. |
| `DATA_DIR` | no | `/data` | SQLite file `sync.db` and session file `.secret_key` live here; keep as a volume. |
| `PORT` | no | `7050` | Container listen port. |

The first boot stores a hash of the default admin password `cursorpace01`.
A random session secret is written to `$DATA_DIR/.secret_key` (mode `0600`)
if that file is missing.

## API summary

- `GET /healthz` → `{"status": "ok"}` (no auth).
- `POST /api/v1/push` with `Authorization: Bearer <token>` merges samples +
  cycle bounds (spec §6.3). Max 50,000 samples per request.
- `GET /api/v1/pull` with `Authorization: Bearer <token>` returns the full
  canonical state (spec §6.4).

## Backup / restore

**Backup** page → **Export** downloads `cursorpace-backup-<stamp>.zip`
(`manifest.json`, `settings.json`, `usage-samples.json`).
**Import** accepts app- or server-produced zips and replaces the canonical
dataset in one transaction.

## Development

Local setup, tests, image builds, and release workflows are documented in
[`dev/DEVEL.md`](dev/DEVEL.md).
