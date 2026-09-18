"""Admin HTML: labels, empty states, timestamps, and theme assets."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import DEFAULT_ADMIN_PASSWORD
from app.config import Settings
from app.main import create_app, enable_console_timestamps


def make_app(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        port=8080,
        secret_key="test-secret",
        secret_key_was_generated=False,
    )
    return create_app(settings)


def login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"password": DEFAULT_ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/change-password"
    changed = client.post(
        "/change-password",
        data={"password": "chosen-admin-pass", "confirm": "chosen-admin-pass"},
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert changed.headers["location"] == "/"


def test_dashboard_empty_states_and_last_activity_label(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        html = client.get("/").text
        assert "Last activity" in html
        assert "Last push" not in html
        assert "No active cycle" in html
        assert "No samples yet" in html
        assert 'aria-current="page"' in html
        assert client.get("/tokens").text.count("No tokens yet") == 1
        assert "No machines yet" in client.get("/machines").text
        assert "No samples yet" in client.get("/data").text
        backup = client.get("/backup").text
        assert 'href="/backup/export"' in backup
        assert "<a href=\"/backup/export\"><button>" not in backup
        assert "Import replaces the current samples" in backup


def test_theme_assets_follow_color_scheme(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text
        assert "prefers-color-scheme: dark" in css
        assert "--bg:" in css
        js = client.get("/static/app.js").text
        assert "Intl.DateTimeFormat" in js
        assert client.get("/static/cursor_pace.png").status_code == 200
        assert client.get("/static/cursor_pace.ico").status_code == 200
        login_html = client.get("/login").text
        assert "/static/cursor_pace.png" in login_html
        assert 'rel="icon"' in login_html
        assert "cursorpace01" in login_html
        login(client)
        dash = client.get("/").text
        assert 'class="brand-mark"' in dash
        assert "/static/cursor_pace.png" in dash
        assert "Refresh" in dash
        assert 'class="btn-icon"' in dash


def test_dashboard_and_data_render_friendly_timestamps(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        created = client.post(
            "/tokens", data={"name": "desk"}, follow_redirects=True
        )
        match = re.search(r'class="token">([^<]+)', created.text)
        assert match, created.text
        token = match.group(1)
        payload = {
            "machine_name": "desk",
            "cycle_start_utc": "2026-08-15T00:00:00.000000Z",
            "active_cycle": {
                "cycle_start": "2026-08-15T01:00:00",
                "next_renewal": "2026-09-15T01:00:00",
            },
            "cycle_history": [
                {
                    "cycle_start": "2026-07-15T01:00:00",
                    "next_renewal": "2026-08-15T01:00:00",
                }
            ],
            "samples": [
                {"ts": "2026-09-01T10:00:00Z", "cursor": "12.50", "other": "3.25"}
            ],
        }
        pushed = client.post(
            "/api/v1/push",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert pushed.status_code == 200, pushed.text

        dash = client.get("/").text
        assert "Last activity" in dash
        assert 'data-utc' in dash
        assert 'datetime="2026-09-01T10:00:00.000000Z"' in dash
        assert "15 Aug 2026, 01:00" in dash
        assert "account time" in dash

        machines = client.get("/machines").text
        assert "chip-active" in machines or "chip-recent" in machines
        assert 'data-relative' in machines

        data = client.get("/data").text
        assert "Cursor %" in data
        assert "15 Aug 2026, 01:00" in data
        assert 'datetime="2026-09-01T10:00:00.000000Z"' in data
        assert "1 Sep 2026, 10:00 UTC" in data


def test_console_logs_include_clock_time():
    access = logging.getLogger("uvicorn.access")
    error = logging.getLogger("uvicorn")
    access_handler = logging.StreamHandler()
    error_handler = logging.StreamHandler()
    access.addHandler(access_handler)
    error.addHandler(error_handler)
    try:
        enable_console_timestamps()
        assert access_handler.formatter is not None
        assert error_handler.formatter is not None
        assert access_handler.formatter.datefmt == "%H:%M:%S"
        assert error_handler.formatter.datefmt == "%H:%M:%S"
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1:1", "GET", "/machines", "1.1", 200),
            exc_info=None,
        )
        formatted = access_handler.formatter.format(record)
        assert re.search(r"\d{2}:\d{2}:\d{2}", formatted)
        assert "GET /machines" in formatted
    finally:
        access.removeHandler(access_handler)
        error.removeHandler(error_handler)


def test_first_login_forces_password_change(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        login_page = client.get("/login")
        assert login_page.status_code == 200
        assert "cursorpace01" in login_page.text

        wrong = client.post("/login", data={"password": "nope"})
        assert wrong.status_code == 200
        assert "Wrong password" in wrong.text

        signed_in = client.post(
            "/login",
            data={"password": DEFAULT_ADMIN_PASSWORD},
            follow_redirects=False,
        )
        assert signed_in.status_code == 303
        assert signed_in.headers["location"] == "/change-password"

        blocked = client.get("/", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/change-password"
        assert client.get("/tokens", follow_redirects=False).headers["location"] == (
            "/change-password"
        )

        form = client.get("/change-password")
        assert form.status_code == 200
        assert "Choose a new password" in form.text

        keep_default = client.post(
            "/change-password",
            data={
                "password": DEFAULT_ADMIN_PASSWORD,
                "confirm": DEFAULT_ADMIN_PASSWORD,
            },
        )
        assert keep_default.status_code == 200
        assert "default password" in keep_default.text

        mismatch = client.post(
            "/change-password",
            data={"password": "new-secret-1", "confirm": "new-secret-2"},
        )
        assert mismatch.status_code == 200
        assert "do not match" in mismatch.text

        too_short = client.post(
            "/change-password",
            data={"password": "short", "confirm": "short"},
        )
        assert too_short.status_code == 200
        assert "at least" in too_short.text

        saved = client.post(
            "/change-password",
            data={"password": "chosen-admin-pass", "confirm": "chosen-admin-pass"},
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"] == "/"
        assert "Dashboard" in client.get("/").text
        assert "cursorpace01" not in client.get("/login").text

        client.post("/logout")
        still_default = client.post(
            "/login",
            data={"password": DEFAULT_ADMIN_PASSWORD},
            follow_redirects=False,
        )
        assert still_default.status_code == 200
        assert "Wrong password" in still_default.text

        with_new = client.post(
            "/login",
            data={"password": "chosen-admin-pass"},
            follow_redirects=False,
        )
        assert with_new.status_code == 303
        assert with_new.headers["location"] == "/"
