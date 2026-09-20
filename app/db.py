"""SQLite access via aiosqlite, plain SQL, no ORM (spec section 5)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


DDL = """
CREATE TABLE IF NOT EXISTS samples (
    ts TEXT PRIMARY KEY,
    cursor TEXT NOT NULL,
    other TEXT NOT NULL,
    source_machine TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    token_prefix TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    last_seen_utc TEXT,
    last_sample_count INTEGER NOT NULL DEFAULT 0,
    last_push_count INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class Device:
    id: int
    name: str
    token_hash: str
    token_prefix: str
    created_utc: str
    last_seen_utc: str | None
    last_sample_count: int
    last_push_count: int


def db_path_for(data_dir: Path) -> Path:
    return data_dir / "sync.db"


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(DDL)
        await db.commit()


async def snapshot_database(db_path: Path) -> bytes:
    """Consistent SQLite snapshot bytes (no WAL/SHM sidecars)."""
    dest = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    dest.close()
    dest_path = Path(dest.name)
    try:
        async with aiosqlite.connect(str(db_path)) as src:
            async with aiosqlite.connect(str(dest_path)) as dst:
                await src.backup(dst)
        return dest_path.read_bytes()
    finally:
        dest_path.unlink(missing_ok=True)


async def get_meta(db: aiosqlite.Connection, key: str) -> str | None:
    async with db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def set_meta(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def get_all_samples(
    db: aiosqlite.Connection,
) -> list[dict[str, str]]:
    async with db.execute(
        "SELECT ts, cursor, other FROM samples ORDER BY ts ASC"
    ) as cur:
        rows = await cur.fetchall()
    return [{"ts": r[0], "cursor": r[1], "other": r[2]} for r in rows]


async def count_samples(db: aiosqlite.Connection) -> int:
    async with db.execute("SELECT COUNT(*) FROM samples") as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def sample_bounds(
    db: aiosqlite.Connection,
) -> tuple[str | None, str | None]:
    async with db.execute("SELECT MIN(ts), MAX(ts) FROM samples") as cur:
        row = await cur.fetchone()
    if not row or not row[0]:
        return None, None
    return str(row[0]), str(row[1])


async def get_recent_samples(
    db: aiosqlite.Connection, limit: int = 20
) -> list[dict[str, str]]:
    async with db.execute(
        "SELECT ts, cursor, other FROM samples ORDER BY ts DESC LIMIT ?",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [{"ts": r[0], "cursor": r[1], "other": r[2]} for r in rows]


async def insert_samples_ignore(
    db: aiosqlite.Connection,
    samples: list[tuple[str, str, str, str]],
) -> tuple[int, int]:
    """INSERT OR IGNORE a batch. Returns (accepted, duplicates)."""
    accepted = 0
    duplicates = 0
    for ts, cursor, other, source_machine in samples:
        before = db.total_changes
        await db.execute(
            "INSERT OR IGNORE INTO samples (ts, cursor, other, source_machine)"
            " VALUES (?, ?, ?, ?)",
            (ts, cursor, other, source_machine),
        )
        if db.total_changes > before:
            accepted += 1
        else:
            duplicates += 1
    return accepted, duplicates


async def clear_samples(db: aiosqlite.Connection) -> None:
    await db.execute("DELETE FROM samples")


def _device_from_row(row: tuple) -> Device:
    return Device(
        id=row[0],
        name=row[1],
        token_hash=row[2],
        token_prefix=row[3],
        created_utc=row[4],
        last_seen_utc=row[5],
        last_sample_count=row[6],
        last_push_count=row[7],
    )


async def list_devices(db: aiosqlite.Connection) -> list[Device]:
    async with db.execute(
        "SELECT id, name, token_hash, token_prefix, created_utc,"
        " last_seen_utc, last_sample_count, last_push_count"
        " FROM devices ORDER BY id ASC"
    ) as cur:
        rows = await cur.fetchall()
    return [_device_from_row(r) for r in rows]


async def get_device_by_token_hash(
    db: aiosqlite.Connection, token_hash: str
) -> Device | None:
    async with db.execute(
        "SELECT id, name, token_hash, token_prefix, created_utc,"
        " last_seen_utc, last_sample_count, last_push_count"
        " FROM devices WHERE token_hash = ?",
        (token_hash,),
    ) as cur:
        row = await cur.fetchone()
    return _device_from_row(row) if row else None


async def create_device(
    db: aiosqlite.Connection,
    *,
    name: str,
    token_hash: str,
    token_prefix: str,
    created_utc: str,
) -> int:
    cur = await db.execute(
        "INSERT INTO devices (name, token_hash, token_prefix, created_utc)"
        " VALUES (?, ?, ?, ?)",
        (name, token_hash, token_prefix, created_utc),
    )
    return int(cur.lastrowid or 0)


async def update_device_seen(
    db: aiosqlite.Connection,
    *,
    device_id: int,
    name: str | None = None,
    last_seen_utc: str,
    last_sample_count: int | None = None,
    last_push_count: int | None = None,
) -> None:
    sets: list[str] = ["last_seen_utc = ?"]
    params: list[object] = [last_seen_utc]
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if last_sample_count is not None:
        sets.append("last_sample_count = ?")
        params.append(last_sample_count)
    if last_push_count is not None:
        sets.append("last_push_count = ?")
        params.append(last_push_count)
    params.append(device_id)
    await db.execute(
        f"UPDATE devices SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )


async def delete_device(db: aiosqlite.Connection, device_id: int) -> None:
    await db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
