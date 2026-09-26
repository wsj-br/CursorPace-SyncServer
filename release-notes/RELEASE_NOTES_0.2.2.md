# CursorPace Sync Server 0.2.2 Release Notes

## Highlights

- The server writes its version and UTC build timestamp to the uvicorn error
  log at startup, so a `docker logs` check confirms which image is running.
- Docker healthcheck probes to `GET /healthz` are omitted from the access log.
- Multi-arch release images (`linux/amd64` and `linux/arm64`) are built on
  native GitHub-hosted runners instead of QEMU.

## Why this release matters

Operators can tell which build is serving a host without opening the admin
UI, and healthcheck traffic no longer fills the access log. ARM64 images are
built natively rather than emulated.

## Detailed Changes

See [`dev/CHANGELOG.md`](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/CHANGELOG.md#022---2026-09-26) for the full list of changes in this release.

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
CURSORPACE_VERSION=0.2.2
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
