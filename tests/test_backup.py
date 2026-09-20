"""Backup round-trip + validation tests (spec 7)."""

from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import zipfile
from decimal import Decimal
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app import db as db_mod
from app.auth import DEFAULT_ADMIN_PASSWORD, generate_token
from app.backup import (
    SERVER_PRODUCT,
    build_export_zip,
    build_server_export_zip,
    parse_import_zip,
    parse_server_import_zip,
)
from app.config import Settings, secret_key_path
from app.main import create_app
from app.merge import utc_now_canonical


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


def _init_db_bytes(tmp_path: Path) -> bytes:
    db_path = tmp_path / "seed.db"
    asyncio.run(db_mod.init_db(db_path))
    return asyncio.run(db_mod.snapshot_database(db_path))


def test_server_zip_round_trip(tmp_path: Path):
    db_bytes = _init_db_bytes(tmp_path)
    payload = build_server_export_zip(db_bytes=db_bytes, secret_key="abc")
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert set(zf.namelist()) == {
            "manifest.json",
            "sync.db",
            "secret_key",
        }
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["product"] == SERVER_PRODUCT
        assert manifest["formatVersion"] == 1
    parsed = parse_server_import_zip(payload)
    assert parsed["secret_key"] == "abc"
    assert isinstance(parsed["db_bytes"], bytes)
    assert parsed["db_bytes"]


def test_server_zip_rejects_wrong_product_and_version(tmp_path: Path):
    db_bytes = _init_db_bytes(tmp_path)
    with pytest.raises(ValueError, match="product"):
        parse_server_import_zip(
            _make_zip(
                {
                    "manifest.json": {"formatVersion": 1, "product": "Other"},
                    "sync.db": db_bytes,
                    "secret_key": b"abc\n",
                }
            )
        )
    with pytest.raises(ValueError, match="formatVersion"):
        parse_server_import_zip(
            _make_zip(
                {
                    "manifest.json": {
                        "formatVersion": 99,
                        "product": SERVER_PRODUCT,
                    },
                    "sync.db": db_bytes,
                    "secret_key": b"abc\n",
                }
            )
        )


def test_server_zip_requires_db_and_secret(tmp_path: Path):
    db_bytes = _init_db_bytes(tmp_path)
    with pytest.raises(ValueError, match="secret_key"):
        parse_server_import_zip(
            _make_zip(
                {
                    "manifest.json": {
                        "formatVersion": 1,
                        "product": SERVER_PRODUCT,
                    },
                    "sync.db": db_bytes,
                }
            )
        )
    with pytest.raises(ValueError, match="sync.db"):
        parse_server_import_zip(
            _make_zip(
                {
                    "manifest.json": {
                        "formatVersion": 1,
                        "product": SERVER_PRODUCT,
                    },
                    "secret_key": b"abc\n",
                }
            )
        )
    with pytest.raises(ValueError, match="SQLite"):
        parse_server_import_zip(
            _make_zip(
                {
                    "manifest.json": {
                        "formatVersion": 1,
                        "product": SERVER_PRODUCT,
                    },
                    "sync.db": b"not a database",
                    "secret_key": b"abc\n",
                }
            )
        )
        empty_path = tmp_path / "empty.db"
        empty = sqlite3.connect(str(empty_path))
        empty.close()
        with pytest.raises(ValueError, match="missing tables"):
            parse_server_import_zip(
                _make_zip(
                    {
                        "manifest.json": {
                            "formatVersion": 1,
                            "product": SERVER_PRODUCT,
                        },
                        "sync.db": empty_path.read_bytes(),
                        "secret_key": b"abc\n",
                    }
                )
            )


def test_wrong_zip_kind_is_rejected(tmp_path: Path):
    app_zip = build_export_zip(
        samples=[],
        cycle_start_utc=None,
        active_cycle=None,
        cycle_history=[],
    )
    with pytest.raises(ValueError, match="dataset import"):
        parse_server_import_zip(app_zip)
    server_zip = build_server_export_zip(
        db_bytes=_init_db_bytes(tmp_path), secret_key="abc"
    )
    with pytest.raises(ValueError, match="sync server backup"):
        parse_import_zip(server_zip)


