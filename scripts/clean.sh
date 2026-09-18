#!/usr/bin/env bash
# Remove generated Python, test, and leftover runtime artifacts from the repository.
#
# Usage:
#   ./scripts/clean.sh
#   ./scripts/clean.sh --dry-run
#   ./scripts/clean.sh --purge-data
#   ./scripts/clean.sh --purge-venv
#   ./scripts/clean.sh --no-purge-temp
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PURGE_DATA=0
PURGE_VENV=0
PURGE_USER_TEMP=1
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./scripts/clean.sh [options]

  --dry-run         Skip deletions; print paths that would be removed.
  --purge-data      Also remove the local data directory (sync.db, .secret_key).
  --purge-venv      Also remove .venv.
  --no-purge-temp   Keep CursorPace-related files under the user TEMP folder.
  -h, --help        Show this help.

By default removes bytecode, pytest caches, coverage leftovers, temp/log
files, and app/BUILD_TIMESTAMP. Does not touch .env, .env.local, or .git.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --purge-data)
      PURGE_DATA=1
      shift
      ;;
    --purge-venv)
      PURGE_VENV=1
      shift
      ;;
    --no-purge-temp)
      PURGE_USER_TEMP=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
}

load_env_file "$REPO_ROOT/.env"
load_env_file "$REPO_ROOT/.env.local"

is_under_repo() {
  local path="$1"
  case "$path" in
    "$REPO_ROOT"/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_existing_path() {
  local raw="$1"
  local path
  if [[ "$raw" = /* ]]; then
    path="$raw"
  else
    path="$REPO_ROOT/$raw"
  fi
  if [[ -e "$path" ]]; then
    (cd "$path" && pwd)
    return 0
  fi
  return 1
}

remove_generated_path() {
  local path="$1"
  if [[ ! -e "$path" && ! -L "$path" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] $path"
    return 0
  fi
  echo "  $path"
  rm -rf "$path"
}

echo "Cleaning CursorPace Sync Server..."

if [[ "$PURGE_VENV" -eq 1 ]]; then
  remove_generated_path "$REPO_ROOT/.venv"
fi

remove_generated_path "$REPO_ROOT/app/BUILD_TIMESTAMP"

if [[ "$PURGE_DATA" -eq 1 ]]; then
  remove_generated_path "$REPO_ROOT/data"
  if [[ -n "${DATA_DIR:-}" ]]; then
    if resolved="$(resolve_existing_path "$DATA_DIR")"; then
      if [[ "$resolved" != "$REPO_ROOT/data" ]]; then
        if is_under_repo "$resolved"; then
          remove_generated_path "$resolved"
        else
          echo "Warning: refusing to purge DATA_DIR outside the repository: $resolved" >&2
        fi
      fi
    fi
  fi
fi

while IFS= read -r -d '' file; do
  remove_generated_path "$file"
done < <(
  find "$REPO_ROOT" \
    \( -name .git -o -name .venv \) -prune -o \
    \( -type d \( \
         -name __pycache__ -o \
         -name .pytest_cache -o \
         -name htmlcov \
       \) -print0 -prune \) -o \
    -type f \( \
      -name '*.pyc' -o \
      -name '*.pyo' -o \
      -name '*.tmp' -o \
      -name '*.log' -o \
      -name '.coverage' -o \
      -name '.coverage.*' \
    \) -print0 2>/dev/null
)

if [[ "$PURGE_USER_TEMP" -eq 1 ]]; then
  temp_root="${TMPDIR:-${TEMP:-${TMP:-/tmp}}}"
  temp_root="${temp_root%/}"
  if [[ -d "$temp_root" ]]; then
    shopt -s nullglob
    for entry in "$temp_root"/*CursorPace*; do
      remove_generated_path "$entry"
    done
    shopt -u nullglob
  fi
fi

echo 'Workspace cleanup complete.'
