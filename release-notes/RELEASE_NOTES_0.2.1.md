# CursorPace Sync Server 0.2.1 Release Notes

## Highlights

- Within the current billing cycle, push and dataset import now drop samples
  whose `cursor` or `other` percentage goes backwards, and delete any already
  stored dip so the shared dataset stays monotonically non-decreasing.

## Why this release matters

A later sample that reports a lower usage percentage no longer leaves a dip
in the canonical dataset. Machines that push or import overlapping cycle data
converge on the same non-decreasing series.

## Detailed Changes

See [`dev/CHANGELOG.md`](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/CHANGELOG.md#021---2026-09-26) for the full list of changes in this release.

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
CURSORPACE_VERSION=0.2.1
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
