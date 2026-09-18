"""FastAPI app: route wiring, startup (migrate + seed admin)."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import backup as backup_mod
from . import db as db_mod
from .auth import (
    SESSION_COOKIE,
    create_session_value,
    generate_token,
    hash_admin_password,
    hash_token,
    verify_admin_password,
    verify_session_value,
)
from .config import Settings, ensure_data_dir, get_settings
from .merge import (
    normalize_decimal,
    normalize_timestamp,
    pick_active_cycle,
    pick_cycle_start_utc,
    union_cycle_history,
    utc_now_canonical,
)

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))

INVALID_TOKEN_DETAIL = "Invalid or missing API token"


# ---------------------------------------------------------------------------
# Pydantic models (API shape, spec 8.1)
# ---------------------------------------------------------------------------


class SampleIn(BaseModel):
    ts: Any
    cursor: Any
    other: Any


class ActiveCycleIn(BaseModel):
    cycle_start: str
    next_renewal: str


class PushIn(BaseModel):
    machine_name: str = Field(min_length=1, max_length=64)
    cycle_start_utc: str | None = None
    active_cycle: ActiveCycleIn | None = None
    cycle_history: list[ActiveCycleIn] = Field(default_factory=list)
    samples: list[SampleIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def presence_status(last_seen_utc: str | None, now: datetime | None = None) -> str:
    if not last_seen_utc:
        return "Never"
    try:
        text = last_seen_utc.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        seen = datetime.fromisoformat(text)
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
    except ValueError:
        return "Stale"
    now = now or datetime.now(timezone.utc)
    delta = (now - seen).total_seconds()
    if delta < 0:
        return "Active"
    if delta <= 15 * 60:
        return "Active"
    if delta <= 24 * 3600:
        return "Recent"
    return "Stale"


def _local_valid(value: str) -> bool:
    try:
        datetime.fromisoformat(value.strip().removesuffix("Z"))
    except ValueError:
        return False
    return True


def _open_db(settings: Settings) -> aiosqlite.Connection:
    # NOTE: aiosqlite connections must be awaited exactly once (the worker
    # thread cannot be started twice), so this returns the un-awaited
    # connection for use as `async with _open_db(...) as conn:`.
    return aiosqlite.connect(str(db_mod.db_path_for(settings.data_dir)))


async def _read_cycle_state(
    conn: aiosqlite.Connection,
) -> tuple[str | None, dict[str, str] | None, list[dict[str, str]]]:
    raw_start = await db_mod.get_meta(conn, "cycle_start_utc")
    raw_active = await db_mod.get_meta(conn, "active_cycle")
    raw_history = await db_mod.get_meta(conn, "cycle_history")
    active = json.loads(raw_active) if raw_active else None
    history = json.loads(raw_history) if raw_history else []
    return raw_start, active, history if isinstance(history, list) else []


def is_admin(request: Request) -> bool:
    settings: Settings = request.app.state.settings
    return verify_session_value(
        settings.secret_key, request.cookies.get(SESSION_COOKIE)
    )


def require_admin_redirect(request: Request) -> bool:
    return is_admin(request)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_data_dir(resolved.data_dir)
        if resolved.secret_key_was_generated:
            logger.warning(
                "SECRET_KEY not set; using random per-boot key, "
                "admin sessions will not survive restarts."
            )
        await db_mod.init_db(db_mod.db_path_for(resolved.data_dir))
        # Seed admin hash if absent.
        async with _open_db(resolved) as conn:
            existing = await db_mod.get_meta(conn, "admin_hash")
            if not existing and resolved.admin_password:
                await db_mod.set_meta(
                    conn, "admin_hash", hash_admin_password(resolved.admin_password)
                )
                await conn.commit()
        yield

    app = FastAPI(title="CursorPace Sync Server", lifespan=lifespan)
    app.state.settings = resolved
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    # -- health ----------------------------------------------------------
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # -- API auth dependency ---------------------------------------------
    async def current_device(
        authorization: str | None = Header(default=None),
    ) -> db_mod.Device:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL)
        raw = authorization.removeprefix("Bearer ").strip()
        if not raw:
            raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL)
        token_hash = hash_token(raw)
        async with _open_db(resolved) as conn:
            device = await db_mod.get_device_by_token_hash(conn, token_hash)
        if device is None:
            raise HTTPException(status_code=401, detail=INVALID_TOKEN_DETAIL)
        return device

    # -- push -------------------------------------------------------------
    @app.post("/api/v1/push")
    async def push(body: PushIn, device: db_mod.Device = Depends(current_device)):
        if not body.machine_name.strip():
            raise HTTPException(status_code=422, detail="machine_name required")
        if len(body.samples) > 50_000:
            raise HTTPException(status_code=413, detail="Too many samples (max 50000)")

        # Normalize / validate inputs with 400s naming the index.
        normalized: list[tuple[str, str, str]] = []
        for i, s in enumerate(body.samples):
            if s.ts is None or s.cursor is None or s.other is None:
                raise HTTPException(
                    status_code=400, detail=f"samples[{i}]: missing field"
                )
            try:
                ts = normalize_timestamp(str(s.ts))
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"samples[{i}]: invalid ts"
                )
            try:
                cursor = normalize_decimal(s.cursor)
                other = normalize_decimal(s.other)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"samples[{i}]: invalid decimal"
                )
            normalized.append((ts, cursor, other))

        pushed_start: str | None = None
        if body.cycle_start_utc is not None:
            try:
                pushed_start = normalize_timestamp(body.cycle_start_utc)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="invalid cycle_start_utc"
                )

        pushed_active: dict[str, str] | None = None
        if body.active_cycle is not None:
            if not _local_valid(
                body.active_cycle.cycle_start
            ) or not _local_valid(body.active_cycle.next_renewal):
                raise HTTPException(
                    status_code=400, detail="invalid active_cycle datetime"
                )
            pushed_active = {
                "cycle_start": body.active_cycle.cycle_start,
                "next_renewal": body.active_cycle.next_renewal,
            }
        pushed_history: list[dict[str, str]] = []
        for i, h in enumerate(body.cycle_history):
            if not _local_valid(h.cycle_start) or not _local_valid(h.next_renewal):
                raise HTTPException(
                    status_code=400, detail=f"cycle_history[{i}]: invalid datetime"
                )
            pushed_history.append(
                {"cycle_start": h.cycle_start, "next_renewal": h.next_renewal}
            )

        now = utc_now_canonical()
        async with _open_db(resolved) as conn:
            stored_start, stored_active, stored_history = await _read_cycle_state(conn)
            merged_start = pick_cycle_start_utc(stored_start, pushed_start)
            merged_active = pick_active_cycle(stored_active, pushed_active)
            merged_history = union_cycle_history(stored_history, pushed_history)

            accepted, duplicates = await db_mod.insert_samples_ignore(
                conn,
                [
                    (ts, cursor, other, body.machine_name)
                    for ts, cursor, other in normalized
                ],
            )
            if merged_start is not None:
                await db_mod.set_meta(conn, "cycle_start_utc", merged_start)
            if merged_active is not None:
                await db_mod.set_meta(conn, "active_cycle", json.dumps(merged_active))
            await db_mod.set_meta(
                conn, "cycle_history", json.dumps(merged_history)
            )
            total = await db_mod.count_samples(conn)
            await db_mod.update_device_seen(
                conn,
                device_id=device.id,
                name=body.machine_name,
                last_seen_utc=now,
                last_sample_count=total,
                last_push_count=len(normalized),
            )
            await conn.commit()

        return {
            "accepted": accepted,
            "duplicates": duplicates,
            "total_samples": total,
            "server_time": now,
        }

    # -- pull -------------------------------------------------------------
    @app.get("/api/v1/pull")
    async def pull(device: db_mod.Device = Depends(current_device)):
        now = utc_now_canonical()
        async with _open_db(resolved) as conn:
            stored_start, stored_active, stored_history = await _read_cycle_state(conn)
            samples = await db_mod.get_all_samples(conn)
            total = len(samples)
            await db_mod.update_device_seen(
                conn,
                device_id=device.id,
                last_seen_utc=now,
                last_sample_count=total,
            )
            await conn.commit()
        return {
            "cycle_start_utc": stored_start,
            "active_cycle": stored_active,
            "cycle_history": stored_history,
            "samples": samples,
            "server_time": now,
        }

    # -- web UI -----------------------------------------------------------
    def _device_rows(devices: list[db_mod.Device]) -> list[dict[str, Any]]:
        rows = []
        for d in devices:
            rows.append(
                {
                    "id": d.id,
                    "name": d.name,
                    "token_prefix": d.token_prefix,
                    "created_utc": d.created_utc,
                    "last_seen_utc": d.last_seen_utc,
                    "status": presence_status(d.last_seen_utc),
                    "last_sample_count": d.last_sample_count,
                    "last_push_count": d.last_push_count,
                }
            )
        return rows

    @app.get("/login", response_class=HTMLResponse)
    async def login_get(request: Request):
        return TEMPLATES.TemplateResponse(
            "login.html", {"request": request, "error": None}
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login_post(request: Request, password: str = Form(default="")):
        async with _open_db(resolved) as conn:
            stored = await db_mod.get_meta(conn, "admin_hash")
        ok = stored is not None and verify_admin_password(password, stored)
        if not ok:
            return TEMPLATES.TemplateResponse(
                "login.html",
                {"request": request, "error": "Wrong password"},
                status_code=200,
            )
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(
            SESSION_COOKIE,
            create_session_value(resolved.secret_key),
            httponly=True,
            samesite="lax",
        )
        return resp

    @app.post("/logout")
    async def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            devices = await db_mod.list_devices(conn)
            stored_start, stored_active, _ = await _read_cycle_state(conn)
            total = await db_mod.count_samples(conn)
        last_push = None
        seen_times = [d.last_seen_utc for d in devices if d.last_seen_utc]
        if seen_times:
            last_push = max(seen_times)
        return TEMPLATES.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "device_count": len(devices),
                "total_samples": total,
                "active_cycle": stored_active,
                "cycle_start_utc": stored_start,
                "last_push": last_push,
            },
        )

    @app.get("/tokens", response_class=HTMLResponse)
    async def tokens_get(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            devices = await db_mod.list_devices(conn)
        return TEMPLATES.TemplateResponse(
            "tokens.html",
            {"request": request, "devices": _device_rows(devices), "new_token": None},
        )

    @app.post("/tokens", response_class=HTMLResponse)
    async def tokens_post(request: Request, name: str = Form(default="")):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        clean = name.strip()
        if not clean or len(clean) > 64:
            async with _open_db(resolved) as conn:
                devices = await db_mod.list_devices(conn)
            return TEMPLATES.TemplateResponse(
                "tokens.html",
                {
                    "request": request,
                    "devices": _device_rows(devices),
                    "new_token": None,
                    "error": "Name must be 1-64 characters",
                },
            )
        raw, token_hash, prefix = generate_token()
        now = utc_now_canonical()
        async with _open_db(resolved) as conn:
            new_id = await db_mod.create_device(
                conn,
                name=clean,
                token_hash=token_hash,
                token_prefix=prefix,
                created_utc=now,
            )
            await conn.commit()
        return TEMPLATES.TemplateResponse(
            "token_created.html",
            {
                "request": request,
                "raw_token": raw,
                "device_name": clean,
                "device_id": new_id,
            },
        )

    @app.post("/tokens/{device_id}/delete")
    async def tokens_delete(request: Request, device_id: int):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            await db_mod.delete_device(conn, device_id)
            await conn.commit()
        return RedirectResponse("/tokens", status_code=303)

    @app.get("/machines", response_class=HTMLResponse)
    async def machines(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            devices = await db_mod.list_devices(conn)
        return TEMPLATES.TemplateResponse(
            "machines.html",
            {"request": request, "devices": _device_rows(devices)},
        )

    @app.get("/data", response_class=HTMLResponse)
    async def data_page(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            _, stored_active, stored_history = await _read_cycle_state(conn)
            samples = await db_mod.get_all_samples(conn)
        earliest = samples[0]["ts"] if samples else None
        latest = samples[-1]["ts"] if samples else None
        return TEMPLATES.TemplateResponse(
            "data.html",
            {
                "request": request,
                "active_cycle": stored_active,
                "history_count": len(stored_history),
                "history": stored_history,
                "sample_count": len(samples),
                "earliest": earliest,
                "latest": latest,
                "recent": samples[-20:][::-1],
            },
        )

    @app.get("/backup", response_class=HTMLResponse)
    async def backup_page(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        return TEMPLATES.TemplateResponse(
            "backup.html", {"request": request, "message": None, "error": None}
        )

    @app.get("/backup/export")
    async def backup_export(request: Request):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        async with _open_db(resolved) as conn:
            stored_start, stored_active, stored_history = await _read_cycle_state(conn)
            samples = await db_mod.get_all_samples(conn)
        payload = backup_mod.build_export_zip(
            samples=samples,
            cycle_start_utc=stored_start,
            active_cycle=stored_active,
            cycle_history=stored_history,
        )
        stamp = utc_now_canonical().replace(":", "").replace("-", "")
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=cursorpace-backup-{stamp}.zip"
                )
            },
        )

    @app.post("/backup/import", response_class=HTMLResponse)
    async def backup_import(request: Request, file: UploadFile = File(...)):
        if not require_admin_redirect(request):
            return RedirectResponse("/login", status_code=303)
        raw = await file.read()
        try:
            parsed = backup_mod.parse_import_zip(raw)
        except ValueError as exc:
            return TEMPLATES.TemplateResponse(
                "backup.html",
                {"request": request, "message": None, "error": str(exc)},
            )
        samples = parsed["samples"]
        assert isinstance(samples, list)
        async with _open_db(resolved) as conn:
            await db_mod.clear_samples(conn)
            await db_mod.insert_samples_ignore(
                conn,
                [
                    (s["ts"], s["cursor"], s["other"], "")
                    for s in samples  # type: ignore[misc]
                ],
            )
            cycle_start_utc = parsed["cycle_start_utc"]
            if cycle_start_utc is not None:
                await db_mod.set_meta(
                    conn, "cycle_start_utc", str(cycle_start_utc)
                )
            else:
                await conn.execute(
                    "DELETE FROM meta WHERE key = 'cycle_start_utc'"
                )
            active_cycle = parsed["active_cycle"]
            if active_cycle is not None:
                await db_mod.set_meta(
                    conn, "active_cycle", json.dumps(active_cycle)
                )
            else:
                await conn.execute("DELETE FROM meta WHERE key = 'active_cycle'")
            await db_mod.set_meta(
                conn, "cycle_history", json.dumps(parsed["cycle_history"])
            )
            await conn.commit()
        return TEMPLATES.TemplateResponse(
            "backup.html",
            {
                "request": request,
                "message": (
                    f"Imported {len(samples)} samples, "
                    f"{len(parsed['cycle_history']) if isinstance(parsed['cycle_history'], list) else 0} history entries."
                ),
                "error": None,
            },
        )

    # Store lifespan manually for older TestClient without lifespan support:
    # TestClient in recent httpx-based versions handles lifespan via `with`.
    # uvicorn uses the lifespan passed to the FastAPI constructor above.

    return app


# Default app instance for `uvicorn app.main:app`.
app = create_app()
