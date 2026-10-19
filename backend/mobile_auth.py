"""Expiring patient API sessions, tied to the existing password-reset revision."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import sqlite3
import threading
import time
from uuid import UUID

from backend import services
from backend.config import get_settings
from backend.production import verify_session_revision

SESSION_SECONDS = 12 * 60 * 60


def load_secret() -> bytes:
    """Create a private, durable signing key without putting it in the APK."""
    configured = os.getenv("PARKINSENSE_MOBILE_SECRET")
    if configured:
        if len(configured.encode()) < 32:
            raise ValueError("PARKINSENSE_MOBILE_SECRET must contain at least 32 bytes.")
        return configured.encode()
    root = get_settings().storage_root
    if root.is_symlink():
        raise ValueError("Private storage root cannot be a symlink.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    path = root / "mobile-api.key"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags, 0o600), "wb") as handle:
            handle.write(secrets.token_bytes(64))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        pass
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError("The mobile signing key must be an owned private regular file.")
        os.fchmod(handle.fileno(), 0o600)
        value = handle.read(129)
    if not 32 <= len(value) <= 128:
        raise ValueError("The mobile signing key is invalid.")
    return value


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_token(user: dict, secret: bytes) -> str:
    if user.get("role") != "patient" or not user.get("patient_id"):
        raise PermissionError("Use an active patient account.")
    now = int(time.time())
    payload = {"v": 1, "sub": user["id"], "rev": user["_auth_revision"],
               "iat": now, "exp": now + SESSION_SECONDS, "jti": secrets.token_urlsafe(32)}
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _encode(hmac.digest(secret, encoded.encode(), "sha256"))
    return f"{encoded}.{signature}"


def decode_token(token: str, secret: bytes) -> dict:
    error = PermissionError("Your session has expired. Please sign in again.")
    if not isinstance(token, str) or len(token) > 1024 or token.count(".") != 1:
        raise error
    try:
        encoded, signature = token.split(".")
        expected = _encode(hmac.digest(secret, encoded.encode("ascii"), "sha256"))
        if not hmac.compare_digest(signature, expected):
            raise error
        value = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True))
        if not isinstance(value, dict) or value.get("v") != 1:
            raise error
        if str(UUID(value["sub"])) != value["sub"]:
            raise error
        if any(type(value.get(name)) is not int for name in ("rev", "iat", "exp")):
            raise error
        now = int(time.time())
        if value["iat"] > now + 30 or value["exp"] <= now or value["exp"] - value["iat"] != SESSION_SECONDS:
            raise error
        if value["rev"] < 0 or not isinstance(value.get("jti"), str) or len(value["jti"]) != 43:
            raise error
        return value
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise error from None


def authenticate_token(token: str, secret: bytes, registry: "SessionRegistry") -> dict:
    payload = decode_token(token, secret)
    registry.verify(payload)
    verify_session_revision(payload["sub"], payload["rev"])
    user = services.get_user(payload["sub"])
    if user["role"] != "patient" or not user.get("patient_id"):
        raise PermissionError("Use an active patient account.")
    user["_auth_revision"] = payload["rev"]
    user["_mobile_jti"] = payload["jti"]
    return user


class SessionRegistry:
    """Separate private database for durable, per-device mobile sign-out.

    No current web session or application ORM schema is changed. Only a hash of
    each session nonce and its expiry are stored; the bearer token is never kept.
    """
    def __init__(self, path: Path):
        self.path, self._lock = Path(path), threading.Lock()
        root = self.path.parent
        if root.is_symlink():
            raise ValueError("Private storage root cannot be a symlink.")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise ValueError("The mobile session registry must be an owned private regular file.")
            os.fchmod(handle.fileno(), 0o600)
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS sessions (nonce_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL)")

    @staticmethod
    def _hash(jti):
        return hashlib.sha256(jti.encode()).hexdigest()

    def issue(self, payload: dict):
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM sessions WHERE expires <= ?", (int(time.time()),))
            connection.execute("INSERT INTO sessions(nonce_hash, expires) VALUES (?, ?)",
                               (self._hash(payload["jti"]), payload["exp"]))

    def verify(self, payload: dict):
        with self._lock, sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT expires FROM sessions WHERE nonce_hash = ?", (self._hash(payload["jti"]),)).fetchone()
        if row is None or row[0] != payload["exp"] or row[0] <= int(time.time()):
            raise PermissionError("Your session has expired. Please sign in again.")

    def logout(self, user: dict):
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM sessions WHERE nonce_hash = ?", (self._hash(user["_mobile_jti"]),))
        services.record_logout(user["id"])


class RateLimiter:
    """Small bounded per-process login/register limiter; no emails or tokens kept."""
    def __init__(self):
        self._entries: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity: str, *, limit: int = 10, seconds: int = 60) -> bool:
        key = hashlib.sha256(identity.encode()).hexdigest()
        now = time.monotonic()
        with self._lock:
            if len(self._entries) >= 2048:
                self._entries = {name: values for name, values in self._entries.items()
                                 if values and values[-1] > now - 60}
                if len(self._entries) >= 2048 and key not in self._entries:
                    return False
            values = [value for value in self._entries.get(key, []) if value > now - seconds]
            self._entries[key] = values
            if len(values) >= limit:
                return False
            values.append(now)
            return True
