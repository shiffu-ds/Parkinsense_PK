"""Display definitions and descriptive statistics of accepted module measurements.

No clinical score is constructed. A unit is attached only when it is defined by
an implemented extractor or its explicit feature metadata. Missing values stay
missing; zero is retained as an actual observation.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import hashlib
import math
from numbers import Real
from typing import Any

import numpy as np

MOVEMENT_TASKS = frozenset({"gait", "turning", "finger_left", "finger_right", "hand_open_close", "sit_to_stand", "reach", "grasp", "object_transfer"})
TOUCH_TASKS = frozenset({"spiral_left", "spiral_right", "touch_tap_left", "touch_tap_right"})
AUDIO_TASKS = frozenset({"voice", "voice_natural", "voice_vowel", "voice_sentence", "audio_natural", "audio_vowel", "audio_sentence"})
MAX_DISPLAY_POINTS = 300

# Explicit units for features actually implemented by the local acoustic code.
_AUDIO_UNITS = {
    "duration_seconds": "seconds", "signal_rms_dbfs": "dBFS",
    "signal_active_fraction": "fraction (0–1)", "internal_pause_count": "pauses (count)",
    "internal_pause_seconds": "seconds", "spectral_centroid_mean_hz": "Hz",
    "spectral_centroid_std_hz": "Hz", "clipping_fraction": "fraction (0–1)",
    "f0_autocorrelation_median_hz": "Hz", "f0_autocorrelation_std_hz": "Hz",
    "f0_periodicity_mean": "fraction (0–1)",
}
_AUDIO_LABELS = {
    "duration_seconds": "Recording duration", "signal_rms_dbfs": "Signal level",
    "signal_active_fraction": "Signal-active fraction", "internal_pause_count": "Internal pauses",
    "internal_pause_seconds": "Internal pause time", "spectral_centroid_mean_hz": "Spectral centroid · mean",
    "spectral_centroid_std_hz": "Spectral centroid · SD", "clipping_fraction": "Clipped samples",
    "f0_autocorrelation_median_hz": "Estimated pitch · median", "f0_autocorrelation_std_hz": "Estimated pitch · SD",
    "f0_periodicity_mean": "Autocorrelation periodicity",
}
_CURVE_DEFINITIONS = {
    "thumb_index_distance_ratio": ("Thumb–index distance", "hand lengths (relative)"),
    "hand_opening_ratio": ("Hand opening", "hand lengths (relative)"),
    "left_knee_angle_deg_proxy": ("Left knee angle", "degrees (estimated)"),
    "right_knee_angle_deg_proxy": ("Right knee angle", "degrees (estimated)"),
    "mean_knee_angle_deg_proxy": ("Mean knee angle", "degrees (estimated)"),
    "shoulder_orientation_deg_proxy": ("Shoulder orientation", "degrees (estimated)"),
    "ankle_separation_trunk_lengths_proxy": ("Ankle separation", "trunk lengths (relative)"),
    "left_reach_trunk_lengths_proxy": ("Left reach", "trunk lengths (relative)"),
    "right_reach_trunk_lengths_proxy": ("Right reach", "trunk lengths (relative)"),
}


def accepted(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    quality = result.get("quality")
    return bool(isinstance(quality, dict)
                and result.get("status") in {"accepted", "completed", "ACCEPT"}
                and quality.get("accepted") is not False
                and quality.get("decision") not in {"REPEAT", "REJECT"}
                and (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"))


def safe_label(value: Any, *, limit: int = 110) -> str:
    """Plotly supports HTML in text; measurements may contain untrusted labels."""
    return escape(" ".join(str(value).split())[:limit], quote=True)


def module_family(task: str) -> str | None:
    if task in MOVEMENT_TASKS:
        return "movement"
    if task in TOUCH_TASKS:
        return "touch"
    if task in AUDIO_TASKS:
        return "audio"
    if task in {"nlp", "text"}:
        return "nlp"
    if task == "adl":
        return "adl"
    return None


def source_note(task: str) -> str:
    return {
        "movement": "Landmark-derived movement proxies. Camera setup affects comparisons; these are not clinical scores.",
        "audio": "Local WAV measurements. Microphone, room and task affect comparisons; no clinical voice score is inferred.",
        "nlp": "Keyword-rule matches in patient self-report. A value of 0 means no matched difficulty phrase, not confirmed absence of difficulty.",
        "adl": "Patient self-report on a custom, unvalidated 0–4 difficulty scale. These ratings do not estimate disease severity.",
        "touch": "Touchscreen measurements. Screen size, finger or stylus and the hand used affect comparisons; these are not clinical scores.",
    }.get(module_family(task), "No measurement definition is available for this module.")


def measurement_definition(result: dict, name: str, task: str) -> dict[str, str] | None:
    """Return exact extractor units, without guessing units for unknown features."""
    family = module_family(task)
    label, unit, source = None, None, None
    if family == "movement":
        metadata = result.get("feature_metadata", {})
        definition = metadata.get(name) if isinstance(metadata, dict) else None
        if isinstance(definition, dict) and isinstance(definition.get("unit"), str) and definition["unit"].strip():
            label, unit = definition.get("label", name.replace("_", " ").capitalize()), definition["unit"]
        source = "Landmark-derived proxy"
    elif family == "audio":
        if name in _AUDIO_UNITS:
            unit, label = _AUDIO_UNITS[name], _AUDIO_LABELS[name]
        elif len(name) == 12 and name.startswith("mfcc_") and name.endswith("_mean") and name[5:7].isdigit() and 1 <= int(name[5:7]) <= 13:
            unit, label = "log-mel DCT units", f"MFCC {int(name[5:7])} · mean"
        source = "Local WAV measurement"
    elif family == "nlp":
        if name == "reported_difficulty_domain_count":
            unit, label = "matched domains (count)", "Difficulty domains matched by rules"
        elif name.startswith("self_report_") and name.endswith("_difficulty"):
            from ml.nlp.functional import DOMAINS
            domain = name[len("self_report_"):-len("_difficulty")]
            if domain in DOMAINS:
                unit, label = "rule match (0 or 1)", domain.replace("_", " ").capitalize()
        source = "Keyword rules · patient self-report"
    elif family == "touch":
        from ml.touch import DEFINITIONS
        if name in DEFINITIONS:
            label, unit = DEFINITIONS[name]
        source = "Touchscreen measurement"
    elif family == "adl":
        from ml.tabular.adl import ADL_ITEMS
        if name == "adl_self_report_mean":
            label = "Mean of patient ratings"
        elif name.startswith("adl_") and name.endswith("_self_report"):
            label = ADL_ITEMS.get(name[len("adl_"):-len("_self_report")])
        if label:
            unit = "difficulty rating (0–4)"
        source = "Patient self-report · custom scale"
    if family is None:
        return None
    if label is None or unit is None:
        # Unknown units are visible only in a group dedicated to this exact
        # feature. A missing definition never makes unrelated values commensurate.
        label = name.replace("_", " ").capitalize()
        display_name = name if len(name) <= 64 else name[:60] + " · " + hashlib.sha256(name.encode()).hexdigest()[:10]
        unit = "Unit not specified · " + display_name
    return {"label": safe_label(label), "unit": safe_label(unit), "source": safe_label(source)}


@dataclass(frozen=True)
class Measurement:
    key: str
    label: str
    unit: str
    value: float
    source: str


@dataclass(frozen=True)
class Curve:
    key: str
    label: str
    unit: str
    timestamps: tuple[float, ...]
    values: tuple[float | None, ...]


def measurements(result: dict, task: str) -> list[Measurement]:
    if not accepted(result):
        return []
    values = result.get("features")
    if not isinstance(values, dict):
        return []
    rows = []
    for key, raw_value in values.items():
        key = str(key)
        value = _finite(raw_value)
        if value is None:
            continue
        definition = measurement_definition(result, key, task)
        if definition:
            if module_family(task) == "adl" and not 0 <= value <= 4:
                continue
            if definition["unit"] == "rule match (0 or 1)" and value not in (0, 1):
                continue
            rows.append(Measurement(key, **definition, value=value))
    return rows


def _finite(value: Any) -> float | None:
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            number = float(value)
        except (OverflowError, ValueError, TypeError):
            return None
        if math.isfinite(number):
            return number
    return None


def recording_curves(result: dict, task: str) -> list[Curve]:
    if not accepted(result) or task not in MOVEMENT_TASKS:
        return []
    raw = result.get("curves")
    if not isinstance(raw, dict) or not isinstance(raw.get("timestamp_s"), (list, tuple)):
        return []
    original_times = raw["timestamp_s"]
    # Invalid or unsorted timestamps cannot define a truthful elapsed-time axis.
    times = [_finite(value) for value in original_times]
    if len(times) < 2 or any(value is None or value < 0 for value in times) or any(b <= a for a, b in zip(times, times[1:])):
        return []
    rows = []
    for key, (label, unit) in _CURVE_DEFINITIONS.items():
        values = raw.get(key)
        if not isinstance(values, (list, tuple)) or len(values) != len(times):
            continue
        cleaned = tuple(_finite(value) for value in values)
        if any(value is not None for value in cleaned):
            rows.append(Curve(key, label, unit, tuple(times), cleaned))
    return rows


def descriptive_rows(result: dict, task: str, unit: str, *, curves: bool = False) -> list[dict]:
    if curves:
        rows = []
        for curve in recording_curves(result, task):
            if curve.unit != unit:
                continue
            values = np.asarray([value for value in curve.values if value is not None], dtype=float)
            rows.append({"Measurement": curve.label, "Samples": len(values), "Mean": float(values.mean()),
                         "Median": float(np.median(values)), "SD": float(values.std(ddof=0)),
                         "Minimum": float(values.min()), "Maximum": float(values.max()), "Unit": curve.unit})
        return rows
    return [{"Measurement": row.label, "Value": row.value, "Unit": row.unit, "Source": row.source}
            for row in measurements(result, task) if row.unit == unit]


def bounded_curve(curve: Curve) -> tuple[list, list]:
    """Decimate actual samples only; break every lost or invalid segment.

    Even decimation must not conceal a missing sample or timestamp gap by
    drawing a line over it. The output includes separators in the 300-point
    bound; no missing values are interpolated or replaced by zero.
    """
    times, values = curve.timestamps, curve.values
    dt = float(np.median(np.diff(times)))
    segments: list[list[int]] = []
    segment = []
    for index, value in enumerate(values):
        broken = index > 0 and times[index] - times[index - 1] > 2.5 * dt
        if value is None or broken:
            if segment:
                segments.append(segment)
                segment = []
        if value is not None:
            segment.append(index)
    if segment:
        segments.append(segment)
    if not segments:
        return [], []
    # If many gaps exceed the budget, show separated markers only for the
    # selected segments; the figure still never bridges unobserved samples.
    if len(segments) > MAX_DISPLAY_POINTS // 2:
        chosen = np.linspace(0, len(segments) - 1, MAX_DISPLAY_POINTS // 2, dtype=int)
        segments = [segments[int(i)] for i in chosen]
    budget = MAX_DISPLAY_POINTS - max(0, len(segments) - 1)
    allocation = np.ones(len(segments), dtype=int)
    remaining = budget - len(segments)
    capacities = np.asarray([len(segment) - 1 for segment in segments])
    while remaining > 0 and np.any(allocation - 1 < capacities):
        for n in np.argsort(-capacities):
            if remaining <= 0:
                break
            if allocation[n] < len(segments[n]):
                allocation[n] += 1
                remaining -= 1
    out_time, out_value = [], []
    for number, indices in enumerate(segments):
        selected = np.linspace(0, len(indices) - 1, min(len(indices), allocation[number]), dtype=int)
        if number:
            out_time.append(None)
            out_value.append(None)
        for local in selected:
            index = indices[int(local)]
            out_time.append(times[index])
            out_value.append(values[index])
    return out_time, out_value


def method(result: dict) -> str | None:
    value = result.get("method") or result.get("analysis_version")
    return value if isinstance(value, str) and value else None


def compatible_history(result: dict, task: str, history: list[dict] | None) -> list[dict]:
    if not accepted(result) or not method(result) or module_family(task) is None:
        return []
    output = []
    for visit in sorted((item for item in (history or []) if isinstance(item, dict)), key=lambda item: (str(item.get("created_at", item.get("session_date", ""))), str(item.get("id", "")))):
        if visit.get("status") == "abandoned":
            continue
        modules = visit.get("modules", {})
        candidate = modules.get(task) if isinstance(modules, dict) else None
        matches = bool(isinstance(candidate, dict) and accepted(candidate)
                       and method(candidate) == method(result) and candidate.get("task") == result.get("task")
                       and candidate.get("language") == result.get("language"))
        output.append({"date": safe_label(visit.get("created_at", visit.get("session_date", "Visit date unavailable")), limit=45),
                       "measurements": measurements(candidate, task) if matches else [], "compatible": matches})
    return output[-MAX_DISPLAY_POINTS:]
