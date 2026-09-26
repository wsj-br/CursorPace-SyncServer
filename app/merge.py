"""Pure merge functions (spec section 6). No I/O, no SQL."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


CANONICAL_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now_canonical() -> str:
    return datetime.now(timezone.utc).strftime(CANONICAL_FORMAT)


def normalize_timestamp(raw: str) -> str:
    """Parse any ISO-8601 ts to canonical UTC ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

    Raises ValueError on unparseable input.
    """
    text = raw.strip()
    if not text:
        raise ValueError("empty timestamp")
    candidate = text
    # fromisoformat understands +HH:MM offsets but not trailing Z.
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"unparseable timestamp: {raw!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(CANONICAL_FORMAT)


def normalize_decimal(raw: object) -> str:
    """Validate a percentage decimal and return normalized plain string.

    Accepts numbers or numeric strings. Max 4 fractional digits, non-negative.
    Raises ValueError on invalid input.
    """
    if isinstance(raw, bool):
        raise ValueError(f"invalid decimal: {raw!r}")
    text = str(raw).strip() if not isinstance(raw, str) else raw.strip()
    if not text:
        raise ValueError("empty decimal")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal: {raw!r}") from exc
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"invalid decimal: {raw!r}")
    if value < 0:
        raise ValueError(f"negative decimal: {raw!r}")
    # Max 4 fractional digits: exponent must be >= -4.
    if value.as_tuple().exponent < -4:
        raise ValueError(f"too many fractional digits (max 4): {raw!r}")
    # Strip exponent, keep value as plain string (e.g. 1E+2 -> "100").
    return format(value, "f")


def _parse_utc_instant(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def pick_cycle_start_utc(
    stored: str | None, pushed: str | None
) -> str | None:
    """Keep the latest instant (max) of stored vs pushed (spec 6.3.2)."""
    if stored and pushed:
        stored_norm = normalize_timestamp(stored)
        pushed_norm = normalize_timestamp(pushed)
        return stored_norm if stored_norm >= pushed_norm else pushed_norm
    if pushed:
        return normalize_timestamp(pushed)
    if stored:
        return normalize_timestamp(stored)
    return None


def _parse_local(value: str) -> datetime:
    # Local wall-clock ISO without offset, e.g. 2026-08-15T01:00:00.
    # Be lenient: ignore a trailing Z / offset if present, then compare as
    # naive wall-clock (spec 6.3.3 — machines share one Cursor account).
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"unparseable local datetime: {value!r}") from exc
    return dt.replace(tzinfo=None)


def pick_active_cycle(
    stored: dict[str, str] | None, pushed: dict[str, str] | None
) -> dict[str, str] | None:
    """Newest wins by cycle_start, then next_renewal; tie keeps stored."""
    if stored is None:
        return dict(pushed) if pushed is not None else None
    if pushed is None:
        return dict(stored)
    stored_start = _parse_local(stored["cycle_start"])
    pushed_start = _parse_local(pushed["cycle_start"])
    if pushed_start != stored_start:
        return dict(pushed) if pushed_start > stored_start else dict(stored)
    stored_end = _parse_local(stored["next_renewal"])
    pushed_end = _parse_local(pushed["next_renewal"])
    if pushed_end != stored_end:
        return dict(pushed) if pushed_end > stored_end else dict(stored)
    return dict(stored)


def _history_date_key(entry: dict[str, str]) -> str:
    # Union by cycle_start date part (YYYY-MM-DD).
    return _parse_local(entry["cycle_start"]).date().isoformat()


def filter_monotonic_cycle_samples(
    samples: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Drop in-cycle samples whose cursor or other falls below the last kept row.

    ``samples`` must already be ordered by ``ts`` and limited to the current
    cycle. Equals are kept. Comparison uses ``Decimal`` (no float).
    """
    kept: list[dict[str, str]] = []
    baseline_cursor: Decimal | None = None
    baseline_other: Decimal | None = None
    for sample in samples:
        cursor = Decimal(sample["cursor"])
        other = Decimal(sample["other"])
        if baseline_cursor is not None and baseline_other is not None:
            if cursor < baseline_cursor or other < baseline_other:
                continue
        kept.append(sample)
        baseline_cursor = cursor
        baseline_other = other
    return kept


def reconcile_cycle_samples(
    stored: list[dict[str, str]],
    incoming: list[tuple[str, str, str, str]],
    cycle_start_utc: str | None,
) -> tuple[list[str], list[tuple[str, str, str, str]]]:
    """Plan deletes and inserts so the current cycle is non-decreasing.

    First writer wins per ``ts``. Samples with ``ts < cycle_start_utc`` are
    not filtered. When ``cycle_start_utc`` is null, every sample is in cycle.
    Returns ``(delete_ts, insert_rows)``. ``insert_rows`` keeps incoming order
    and includes same-timestamp duplicates so the caller can count them.
    """

    def in_cycle(ts: str) -> bool:
        return not cycle_start_utc or ts >= cycle_start_utc

    stored_in = [sample for sample in stored if in_cycle(sample["ts"])]
    by_ts: dict[str, dict[str, str]] = {
        sample["ts"]: sample for sample in stored_in
    }
    for ts, cursor, other, _source in incoming:
        if not in_cycle(ts):
            continue
        by_ts.setdefault(ts, {"ts": ts, "cursor": cursor, "other": other})
    ordered = [by_ts[ts] for ts in sorted(by_ts)]
    kept_ts = {sample["ts"] for sample in filter_monotonic_cycle_samples(ordered)}
    delete_ts = [sample["ts"] for sample in stored_in if sample["ts"] not in kept_ts]
    insert_rows = [
        row for row in incoming if not in_cycle(row[0]) or row[0] in kept_ts
    ]
    return delete_ts, insert_rows


def union_cycle_history(
    stored: list[dict[str, str]],
    pushed: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Union by start date; duplicate dates keep later next_renewal."""
    merged: dict[str, dict[str, str]] = {}
    for entry in [*stored, *pushed]:
        key = _history_date_key(entry)
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(entry)
            continue
        if _parse_local(entry["next_renewal"]) > _parse_local(
            existing["next_renewal"]
        ):
            merged[key] = dict(entry)
    return sorted(merged.values(), key=lambda e: _parse_local(e["cycle_start"]))
