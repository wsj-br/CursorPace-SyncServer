"""Environment configuration parsing (spec section 4)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

SECRET_KEY_FILENAME = ".secret_key"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    port: int
    secret_key: str = ""


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    port = int(os.environ.get("PORT", "7050"))
    return Settings(data_dir=data_dir, port=port)


def ensure_data_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key_path(data_dir: Path) -> Path:
    return data_dir / SECRET_KEY_FILENAME


def write_secret_key(data_dir: Path, value: str) -> None:
    """Write `$DATA_DIR/.secret_key` with mode 0600."""
    text = value.strip()
    if not text:
        raise ValueError("secret key must not be empty")
    ensure_data_dir(data_dir)
    path = secret_key_path(data_dir)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (text + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def load_or_create_secret_key(data_dir: Path) -> str:
    ensure_data_dir(data_dir)
    path = secret_key_path(data_dir)
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            os.chmod(path, 0o600)
            return existing
    value = secrets.token_urlsafe(32)
    write_secret_key(data_dir, value)
    return value
