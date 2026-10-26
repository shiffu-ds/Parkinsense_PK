"""Bounded private uploads. Client filenames never become storage paths."""

import hashlib
from io import BytesIO
import mimetypes
import os
from pathlib import Path, PurePosixPath
import time
from uuid import UUID, uuid4

from backend.config import get_settings

EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wav", ".ogg", ".webm", ".mp3", ".m4a", ".flac"}
# Live camera clips are written here before analysis. A clip lasts at most 45
# seconds, so anything untouched for this long belongs to a session that ended
# without logging out (closed tab, expired session, server restart).
CAPTURE_MAX_AGE_SECONDS = 12 * 3600


def _private_root() -> Path:
    root = get_settings().storage_root
    if root.is_symlink():
        raise ValueError("Private storage root cannot be a symlink.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root.resolve()


def capture_root() -> Path:
    """Owner-only directory for in-progress live camera clips."""
    root = _private_root() / "capture"
    if root.is_symlink():
        raise ValueError("Private storage cannot contain symlinks.")
    root.mkdir(mode=0o700, exist_ok=True)
    root.chmod(0o700)
    return root


def sweep_stale_captures(max_age_seconds: float = CAPTURE_MAX_AGE_SECONDS, now: float | None = None) -> int:
    """Delete abandoned live-capture clips; returns how many were removed.

    Only the app's own ``tmp*.avi`` files are considered. An in-use clip is
    either being written (fresh mtime) or is recreated by the camera writer.
    """
    root = capture_root()
    cutoff = (time.time() if now is None else now) - max_age_seconds
    removed = 0
    for path in root.iterdir():
        if not (path.name.startswith("tmp") and path.suffix == ".avi") or path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def resolve_key(storage_key: str) -> Path:
    if not isinstance(storage_key, str):
        raise ValueError("Invalid storage key.")
    key = PurePosixPath(storage_key)
    if key.is_absolute() or ".." in key.parts or "\\" in storage_key or len(key.parts) != 3:
        raise ValueError("Invalid storage key.")
    root = _private_root()
    target = root.joinpath(*key.parts)
    for part in [target.parent.parent, target.parent, target]:
        if part.is_symlink():
            raise ValueError("Private storage cannot contain symlinks.")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Private file must stay within private storage.")
    return target


def write_upload(patient_id: str, assessment_id: str, module: str, filename: str, data) -> dict:
    UUID(patient_id)
    UUID(assessment_id)
    if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename:
        raise ValueError("Upload filename must be a plain filename.")
    extension = Path(filename).suffix.lower()
    if extension not in EXTENSIONS:
        raise ValueError("Unsupported media format.")
    key = f"patient_{patient_id}/assessment_{assessment_id}/{module}_{uuid4()}{extension}"
    target = resolve_key(key)
    target.parent.parent.mkdir(mode=0o700, exist_ok=True)
    target.parent.mkdir(mode=0o700, exist_ok=True)
    target.parent.parent.chmod(0o700)
    target.parent.chmod(0o700)
    stream = BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    if not hasattr(stream, "read"):
        raise ValueError("Upload must contain bytes or a binary file.")
    temp = target.with_suffix(target.suffix + ".pending")
    size = 0
    digest = hashlib.sha256()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(temp, flags, 0o600), "wb") as handle:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ValueError("Upload must be a binary stream.")
                size += len(chunk)
                if size > get_settings().max_upload_bytes:
                    raise ValueError("Upload exceeds the configured size limit.")
                handle.write(chunk)
                digest.update(chunk)
            if not size:
                raise ValueError("Empty media cannot be saved.")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return {"storage_key": key, "size_bytes": size, "sha256": digest.hexdigest(),
            "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}
