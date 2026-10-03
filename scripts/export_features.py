"""Authorized developer export into ignored local feature storage.

UUIDs are pseudonymous patient identifiers, not proof of anonymization. No
raw media, transcripts, names, emails or arbitrary clinical prose are exported.
"""

import argparse
from getpass import getpass
import os
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import services
from backend.db import init_db
from ml.common.tables import feature_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", type=UUID, help="Required for clinician exports; patients can omit this.")
    parser.add_argument("--filename", default="features.parquet", help="Plain .parquet filename under ignored data/features.")
    args = parser.parse_args()
    if Path(args.filename).name != args.filename or not args.filename.endswith(".parquet") or "\\" in args.filename:
        parser.error("Use a plain .parquet filename.")
    init_db()
    try:
        user = services.authenticate(input("Account email: "), getpass("Password: "))
        patient_id = str(args.patient_id) if args.patient_id else user.get("patient_id")
        if not patient_id:
            raise ValueError("Select an assigned patient using --patient-id.")
        table = feature_table(patient_id, services.list_assessments(user["id"], patient_id))
        if table.empty:
            raise ValueError("No accepted task measurements are available to export.")
        directory = ROOT / "data" / "features"
        if directory.is_symlink():
            raise ValueError("Feature storage cannot be a symlink.")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        target = directory / args.filename
        if target.exists() or target.is_symlink():
            raise ValueError("That export already exists. Choose a new filename to preserve it.")
        # Exclusively create private output before writing any patient measurements.
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600), "wb") as handle:
            table.to_parquet(handle, index=False)
        services.record_tool_audit(user["id"], "export_feature_table")
    except (ValueError, PermissionError, LookupError) as exc:
        parser.error(str(exc))
    print(f"Exported {len(table)} visit rows to ignored data/features/{args.filename}. Review consent and reference targets before training.")


if __name__ == "__main__":
    main()
