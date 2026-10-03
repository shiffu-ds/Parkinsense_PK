"""Conservative motion proxies; no clinical score or disease prediction.

Image-plane distances are aspect-corrected then divided by a body/hand scale.
Angles use MediaPipe's approximate hip-/hand-centered world coordinates when
available. Nothing here treats monocular depth as a measured walking distance.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, savgol_filter


def _smooth(values: np.ndarray) -> np.ndarray:
    if len(values) < 7:
        return values
    size = min(9, len(values) if len(values) % 2 else len(values) - 1)
    return savgol_filter(values, size, 2)


def _range(values: np.ndarray) -> float:
    return float(np.percentile(values, 95) - np.percentile(values, 5))


def joint_angle(points: np.ndarray, first: int, middle: int, last: int) -> np.ndarray:
    a = points[:, first, :3] - points[:, middle, :3]
    b = points[:, last, :3] - points[:, middle, :3]
    denominator = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    cosine = np.sum(a * b, axis=1) / np.maximum(denominator, 1e-8)
    return np.degrees(np.arccos(np.clip(cosine, -1, 1)))


def cycle_features(signal: np.ndarray, times: np.ndarray, prefix: str) -> dict[str, float]:
    """Count peaks only within contiguous detected segments.

    Sparse detection gaps must not create artificial cycles or rhythm metrics.
    Every cycle count is a sampling-dependent proxy, not a clinical score.
    """
    values = _smooth(signal)
    duration = max(float(times[-1] - times[0]), 1e-6)
    dt = float(np.median(np.diff(times)))
    amplitude = _range(values)
    prominence = max(amplitude * 0.2, 0.025)
    peaks, _ = find_peaks(values, prominence=prominence, distance=max(1, round(0.2 / dt)))
    # Reject intervals that span a missing segment; comparisons use valid time only.
    intervals = np.diff(times[peaks])
    good = []
    for i, interval in enumerate(intervals):
        if np.max(np.diff(times[peaks[i]:peaks[i + 1] + 1])) <= 2.5 * dt:
            good.append(float(interval))
    n = max(3, len(values) // 3)
    early = _range(values[:n])
    late = _range(values[-n:])
    out = {
        f"{prefix}_cycle_count_proxy": float(len(peaks)),
        f"{prefix}_frequency_hz_proxy": float(len(peaks) / duration),
        f"{prefix}_range_ratio": amplitude,
    }
    if len(good) >= 2:
        out[f"{prefix}_interval_cv_proxy"] = float(np.std(good) / max(np.mean(good), 1e-8))
    if early > 0.03:
        out[f"{prefix}_late_to_early_range_ratio"] = float(late / early)
    return out


def extract_features(frames: list[dict], task: str, aspect_ratio: float = 1.0) -> tuple[dict[str, float], dict, list[str], dict]:
    """Returns features, metadata, task activity issues, and chart curves."""
    if len(frames) < 10:
        return {}, {}, ["Too few visible landmark frames for motion measurements."], {}
    times = np.asarray([f["timestamp_s"] for f in frames], dtype=np.float64)
    points = np.asarray([f["landmarks"] for f in frames], dtype=np.float32)
    image = points[:, :, :2].copy()
    image[:, :, 0] *= aspect_ratio
    duration = float(times[-1] - times[0])
    out = {"observed_duration_s": duration}
    issues: list[str] = []
    curves: dict = {"timestamp_s": times.tolist()}
    hand = points.shape[1] == 21
    if hand:
        scale = np.maximum(np.linalg.norm(image[:, 0] - image[:, 9], axis=1), 0.02)
        distance = np.linalg.norm(image[:, 4] - image[:, 8], axis=1) / scale
        opening = np.mean([np.linalg.norm(image[:, tip] - image[:, 0], axis=1) / scale for tip in (8, 12, 16, 20)], axis=0)
        signal = opening if task == "hand_open_close" else distance
        prefix = "opening" if task == "hand_open_close" else "tap" if task.startswith("finger") else "grip_aperture"
        out.update(cycle_features(signal, times, prefix))
        out["thumb_index_mean_ratio"] = float(np.mean(distance))
        out["hand_opening_mean_ratio"] = float(np.mean(opening))
        curves["thumb_index_distance_ratio"] = distance.tolist()
        curves["hand_opening_ratio"] = opening.tolist()
        wrist = np.column_stack([_smooth(image[:, 0, i]) for i in range(2)])
        # Divide wrist path by the recording's median hand length, not a moving scale.
        path = np.linalg.norm(np.diff(wrist, axis=0), axis=1)
        contiguous = np.diff(times) <= 2.5 * np.median(np.diff(times))
        out["wrist_path_hand_lengths_proxy"] = float(np.sum(path[contiguous]) / np.median(scale))
        if task == "object_transfer":
            if out["wrist_path_hand_lengths_proxy"] < 0.3:
                issues.append("Little wrist travel was detected. Repeat the transfer with the whole hand visible.")
        elif _range(_smooth(signal)) < 0.08:
            issues.append("Little opening/closing activity was detected. Repeat the selected finger/hand task.")
        if task.startswith("finger") or task == "hand_open_close":
            if out[f"{prefix}_cycle_count_proxy"] < 2:
                issues.append("Fewer than two distinct movement cycles were visible. Record several complete cycles.")
    else:
        scale = np.maximum(np.linalg.norm((image[:, 11] + image[:, 12]) / 2 - (image[:, 23] + image[:, 24]) / 2, axis=1), 0.04)
        worlds = [f.get("world_landmarks") for f in frames]
        angle_points = np.asarray(worlds, dtype=np.float32) if all(worlds) else points.copy()
        if not all(worlds):
            angle_points[:, :, 0] *= aspect_ratio
        left_knee = joint_angle(angle_points, 23, 25, 27)
        right_knee = joint_angle(angle_points, 24, 26, 28)
        curves.update({"left_knee_angle_deg_proxy": left_knee.tolist(), "right_knee_angle_deg_proxy": right_knee.tolist()})
        out.update({"left_knee_range_deg_proxy": _range(left_knee), "right_knee_range_deg_proxy": _range(right_knee)})
        hip_y = _smooth((image[:, 23, 1] + image[:, 24, 1]) / 2)
        out["hip_vertical_range_trunk_lengths_proxy"] = _range(hip_y) / float(np.median(scale))
        if task == "gait":
            separation = (image[:, 27, 0] - image[:, 28, 0]) / scale
            out.update(cycle_features(separation, times, "gait"))
            # A separation peak occurs once per gait cycle; both feet contribute steps.
            out["cadence_steps_per_min_proxy"] = out.pop("gait_frequency_hz_proxy") * 120
            left_range = _range(image[:, 27, 0] / scale)
            right_range = _range(image[:, 28, 0] / scale)
            out["ankle_range_asymmetry_proxy"] = float(abs(left_range - right_range) / max(left_range + right_range, 0.01))
            out["arm_swing_trunk_lengths_proxy"] = float((_range((image[:, 15, 0] - image[:, 11, 0]) / scale) + _range((image[:, 16, 0] - image[:, 12, 0]) / scale)) / 2)
            curves["ankle_separation_trunk_lengths_proxy"] = separation.tolist()
            if _range(separation) < 0.1 and max(_range(left_knee), _range(right_knee)) < 8:
                issues.append("Little stepping activity was visible. Repeat walking with the full body in view.")
        elif task == "turning":
            shoulder = angle_points[:, 12, :3] - angle_points[:, 11, :3]
            heading = np.degrees(np.unwrap(np.arctan2(shoulder[:, 2], shoulder[:, 0])))
            heading = _smooth(heading)
            out["shoulder_orientation_range_deg_proxy"] = _range(heading)
            curves["shoulder_orientation_deg_proxy"] = heading.tolist()
            velocity = np.abs(np.gradient(heading, times))
            active = velocity > 15
            out["turn_active_duration_s_proxy"] = float(np.sum(np.diff(times) * (active[:-1] & active[1:])))
            if _range(heading) < 25:
                issues.append("A clear turning movement was not visible. Repeat the selected turning task.")
        elif task == "sit_to_stand":
            knee = _smooth((left_knee + right_knee) / 2)
            out["knee_extension_range_deg_proxy"] = _range(knee)
            curves["mean_knee_angle_deg_proxy"] = knee.tolist()
            angle_change = float(np.percentile(knee, 90) - np.percentile(knee, 10))
            if angle_change >= 12:
                low, high = np.percentile(knee, [10, 90])
                # First observed low-to-high transition. Not a validated sit/stand classifier.
                starts = np.flatnonzero(knee <= low + 0.15 * (high - low))
                start = int(starts[0]) if len(starts) else 0
                ends = np.flatnonzero((knee >= high - 0.15 * (high - low)) & (np.arange(len(knee)) > start))
                if len(ends):
                    out["extension_transition_duration_s_proxy"] = float(times[ends[0]] - times[start])
            else:
                issues.append("A clear knee extension transition was not visible. Repeat sit-to-stand safely with hips and legs in view.")
        elif task == "reach":
            displacements = []
            for side, shoulder, wrist in [("left", 11, 15), ("right", 12, 16)]:
                reach = np.linalg.norm(image[:, wrist] - image[:, shoulder], axis=1) / scale
                out[f"{side}_reach_range_trunk_lengths_proxy"] = _range(_smooth(reach))
                curves[f"{side}_reach_trunk_lengths_proxy"] = reach.tolist()
                displacements.append(_range(_smooth(reach)))
            if max(displacements) < 0.12:
                issues.append("Little reaching activity was visible. Keep shoulders, elbows and wrists in view while reaching.")
    # Make sure JSON has only finite native floats; do not replace invalid values with 0.
    out = {key: float(value) for key, value in out.items() if np.isfinite(value)}
    metadata = {key: {"label": key.replace("_", " ").removesuffix(" proxy").capitalize(), "unit": _unit(key), "method": "Unvalidated landmark-derived functional monitoring proxy"} for key in out}
    return out, metadata, issues, curves


def _unit(key: str) -> str:
    if "_hz_" in key:
        return "Hz (proxy)"
    if "steps_per_min" in key:
        return "steps/min (proxy)"
    if "_deg_" in key:
        return "degrees (estimated)"
    if "_duration_s" in key:
        return "seconds"
    if "_count_" in key:
        return "cycles (proxy)"
    if "hand_lengths" in key:
        return "hand lengths (relative)"
    if "trunk_lengths" in key:
        return "trunk lengths (relative)"
    return "ratio (relative)"
