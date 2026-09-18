"""Environment configuration parsing (spec section 4)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    port: int
    secret_key: str
    secret_key_was_generated: bool


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    port = int(os.environ.get("PORT", "8080"))

    secret_key = os.environ.get("SECRET_KEY")
    was_generated = False
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        was_generated = True
    return Settings(
        data_dir=data_dir,
        port=port,
        secret_key=secret_key,
        secret_key_was_generated=was_generated,
    )


def ensure_data_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
