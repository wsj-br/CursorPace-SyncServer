# CursorPace Sync Server 0.2.0 Release Notes

## Highlights

- Export and import a full sync-server snapshot zip (`sync.db` plus the
  session secret) so operators can move or restore an entire deployment.
- Optionally merge when importing a CursorPace app backup zip, instead of
  always replacing samples and cycle metadata.

## Why this release matters

Operators can back up and restore the whole sync server, and can import
desktop app backups without discarding data already stored on the server.

## Detailed Changes

See [`dev/CHANGELOG.md`](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/CHANGELOG.md#020---2026-09-20) for the full list of changes in this release.

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
CURSORPACE_VERSION=0.2.0
SYNC_PORT=7050
```

`CURSORPACE_VERSION` defaults to `latest` when omitted. Pull and start the
server:

```bash
docker compose -f cursorpace-syncserver.yml pull
docker compose -f cursorpace-syncserver.yml up -d
docker compose -f cursorpace-syncserver.yml ps
```

The named volume keeps the database, tokens, samples, cycle data, and session
secret across updates. Open `http://server:7050/login` (or the configured
`SYNC_PORT`) and sign in with `cursorpace01`. The first boot requires choosing
a new admin password.

---

## Documentation

- [README](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/README.md) — first run, env vars, API summary, tokens, backup.
- [Development](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/DEVEL.md) — venv, tests, Docker, troubleshooting.

---

## License

MIT © [Waldemar Scudeller Jr.](https://github.com/wsj-br/CursorPace-SyncServer)
