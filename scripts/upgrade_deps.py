#!/usr/bin/env python3
"""Upgrade pinned packages in requirements.txt.

Usage:
  ./scripts/upgrade-deps                 # every pin to current PyPI
  ./scripts/upgrade-deps --alerts        # packages with open Dependabot alerts
  ./scripts/upgrade-deps anyio httpx
  ./scripts/upgrade-deps --set anyio==4.14.2
  ./scripts/upgrade-deps --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent
REQUIREMENTS_NAME = "requirements.txt"
CHANGELOG_NAME = Path("dev") / "CHANGELOG.md"
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(.*)$")
SET_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(.*)$")
UNRELEASED = "## [Unreleased]"
PYPI_TIMEOUT_SEC = 20


@dataclass(frozen=True)
class Pin:
    name: str
    version: str
    raw: str


@dataclass(frozen=True)
class Bump:
    name: str
    old: str
    new: str
    reason: str


class UpgradeError(Exception):
    pass


def parse_requirements(text: str) -> list[Pin]:
    pins: list[Pin] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = PIN_RE.match(stripped)
        if match is None:
            raise UpgradeError(f"Unsupported requirements line: {raw}")
        pins.append(Pin(name=match.group(1), version=match.group(2), raw=raw))
    return pins


def version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            raise UpgradeError(f"Unsupported version: {value}")
        parts.append(int(digits))
    if not parts:
        raise UpgradeError(f"Unsupported version: {value}")
    return tuple(parts)


def version_gte(left: str, right: str) -> bool:
    left_key = version_key(left)
    right_key = version_key(right)
    width = max(len(left_key), len(right_key))
    left_key += (0,) * (width - len(left_key))
    right_key += (0,) * (width - len(right_key))
    return left_key >= right_key


def normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()


def pin_by_name(pins: list[Pin], name: str) -> Pin | None:
    wanted = normalize_name(name)
    for pin in pins:
        if normalize_name(pin.name) == wanted:
            return pin
    return None


def apply_bumps(text: str, bumps: list[Bump]) -> str:
    targets = {normalize_name(bump.name): bump.new for bump in bumps}
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        match = PIN_RE.match(stripped)
        if match is None:
            lines.append(raw)
            continue
        key = normalize_name(match.group(1))
        if key in targets:
            lines.append(f"{match.group(1)}=={targets[key]}")
        else:
            lines.append(raw)
    if text.endswith("\n"):
        return "\n".join(lines) + "\n"
    return "\n".join(lines)


def changelog_bullet(bump: Bump) -> str:
    kind = "Security" if bump.reason == "alert" else "Changed"
    return f"- **{kind}**: deps - `{bump.name}` {bump.old} to {bump.new}."


def insert_unreleased_bullets(text: str, bullets: list[str]) -> str:
    if UNRELEASED not in text:
        raise UpgradeError(f"{CHANGELOG_NAME} is missing {UNRELEASED}.")
    to_add = [bullet for bullet in bullets if bullet not in text]
    if not to_add:
        return text
    block = "\n".join(to_add) + "\n"
    needle = f"{UNRELEASED}\n\n"
    if needle in text:
        return text.replace(needle, f"{needle}{block}", 1)
    return text.replace(UNRELEASED, f"{UNRELEASED}\n\n{block}", 1)


def parse_set_spec(spec: str) -> tuple[str, str]:
    match = SET_RE.match(spec.strip())
    if match is None:
        raise UpgradeError(f"Invalid --set value: {spec}")
    return match.group(1), match.group(2)


def parse_dependabot_alerts(payload: object) -> dict[str, str]:
    if not isinstance(payload, list):
        raise UpgradeError("Dependabot alerts response must be a JSON array.")
    patched: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("state") != "open":
            continue
        dependency = item.get("dependency")
        if not isinstance(dependency, dict):
            continue
        package = dependency.get("package")
        if not isinstance(package, dict):
            continue
        if str(package.get("ecosystem", "")).lower() not in {"", "pip"}:
            continue
        name = package.get("name")
        if not isinstance(name, str) or not name:
            continue
        vuln = item.get("security_vulnerability")
        if not isinstance(vuln, dict):
            continue
        first = vuln.get("first_patched_version")
        if not isinstance(first, dict):
            continue
        version = first.get("identifier")
        if not isinstance(version, str) or not version:
            continue
        key = normalize_name(name)
        current = patched.get(key)
        if current is None or version_gte(version, current):
            patched[key] = version
    return patched


def fetch_pypi_version(name: str) -> str:
    url = f"https://pypi.org/pypi/{name}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "cursorpace-upgrade-deps"})
    try:
        with urllib.request.urlopen(request, timeout=PYPI_TIMEOUT_SEC) as response:
            data = json.load(response)
    except urllib.error.URLError as exc:
        raise UpgradeError(f"Could not query PyPI for {name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UpgradeError(f"Invalid PyPI response for {name}") from exc
    version = data.get("info", {}).get("version")
    if not isinstance(version, str) or not version:
        raise UpgradeError(f"PyPI did not return a version for {name}")
    version_key(version)
    return version


def github_repo_slug(remote_url: str) -> str:
    url = remote_url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@github.com:"):
        return url[len("git@github.com:") :]
    if url.startswith("ssh://git@github.com/"):
        return url[len("ssh://git@github.com/") :]
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc == "github.com":
        return parsed.path.lstrip("/")
    raise UpgradeError(f"Unsupported git remote: {remote_url}")


def fetch_dependabot_alerts(repo: str) -> dict[str, str]:
    try:
        completed = subprocess.run(
            ["gh", "api", "--paginate", f"repos/{repo}/dependabot/alerts"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise UpgradeError("Missing required command: gh") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "gh api failed"
        raise UpgradeError(detail)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise UpgradeError("Invalid Dependabot alerts JSON from gh.") from exc
    return parse_dependabot_alerts(payload)


def origin_repo_slug(root: Path) -> str:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise UpgradeError("Remote 'origin' not configured.")
    return github_repo_slug(completed.stdout)


def select_bumps(
    pins: list[Pin],
    *,
    names: list[str],
    alerts_only: bool,
    sets: dict[str, str],
    alerts: dict[str, str],
    latest_for: Callable[[str], str],
) -> list[Bump]:
    selected: list[Pin]
    if names:
        selected = []
        for name in names:
            pin = pin_by_name(pins, name)
            if pin is None:
                raise UpgradeError(f"{name} is not pinned in {REQUIREMENTS_NAME}")
            selected.append(pin)
        if alerts_only:
            selected = [pin for pin in selected if normalize_name(pin.name) in alerts]
    elif alerts_only:
        selected = [pin for pin in pins if normalize_name(pin.name) in alerts]
    elif sets:
        selected = []
        for name in sets:
            pin = pin_by_name(pins, name)
            if pin is None:
                raise UpgradeError(f"{name} is not pinned in {REQUIREMENTS_NAME}")
            selected.append(pin)
    else:
        selected = list(pins)

    bumps: list[Bump] = []
    for pin in selected:
        key = normalize_name(pin.name)
        reason = "pypi"
        if key in sets:
            target = sets[key]
            reason = "set"
        else:
            target = latest_for(pin.name)
        patched = alerts.get(key)
        if patched is not None:
            if not version_gte(target, patched):
                target = patched
            reason = "alert"
        if pin.version == target:
            continue
        if not version_gte(target, pin.version) and reason != "set":
            continue
        bumps.append(Bump(name=pin.name, old=pin.version, new=target, reason=reason))
    return bumps


def format_plan(bumps: list[Bump]) -> str:
    if not bumps:
        return "No requirement pins to upgrade."
    lines = ["Planned upgrades:"]
    for bump in bumps:
        lines.append(f"  {bump.name} {bump.old} -> {bump.new} ({bump.reason})")
    return "\n".join(lines)


def resolve_python(root: Path) -> Path:
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return venv_python
    return Path(sys.executable)


def os_fspath(path: Path) -> str:
    return path.as_posix() if sys.platform != "win32" else str(path)


def install_requirements(root: Path) -> None:
    python = resolve_python(root)
    completed = subprocess.run(
        [os_fspath(python), "-m", "pip", "install", "-q", "-r", REQUIREMENTS_NAME],
        cwd=root,
        check=False,
    )
    if completed.returncode != 0:
        raise UpgradeError("pip install -r requirements.txt failed.")


def run_pytest(root: Path) -> None:
    python = resolve_python(root)
    completed = subprocess.run(
        [os_fspath(python), "-m", "pytest", "-q"],
        cwd=root,
        check=False,
    )
    if completed.returncode != 0:
        raise UpgradeError("pytest failed after upgrading pins.")


def can_verify(root: Path) -> bool:
    return (root / "app").is_dir() and (root / "tests").is_dir()


def apply_and_verify(
    root: Path,
    bumps: list[Bump],
    *,
    update_changelog: bool,
    install: bool,
    test: bool,
) -> None:
    requirements_path = root / REQUIREMENTS_NAME
    changelog_path = root / CHANGELOG_NAME
    original_requirements = requirements_path.read_text(encoding="utf-8")
    original_changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else None
    try:
        requirements_path.write_text(apply_bumps(original_requirements, bumps), encoding="utf-8")
        if update_changelog:
            if original_changelog is None:
                raise UpgradeError(f"{CHANGELOG_NAME} not found.")
            bullets = [changelog_bullet(bump) for bump in bumps]
            changelog_path.write_text(
                insert_unreleased_bullets(original_changelog, bullets),
                encoding="utf-8",
            )
        if install and can_verify(root):
            install_requirements(root)
        if test and can_verify(root):
            run_pytest(root)
    except Exception:
        requirements_path.write_text(original_requirements, encoding="utf-8")
        if original_changelog is not None:
            changelog_path.write_text(original_changelog, encoding="utf-8")
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upgrade pinned packages in requirements.txt from PyPI or Dependabot alerts."
    )
    parser.add_argument(
        "packages",
        nargs="*",
        help="Limit the upgrade to these requirement names (default: all pins).",
    )
    parser.add_argument(
        "--alerts",
        action="store_true",
        help="Only upgrade packages that have open GitHub Dependabot alerts.",
    )
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="NAME==VERSION",
        help="Pin a package to an explicit version instead of querying PyPI.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned bumps and leave files unchanged.",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Do not run pytest after writing pins.",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Do not run pip install after writing pins.",
    )
    parser.add_argument(
        "--no-changelog",
        action="store_true",
        help="Do not add Unreleased bullets to dev/CHANGELOG.md.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root (default: parent of this script).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    requirements_path = root / REQUIREMENTS_NAME
    if not requirements_path.is_file():
        raise UpgradeError(f"{REQUIREMENTS_NAME} not found in {root}")

    pins = parse_requirements(requirements_path.read_text(encoding="utf-8"))
    sets = {normalize_name(name): version for name, version in (parse_set_spec(spec) for spec in args.sets)}
    alerts: dict[str, str] = {}
    if args.alerts:
        alerts = fetch_dependabot_alerts(origin_repo_slug(root))

    def latest_for(name: str) -> str:
        key = normalize_name(name)
        if key in sets:
            return sets[key]
        return fetch_pypi_version(name)

    bumps = select_bumps(
        pins,
        names=list(args.packages),
        alerts_only=args.alerts,
        sets=sets,
        alerts=alerts,
        latest_for=latest_for,
    )
    print(format_plan(bumps))
    if not bumps or args.dry_run:
        return 0
    apply_and_verify(
        root,
        bumps,
        update_changelog=not args.no_changelog,
        install=not args.no_install,
        test=not args.no_test,
    )
    print(f"Updated {REQUIREMENTS_NAME}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpgradeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
