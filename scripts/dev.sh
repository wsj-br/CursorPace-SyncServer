#!/usr/bin/env bash
# Run the sync server locally with auto-reload.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
}

load_env_file "$ROOT/.env"
load_env_file "$ROOT/.env.local"

export DATA_DIR="${DATA_DIR:-$ROOT/data}"
export PORT="${PORT:-7050}"
export HOST="${HOST:-127.0.0.1}"

mkdir -p "$DATA_DIR"

if [[ -x "$ROOT/.venv/bin/uvicorn" ]]; then
  UVICORN="$ROOT/.venv/bin/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
  UVICORN="$(command -v uvicorn)"
else
  echo "uvicorn not found. Create a venv and run: pip install -r requirements.txt" >&2
  exit 1
fi

echo "CursorPace Sync (devel)  http://${HOST}:${PORT}  DATA_DIR=${DATA_DIR}"
exec "$UVICORN" app.main:app --reload --host "$HOST" --port "$PORT"
