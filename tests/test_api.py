"""API tests: auth, merge convergence, idempotency (spec 8 + 12)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db as db_mod
from app.auth import generate_token
from app.config import Settings
from app.main import create_app
from app.merge import utc_now_canonical


def make_app(tmp_path: Path) -> tuple[FastAPI, str]:
    settings = Settings(
        data_dir=tmp_path,
        port=7050,
        secret_key="test-secret",
    )
    app = create_app(settings)
    db_path = db_mod.db_path_for(tmp_path)

    async def seed() -> str:
        await db_mod.init_db(db_path)
        raw, token_hash, prefix = generate_token()
        async with aiosqlite.connect(str(db_path)) as conn:
            await db_mod.create_device(
                conn,
                name="seed",
                token_hash=token_hash,
                token_prefix=prefix,
                created_utc=utc_now_canonical(),
            )
            await conn.commit()
        return raw

    return app, asyncio.run(seed())


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_healthz(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_invalid_token_401(tmp_path):
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        r = client.get("/api/v1/pull")
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid or missing API token"}
        r = client.get("/api/v1/pull", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401


def test_push_pull_converge_and_idempotent(tmp_path):
    app, token = make_app(tmp_path)
    headers = auth(token)
    active = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"}

    body_a = {
        "machine_name": "machine-a",
        "cycle_start_utc": "2026-08-15T00:00:00.000000Z",
        "active_cycle": active,
        "cycle_history": [],
        "samples": [
            {"ts": "2026-09-01T10:00:00Z", "cursor": "12.50", "other": "3.25"},
            {"ts": "2026-09-02T10:00:00Z", "cursor": "1.00", "other": "0.50"},
        ],
    }
    with TestClient(app) as client:
        r = client.post("/api/v1/push", json=body_a, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] == 2
        assert r.json()["total_samples"] == 2

        body_b = {
            "machine_name": "machine-b",
            "cycle_start_utc": "2026-08-15T00:00:00.000000Z",
            "active_cycle": active,
            "cycle_history": [],
            "samples": [
                {"ts": "2026-09-02T10:00:00Z", "cursor": "1.00", "other": "0.50"},
                {"ts": "2026-09-03T10:00:00Z", "cursor": "2.00", "other": "1.00"},
            ],
        }
        r = client.post("/api/v1/push", json=body_b, headers=headers)
        assert r.json()["accepted"] == 1
        assert r.json()["duplicates"] == 1
        assert r.json()["total_samples"] == 3

        # Re-push identical data is idempotent.
        r = client.post("/api/v1/push", json=body_b, headers=headers)
        assert r.json()["accepted"] == 0
        assert r.json()["total_samples"] == 3

        pulled = client.get("/api/v1/pull", headers=headers).json()
        assert len(pulled["samples"]) == 3
        assert pulled["active_cycle"] == active


def test_newer_active_cycle_wins(tmp_path):
    app, token = make_app(tmp_path)
    headers = auth(token)
    old = {"cycle_start": "2026-07-15T01:00:00", "next_renewal": "2026-08-15T01:00:00"}
    new = {"cycle_start": "2026-08-15T01:00:00", "next_renewal": "2026-09-15T01:00:00"}
    with TestClient(app) as client:
        client.post(
            "/api/v1/push",
            json={"machine_name": "m", "active_cycle": old, "samples": []},
            headers=headers,
        )
        client.post(
            "/api/v1/push",
            json={"machine_name": "m", "active_cycle": new, "samples": []},
            headers=headers,
        )
        pulled = client.get("/api/v1/pull", headers=headers).json()
        assert pulled["active_cycle"] == new
        # Pushing the older one again must not regress.
        client.post(
            "/api/v1/push",
            json={"machine_name": "m", "active_cycle": old, "samples": []},
            headers=headers,
        )
        assert client.get("/api/v1/pull", headers=headers).json()["active_cycle"] == new


def test_bad_timestamp_400_names_index(tmp_path):
    app, token = make_app(tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/push",
            json={
                "machine_name": "m",
                "samples": [{"ts": "bogus", "cursor": "1", "other": "1"}],
            },
            headers=auth(token),
        )
        assert r.status_code == 400
        assert "samples[0]" in r.json()["detail"]
