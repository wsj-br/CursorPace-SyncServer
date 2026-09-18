"""Pure merge function tests (spec 6)."""

import pytest

from app.merge import (
    normalize_decimal,
    normalize_timestamp,
    pick_active_cycle,
    pick_cycle_start_utc,
    union_cycle_history,
)


def test_normalize_timestamp_variants():
    assert (
        normalize_timestamp("2026-09-01T10:00:00Z")
        == "2026-09-01T10:00:00.000000Z"
    )
    assert (
        normalize_timestamp("2026-09-01T12:00:00+02:00")
        == "2026-09-01T10:00:00.000000Z"
    )
    assert (
        normalize_timestamp("2026-09-01T10:00:00.123456Z")
        == "2026-09-01T10:00:00.123456Z"
    )
    with pytest.raises(ValueError):
        normalize_timestamp("not-a-date")


def test_normalize_decimal():
    assert normalize_decimal("12.50") == "12.50"
    assert normalize_decimal("1E+2") == "100"
    assert normalize_decimal(12.5) == "12.5"
    with pytest.raises(ValueError):
        normalize_decimal("12.12345")  # > 4 fractional digits
    with pytest.raises(ValueError):
        normalize_decimal("-1")
    with pytest.raises(ValueError):
        normalize_decimal("abc")


def test_pick_cycle_start_utc_keeps_latest():
    assert (
        pick_cycle_start_utc(
            "2026-08-15T00:00:00.000000Z", "2026-09-15T00:00:00.000000Z"
        )
        == "2026-09-15T00:00:00.000000Z"
    )
    assert pick_cycle_start_utc(None, "2026-09-15T00:00:00.000000Z") == (
        "2026-09-15T00:00:00.000000Z"
    )
    assert pick_cycle_start_utc(None, None) is None


def test_pick_active_cycle_newest_wins():
    old = {"cycle_start": "2026-07-15T01:00:00", "next_renewal": "2026-08-15T01:00:00"}
    new = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"}
    assert pick_active_cycle(old, new) == new
    assert pick_active_cycle(new, old) == new
    # Tie on start: later renewal wins.
    a = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"}
    b = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-16T01:00:00"}
    assert pick_active_cycle(a, b) == b
    # Full tie keeps stored.
    assert pick_active_cycle(a, dict(a)) == a
    # Mixed naive vs Z/offset must not raise (desktop may send either).
    with_z = {
        "cycle_start": "2026-08-15T01:00:00Z",
        "next_renewal": "2026-09-15T01:00:00Z",
    }
    with_offset = {
        "cycle_start": "2026-08-15T01:00:00+01:00",
        "next_renewal": "2026-09-15T01:00:00+01:00",
    }
    assert pick_active_cycle(a, with_z) == a
    assert pick_active_cycle(a, with_offset) == a
    later_aware = {
        "cycle_start": "2026-09-15T01:00:00+01:00",
        "next_renewal": "2026-10-15T01:00:00+01:00",
    }
    assert pick_active_cycle(a, later_aware) == later_aware


def test_union_cycle_history_one_per_start_date():
    stored = [
        {"cycle_start": "2026-07-15T01:00:00", "next_renewal": "2026-08-15T01:00:00"}
    ]
    pushed = [
        {"cycle_start": "2026-07-15T05:00:00", "next_renewal": "2026-08-16T01:00:00"},
        {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"},
    ]
    merged = union_cycle_history(stored, pushed)
    assert len(merged) == 2
    july = [e for e in merged if e["cycle_start"].startswith("2026-07-15")][0]
    assert july["next_renewal"] == "2026-08-16T01:00:00"
