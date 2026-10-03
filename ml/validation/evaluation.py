"""Participant-balanced measurement accuracy and matched repeatability.

Each row describes one attempted recording/metric. Rejected attempts remain in
coverage denominators. Accuracy uses independent reference values; repeated
recordings do not increase the participant count or bootstrap sampling unit.
"""

from collections import defaultdict
import math

import numpy as np

FIELDS = (
    "participant_id", "recording_id", "task", "metric", "unit", "method_version",
    "split", "status", "measured", "reference", "reference_method", "reference_blinded",
    "device_family", "lighting", "site", "age_band", "repeat_group",
)
STRATA = ("device_family", "lighting", "site", "age_band")
SPLITS = {"training", "tuning", "evaluation"}
STATUSES = {"accepted", "rejected", "unavailable"}


def _number(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number or empty.")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number or empty.") from exc
    if not math.isfinite(result) or abs(result) > 1e100:
        raise ValueError(f"{field} must be finite and within supported numeric bounds.")
    return result


def normalize_rows(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Supply at most 10,000 validation rows.")
    clean, keys, participant_splits = [], set(), defaultdict(set)
    for original in rows:
        if not isinstance(original, dict):
            raise ValueError("Each validation row must be a mapping.")
        row = {}
        for field in FIELDS:
            if field in {"measured", "reference", "reference_blinded"}:
                continue
            value = original.get(field, "")
            if value is None:
                value = ""
            if not isinstance(value, str) or len(value.strip()) > 120:
                raise ValueError(f"{field} must contain up to 120 characters.")
            row[field] = value.strip()
        for field in ("participant_id", "recording_id", "task", "metric", "unit", "method_version"):
            if not row[field]:
                raise ValueError(f"{field} is required.")
        if row["unit"].startswith("Unit not specified"):
            raise ValueError("Validation requires a defined measurement unit.")
        if row["split"] not in SPLITS or row["status"] not in STATUSES:
            raise ValueError("Choose a valid split and recording status.")
        key = (row["recording_id"], row["task"], row["metric"], row["method_version"])
        if key in keys:
            raise ValueError("Duplicate recording/metric/method row; record a new attempt instead.")
        keys.add(key)
        participant_splits[row["participant_id"]].add(row["split"])
        row["measured"] = _number(original.get("measured"), "Measured value")
        row["reference"] = _number(original.get("reference"), "Reference value")
        blinded = original.get("reference_blinded")
        if isinstance(blinded, str):
            blinded = blinded.strip().lower()
        if blinded in (None, "", "unknown"):
            blinded = None
        elif blinded in (True, "true", "yes", "1"):
            blinded = True
        elif blinded in (False, "false", "no", "0"):
            blinded = False
        else:
            raise ValueError("Reference blinding must be true, false, or unknown.")
        row["reference_blinded"] = blinded
        if row["status"] == "accepted" and row["measured"] is None:
            raise ValueError("An accepted attempt must have a measured value.")
        if row["status"] != "accepted" and row["measured"] is not None:
            raise ValueError("Rejected/unavailable attempts cannot carry a measured value.")
        if row["reference"] is not None and not row["reference_method"]:
            raise ValueError("Describe the reference method for each reference value.")
        for field in STRATA:
            row[field] = row[field] or "unknown"
        clean.append(row)
    if any("evaluation" in splits and len(splits) > 1 for splits in participant_splits.values()):
        raise ValueError("Participant leakage: evaluation participants also occur in training/tuning.")
    return clean


def _accuracy(rows):
    paired = [r for r in rows if r["status"] == "accepted" and r["reference"] is not None]
    by_person = defaultdict(list)
    for row in paired:
        by_person[row["participant_id"]].append(row["measured"] - row["reference"])
    # Equal participant weights; one prolific participant cannot dominate accuracy.
    summaries = np.asarray([[np.mean(by_person[k]), np.mean(np.abs(by_person[k])), np.mean(np.square(by_person[k]))]
                            for k in sorted(by_person)], dtype=float)
    result = {"attempts": len(rows), "accepted_attempts": sum(r["status"] == "accepted" for r in rows),
              "rejected_attempts": sum(r["status"] == "rejected" for r in rows),
              "unavailable_attempts": sum(r["status"] == "unavailable" for r in rows),
              "participants": len({r["participant_id"] for r in rows}),
              "paired_recordings": len(paired), "paired_participants": len(by_person),
              "reference_missing": sum(r["status"] == "accepted" and r["reference"] is None for r in rows),
              "reference_blinded_recordings": sum(r["reference_blinded"] is True for r in paired),
              "reference_blinding_unknown": sum(r["reference_blinded"] is None for r in paired),
              "reference_not_blinded": sum(r["reference_blinded"] is False for r in paired),
              "reference_methods": sorted({r["reference_method"] for r in paired}),
              "bias": None, "mae": None, "rmse": None, "mae_ci95": None}
    if not len(summaries):
        return result
    result.update(bias=float(summaries[:, 0].mean()), mae=float(summaries[:, 1].mean()),
                  rmse=float(np.sqrt(summaries[:, 2].mean())))
    if len(summaries) >= 3:
        rng = np.random.default_rng(2026)
        # Bound memory even for large manifests; participants remain the unit.
        bootstrap = np.concatenate([summaries[rng.integers(0, len(summaries), size=(100, len(summaries))), 1].mean(axis=1)
                                    for _ in range(20)])
        result["mae_ci95"] = np.quantile(bootstrap, [0.025, 0.975]).tolist()
    return result


def _repeatability(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["status"] == "accepted" and row["repeat_group"]:
            key = (row["participant_id"], row["repeat_group"], row["device_family"], row["lighting"], row["site"])
            groups[key].append(row["measured"])
    eligible = {key: values for key, values in groups.items() if len(values) >= 2}
    # Average repeat-group variance within each participant, then across people.
    person_vars = defaultdict(list)
    for key, values in eligible.items():
        person_vars[key[0]].append(float(np.var(values, ddof=1)))
    sw = float(np.sqrt(np.mean([np.mean(v) for v in person_vars.values()]))) if person_vars else None
    return {"matched_groups": len(eligible), "participants": len(person_vars),
            "within_participant_sd": sw,
            "repeatability_coefficient": 1.96 * math.sqrt(2) * sw if sw is not None else None,
            "assumption": "Explicit matched repeats of a stable task/context; coefficient assumes approximately normal, stable measurement error. True movement change is not measurement noise."}


def evaluate(rows, *, tolerance=None, minimum_participants=None):
    """Evaluate held-out participants only; return JSON-safe descriptive evidence."""
    clean = normalize_rows(rows)
    tolerance = _number(tolerance, "Tolerance")
    if tolerance is not None and tolerance < 0:
        raise ValueError("Tolerance cannot be negative.")
    if minimum_participants is not None and (type(minimum_participants) is not int or minimum_participants < 1):
        raise ValueError("Minimum participants must be a positive integer.")
    held_out = [r for r in clean if r["split"] == "evaluation"]
    grouped = defaultdict(list)
    for row in held_out:
        grouped[(row["task"], row["metric"], row["unit"], row["method_version"])].append(row)
    if tolerance is not None and len(grouped) > 1:
        raise ValueError("A tolerance applies to one exact task/metric/unit/method protocol. Evaluate separate protocols.")
    outputs = []
    for (task, metric, unit, method), values in sorted(grouped.items()):
        summary = _accuracy(values)
        outputs.append({"task": task, "metric": metric, "unit": unit, "method_version": method,
                        "accuracy": summary, "repeatability": _repeatability(values),
                        "strata": {field: [{"group": group, **_accuracy([r for r in values if r[field] == group])}
                                          for group in sorted({r[field] for r in values})] for field in STRATA},
                        "target": {"tolerance_mae": tolerance, "minimum_participants": minimum_participants,
                                   "observed_mae_within_tolerance": (summary["mae"] <= tolerance
                                       if tolerance is not None and summary["mae"] is not None else None),
                                   "planned_sample_reached": (summary["paired_participants"] >= minimum_participants
                                       if minimum_participants is not None else None)}})
    return {"schema_version": "measurement-validation-1.0", "input_rows": len(clean),
            "evaluation_rows": len(held_out), "metrics": outputs,
            "limitations": ["Descriptive measurement evidence; no clinical approval or disease-severity validation.",
                            "Local participant split audit does not verify the provenance of pretrained landmark models.",
                            "MAE intervals bootstrap participants, not recordings; fewer than three paired participants have no interval.",
                            "Reference methods, representativeness and confounders need independent human review."]}
