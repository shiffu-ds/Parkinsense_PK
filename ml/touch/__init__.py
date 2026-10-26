"""Touchscreen spiral drawing and two-target tapping, scored from raw touches.

The browser sends only normalized coordinates and times; all scoring happens
here so one version of the rules applies everywhere. Coordinates are divided
by the drawing width in both directions, so distances are isotropic and are
reported as a percentage of that width. Screen size, finger or stylus and the
hand used all change these numbers: they are monitoring measurements for
comparing like with like, not clinical scores.
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Any

import numpy as np

SPIRAL_METHOD = "touch-spiral-1.0"
TAPPING_METHOD = "touch-tapping-1.0"
# Archimedean guide spiral in drawing-width units, centre outwards.
SPIRAL_GEOMETRY = {"cx": 0.5, "cy": 0.5, "r_max": 0.42, "turns": 3.0}
# Two round targets on a canvas 0.6 widths tall.
TAP_GEOMETRY = {"height": 0.6, "radius": 0.12, "targets": [[0.25, 0.3], [0.75, 0.3]]}
TAP_SECONDS = 20.0
TOUCH_TASKS = {"spiral_left": ("spiral", "Left"), "spiral_right": ("spiral", "Right"),
               "touch_tap_left": ("tapping", "Left"), "touch_tap_right": ("tapping", "Right")}

MAX_SPIRAL_POINTS = 4000
MAX_TAPS = 400
TREMOR_BAND_HZ = (4.0, 7.0)
ANALYSIS_BAND_HZ = (1.0, 15.0)
RESAMPLE_HZ = 60.0

DEFINITIONS = {
    "spiral_duration_s": ("Drawing time", "seconds"),
    "spiral_mean_deviation_pct": ("Distance from the guide spiral · mean", "% of drawing width"),
    "spiral_coverage_pct": ("Guide spiral covered", "% of guide length"),
    "spiral_mean_speed_pct_per_s": ("Drawing speed · mean", "% of drawing width per second"),
    "spiral_speed_cv": ("Drawing speed variability", "coefficient of variation (SD/mean)"),
    "spiral_tremor_band_fraction": ("Oscillation in the 4–7 Hz band", "fraction of 1–15 Hz power (0–1)"),
    "spiral_lifts": ("Finger lifts while drawing", "lifts (count)"),
    "tap_count": ("Taps in 20 seconds", "taps (count)"),
    "tap_rate_per_s": ("Tapping rate", "taps per second"),
    "tap_hit_fraction": ("Taps inside a circle", "fraction (0–1)"),
    "tap_alternation_fraction": ("Correct left–right alternation", "fraction (0–1)"),
    "tap_interval_mean_ms": ("Time between taps · mean", "milliseconds"),
    "tap_interval_cv": ("Tapping rhythm variability", "coefficient of variation (SD/mean)"),
    "tap_rate_change_pct": ("Tapping rate change, first to last third", "percent"),
    "tap_error_mean_pct": ("Distance from the circle centre · mean", "% of drawing width"),
}
LIMITATIONS = [
    "Touchscreen measurements depend on screen size, finger or stylus and the hand used; compare only with the same phone, hand and test.",
    "These are monitoring measurements from an unvalidated touchscreen task, not a diagnosis or a clinical score.",
]


def _number(value: Any, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)) or not low <= float(value) <= high:
        raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
    return float(value)


def _device(payload: dict) -> dict:
    canvas = payload.get("canvas_px")
    if not (isinstance(canvas, list) and len(canvas) == 2):
        raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
    pointer = payload.get("pointer")
    return {"canvas_px": [round(_number(canvas[0], 80, 4000)), round(_number(canvas[1], 50, 4000))],
            "pointer": pointer if pointer in {"touch", "pen", "mouse"} else "unknown",
            "pixel_ratio": round(_number(payload.get("dpr", 1), 0.5, 6), 2)}


def _result(task: str, kind: str, method: str, accepted: bool, messages: list[str], features: dict, **extra) -> dict:
    side = TOUCH_TASKS[task][1]
    return {
        "status": "completed" if accepted else "repeat", "task": task, "test": kind, "side": side,
        "quality": {"accepted": accepted, "decision": "ACCEPT" if accepted else "REPEAT", "messages": messages},
        "features": features if accepted else {},
        "feature_metadata": {name: {"label": DEFINITIONS[name][0], "unit": DEFINITIONS[name][1]} for name in features} if accepted else {},
        "method": method, "limitations": list(LIMITATIONS), **extra,
    }


def spiral_template(samples: int = 1200) -> np.ndarray:
    g = SPIRAL_GEOMETRY
    theta = np.linspace(0.0, 2 * math.pi * g["turns"], samples)
    radius = g["r_max"] * theta / (2 * math.pi * g["turns"])
    return np.column_stack([g["cx"] + radius * np.cos(theta), g["cy"] + radius * np.sin(theta)])


def _nearest_to_template(xy: np.ndarray, template: np.ndarray, chunk: int = 400) -> tuple[np.ndarray, np.ndarray, float]:
    """Per-point distance to the guide and position along it, plus the share of
    the guide passed within 4% of the width.

    Turns are 14% apart, so a point near one turn never counts for its neighbour.
    Chunks keep memory small for long drawings.
    """
    deviation = np.empty(len(xy))
    position = np.empty(len(xy), dtype=int)
    covered = np.zeros(len(template), dtype=bool)
    for start in range(0, len(xy), chunk):
        block = xy[start:start + chunk]
        distances = np.sqrt(((block[:, None, :] - template[None, :, :]) ** 2).sum(axis=2))
        deviation[start:start + chunk] = distances.min(axis=1)
        position[start:start + chunk] = distances.argmin(axis=1)
        covered |= (distances <= 0.04).any(axis=0)
    return deviation, position, float(covered.mean())


def _rank_correlation(first: np.ndarray, second: np.ndarray) -> float:
    a, b = np.argsort(np.argsort(first)), np.argsort(np.argsort(second))
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _signed_radial_error(xy: np.ndarray) -> np.ndarray:
    """Radius minus the radius of the nearest guide turn at the same angle."""
    g = SPIRAL_GEOMETRY
    dx, dy = xy[:, 0] - g["cx"], xy[:, 1] - g["cy"]
    radius = np.hypot(dx, dy)
    angle = np.mod(np.arctan2(dy, dx), 2 * math.pi)
    total = 2 * math.pi * g["turns"]
    turn = np.clip(np.round((radius / g["r_max"] * total - angle) / (2 * math.pi)), 0, math.ceil(g["turns"]) - 1)
    return radius - g["r_max"] * (angle + 2 * math.pi * turn) / total


def _band_fraction(times: np.ndarray, signal: np.ndarray) -> float | None:
    """Share of 1–15 Hz power that falls in 4–7 Hz, after uniform resampling."""
    if times[-1] - times[0] < 2.0 or len(times) < 40:
        return None
    if float(np.median(np.diff(times))) > 1 / 30:
        return None  # Too few touch samples per second to see 4–7 Hz.
    grid = np.arange(times[0], times[-1], 1 / RESAMPLE_HZ)
    values = np.interp(grid, times, signal)
    window = max(3, int(RESAMPLE_HZ * 0.5))
    trend = np.convolve(values, np.ones(window) / window, mode="same")
    values = (values - trend) * np.hanning(len(values))
    power = np.abs(np.fft.rfft(values)) ** 2
    freqs = np.fft.rfftfreq(len(values), 1 / RESAMPLE_HZ)
    total = power[(freqs >= ANALYSIS_BAND_HZ[0]) & (freqs <= ANALYSIS_BAND_HZ[1])].sum()
    if not total > 0:
        return None
    band = power[(freqs >= TREMOR_BAND_HZ[0]) & (freqs <= TREMOR_BAND_HZ[1])].sum()
    return float(band / total)


def analyze_spiral(task: str, payload: dict) -> dict:
    if TOUCH_TASKS.get(task, ("",))[0] != "spiral" or not isinstance(payload, dict) or payload.get("mode") != "spiral":
        raise ValueError("Choose the spiral drawing test before drawing.")
    raw = payload.get("points")
    if not isinstance(raw, list) or len(raw) > MAX_SPIRAL_POINTS:
        raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
    device = _device(payload)
    points = []
    for item in raw:
        if not (isinstance(item, list) and len(item) == 4):
            raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
        x, y = _number(item[0], -0.05, 1.05), _number(item[1], -0.05, 1.05)
        t, stroke = _number(item[2], 0, 600), _number(item[3], 0, 500)
        points.append((x, y, t, int(stroke)))
    messages: list[str] = []
    if len(points) < 40:
        messages.append("The touch test needs a longer drawing along the guide spiral.")
        return _result(task, "spiral", SPIRAL_METHOD, False, messages, {}, device=device)
    data = np.asarray(points, dtype=float)
    order = np.argsort(data[:, 2], kind="stable")
    data = data[order]
    xy, times, strokes = data[:, :2], data[:, 2], data[:, 3].astype(int)
    duration = float(times[-1] - times[0])
    deviation, position, covered = _nearest_to_template(xy, spiral_template())
    same_stroke = strokes[1:] == strokes[:-1]
    steps = np.hypot(*np.diff(xy, axis=0).T)
    if duration < 2.0:
        messages.append("The touch test needs a longer drawing along the guide spiral.")
    if covered < 0.6:
        messages.append("The touch test needs most of the guide spiral traced, from the centre outwards.")
    # A tracing moves steadily along the guide in one direction with short steps;
    # scattered taps or scribbles near the guide do neither.
    continuous = same_stroke.any() and float(np.median(steps[same_stroke])) <= 0.05
    if float(deviation.mean()) > 0.06 or not continuous or abs(_rank_correlation(times, position)) < 0.7:
        messages.append("The touch test needs the drawing to follow the guide spiral.")
    gaps = np.diff(times)
    path = float(steps[same_stroke].sum())
    active = float(gaps[same_stroke].sum())
    usable = same_stroke & (gaps > 0)
    speeds = steps[usable] / gaps[usable]
    features = {
        "spiral_duration_s": duration,
        "spiral_mean_deviation_pct": float(deviation.mean() * 100),
        "spiral_coverage_pct": float(covered * 100),
        "spiral_mean_speed_pct_per_s": path / active * 100 if active > 0 else None,
        "spiral_speed_cv": float(speeds.std() / speeds.mean()) if len(speeds) > 5 and speeds.mean() > 0 else None,
        "spiral_tremor_band_fraction": _band_fraction(times, _signed_radial_error(xy)),
        "spiral_lifts": int(len(np.unique(strokes)) - 1),
    }
    features = {name: value for name, value in features.items() if value is not None and math.isfinite(value)}
    accepted = not messages
    if accepted:
        messages = ["The drawing followed the guide spiral closely enough to measure."]
    trace = [[round(x, 4), round(y, 4), round(t - times[0], 3), int(s)] for (x, y), t, s in zip(xy, times, strokes)][::max(1, len(xy) // 2400 + 1)]
    return _result(task, "spiral", SPIRAL_METHOD, accepted, messages, features, device=device,
                   geometry=dict(SPIRAL_GEOMETRY), trace=trace,
                   capture={"points": len(points), "sampling_hz": round(float(1 / np.median(gaps[gaps > 0])), 1) if (gaps > 0).any() else None})


def analyze_tapping(task: str, payload: dict) -> dict:
    if TOUCH_TASKS.get(task, ("",))[0] != "tapping" or not isinstance(payload, dict) or payload.get("mode") != "tapping":
        raise ValueError("Choose the tapping test before tapping.")
    raw = payload.get("taps")
    if not isinstance(raw, list) or len(raw) > MAX_TAPS:
        raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
    device = _device(payload)
    taps = []
    for item in raw:
        if not (isinstance(item, list) and len(item) == 3):
            raise ValueError("The touch test data could not be read. Clear the drawing area and try again.")
        taps.append((_number(item[0], -0.05, 1.05), _number(item[1], -0.05, TAP_GEOMETRY["height"] + 0.05),
                     _number(item[2], 0, TAP_SECONDS + 1)))
    completed = payload.get("completed") is True
    messages: list[str] = []
    if not completed:
        messages.append(f"The touch test needs the full {TAP_SECONDS:g} seconds of tapping.")
    if len(taps) < 8:
        messages.append("The touch test needs at least 8 taps within the 20 seconds.")
    if messages:
        return _result(task, "tapping", TAPPING_METHOD, False, messages, {}, device=device)
    data = np.asarray(sorted(taps, key=lambda tap: tap[2]))
    centres = np.asarray(TAP_GEOMETRY["targets"], dtype=float)
    distances = np.sqrt(((data[:, None, :2] - centres[None, :, :]) ** 2).sum(axis=2))
    nearest = distances.argmin(axis=1)
    error = distances.min(axis=1)
    hit = error <= TAP_GEOMETRY["radius"]
    hit_targets = nearest[hit]
    if hit.mean() < 0.5:
        messages.append("The touch test needs taps on the two circles.")
    intervals = np.diff(data[:, 2]) * 1000
    third = TAP_SECONDS / 3
    first = int((data[:, 2] < third).sum())
    last = int((data[:, 2] >= 2 * third).sum())
    features = {
        "tap_count": int(len(data)),
        "tap_rate_per_s": float(len(data) / TAP_SECONDS),
        "tap_hit_fraction": float(hit.mean()),
        "tap_alternation_fraction": float((hit_targets[1:] != hit_targets[:-1]).mean()) if len(hit_targets) > 1 else None,
        "tap_interval_mean_ms": float(intervals.mean()),
        "tap_interval_cv": float(intervals.std() / intervals.mean()) if intervals.mean() > 0 else None,
        "tap_rate_change_pct": float((last - first) / first * 100) if first else None,
        "tap_error_mean_pct": float(error.mean() * 100),
    }
    features = {name: value for name, value in features.items() if value is not None and math.isfinite(value)}
    accepted = not messages
    if accepted:
        messages = ["Taps were recorded on both circles for the full test."]
    return _result(task, "tapping", TAPPING_METHOD, accepted, messages, features, device=device,
                   geometry={**TAP_GEOMETRY, "seconds": TAP_SECONDS},
                   taps=[[round(x, 4), round(y, 4), round(t, 3)] for x, y, t in data.tolist()])


def analyze_touch(task: str, payload: dict) -> dict:
    kind = TOUCH_TASKS.get(task, ("",))[0]
    if kind == "spiral":
        return analyze_spiral(task, payload)
    if kind == "tapping":
        return analyze_tapping(task, payload)
    raise ValueError("Choose a supported touch test.")
