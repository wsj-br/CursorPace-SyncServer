Create a new release notes file `release-notes/RELEASE_NOTES_<version>.md` for CursorPace Sync Server using the instructions below. Use it as the GitHub Release description.

**Instructions:**

1. **Read `app/version.py`** and take `VERSION` (`x.y.z`). You can confirm with `./scripts/set-version`. Do not bump the version in this step; it must already be the version being released.
2. **Open `dev/CHANGELOG.md`**.
3. **Copy all entries under the `## [Unreleased]` section** up to (but not including) the next `## [` heading (the last released version). If `[Unreleased]` has no bullets, stop and say there is nothing to release.
4. **Format the new file** according to prior notes in `release-notes/RELEASE_NOTES_x.y.z.md`:
   - Title: `# CursorPace Sync Server <version> Release Notes`
   - Sections:
     - `## Highlights` — Summarize the most important operator-facing changes from the changelog bullets (API, merge, admin UI, Docker). Do not list every change verbatim; write clear summaries for people who run the server.
     - `## Why this release matters` — One or two sentences on the main impact or reason for this release.
     - `## Detailed Changes` — Do not copy changelog bullets. Point to `dev/CHANGELOG.md` on `main` with a fragment for the version heading (for example `[0.1.1] - 2026-09-18` becomes `#011---2026-09-18`).
     - `---`
     - `## Install` — Follow the production deployment documented in `README.md`: explain that `production.yml` runs the published GHCR image without building locally; show downloading it from the `main` branch; show an optional `.env` with `CURSORPACE_VERSION=<version>` and `SYNC_PORT=7050`; explain that omitting `CURSORPACE_VERSION` uses `latest`; show `docker compose -f cursorpace-syncserver.yml pull`, `up -d`, and `ps`; mention the persistent named `/data` volume, the configurable host port, and first-run login at `/login` with the default password `cursorpace01` and required password change. Do not substitute standalone `docker run`, local `docker build`, or the development `docker-compose.yml` workflow unless `README.md` has changed its production deployment instructions.
     - `---`
     - `## Documentation` — Link README and `dev/DEVEL.md` as in the example below. Use the `main` branch on `https://github.com/wsj-br/CursorPace-SyncServer`.
     - `---`
     - `## License` — Same MIT line as prior notes.
     - Do not include a `### Full Changelog` heading or an `[Unreleased]` section.
5. **Update `dev/CHANGELOG.md`**:
   - Move all lines from `[Unreleased]` to a new section with the current version and today's date (`## [x.y.z] - YYYY-MM-DD`).
   - Leave an empty `[Unreleased]` section at the top for future work.

**Example format for the file:**

```markdown
# CursorPace Sync Server 0.1.1 Release Notes

## Highlights

- Briefly state the most important API, merge, admin-UI, or Docker changes.
- Focus on what most directly affects people who run the server or point CursorPace at it.

## Why this release matters

One or two sentences describing the practical impact (for example, "Two machines now converge on one sample set after overlapping pushes, so the desktop apps stay aligned.").

## Detailed Changes

See [`dev/CHANGELOG.md`](https://github.com/wsj-br/CursorPace-SyncServer/blob/main/dev/CHANGELOG.md#011---2026-09-18) for the full list of changes in this release.

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
```

**Summary:**
Ensure the new release notes file matches prior notes, highlights operator-facing changes from the changelog, describes how to run this version, and leaves the changelog ready for the next iteration. Write clearly and concisely for GitHub Release readers.
