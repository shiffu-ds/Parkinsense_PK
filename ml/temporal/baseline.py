"""Compare aligned measurements against the first accepted task result."""
from __future__ import annotations

from typing import Any

from ml.common.results import numeric_features


def _ordered(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((assessment for assessment in history if assessment.get("status") != "abandoned"),
                  key=lambda assessment: (str(assessment.get("created_at", assessment.get("session_date", ""))), str(assessment.get("id", ""))))


def _method(result: dict[str, Any]) -> Any:
    return result.get("method") or result.get("analysis_version") or (result.get("pipeline"), result.get("version"))


def compare_to_baseline(current: dict[str, dict[str, Any]], history: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = {}
    for task, result in current.items():
        features = numeric_features(result)
        if not features:
            comparisons[task] = {"status": "unavailable", "changes": [], "reason": "No accepted finite measurements."}
            continue
        first = next(((assessment, assessment["modules"][task]) for assessment in _ordered(history)
                      if task in assessment.get("modules", {}) and numeric_features(assessment["modules"][task])), None)
        if first is None:
            comparisons[task] = {"status": "baseline_established", "changes": [], "baseline_features": features,
                                 "reason": "This is the first accepted result for this task."}
            continue
        assessment, baseline = first
        if (_method(baseline) != _method(result) or baseline.get("task") != result.get("task")
                or baseline.get("language") != result.get("language")):
            comparisons[task] = {"status": "incompatible_method", "changes": [],
                                 "baseline_assessment_id": assessment.get("id"),
                                 "reason": "Task, language or measurement method changed; direct deltas are unavailable."}
            continue
        reference = numeric_features(baseline)
        changes = [{"feature": name, "baseline": reference[name], "current": value,
                    "delta": value - reference[name],
                    "percent_change": (value - reference[name]) / abs(reference[name]) * 100 if abs(reference[name]) > 1e-12 else None,
                    "direction": "increased" if value > reference[name] else "decreased" if value < reference[name] else "unchanged",
                    "metadata": result.get("feature_metadata", {}).get(name, {})}
                   for name, value in features.items() if name in reference]
        comparisons[task] = {"status": "compared" if changes else "no_aligned_features",
                             "baseline_assessment_id": assessment.get("id"),
                             "baseline_date": assessment.get("created_at", assessment.get("session_date")),
                             "baseline_features": reference, "changes": changes}
    return {"modules": comparisons, "method": "first-accepted-task-baseline-1.0",
            "limitations": ["Differences describe measured changes, not clinical improvement or deterioration.",
                            "Recording environment, task duration and technique affect comparability.",
                            "No statistical confidence interval or change threshold has been validated."]}


def build_timeline(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for assessment in _ordered(history):
        for task, result in assessment.get("modules", {}).items():
            for name, value in numeric_features(result).items():
                timeline.append({"assessment_id": assessment.get("id"),
                                 "date": assessment.get("created_at", assessment.get("session_date")),
                                 "task": task, "feature": name, "value": value,
                                 "method": _method(result),
                                 "unit": result.get("feature_metadata", {}).get(name, {}).get("unit", "see feature definition")})
    return timeline
