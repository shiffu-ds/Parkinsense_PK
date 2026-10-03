"""Encrypted database + private-media snapshot, requiring a paused-write maintenance window."""

import argparse
import base64
from datetime import date, datetime
from decimal import Decimal
from getpass import getpass
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import MetaData, select

from backend.config import get_settings
from backend.db import get_engine

MAGIC = b"PSPKBACKUP\x01"
CHUNK_SIZE = 256 * 1024
MAX_RESTORE_BYTES = 20 * 1024 * 1024 * 1024


def load_models():
    """Register project schema without connecting to or changing the source database."""
    import backend.db.models  # noqa: F401
    model_dir = Path(__file__).resolve().parents[1] / "backend" / "db"
    for source in sorted(model_dir.glob("*_models.py")):
        importlib.import_module(f"backend.db.{source.stem}")


def _private_directory(path: Path) -> Path:
    if not path.is_dir() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("Use an existing private directory with permission 700.")
    return path.resolve()


def _key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not 16 <= len(passphrase) <= 1024:
        raise ValueError("Use a separate backup passphrase of 16 to 1024 characters.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_file(source: Path, output: Path, passphrase: str) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("Backup output must be a new file.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    pending = output.with_name(f".{output.name}.{secrets.token_hex(8)}.pending")
    try:
        with source.open("rb") as handle, os.fdopen(os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as encrypted:
            encrypted.write(header)
            while chunk := handle.read(CHUNK_SIZE):
                encrypted.write(encryptor.update(chunk))
            encrypted.write(encryptor.finalize())
            encrypted.write(encryptor.tag)
            encrypted.flush()
            os.fsync(encrypted.fileno())
        # Atomic publication with no overwrite, even if another job chose the same filename.
        os.link(pending, output, follow_symlinks=False)
    finally:
        pending.unlink(missing_ok=True)


def decrypt_file(source: Path, output: Path, passphrase: str) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("Decryption output must be a new file.")
    if source.is_symlink() or source.stat().st_size > MAX_RESTORE_BYTES:
        raise ValueError("Invalid or oversized encrypted backup.")
    header_size = len(MAGIC) + 28
    try:
        with source.open("rb") as encrypted:
            header = encrypted.read(header_size)
            if not header.startswith(MAGIC) or len(header) != header_size:
                raise ValueError("Unsupported backup format.")
            salt, nonce = header[len(MAGIC):len(MAGIC) + 16], header[-12:]
            encrypted.seek(-16, 2)
            tag = encrypted.read(16)
            remaining = encrypted.tell() - header_size - 16
            if remaining < 0:
                raise ValueError("Truncated backup.")
            encrypted.seek(header_size)
            decryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(header)
            with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                while remaining:
                    chunk = encrypted.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ValueError("Truncated backup.")
                    handle.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                handle.write(decryptor.finalize())
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def _encoded(value):
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    # Column values are wrapped so a patient's JSON containing "$type" cannot be confused with a scalar.
    return {"$type": "json", "value": value}


def decoded(value):
    if not isinstance(value, dict) or set(value) != {"$type", "value"}:
        raise ValueError("Invalid backup database value.")
    kind, payload = value["$type"], value["value"]
    if kind == "datetime":
        return datetime.fromisoformat(payload)
    if kind == "date":
        return date.fromisoformat(payload)
    if kind == "decimal":
        return Decimal(payload)
    if kind == "bytes":
        return base64.b64decode(payload, validate=True)
    if kind == "json":
        return payload
    raise ValueError("Unsupported backup database value.")


def database_snapshot(output: Path) -> dict:
    load_models()
    engine = get_engine()
    tables = MetaData()
    tables.reflect(bind=engine)
    options = {"isolation_level": "REPEATABLE READ"} if engine.dialect.name == "postgresql" else {}
    # A single database transaction ensures all rows share one source snapshot.
    counts = {}
    with engine.connect().execution_options(**options) as connection, connection.begin(), output.open("w", encoding="utf-8") as handle:
        def write(value):
            handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        write({"format": "parkinsense-logical-db-v1"})
        for table in tables.sorted_tables:
            write({"kind": "table", "name": table.name, "columns": list(table.columns.keys())})
            count = 0
            for row in connection.execute(select(table)).yield_per(500).mappings():
                write({"kind": "row", "table": table.name,
                       "values": {column: _encoded(value) for column, value in row.items()}})
                count += 1
            counts[table.name] = count
        write({"kind": "complete", "counts": counts})
    output.chmod(0o600)
    return counts


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(output: Path, passphrase: str, *, writes_paused: bool) -> dict:
    if writes_paused is not True:
        raise ValueError("Pause application/gateway writes, then explicitly acknowledge the maintenance window.")
    output = output.expanduser().absolute()
    parent = _private_directory(output.parent)
    root = get_settings().storage_root
    if root.is_symlink():
        raise ValueError("Private media root cannot be a symlink.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = root.resolve()
    if output.is_relative_to(root):
        raise ValueError("Store encrypted backups outside the source media directory.")
    _key(passphrase, secrets.token_bytes(16))  # Validate the passphrase before reading private records.
    with tempfile.TemporaryDirectory(prefix=".parkinsense-backup-", dir=parent) as temp_name:
        temp = Path(temp_name)
        database = temp / "database.jsonl"
        counts = database_snapshot(database)
        archive = temp / "snapshot.tar"
        manifest = {"format": "parkinsense-encrypted-snapshot-v1", "created_at": datetime.now().astimezone().isoformat(),
                    "writes_paused_attested": True, "database_counts": counts, "files": []}
        with tarfile.open(archive, "w") as bundle:
            sources = [(database, "database.jsonl")]
            for path in sorted(root.rglob("*")):
                if path.is_symlink() or (not path.is_dir() and not stat.S_ISREG(path.stat().st_mode)):
                    raise ValueError("Private media must contain only regular files/directories, without symlinks.")
                if path.is_file():
                    if path.name.endswith(".pending"):
                        raise ValueError("An unfinished upload is present. Wait for writes to finish before backing up.")
                    sources.append((path, "media/" + path.relative_to(root).as_posix()))
            for path, name in sources:
                before = path.stat()
                checksum = _digest(path)
                info = bundle.gettarinfo(str(path), arcname=name)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o600
                with path.open("rb") as handle:
                    bundle.addfile(info, handle)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Source media changed during backup. Keep writes paused and retry.")
                manifest["files"].append({"name": name, "size_bytes": before.st_size, "sha256": checksum})
            manifest_data = json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode("utf-8")
            manifest_file = temp / "manifest.json"
            manifest_file.write_bytes(manifest_data)
            manifest_file.chmod(0o600)
            bundle.add(manifest_file, arcname="manifest.json", recursive=False)
        archive.chmod(0o600)
        encrypt_file(archive, output, passphrase)
    return {"tables": len(counts), "media_files": len(manifest["files"]) - 1,
            "encrypted_bytes": output.stat().st_size, "sha256": _digest(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New encrypted file in an existing private backup directory.")
    parser.add_argument("--writes-paused", action="store_true", required=True)
    args = parser.parse_args()
    passphrase = getpass("Separate backup passphrase (at least 16 characters): ")
    if passphrase != getpass("Confirm backup passphrase: "):
        raise SystemExit("Passphrases do not match.")
    try:
        result = create_backup(args.output, passphrase, writes_paused=args.writes_paused)
    except (ValueError, OSError):
        raise SystemExit("Backup could not be completed. Check the private output directory and paused-write window.") from None
    print(f"Encrypted snapshot created: {result['tables']} tables and {result['media_files']} private media files.")
    print(f"Encrypted file SHA-256: {result['sha256']}")
    print("Run restore_drill.py against a new private directory before treating this snapshot as recoverable.")


if __name__ == "__main__":
    main()
