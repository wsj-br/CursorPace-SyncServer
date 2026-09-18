"""Maintainer pin updater: scripts/upgrade-deps."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "upgrade-deps"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import upgrade_deps

SAMPLE_CHANGELOG = """# Changelog

## [Unreleased]

- **Added**: api - existing bullet.
"""


def write_tree(tmp_path: Path, requirements: str, changelog: str | None = None) -> Path:
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")
    if changelog is not None:
        (tmp_path / "dev").mkdir()
        (tmp_path / "dev" / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_parse_requirements_skips_comments():
    pins = upgrade_deps.parse_requirements(
        "# keep\nfastapi==0.116.1\n\nanyio==4.9.0\n"
    )
    assert [(pin.name, pin.version) for pin in pins] == [
        ("fastapi", "0.116.1"),
        ("anyio", "4.9.0"),
    ]


def test_parse_requirements_rejects_unpinned_line():
    with pytest.raises(upgrade_deps.UpgradeError, match="Unsupported"):
        upgrade_deps.parse_requirements("anyio>=4.9.0\n")


def test_version_compare_numeric_segments():
    assert upgrade_deps.version_gte("4.14.2", "4.9.0")
    assert upgrade_deps.version_gte("4.15.1", "4.14.2")
    assert not upgrade_deps.version_gte("4.9.0", "4.14.2")


def test_apply_bumps_rewrites_only_named_pins():
    text = "fastapi==0.116.1\nanyio==4.9.0\n"
    bumped = upgrade_deps.apply_bumps(
        text,
        [upgrade_deps.Bump(name="anyio", old="4.9.0", new="4.14.2", reason="alert")],
    )
    assert bumped == "fastapi==0.116.1\nanyio==4.14.2\n"


def test_insert_unreleased_bullets_is_idempotent():
    bullet = "- **Security**: deps - `anyio` 4.9.0 to 4.14.2."
    once = upgrade_deps.insert_unreleased_bullets(SAMPLE_CHANGELOG, [bullet])
    twice = upgrade_deps.insert_unreleased_bullets(once, [bullet])
    assert once == twice
    assert once.startswith("# Changelog\n\n## [Unreleased]\n\n" + bullet)


def test_parse_dependabot_alerts_keeps_highest_open_patch():
    payload = [
        {
            "state": "open",
            "dependency": {"package": {"name": "anyio", "ecosystem": "pip"}},
            "security_vulnerability": {"first_patched_version": {"identifier": "4.14.2"}},
        },
        {
            "state": "open",
            "dependency": {"package": {"name": "anyio", "ecosystem": "pip"}},
            "security_vulnerability": {"first_patched_version": {"identifier": "4.10.0"}},
        },
        {
            "state": "fixed",
            "dependency": {"package": {"name": "pytest", "ecosystem": "pip"}},
            "security_vulnerability": {"first_patched_version": {"identifier": "9.0.3"}},
        },
    ]
    assert upgrade_deps.parse_dependabot_alerts(payload) == {"anyio": "4.14.2"}


def test_github_repo_slug_accepts_ssh_and_https():
    assert (
        upgrade_deps.github_repo_slug("git@github.com:wsj-br/CursorPace-SyncServer.git")
        == "wsj-br/CursorPace-SyncServer"
    )
    assert (
        upgrade_deps.github_repo_slug("https://github.com/wsj-br/CursorPace-SyncServer.git")
        == "wsj-br/CursorPace-SyncServer"
    )


def test_select_bumps_alerts_uses_patched_floor():
    pins = upgrade_deps.parse_requirements("anyio==4.9.0\npytest==9.0.3\n")
    bumps = upgrade_deps.select_bumps(
        pins,
        names=[],
        alerts_only=True,
        sets={},
        alerts={"anyio": "4.14.2"},
        latest_for=lambda name: {"anyio": "4.13.0", "pytest": "9.1.1"}[name],
    )
    assert [(bump.name, bump.old, bump.new, bump.reason) for bump in bumps] == [
        ("anyio", "4.9.0", "4.14.2", "alert"),
    ]


def test_select_bumps_set_only_does_not_touch_other_pins():
    pins = upgrade_deps.parse_requirements("anyio==4.9.0\npytest==9.0.3\n")
    bumps = upgrade_deps.select_bumps(
        pins,
        names=[],
        alerts_only=False,
        sets={"anyio": "4.14.2"},
        alerts={},
        latest_for=lambda name: pytest.fail(f"unexpected PyPI lookup for {name}"),
    )
    assert [(bump.name, bump.new) for bump in bumps] == [("anyio", "4.14.2")]


def test_cli_set_dry_run_and_write(tmp_path: Path):
    write_tree(tmp_path, "anyio==4.9.0\npytest==9.0.3\n", SAMPLE_CHANGELOG)
    dry = subprocess.run(
        [
            os.fspath(SCRIPT),
            "--root",
            os.fspath(tmp_path),
            "--set",
            "anyio==4.14.2",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "anyio 4.9.0 -> 4.14.2" in dry.stdout
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "anyio==4.9.0\npytest==9.0.3\n"
    )

    written = subprocess.run(
        [
            os.fspath(SCRIPT),
            "--root",
            os.fspath(tmp_path),
            "--set",
            "anyio==4.14.2",
            "--no-install",
            "--no-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert written.returncode == 0
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "anyio==4.14.2\npytest==9.0.3\n"
    )
    changelog = (tmp_path / "dev" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "`anyio` 4.9.0 to 4.14.2." in changelog


def test_cli_unknown_package_fails(tmp_path: Path):
    write_tree(tmp_path, "anyio==4.9.0\n")
    completed = subprocess.run(
        [os.fspath(SCRIPT), "--root", os.fspath(tmp_path), "not-a-dep"],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert "not pinned" in completed.stderr
