"""View-only formatting helpers for the admin UI. No I/O, no merge rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _clock_label(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}, {dt:%H:%M}"


def parse_utc_instant(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_utc_iso(raw: str | None) -> str:
    """Machine-readable UTC instant for <time datetime>."""
    dt = parse_utc_instant(raw)
    if dt is None:
        return (raw or "").strip()
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def format_utc_display(raw: str | None) -> str:
    """Friendly UTC fallback, e.g. '18 Sep 2026, 14:48 UTC'."""
    dt = parse_utc_instant(raw)
    if dt is None:
        return (raw or "").strip()
    return f"{_clock_label(dt)} UTC"


def format_relative(raw: str | None, now: datetime | None = None) -> str:
    dt = parse_utc_instant(raw)
    if dt is None:
        return "Never"
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 45:
        return "just now"
    minutes = max(1, seconds // 60)
    if minutes < 60:
        return "1 minute ago" if minutes == 1 else f"{minutes} minutes ago"
    hours = seconds // 3600
    if hours < 24:
        return "1 hour ago" if hours == 1 else f"{hours} hours ago"
    days = seconds // 86400
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return format_utc_display(raw)


def format_cycle_display(raw: str | None) -> str:
    """Account wall-clock time; do not convert to the viewer's timezone."""
    if not raw:
        return ""
    text = raw.strip()
    if not text:
        return ""
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return text
    label = _clock_label(dt)
    if dt.tzinfo is None:
        return label
    offset = dt.utcoffset()
    if offset is None:
        return label
    if offset == timedelta(0):
        return f"{label} UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    suffix = f"UTC{sign}{hours}"
    if minutes:
        suffix += f":{minutes:02d}"
    return f"{label} ({suffix})"


def status_modifier(status: str) -> str:
    return {
        "Active": "active",
        "Recent": "recent",
        "Stale": "stale",
        "Never": "never",
    }.get(status, "never")


def format_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)
