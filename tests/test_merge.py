"""Pure merge function tests (spec 6)."""

import pytest

from app.merge import (
    filter_monotonic_cycle_samples,
    normalize_decimal,
    normalize_timestamp,
    pick_active_cycle,
    pick_cycle_start_utc,
    reconcile_cycle_samples,
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


def _sample(ts: str, cursor: str, other: str) -> dict[str, str]:
    return {"ts": ts, "cursor": cursor, "other": other}


def test_filter_monotonic_drops_either_percentage_going_backwards():
    samples = [
        _sample("2026-09-26T18:11:00.000000Z", "70.145", "67.0545"),
        _sample("2026-09-26T18:12:00.000000Z", "69.7225", "67.0545"),
        _sample("2026-09-26T18:13:00.000000Z", "70.145", "67.0545"),
    ]
    kept = filter_monotonic_cycle_samples(samples)
    assert [s["ts"] for s in kept] == [
        "2026-09-26T18:11:00.000000Z",
        "2026-09-26T18:13:00.000000Z",
    ]

    equals = [
        _sample("2026-09-26T18:11:00.000000Z", "70.145", "67.0545"),
        _sample("2026-09-26T18:12:00.000000Z", "70.145", "67.0545"),
    ]
    assert filter_monotonic_cycle_samples(equals) == equals

    cursor_down = [
        _sample("2026-09-26T18:11:00.000000Z", "70.145", "67.0545"),
        _sample("2026-09-26T18:12:00.000000Z", "70.144", "68"),
    ]
    assert len(filter_monotonic_cycle_samples(cursor_down)) == 1

    other_down = [
        _sample("2026-09-26T18:11:00.000000Z", "70.145", "67.0545"),
        _sample("2026-09-26T18:12:00.000000Z", "71", "67.0544"),
    ]
    assert len(filter_monotonic_cycle_samples(other_down)) == 1

    assert filter_monotonic_cycle_samples([]) == []
    single = [_sample("2026-09-26T18:11:00.000000Z", "1", "1")]
    assert filter_monotonic_cycle_samples(single) == single


def test_filter_monotonic_baseline_is_last_kept_not_dropped():
    samples = [
        _sample("2026-09-26T18:11:00.000000Z", "10", "10"),
        _sample("2026-09-26T18:12:00.000000Z", "5", "10"),
        _sample("2026-09-26T18:13:00.000000Z", "8", "10"),
        _sample("2026-09-26T18:14:00.000000Z", "10", "10"),
        _sample("2026-09-26T18:15:00.000000Z", "11", "10"),
    ]
    kept = filter_monotonic_cycle_samples(samples)
    assert [s["ts"] for s in kept] == [
        "2026-09-26T18:11:00.000000Z",
        "2026-09-26T18:14:00.000000Z",
        "2026-09-26T18:15:00.000000Z",
    ]


def test_reconcile_leaves_pre_cycle_samples_and_purges_stored_dip():
    stored = [
        _sample("2026-09-25T18:00:00.000000Z", "80", "80"),
        _sample("2026-09-25T19:00:00.000000Z", "10", "10"),
        _sample("2026-09-26T18:11:00.000000Z", "70.145", "67.0545"),
        _sample("2026-09-26T18:12:00.000000Z", "69.7225", "67.0545"),
        _sample("2026-09-26T18:13:00.000000Z", "70.145", "67.0545"),
    ]
    incoming = [
        (
            "2026-09-26T18:14:00.000000Z",
            "70.200",
            "67.0545",
            "machine",
        )
    ]
    delete_ts, insert_rows = reconcile_cycle_samples(
        stored, incoming, "2026-09-26T00:00:00.000000Z"
    )
    assert delete_ts == ["2026-09-26T18:12:00.000000Z"]
    assert insert_rows == incoming
