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
     - `## Install` — How to run this version with Docker Compose or `docker build` / `docker run`, a persistent `/data` volume, and the listen port (default `7050`). Mention first-run login at `/login` with the default password `cursorpace01` and the required password change. Do not invent a published registry image name unless this repo already documents one.
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

Build and run with a persistent `/data` volume:

```bash
docker compose up --build -d
```

Or `docker build -t cursorpace-sync .` and `docker run` with `-p 7050:7050` and `-v <volume>:/data`. Open `http://server:7050/login`. The first boot uses the default admin password `cursorpace01`; you must set a new password before tokens or backup are available.

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
