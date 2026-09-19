# CursorPace Sync Server 0.1.1 Release Notes

## Highlights

- Sync multiple CursorPace desktop instances through the `/api/v1/push` and
  `/api/v1/pull` endpoints, with canonical timestamps, decimal percentages,
  deterministic sample merging, and cycle metadata convergence.
- Manage per-machine Bearer tokens and inspect machines, usage data, and
  backups from the signed-cookie admin UI.
- Export and import the CursorPace backup format, with dataset replacement
  performed transactionally.
- Run the server as a persistent Docker deployment on port `7050`, including
  the published GHCR image, a production Compose configuration, and
  restart-safe `/data` storage.
- Refresh the runtime and test dependencies, including security-related
  updates.

## Why this release matters

Operators can give multiple CursorPace clients one canonical usage dataset
while keeping tokens, cycle data, backups, and the admin session state
persistent across container restarts.

## Detailed Changes

See [`dev/CHANGELOG.md`](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/CHANGELOG.md#011---2026-09-19) for the full list of changes in this release.

---

## Install

Use the production Compose file to run the published image without building
locally:

```bash
curl -fsSL https://raw.githubusercontent.com/wsj-br/CursorPace-SyncServer/main/production.yml \
  -o cursorpace-syncserver.yml
```

Create `.env` in the same directory to pin this release and optionally change
the host port:

```dotenv
CURSORPACE_VERSION=0.1.1
SYNC_PORT=7050
```

`CURSORPACE_VERSION` defaults to `latest` when omitted. Pull and start the
server:

```bash
docker compose -f cursorpace-syncserver.yml pull
docker compose -f cursorpace-syncserver.yml up -d
docker compose -f cursorpace-syncserver.yml ps
```

The named volume keeps `sync.db`, tokens, samples, cycle data, and the session
secret across updates. The server exposes plain HTTP for a trusted LAN. The
default host port is `7050`; use the configured `SYNC_PORT` in the URL when it
is different.

Open `http://server:7050/login` (or the configured port) and sign in with the
default password `cursorpace01`. You must choose a new admin password
immediately.

---

## Documentation

- [README](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/README.md) — first run, environment variables, API summary, tokens, and backup.
- [Development](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/DEVEL.md) — virtualenv, tests, Docker, and troubleshooting.

---

## License

MIT © [Waldemar Scudeller Jr.](https://github.com/wsj-br/CursorPace-SyncServer)
