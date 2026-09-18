"""Token hashing, admin password (scrypt), session cookies."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from itsdangerous import BadSignature, URLSafeSerializer

SESSION_COOKIE = "cursorpace_session"
DEFAULT_ADMIN_PASSWORD = "cursorpace01"
MIN_ADMIN_PASSWORD_LENGTH = 8

# scrypt params (stdlib hashlib.scrypt, no extra deps).
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_token(raw_token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(raw_token), token_hash)


def generate_token() -> tuple[str, str, str]:
    """Return (raw_token, token_hash, token_prefix)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw), raw[:8]


def hash_admin_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${dk.hex()}"


def is_default_admin_password(password: str) -> bool:
    return hmac.compare_digest(password, DEFAULT_ADMIN_PASSWORD)


def validate_new_admin_password(password: str, confirm: str) -> str | None:
    if not password:
        return "Enter a new password"
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_ADMIN_PASSWORD_LENGTH} characters"
    if is_default_admin_password(password):
        return "Choose something other than the default password"
    if password != confirm:
        return "Passwords do not match"
    return None


def verify_admin_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return hmac.compare_digest(dk, expected)


def _serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt="cursorpace-admin-session")


def create_session_value(secret_key: str, *, must_change: bool = False) -> str:
    payload: dict[str, bool] = {"admin": True}
    if must_change:
        payload["must_change"] = True
    return _serializer(secret_key).dumps(payload)


def load_session(secret_key: str, value: str | None) -> dict | None:
    if not value:
        return None
    try:
        data = _serializer(secret_key).loads(value)
    except BadSignature:
        return None
    if not isinstance(data, dict) or data.get("admin") is not True:
        return None
    return data


def verify_session_value(secret_key: str, value: str | None) -> bool:
    return load_session(secret_key, value) is not None
