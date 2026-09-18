# Changelog

All notable changes to CursorPace Sync Server will be documented in this file.

Use conventional types (**Added**, **Changed**, **Fixed**, **Removed**), a short **scope** (API, merge, admin UI, Docker, or other subsystem), and a clear description.

Add new entries in the `## [Unreleased]` section. When releasing, move those entries to `## [x.y.z] - YYYY-MM-DD` using `dev/release-new-version-prompt.md`.

## [Unreleased]

- **Added**: docker - Release workflow publishes `ghcr.io/wsj-br/cursorpace-syncserver` and creates the GitHub Release from `./scripts/release.sh`.
- **Added**: scripts - `scripts/clean.sh` removes Python caches, pytest leftovers, and optional local `data/` / `.venv`.
- **Changed**: deps - `pytest` 8.4.1 to 9.0.3.
- **Security**: deps - `python-multipart` 0.0.20 to 0.0.31.
- **Added**: api - `POST /api/v1/push` and `GET /api/v1/pull` merge samples and cycle bounds; `GET /healthz` is unauthenticated.
- **Added**: merge - Canonical UTC timestamps, decimal percentages, first-writer sample union, newest active cycle, and history union by start date.
- **Added**: backup - Export/import of the CursorPace zip (`manifest.json`, `settings.json`, `usage-samples.json`).
- **Added**: tokens - Admin UI to generate and revoke per-machine Bearer tokens.
- **Added**: web - Dashboard, machines, data, and backup pages on a signed session cookie.
- **Added**: docker - Image and Compose service on port `7050` with a `/data` volume for `sync.db`.
- **Added**: config - `.envrc` loads `.env` and `.env.local`; gitignore covers venv, data, secrets, and database files.
- **Added**: web - Relative timestamps, cycle display helpers, and last-N sample views on the data page.
- **Changed**: auth - First login with default password `cursorpace01` must set a new admin password before the rest of the UI.
- **Removed**: docker - `ADMIN_PASSWORD` environment variable from Compose and README.
