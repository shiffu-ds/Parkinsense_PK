from __future__ import annotations

from typing import Any
import re


def explain_measurements(baseline: dict[str, Any]) -> dict[str, Any]:
    changes = []
    for task, comparison in baseline.get("modules", {}).items():
        for change in comparison.get("changes", []):
            # Narrative labels are identifiers, never arbitrary user text.
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,100}", change["feature"]):
                continue
            if any(term in change["feature"] for term in ["diagnos", "medicat", "dose", "disease", "levodopa"]):
                continue
            name = change["feature"].replace("_", " ")
            unit = change.get("metadata", {}).get("unit", "feature units")
            if not isinstance(unit, str) or not re.fullmatch(r"[A-Za-z /()%.-]{1,40}", unit):
                unit = "feature units"
            sentence = (f"{task.replace('_', ' ').capitalize()}: {name} {change['direction']} "
                        f"from {change['baseline']:.3g} to {change['current']:.3g} {unit} "
                        f"(difference {change['delta']:+.3g}).")
            changes.append({"task": task, **change, "description": sentence})
    return {"status": "available" if changes else "baseline_pending",
            "method": "aligned_measured_difference", "changes": changes,
            "model_attributions": [], "model_attribution_status": "unavailable_without_validated_model",
            "limitations": ["Descriptions explain measurements and do not establish causes or clinical significance."]}
