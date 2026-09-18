#!/usr/bin/env bash
# Start a GitHub release from HEAD using the version in app/version.py.
#
# Reads VERSION from app/version.py and requires
# release-notes/RELEASE_NOTES_<version>.md. Then:
#   - Deletes an existing GitHub release and/or tag for v<version> if present
#   - Creates an annotated tag at HEAD and pushes it to origin
#   - Lets the Release workflow build the Docker image, publish it to GHCR,
#     and create the GitHub Release
#
# Usage:
#   ./scripts/release.sh
#   ./scripts/release.sh --dry-run
#   ./scripts/release.sh --no-verify-clean
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=0
VERIFY_CLEAN=1

usage() {
  cat <<'EOF'
Usage: ./scripts/release.sh [options]

  --dry-run           Validate and print planned steps; no deletes, tag, push, or release.
  --no-verify-clean   Allow a dirty git working tree.
  -h, --help          Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-verify-clean)
      VERIFY_CLEAN=0
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

fail() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "Missing required command: $name"
  fi
  if ! "$name" --version >/dev/null 2>&1; then
    fail "Missing required command: $name"
  fi
}

get_app_version() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    fail "app/version.py not found in repository root."
  fi
  local value
  value="$(sed -n 's/^VERSION = "\([^"]*\)"/\1/p' "$path" | head -n 1 | tr -d '[:space:]')"
  if [[ -z "$value" ]]; then
    fail "Could not find VERSION in app/version.py"
  fi
  printf '%s\n' "$value"
}

convert_to_repo_web_url() {
  local url="$1"
  url="$(printf '%s' "$url" | tr -d '[:space:]')"
  url="${url%.git}"
  case "$url" in
    git@github.com:*)
      printf 'https://github.com/%s\n' "${url#git@github.com:}"
      ;;
    https://github.com/*)
      printf 'https://github.com/%s\n' "${url#https://github.com/}"
      ;;
    ssh://git@github.com/*)
      printf 'https://github.com/%s\n' "${url#ssh://git@github.com/}"
      ;;
    *)
      printf '%s\n' "$url"
      ;;
  esac
}

require_command git
require_command gh

if [[ "$(git rev-parse --is-inside-work-tree 2>/dev/null || true)" != "true" ]]; then
  fail 'Not inside a git repository.'
fi

if ! gh auth status >/dev/null 2>&1; then
  fail 'GitHub CLI is not authenticated. Run: gh auth login'
fi

VERSION="$(get_app_version "$REPO_ROOT/app/version.py")"
TAG="v$VERSION"
NOTES_FILE="release-notes/RELEASE_NOTES_${VERSION}.md"
NOTES_PATH="$REPO_ROOT/$NOTES_FILE"

if [[ ! -f "$NOTES_PATH" ]]; then
  fail "Release notes file not found: $NOTES_FILE"
fi

if [[ "$VERIFY_CLEAN" -eq 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    fail 'Working tree is not clean. Commit/stash changes or run with --no-verify-clean'
  fi
fi

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE_URL" ]]; then
  fail "Remote 'origin' not configured."
fi
REPO_URL="$(convert_to_repo_web_url "$REMOTE_URL")"
IMAGE="$(printf 'ghcr.io/%s\n' "${REPO_URL#https://github.com/}" | tr '[:upper:]' '[:lower:]')"

HEAD_COMMIT="$(git rev-parse HEAD)"

remote_tag_exists() {
  local out
  out="$(git ls-remote origin "refs/tags/$TAG" 2>/dev/null || true)"
  [[ -n "$(printf '%s' "$out" | tr -d '[:space:]')" ]]
}

local_tag_exists() {
  git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1
}

release_exists() {
  gh release view "$TAG" >/dev/null 2>&1
}

set_release_tag_at_head() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] HEAD commit: $HEAD_COMMIT"
    if release_exists; then
      echo "[dry-run] Would delete GitHub release: $TAG"
    fi
    if remote_tag_exists; then
      echo "[dry-run] Would delete remote tag: origin $TAG"
    fi
    if local_tag_exists; then
      echo "[dry-run] Would delete local tag: $TAG"
    fi
    echo "[dry-run] Would create annotated tag $TAG at HEAD and push to origin."
    return 0
  fi

  if release_exists; then
    echo "Deleting existing GitHub release $TAG (and its tag on the remote)..."
    gh release delete "$TAG" --yes --cleanup-tag
  elif remote_tag_exists; then
    echo "Deleting remote tag $TAG..."
    git push origin ":refs/tags/$TAG"
  fi

  if local_tag_exists; then
    echo "Deleting local tag $TAG..."
    git tag -d "$TAG"
  fi

  echo "Creating annotated tag $TAG at HEAD ($HEAD_COMMIT)..."
  git tag -a "$TAG" -m "Release $TAG" HEAD

  echo "Pushing tag $TAG to origin..."
  git push origin "refs/tags/$TAG"
}

set_release_tag_at_head

echo 'Release inputs:'
echo "  Tag:        $TAG"
echo "  Title:      $TAG"
echo "  Notes file: $NOTES_FILE"
echo "  Image:      $IMAGE:$VERSION"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] Pushing $TAG would trigger the Release workflow."
  exit 0
fi

echo "Release tag pushed successfully: $TAG"
echo ''
echo "The Release workflow will run tests, publish $IMAGE:$VERSION to GHCR, and create $TAG."
echo "See progress at $REPO_URL/actions"
echo ''
