"""Backup round-trip + validation tests (spec 7)."""

from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal

import pytest

from app.backup import build_export_zip, parse_import_zip


def test_round_trip_zero_diff():
    samples = [
        {"ts": "2026-09-02T10:00:00.000000Z", "cursor": "1.00", "other": "0.50"},
        {"ts": "2026-09-01T10:00:00.000000Z", "cursor": "12.50", "other": "3.25"},
    ]
    active = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"}
    history = [
        {"cycle_start": "2026-07-15T01:00:00", "next_renewal": "2026-08-15T01:00:00"}
    ]
    payload = build_export_zip(
        samples=samples,
        cycle_start_utc="2026-08-15T00:00:00.000000Z",
        active_cycle=active,
        cycle_history=history,
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert set(zf.namelist()) == {
            "manifest.json",
            "settings.json",
            "usage-samples.json",
        }
    parsed = parse_import_zip(payload)
    assert parsed["cycle_start_utc"] == "2026-08-15T00:00:00.000000Z"
    assert parsed["active_cycle"] == active
    assert parsed["cycle_history"] == history
    # JSON numbers don't preserve trailing zeros ("12.50" -> 12.5), so compare
    # semantic values, not raw strings: same instants, same Decimals.
    assert [s["ts"] for s in parsed["samples"]] == [
        "2026-09-01T10:00:00.000000Z",
        "2026-09-02T10:00:00.000000Z",
    ]
    assert [(s["cursor"], s["other"]) for s in parsed["samples"]] == [
        ("12.5", "3.25"),
        ("1", "0.5"),
    ]
    assert [Decimal(s["cursor"]) for s in parsed["samples"]] == [
        Decimal(s["cursor"]) for s in sorted(samples, key=lambda s: s["ts"])
    ]


def _make_zip(files: dict[str, object]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, obj in files.items():
            content = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            zf.writestr(name, content)
    return buf.getvalue()


def test_import_app_style_zip():
    payload = _make_zip(
        {
            "manifest.json": {
                "formatVersion": 1,
                "product": "CursorPace",
                "createdUtc": "2026-09-18T10:00:00.000000Z",
            },
            "settings.json": {
                "version": 2,
                "activeCycle": {
                    "renewalDay": 15,
                    "cycleStart": "2026-08-15T01:00:00",
                    "nextRenewal": "2026-09-15T01:00:00",
                    "extraIgnored": True,
                },
                "cycleHistory": [
                    {
                        "renewalDay": 15,
                        "cycleStart": "2026-07-15T01:00:00",
                        "nextRenewal": "2026-08-15T01:00:00",
                    },
                    {
                        "renewalDay": 15,
                        "cycleStart": "bad",
                        "nextRenewal": "2026-08-15T01:00:00",
                    },
                ],
                "legacy": "ignored",
            },
            "usage-samples.json": {
                "version": 1,
                "cycleStartUtc": "2026-08-15T00:00:00Z",
                "samples": [{"ts": "2026-09-01T10:00:00Z", "cursor": 12.5, "other": "3.25"}],
            },
        }
    )
    parsed = parse_import_zip(payload)
    assert parsed["active_cycle"] == {
        "cycle_start": "2026-08-15T01:00:00",
        "next_renewal": "2026-09-15T01:00:00",
    }
    # Invalid history entry skipped.
    assert len(parsed["samples"]) == 1
    assert parsed["samples"][0]["ts"] == "2026-09-01T10:00:00.000000Z"


def test_reject_bad_product_and_new_version():
    bad_product = _make_zip(
        {
            "manifest.json": {"formatVersion": 1, "product": "Other"},
            "settings.json": {},
        }
    )
    with pytest.raises(ValueError, match="product"):
        parse_import_zip(bad_product)
    new_version = _make_zip(
        {
            "manifest.json": {"formatVersion": 99, "product": "CursorPace"},
            "settings.json": {},
        }
    )
    with pytest.raises(ValueError, match="formatVersion"):
        parse_import_zip(new_version)


def test_missing_usage_samples_means_empty():
    payload = _make_zip(
        {
            "settings.json": {"version": 2},
        }
    )
    parsed = parse_import_zip(payload)
    assert parsed["samples"] == []
