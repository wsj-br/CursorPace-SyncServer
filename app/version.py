"""Application release metadata shown in the UI footer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION_FILE = Path(__file__).resolve()
BUILD_STAMP_FILE = VERSION_FILE.with_name("BUILD_TIMESTAMP")

# set-version script updates these two assignments.
VERSION = "0.2.0"
BUILD_TIMESTAMP = "2026-09-20T10:13:14Z"
GITHUB_URL = "https://github.com/wsj-br/CursorPace-SyncServer"
LICENSE_URL = f"{GITHUB_URL}/blob/main/LICENSE"
COPYRIGHT = "© 2026 Waldemar Scudeller Jr."

_VERSION_ASSIGN = re.compile(r'^(VERSION = ")[^"]*(")$', re.MULTILINE)
_BUILD_ASSIGN = re.compile(r'^(BUILD_TIMESTAMP = ")[^"]*(")$', re.MULTILINE)
_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    build_timestamp: str
    github_url: str
    license_url: str
    copyright: str


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_version(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    if not _VERSION_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"invalid version {value!r}; expected semver like 1.2.3"
        )
    return cleaned


def write_version(
    version: str,
    *,
    build_timestamp: str | None = None,
    path: Path = VERSION_FILE,
) -> ReleaseInfo:
    """Rewrite VERSION and BUILD_TIMESTAMP assignments in version.py."""
    new_version = validate_version(version)
    stamp = build_timestamp or utc_now_stamp()
    text = path.read_text(encoding="utf-8")
    updated, n_version = _VERSION_ASSIGN.subn(rf"\g<1>{new_version}\2", text, count=1)
    if n_version != 1:
        raise RuntimeError(f"could not find VERSION assignment in {path}")
    updated, n_build = _BUILD_ASSIGN.subn(rf"\g<1>{stamp}\2", updated, count=1)
    if n_build != 1:
        raise RuntimeError(f"could not find BUILD_TIMESTAMP assignment in {path}")
    path.write_text(updated, encoding="utf-8")
    return ReleaseInfo(
        version=new_version,
        build_timestamp=stamp,
        github_url=GITHUB_URL,
        license_url=LICENSE_URL,
        copyright=COPYRIGHT,
    )


def _stamp_from_file() -> str:
    if BUILD_STAMP_FILE.is_file():
        value = BUILD_STAMP_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return ""


def load_release_info() -> ReleaseInfo:
    version = os.environ.get("APP_VERSION", VERSION).strip() or VERSION
    build = (
        os.environ.get("BUILD_TIMESTAMP", "").strip()
        or _stamp_from_file()
        or BUILD_TIMESTAMP
    )
    return ReleaseInfo(
        version=version,
        build_timestamp=build,
        github_url=GITHUB_URL,
        license_url=LICENSE_URL,
        copyright=COPYRIGHT,
    )
