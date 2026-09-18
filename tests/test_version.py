"""Release metadata and the set-version helper."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.version import (
    COPYRIGHT,
    GITHUB_URL,
    LICENSE_URL,
    VERSION_FILE,
    load_release_info,
    validate_version,
    write_version,
)


def test_validate_version_accepts_semver():
    assert validate_version("v1.2.3") == "1.2.3"
    assert validate_version("0.1.0-rc.1") == "0.1.0-rc.1"


def test_validate_version_rejects_junk():
    with pytest.raises(ValueError):
        validate_version("latest")


def test_write_version_rewrites_assignments(tmp_path: Path):
    copy = tmp_path / "version.py"
    copy.write_text(VERSION_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    info = write_version("2.0.0", build_timestamp="2026-01-02T03:04:05Z", path=copy)
    text = copy.read_text(encoding="utf-8")
    assert 'VERSION = "2.0.0"' in text
    assert 'BUILD_TIMESTAMP = "2026-01-02T03:04:05Z"' in text
    assert info.version == "2.0.0"
    assert info.build_timestamp == "2026-01-02T03:04:05Z"
    assert info.github_url == GITHUB_URL
    assert info.license_url == LICENSE_URL
    assert info.copyright == COPYRIGHT


def test_load_release_info_prefers_env(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("BUILD_TIMESTAMP", "2020-01-01T00:00:00Z")
    info = load_release_info()
    assert info.version == "9.9.9"
    assert info.build_timestamp == "2020-01-01T00:00:00Z"
    assert info.github_url == GITHUB_URL
    assert info.license_url == LICENSE_URL
    assert info.copyright == COPYRIGHT
    monkeypatch.delenv("APP_VERSION")
    monkeypatch.delenv("BUILD_TIMESTAMP")
    assert load_release_info().version


def test_set_version_show_script():
    from subprocess import run

    shown = run(
        [os.fspath(Path("scripts/set-version"))],
        check=True,
        capture_output=True,
        text=True,
    )
    flagged = run(
        [os.fspath(Path("scripts/set-version")), "--show"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert shown.stdout == flagged.stdout
    parts = shown.stdout.split()
    assert len(parts) == 2
    assert parts[0]
    assert "T" in parts[1]
