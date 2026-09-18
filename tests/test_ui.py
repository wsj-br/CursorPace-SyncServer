"""View-only timestamp and number formatting for the admin UI."""

from datetime import datetime, timezone

from app.ui import (
    format_cycle_display,
    format_int,
    format_relative,
    format_utc_display,
    format_utc_iso,
    status_modifier,
)


NOW = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def test_format_utc_display_and_iso():
    assert (
        format_utc_display("2026-09-18T14:48:20.885287Z")
        == "18 Sep 2026, 14:48 UTC"
    )
    assert (
        format_utc_iso("2026-09-01T12:00:00+02:00")
        == "2026-09-01T10:00:00.000000Z"
    )
    assert format_utc_display(None) == ""
    assert format_utc_iso("not-a-date") == "not-a-date"


def test_format_relative_buckets():
    assert format_relative(None) == "Never"
    assert format_relative("2026-09-18T14:59:30.000000Z", NOW) == "just now"
    assert format_relative("2026-09-18T14:58:30.000000Z", NOW) == "1 minute ago"
    assert format_relative("2026-09-18T14:48:00.000000Z", NOW) == "12 minutes ago"
    assert format_relative("2026-09-18T13:30:00.000000Z", NOW) == "1 hour ago"
    assert format_relative("2026-09-18T13:00:00.000000Z", NOW) == "2 hours ago"
    assert format_relative("2026-09-17T15:00:00.000000Z", NOW) == "yesterday"
    assert (
        format_relative("2026-09-01T10:00:00.000000Z", NOW)
        == "1 Sep 2026, 10:00 UTC"
    )


def test_format_cycle_keeps_wall_clock():
    assert format_cycle_display("2026-08-15T01:00:00") == "15 Aug 2026, 01:00"
    assert (
        format_cycle_display("2026-09-02T22:19:47+01:00")
        == "2 Sep 2026, 22:19 (UTC+1)"
    )
    assert format_cycle_display("2026-08-15T01:00:00Z") == "15 Aug 2026, 01:00 UTC"


def test_status_and_int_helpers():
    assert status_modifier("Active") == "active"
    assert status_modifier("Mystery") == "never"
    assert format_int(1234) == "1,234"
