"""Authenticate and restore a snapshot into a NEW isolated SQLite/media directory only."""

import argparse
from getpass import getpass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, event, select, func

from backend.db.models import Base
from scripts.backup_private import MAX_RESTORE_BYTES, _digest, _private_directory, decoded, decrypt_file, load_models

MAX_LINE_BYTES = 24 * 1024 * 1024


def safe_extract(archive: Path, target: Path) -> dict:
    """Do not use extractall: reject links, traversal, duplicate names and unbounded expansion."""
    names, total = set(), 0
    with tarfile.open(archive, "r:") as bundle:
        for entry in bundle:
            key = PurePosixPath(entry.name)
            if entry.name in names or key.is_absolute() or ".." in key.parts or "\\" in entry.name or not entry.isfile():
                raise ValueError("Unsafe backup archive member.")
            if entry.name not in {"database.jsonl", "manifest.json"} and not entry.name.startswith("media/"):
                raise ValueError("Unexpected backup archive member.")
            if entry.size < 0 or total + entry.size > MAX_RESTORE_BYTES:
                raise ValueError("Backup expansion exceeds the restore limit.")
            total += entry.size
            names.add(entry.name)
            path = target.joinpath(*key.parts)
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError("Unsafe backup archive path.")
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            for parent in [path.parent, *path.parent.parents]:
                if parent == target.parent:
                    break
                parent.chmod(0o700)
            incoming = bundle.extractfile(entry)
            with incoming, os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                shutil.copyfileobj(incoming, handle, length=256 * 1024)
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_LINE_BYTES:
        raise ValueError("Backup manifest is missing or oversized.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "parkinsense-encrypted-snapshot-v1" or manifest.get("writes_paused_attested") is not True:
        raise ValueError("Unsupported backup manifest.")
    expected = {"manifest.json"}
    for item in manifest.get("files", []):
        name = item.get("name")
        if not isinstance(name, str) or name in expected or name not in names:
            raise ValueError("Manifest file inventory is invalid.")
        expected.add(name)
        path = target / name
        if path.stat().st_size != item.get("size_bytes") or _digest(path) != item.get("sha256"):
            raise ValueError("Backup checksum verification failed.")
    if names != expected or "database.jsonl" not in expected:
        raise ValueError("Backup file inventory does not match its manifest.")
    return manifest


def restore_database(snapshot: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("Drill database must be a new file.")
    load_models()
    engine = create_engine(f"sqlite:///{output}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(engine)
        counts, seen, completed = {}, set(), False
        with snapshot.open("rb") as handle, engine.begin() as connection:
            first = handle.readline(MAX_LINE_BYTES + 1)
            if len(first) > MAX_LINE_BYTES or json.loads(first).get("format") != "parkinsense-logical-db-v1":
                raise ValueError("Unsupported database snapshot.")
            while line := handle.readline(MAX_LINE_BYTES + 1):
                if len(line) > MAX_LINE_BYTES or completed:
                    raise ValueError("Oversized or trailing database snapshot data.")
                item = json.loads(line)
                if item.get("kind") == "table":
                    name = item.get("name")
                    table = Base.metadata.tables.get(name)
                    if table is None or name in seen or item.get("columns") != list(table.columns.keys()):
                        raise ValueError("Snapshot schema does not match this application version.")
                    counts[name] = 0
                    seen.add(name)
                elif item.get("kind") == "row":
                    name = item.get("table")
                    table = Base.metadata.tables.get(name)
                    values = item.get("values")
                    if name not in seen or not isinstance(values, dict) or set(values) != set(table.columns.keys()):
                        raise ValueError("Invalid database snapshot row.")
                    connection.execute(table.insert().values({key: decoded(value) for key, value in values.items()}))
                    counts[name] += 1
                elif item.get("kind") == "complete" and item.get("counts") == counts:
                    completed = True
                else:
                    raise ValueError("Incomplete or invalid database snapshot.")
            if not completed:
                raise ValueError("Incomplete database snapshot.")
            for name, count in counts.items():
                actual = connection.scalar(select(func.count()).select_from(Base.metadata.tables[name]))
                if actual != count:
                    raise ValueError("Restored database row counts do not match.")
        output.chmod(0o600)
        return counts
    finally:
        engine.dispose()


def restore_drill(source: Path, output_directory: Path, passphrase: str) -> dict:
    output_directory = output_directory.expanduser().absolute()
    parent = _private_directory(output_directory.parent)
    if output_directory.exists() or output_directory.is_symlink():
        raise ValueError("A restore drill must use a NEW directory; existing directories are never overwritten.")
    made_output = False
    try:
        with tempfile.TemporaryDirectory(prefix=".parkinsense-restore-", dir=parent) as temp_name:
            temp = Path(temp_name)
            archive = temp / "verified.tar"
            # Authentication completes before the archive is opened or any production-like records are restored.
            decrypt_file(source, archive, passphrase)
            staging = temp / "staging"
            staging.mkdir(mode=0o700)
            manifest = safe_extract(archive, staging)
            counts = restore_database(staging / "database.jsonl", staging / "drill.sqlite3")
            if counts != manifest.get("database_counts"):
                raise ValueError("Database row counts do not match the encrypted manifest.")
            (staging / "database.jsonl").unlink()
            output_directory.mkdir(mode=0o700)
            made_output = True
            for entry in staging.iterdir():
                shutil.move(str(entry), output_directory / entry.name)
            result = {"format": "parkinsense-restore-drill-v1", "checksums_verified": True,
                      "database_counts": counts, "media_files": len(manifest["files"]) - 1,
                      "production_database_modified": False}
            report = output_directory / "restore-verification.json"
            report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            report.chmod(0o600)
            return result
    except BaseException:
        if made_output:
            shutil.rmtree(output_directory)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True, help="NEW directory beneath a private 700 parent.")
    args = parser.parse_args()
    try:
        result = restore_drill(args.input, args.output_directory, getpass("Backup passphrase: "))
    except (InvalidTag, ValueError, OSError, json.JSONDecodeError):
        raise SystemExit("Restore drill failed authentication, schema, checksum, or directory checks. Production was not modified.") from None
    print(f"Restore drill verified {len(result['database_counts'])} tables and {result['media_files']} private media files.")
    print("The isolated drill directory contains private health data. Keep it private and remove it after the drill.")


if __name__ == "__main__":
    main()
