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

Pull the versioned image from GitHub Container Registry:

```bash
docker pull ghcr.io/wsj-br/cursorpace-syncserver:0.1.1
docker run --name cp-sync -d -p 7050:7050 \
  -v cp-sync-data:/data \
  ghcr.io/wsj-br/cursorpace-syncserver:0.1.1
```

To follow the latest published release, use the `latest` tag:

```bash
docker pull ghcr.io/wsj-br/cursorpace-syncserver:latest
docker run --name cp-sync -d -p 7050:7050 \
  -v cp-sync-data:/data \
  ghcr.io/wsj-br/cursorpace-syncserver:latest
```

Or use Docker Compose:

```bash
docker compose up --build -d
```

Build and run locally:

```bash
docker build -t cursorpace-sync .
docker run --name cp-sync -d -p 7050:7050 \
  -v cp-sync-data:/data \
  cursorpace-sync
```

Keep `/data` on a persistent volume so `sync.db`, tokens, samples, cycle
metadata, and the session secret survive container replacement. The default
listen port is `7050`.

Open `http://server:7050/login`. The first boot uses the default admin
password `cursorpace01`; you must set a new password before tokens or backup
are available.

---

## Documentation

- [README](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/README.md) — first run, environment variables, API summary, tokens, and backup.
- [Development](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/DEVEL.md) — virtualenv, tests, Docker, and troubleshooting.

---

## License

MIT © [Waldemar Scudeller Jr.](https://github.com/wsj-br/CursorPace-SyncServer)
