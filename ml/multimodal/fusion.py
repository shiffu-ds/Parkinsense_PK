from __future__ import annotations

from typing import Any

from ml.common.results import numeric_features

EXPECTED_MODALITIES = ("movement", "audio", "text", "adl")


def modality_for(task: str) -> str:
    if task.startswith(("audio", "voice", "speech")):
        return "audio"
    if task in {"text", "nlp", "transcript"}:
        return "text"
    if task == "adl":
        return "adl"
    if task == "clinical":
        return "clinical"
    return "movement"


def fuse_results(task_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize real coverage; never fill a missing modality with a fake score."""
    measurements = {task: features for task, result in task_results.items() if (features := numeric_features(result))}
    available = sorted({modality_for(task) for task in measurements})
    missing = [modality for modality in EXPECTED_MODALITIES if modality not in available]
    return {"status": "measurement_only" if measurements else "insufficient_data",
            "available_modalities": available, "missing_modalities": missing,
            "contributing_tasks": list(measurements), "measurements": measurements,
            "coverage": len([modality for modality in EXPECTED_MODALITIES if modality in available]) / len(EXPECTED_MODALITIES),
            "model_outputs": {}, "model_status": "unavailable",
            "uncertainty": {"status": "not_estimated", "reason": "No clinically validated fusion artifact is configured."},
            "limitations": ["Coverage is a record of available data, not a functional or disease score.",
                            "Missing modalities are excluded rather than imputed as normal.",
                            "Learned attention fusion and deep embeddings require trained, validated artifacts."]}