def _make_app(tmp_path: Path):
    return create_app(
        Settings(data_dir=tmp_path, port=7050, secret_key="test-secret")
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"password": DEFAULT_ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    changed = client.post(
        "/change-password",
        data={"password": "chosen-admin-pass", "confirm": "chosen-admin-pass"},
        follow_redirects=False,
    )
    assert changed.status_code == 303


def _dataset_zip(
    *,
    samples: list[dict[str, object]],
    cycle_start_utc: str | None,
    active: dict[str, str] | None,
    history: list[dict[str, str]],
) -> bytes:
    return build_export_zip(
        samples=[
            {
                "ts": str(s["ts"]),
                "cursor": str(s["cursor"]),
                "other": str(s["other"]),
            }
            for s in samples
        ],
        cycle_start_utc=cycle_start_utc,
        active_cycle=active,
        cycle_history=history,
    )


async def _seed_dataset(
    db_path: Path,
    *,
    samples: list[tuple[str, str, str]],
    cycle_start_utc: str,
    active: dict[str, str],
    history: list[dict[str, str]],
) -> None:
    await db_mod.init_db(db_path)
    async with aiosqlite.connect(str(db_path)) as conn:
        await db_mod.insert_samples_ignore(
            conn, [(ts, cursor, other, "") for ts, cursor, other in samples]
        )
        await db_mod.set_meta(conn, "cycle_start_utc", cycle_start_utc)
        await db_mod.set_meta(conn, "active_cycle", json.dumps(active))
        await db_mod.set_meta(conn, "cycle_history", json.dumps(history))
        await conn.commit()


def test_http_import_replace_and_merge(tmp_path: Path):
    app = _make_app(tmp_path)
    db_path = db_mod.db_path_for(tmp_path)
    stored_active = {
        "cycle_start": "2026-07-15T01:00:00",
        "next_renewal": "2026-08-15T01:00:00",
    }
    stored_history = [
        {
            "cycle_start": "2026-06-15T01:00:00",
            "next_renewal": "2026-07-15T01:00:00",
        }
    ]
    asyncio.run(
        _seed_dataset(
            db_path,
            samples=[
                ("2026-09-01T10:00:00.000000Z", "1.00", "0.25"),
                ("2026-09-02T10:00:00.000000Z", "2.00", "0.50"),
            ],
            cycle_start_utc="2026-07-15T00:00:00.000000Z",
            active=stored_active,
            history=stored_history,
        )
    )
    incoming_active = {
        "cycle_start": "2026-08-15T01:00:00",
        "next_renewal": "2026-09-15T01:00:00",
    }
    incoming_history = [
        {
            "cycle_start": "2026-08-15T01:00:00",
            "next_renewal": "2026-09-15T01:00:00",
        }
    ]
    incoming = _dataset_zip(
        samples=[
            {
                "ts": "2026-09-01T10:00:00.000000Z",
                "cursor": "99",
                "other": "9",
            },
            {
                "ts": "2026-09-03T10:00:00.000000Z",
                "cursor": "3.00",
                "other": "0.75",
            },
        ],
        cycle_start_utc="2026-08-15T00:00:00.000000Z",
        active=incoming_active,
        history=incoming_history,
    )
    with TestClient(app) as client:
        _login(client)
        merged = client.post(
            "/backup/import",
            files={"file": ("backup.zip", incoming, "application/zip")},
            data={"merge": "1"},
        )
        assert merged.status_code == 200
        assert "Merged 1 new samples (1 already present)" in merged.text
        async def read_merged() -> tuple[list[dict[str, str]], str | None, dict | None, list]:
            async with aiosqlite.connect(str(db_path)) as conn:
                samples = await db_mod.get_all_samples(conn)
                start = await db_mod.get_meta(conn, "cycle_start_utc")
                raw_active = await db_mod.get_meta(conn, "active_cycle")
                raw_history = await db_mod.get_meta(conn, "cycle_history")
            return (
                samples,
                start,
                json.loads(raw_active) if raw_active else None,
                json.loads(raw_history) if raw_history else [],
            )

        samples, start, active, history = asyncio.run(read_merged())
        by_ts = {s["ts"]: s for s in samples}
        assert set(by_ts) == {
            "2026-09-01T10:00:00.000000Z",
            "2026-09-02T10:00:00.000000Z",
            "2026-09-03T10:00:00.000000Z",
        }
        assert by_ts["2026-09-01T10:00:00.000000Z"]["cursor"] == "1.00"
        assert start == "2026-08-15T00:00:00.000000Z"
        assert active == incoming_active
        assert len(history) == 2

        replaced = client.post(
            "/backup/import",
            files={"file": ("backup.zip", incoming, "application/zip")},
        )
        assert replaced.status_code == 200
        assert "Imported 2 samples, 1 history entries." in replaced.text
        samples, start, active, history = asyncio.run(read_merged())
        assert [s["ts"] for s in samples] == [
            "2026-09-01T10:00:00.000000Z",
            "2026-09-03T10:00:00.000000Z",
        ]
        assert samples[0]["cursor"] in ("99", "99.0", "99.00")
        assert start == "2026-08-15T00:00:00.000000Z"
        assert active == incoming_active
        assert history == incoming_history


def test_http_server_export_import_restores_db_and_secret(tmp_path: Path):
    app = _make_app(tmp_path)
    db_path = db_mod.db_path_for(tmp_path)
    asyncio.run(db_mod.init_db(db_path))

    async def seed_snapshot() -> None:
        async with aiosqlite.connect(str(db_path)) as conn:
            await db_mod.insert_samples_ignore(
                conn,
                [("2026-09-01T10:00:00.000000Z", "1.00", "0.25", "alpha")],
            )
            raw, token_hash, prefix = generate_token()
            await db_mod.create_device(
                conn,
                name="alpha",
                token_hash=token_hash,
                token_prefix=prefix,
                created_utc=utc_now_canonical(),
            )
            await conn.commit()
            del raw

    asyncio.run(seed_snapshot())
    with TestClient(app) as client:
        _login(client)
        exported = client.get("/backup/export-server")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/zip")
        assert "cursorpace-sync-backup-" in exported.headers["content-disposition"]
        payload = exported.content
        parsed = parse_server_import_zip(payload)
        assert parsed["secret_key"] == "test-secret"

        async def add_later_sample() -> None:
            async with aiosqlite.connect(str(db_path)) as conn:
                await db_mod.insert_samples_ignore(
                    conn,
                    [("2026-09-09T10:00:00.000000Z", "9.00", "1.00", "beta")],
                )
                await conn.commit()

        asyncio.run(add_later_sample())
        refused = client.post(
            "/backup/import-server",
            files={"file": ("server.zip", payload, "application/zip")},
        )
        assert refused.status_code == 200
        assert "Confirm that this will replace" in refused.text

        restored = client.post(
            "/backup/import-server",
            files={"file": ("server.zip", payload, "application/zip")},
            data={"confirm": "1"},
        )
        assert restored.status_code == 200
        assert "Restored the sync server backup" in restored.text
        follow = client.get("/backup")
        assert follow.status_code == 200
        assert "Export server backup" in follow.text

        async def read_state() -> tuple[list[str], list[str]]:
            async with aiosqlite.connect(str(db_path)) as conn:
                samples = await db_mod.get_all_samples(conn)
                devices = await db_mod.list_devices(conn)
            return [s["ts"] for s in samples], [d.name for d in devices]

        timestamps, names = asyncio.run(read_state())
        assert timestamps == ["2026-09-01T10:00:00.000000Z"]
        assert "alpha" in names
        key_path = secret_key_path(tmp_path)
        assert key_path.is_file()
        assert key_path.read_text(encoding="utf-8").strip() == "test-secret"

        app_zip = _dataset_zip(
            samples=[],
            cycle_start_utc=None,
            active=None,
            history=[],
        )
        mismatch = client.post(
            "/backup/import-server",
            files={"file": ("app.zip", app_zip, "application/zip")},
            data={"confirm": "1"},
        )
        assert mismatch.status_code == 200
        assert "dataset import" in mismatch.text
