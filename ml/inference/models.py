"""Trusted offline baseline artifact inference and explicit advanced availability."""
from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


def predict_experimental_baseline(model_directory: str | Path, features: dict[str, float]) -> dict[str, Any]:
    """Use only administrator-configured trusted directories; joblib can execute code."""
    directory = Path(model_directory).resolve()
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "unavailable", "reason": "No trained baseline manifest found.", "model_outputs": {}}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or manifest.get("purpose") != "experimental_baseline_only":
            raise ValueError("Unsupported model manifest.")
        artifact_path = (directory / manifest["artifact"]).resolve()
        if artifact_path.parent != directory or not artifact_path.is_file():
            raise ValueError("Artifact must be an existing file inside the configured directory.")
        if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != manifest["artifact_sha256"]:
            raise ValueError("Model checksum does not match its provenance manifest.")
        names = manifest["features"]
        if not isinstance(names, list) or not names or any(name not in features for name in names):
            raise ValueError("Measurements are missing required model features.")
        values = np.asarray([features[name] for name in names], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("Model inputs must be finite numeric measurements.")
        artifact = joblib.load(artifact_path)
        if artifact.get("features") != names or artifact.get("kind") != manifest.get("kind"):
            raise ValueError("Artifact input schema does not match the manifest.")
        frame = pd.DataFrame([values], columns=names)
        if artifact["kind"] == "classification":
            probability = float(np.clip(artifact["pipeline"].predict_proba(frame)[0, 1], 1e-6, 1-1e-6))
            if artifact.get("calibrator") is not None:
                probability = float(artifact["calibrator"].predict_proba([[np.log(probability / (1-probability))]])[0, 1])
            output = {"experimental_reference_target_probability": probability}
        else:
            output = {"experimental_reference_target_estimate": float(artifact["pipeline"].predict(frame)[0])}
        return {"status": "experimental_only", "model_outputs": output, "clinical_validated": False,
                "target": manifest["target"], "features_used": names,
                "uncertainty": {"status": "individual_uncertainty_unavailable", "validation_metrics": manifest.get("test_metrics", {})},
                "limitations": ["Experimental output is not approved for patient-facing clinical decisions."]}
    except (ValueError, KeyError, TypeError, OSError, ImportError, EOFError, pickle.UnpicklingError, RuntimeError) as exc:
        return {"status": "unavailable", "reason": f"Cannot use baseline artifact: {exc}", "model_outputs": {}}


def advanced_model_status() -> dict[str, Any]:
    return {name: {"status": "unavailable", "reason": "No locally approved trained weights or evaluation manifest are configured."}
            for name in ["deep_audio_embeddings", "temporal_pose_network", "multilingual_embeddings", "attention_fusion", "temporal_model", "llm_report"]}
