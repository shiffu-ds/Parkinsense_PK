"""Aligned, quality-gated developer feature tables without raw patient content."""

from uuid import UUID

import pandas as pd

from ml.common.results import numeric_features


def feature_table(patient_id: str, assessments: list[dict]) -> pd.DataFrame:
    patient_id = str(UUID(str(patient_id)))
    rows = []
    for assessment in assessments:
        if assessment.get("patient_id") != patient_id:
            raise ValueError("A feature table must contain only the authorized patient's assessments.")
        if assessment.get("status") == "abandoned":
            continue
        row = {"patient_id": patient_id, "assessment_id": assessment["id"], "session_date": assessment["created_at"]}
        methods = {}
        for task, result in assessment.get("modules", {}).items():
            features = numeric_features(result)
            if not features:
                continue
            row.update({f"{task}__{name}": value for name, value in features.items()})
            methods[task] = str(result.get("method", result.get("analysis_version", "unspecified")))
            if result.get("language"):
                row[f"{task}__language"] = result["language"]
        if methods:
            row.update({f"{task}__method": method for task, method in methods.items()})
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["patient_id", "assessment_id", "session_date"])
    frame["session_date"] = pd.to_datetime(frame["session_date"], utc=True)
    identifiers = ["patient_id", "assessment_id", "session_date"]
    return frame[identifiers + sorted(set(frame.columns) - set(identifiers))].sort_values("session_date").reset_index(drop=True)
