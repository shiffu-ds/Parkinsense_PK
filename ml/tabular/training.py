"""Small-data baseline training with patient-disjoint holdouts and provenance.

This developer-only workflow never promotes its artifacts to clinical use.
Supply a real, approved feature table; no synthetic training runs are invented.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, mean_absolute_error, mean_squared_error, precision_score,
                             r2_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def patient_splits(groups: np.ndarray, target: np.ndarray, classification: bool = True,
                   seed: int = 42) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(np.unique(groups)) < 12:
        raise ValueError("At least 12 distinct patients are required for train/validation/test splitting.")
    for attempt in range(100):
        trial = seed + attempt
        development, test = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=trial).split(target, groups=groups))
        relative_train, relative_validation = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=trial).split(target[development], groups=groups[development]))
        train, validation = development[relative_train], development[relative_validation]
        if any(len(np.unique(groups[indices])) < 2 for indices in (train, validation, test)):
            continue
        if classification and any(len(np.unique(target[indices])) != 2 for indices in (train, validation, test)):
            continue
        sets = [set(groups[indices]) for indices in (train, validation, test)]
        assert not sets[0] & sets[1] and not sets[0] & sets[2] and not sets[1] & sets[2]
        return train, validation, test
    raise ValueError("Cannot create patient-disjoint holdouts with both classes; more diverse patient groups are needed.")


def _ece(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    bucket = np.minimum((probability * bins).astype(int), bins - 1)
    return float(sum(np.mean(bucket == value) * abs(float(y[bucket == value].mean()) - float(probability[bucket == value].mean()))
                     for value in range(bins) if np.any(bucket == value)))


def classification_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    predicted = probability >= 0.5
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {"auroc": float(roc_auc_score(y, probability)), "pr_auc_average_precision": float(average_precision_score(y, probability)),
            "f1": float(f1_score(y, predicted, zero_division=0)), "precision": float(precision_score(y, predicted, zero_division=0)),
            "recall_sensitivity": float(recall_score(y, predicted, zero_division=0)), "specificity": float(tn / (tn + fp)),
            "brier_score": float(brier_score_loss(y, probability)), "expected_calibration_error_10_bins": _ece(y, probability)}


def regression_metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float | None]:
    correlation_possible = np.std(y) > 0 and np.std(prediction) > 0 and len(y) > 2
    return {"mae": float(mean_absolute_error(y, prediction)), "rmse": float(np.sqrt(mean_squared_error(y, prediction))),
            "r2": float(r2_score(y, prediction)),
            "pearson": float(pearsonr(y, prediction).statistic) if correlation_possible else None,
            "spearman": float(spearmanr(y, prediction).statistic) if correlation_possible else None}


def _group_bootstrap(y: np.ndarray, predicted: np.ndarray, groups: np.ndarray, classification: bool, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    patients = np.unique(groups)
    estimates: dict[str, list[float]] = {}
    for _ in range(200):
        sampled = rng.choice(patients, len(patients), replace=True)
        indices = np.concatenate([np.flatnonzero(groups == patient) for patient in sampled])
        if classification and len(np.unique(y[indices])) < 2:
            continue
        metrics = classification_metrics(y[indices], predicted[indices]) if classification else regression_metrics(y[indices], predicted[indices])
        for key, value in metrics.items():
            if value is not None and np.isfinite(value):
                estimates.setdefault(key, []).append(value)
    return {"method": "patient_cluster_bootstrap_200_resamples", "interval_level": 0.95,
            "metrics": {key: {"lower": float(np.percentile(values, 2.5)), "upper": float(np.percentile(values, 97.5)),
                              "valid_resamples": len(values)} for key, values in estimates.items()},
            "limitation": "Small numbers of held-out patients yield unstable intervals; these are dataset-level intervals, not patient prediction intervals."}


def train_baseline(csv_path: str | Path, output_dir: str | Path, features: list[str],
                   target: str, patient_column: str = "patient_id", kind: str = "classification",
                   model: str = "logistic", data_origin: str = "deidentified_clinical",
                   target_description: str = "", seed: int = 42) -> dict[str, Any]:
    source, output = Path(csv_path), Path(output_dir)
    if kind not in {"classification", "regression"} or data_origin not in {"public", "deidentified_clinical", "synthetic"}:
        raise ValueError("Specify a supported task and explicit dataset origin.")
    if not target_description.strip():
        raise ValueError("Describe the reference target and its source.")
    if not source.is_file() or source.stat().st_size > 100_000_000:
        raise ValueError("Input CSV must exist and be below 100 MB.")
    if not features or len(set(features)) != len(features) or target in features or patient_column in features:
        raise ValueError("Provide distinct feature columns excluding the target and patient identifier.")
    frame = pd.read_csv(source)
    needed = set(features) | {target, patient_column}
    if not needed <= set(frame):
        raise ValueError("CSV is missing required feature, reference target, or patient identifier columns.")
    if frame[patient_column].isna().any() or frame[target].isna().any():
        raise ValueError("Patient identifiers and reference targets cannot be missing.")
    x = frame[features].apply(pd.to_numeric, errors="raise").replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(frame[target], errors="raise").to_numpy()
    groups = frame[patient_column].astype(str).to_numpy()
    classification = kind == "classification"
    if not np.all(np.isfinite(y)) or (classification and set(np.unique(y)) != {0, 1}):
        raise ValueError("Classification requires a binary 0/1 target; regression requires finite numeric targets.")
    train, validation, test = patient_splits(groups, y, classification, seed)
    if x.iloc[train].isna().all().any():
        raise ValueError("Every feature must have at least one observed training value.")
    if classification:
        estimator = LogisticRegression(max_iter=1000, random_state=seed) if model == "logistic" else RandomForestClassifier(n_estimators=150, min_samples_leaf=3, n_jobs=1, random_state=seed) if model == "random_forest" else None
    else:
        estimator = Ridge() if model == "ridge" else RandomForestRegressor(n_estimators=150, min_samples_leaf=3, n_jobs=1, random_state=seed) if model == "random_forest" else None
    if estimator is None:
        raise ValueError("Use logistic/random_forest for classification or ridge/random_forest for regression.")
    pipeline = Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)), ("scale", StandardScaler()), ("model", estimator)])
    pipeline.fit(x.iloc[train], y[train])
    calibrator = None
    if classification:
        calibration_probability = np.clip(pipeline.predict_proba(x.iloc[validation])[:, 1], 1e-6, 1-1e-6)
        log_odds = np.log(calibration_probability / (1 - calibration_probability)).reshape(-1, 1)
        calibrator = LogisticRegression(random_state=seed).fit(log_odds, y[validation])

        def predict(indices: np.ndarray) -> np.ndarray:
            probability = np.clip(pipeline.predict_proba(x.iloc[indices])[:, 1], 1e-6, 1-1e-6)
            return calibrator.predict_proba(np.log(probability / (1-probability)).reshape(-1, 1))[:, 1]
    else:
        def predict(indices: np.ndarray) -> np.ndarray:
            return pipeline.predict(x.iloc[indices])
    metric = classification_metrics if classification else regression_metrics
    prediction = predict(test)
    importance = permutation_importance(pipeline, x.iloc[test], y[test], n_repeats=5, random_state=seed,
                                        scoring="roc_auc" if classification else "neg_mean_absolute_error", n_jobs=1)
    output.mkdir(parents=True, exist_ok=True)
    artifact_path = output / "baseline.joblib"
    joblib.dump({"pipeline": pipeline, "calibrator": calibrator, "features": features,
                 "kind": kind, "target": target, "clinical_validated": False}, artifact_path)
    group_digest = lambda name: hashlib.sha256(name.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "seed": seed,
        "artifact": artifact_path.name, "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "data_origin": data_origin,
        "clinical_validated": False, "purpose": "experimental_baseline_only", "kind": kind, "model": model,
        "target": target, "target_description": target_description, "features": features,
        "group_column": patient_column,
        "split_method": "patient_disjoint_group_shuffle_60_20_20_approximate",
        "splits": {name: {"rows": len(indices), "patients": len(set(groups[indices])),
                          "patient_id_sha256": sorted(group_digest(value) for value in set(groups[indices]))}
                   for name, indices in [("train", train), ("validation", validation), ("test", test)]},
        "validation_metrics": metric(y[validation], predict(validation)), "test_metrics": metric(y[test], prediction),
        "calibration": {"method": "logistic_sigmoid_on_validation" if classification else "not_applicable",
                        "validation_metrics_are_independent": not classification,
                        "note": "Calibration uses validation data; final test patients remain unseen during fitting."},
        "uncertainty": _group_bootstrap(y[test], prediction, groups[test], classification, seed),
        "explanation": {"method": "held_out_permutation_importance_of_uncalibrated_pipeline",
                        "features": {name: {"mean": float(mean), "std": float(std)} for name, mean, std in zip(features, importance.importances_mean, importance.importances_std)}},
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__},
        "limitations": ["No clinical approval, external validation, clinical cutoff, or longitudinal validation is established.",
                        "Patient-level holdouts prevent identity leakage but do not prove device/site independence.",
                        "Model artifact must only be loaded from a trusted local source.",
                        "Bootstrap intervals quantify held-out metric uncertainty, not individual clinical risk."]
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest
