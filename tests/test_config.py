"""Persisted admin session secret next to the database."""

from __future__ import annotations

import stat
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import (
    SECRET_KEY_FILENAME,
    Settings,
    load_or_create_secret_key,
    secret_key_path,
)
from app.main import create_app


def test_creates_secret_key_file_with_restricted_permissions(tmp_path: Path):
    path = secret_key_path(tmp_path)
    assert not path.exists()
    key = load_or_create_secret_key(tmp_path)
    assert path.is_file()
    assert path.name == SECRET_KEY_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8").strip() == key
    assert key


def test_reuses_existing_secret_key_file(tmp_path: Path):
    path = secret_key_path(tmp_path)
    path.write_text("already-persisted-key\n", encoding="utf-8")
    path.chmod(0o644)
    key = load_or_create_secret_key(tmp_path)
    assert key == "already-persisted-key"
    assert path.read_text(encoding="utf-8").strip() == "already-persisted-key"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_app_startup_writes_secret_key_beside_database(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, port=7050))
    path = secret_key_path(tmp_path)
    assert not path.exists()
    with TestClient(app) as client:
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        stored = path.read_text(encoding="utf-8").strip()
        assert stored == client.app.state.settings.secret_key
        assert client.get("/healthz").json() == {"status": "ok"}
