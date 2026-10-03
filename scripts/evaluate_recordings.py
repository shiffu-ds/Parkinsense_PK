"""Evaluate an explicitly supplied, deidentified recording manifest offline."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.validation.evaluation import FIELDS, evaluate, normalize_rows


def _write_new(path, data):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("Do not write through a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, help="Write a blank CSV template; no example patients.")
    parser.add_argument("--protocol-template", type=Path, help="Alongside --template, write a blank protocol JSON.")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--protocol", type=Path, help="JSON with prespecified tolerance and minimum_participants.")
    parser.add_argument("--deidentified-consented", action="store_true",
                        help="Attest permission to evaluate these recordings and pseudonymous identifiers.")
    args = parser.parse_args()
    if args.template:
        _write_new(args.template, ",".join(FIELDS) + "\n")
        if args.protocol_template:
            _write_new(args.protocol_template, json.dumps({"prespecified_at": "", "reference_procedure": "",
                "measurement": {"task": "", "metric": "", "unit": "", "method_version": ""},
                "tolerance": None, "minimum_participants": None, "sampling_and_confounders": ""}, indent=2) + "\n")
        print("Blank validation template created. No recordings or results were added.")
        return
    if not (args.manifest and args.output and args.protocol and args.deidentified_consented):
        parser.error("Evaluation requires --manifest, --protocol, --output and --deidentified-consented.")
    if args.manifest.stat().st_size > 10 * 1024 * 1024 or args.protocol.stat().st_size > 100_000:
        parser.error("Manifest/protocol exceeds the bounded import size.")
    raw = args.manifest.read_bytes()
    with args.manifest.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or set(FIELDS) - set(reader.fieldnames):
            parser.error("Manifest is missing required template columns.")
        rows = list(reader)
    protocol_raw = args.protocol.read_bytes()
    protocol = json.loads(protocol_raw)
    if not isinstance(protocol, dict) or not protocol.get("prespecified_at") or not protocol.get("reference_procedure"):
        parser.error("Protocol must document prespecified_at and reference_procedure.")
    try:
        planned = datetime.fromisoformat(protocol["prespecified_at"])
    except (ValueError, TypeError):
        parser.error("prespecified_at must be an ISO timestamp with timezone.")
    if planned.tzinfo is None or planned > datetime.now(timezone.utc):
        parser.error("Prespecified timestamp must have a timezone and cannot be in the future.")
    definition = protocol.get("measurement")
    if not isinstance(definition, dict) or any(not isinstance(definition.get(k), str) or not definition[k].strip()
                                             for k in ("task", "metric", "unit", "method_version")):
        parser.error("Protocol must define one exact task, metric, unit and method_version.")
    rows = normalize_rows(rows)
    if any(any(r[k] != definition[k] for k in definition if k in ("task", "metric", "unit", "method_version")) for r in rows):
        parser.error("Manifest rows differ from the prespecified measurement protocol.")
    if protocol.get("tolerance") is None or protocol.get("minimum_participants") is None:
        parser.error("Prespecify tolerance and minimum_participants before evaluation.")
    report = evaluate(rows, tolerance=protocol.get("tolerance"), minimum_participants=protocol.get("minimum_participants"))
    report["provenance"] = {"manifest_sha256": hashlib.sha256(raw).hexdigest(),
                            "protocol_sha256": hashlib.sha256(protocol_raw).hexdigest(),
                            "evaluated_at": datetime.now(timezone.utc).isoformat(),
                            "protocol": protocol,
                            "consent_and_deidentification": "operator_attested"}
    _write_new(args.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Evaluation saved privately: {report['evaluation_rows']} evaluation rows; no diagnostic conclusion.")


if __name__ == "__main__":
    main()
