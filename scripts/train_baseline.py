#!/usr/bin/env python3
"""Offline developer CLI; supply an approved table, never patient raw media."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.tabular.training import train_baseline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--features", nargs="+", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--patient-column", default="patient_id")
    parser.add_argument("--kind", choices=["classification", "regression"], default="classification")
    parser.add_argument("--model", choices=["logistic", "random_forest", "ridge"], default="logistic")
    parser.add_argument("--data-origin", choices=["public", "deidentified_clinical", "synthetic"], required=True)
    parser.add_argument("--target-description", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        manifest = train_baseline(args.csv, args.output, args.features, args.target, args.patient_column,
                                  args.kind, args.model, args.data_origin, args.target_description, args.seed)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": "experimental_artifact_created", "clinical_validated": False,
                      "test_metrics": manifest["test_metrics"], "data_origin": manifest["data_origin"]}, indent=2))


if __name__ == "__main__":
    main()
