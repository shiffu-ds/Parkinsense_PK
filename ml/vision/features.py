"""Conservative motion proxies; no clinical score or disease prediction.

Image-plane distances are aspect-corrected then divided by a body/hand scale.
Angles use MediaPipe's approximate hip-/hand-centered world coordinates when
available. Nothing here treats monocular depth as a measured walking distance.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, savgol_filter


def _smooth(values: np.ndarray) -> np.ndarray:
    # Filtering float32 landmarks can turn a constant segment into apparent
    # motion. Keep temporal calculations in double precision.
    values = np.asarray(values, dtype=np.float64)
    if len(values) < 7:
        return values
    size = min(9, len(values) if len(values) % 2 else len(values) - 1)
    return savgol_filter(values, size, 2)


def _continuous_slices(times: np.ndarray) -> list[slice]:
    """Separate observed runs before any temporal filtering or derivatives."""
    if len(times) < 2:
        return [slice(0, len(times))]
    deltas = np.diff(times)
    positive = deltas[np.isfinite(deltas) & (deltas > 0)]
    if not len(positive):
        return [slice(index, index + 1) for index in range(len(times))]
    limit = 2.5 * float(np.median(positive))
    boundaries = np.flatnonzero(~np.isfinite(deltas) | (deltas <= 0) | (deltas > limit)) + 1
    starts, ends = np.r_[0, boundaries], np.r_[boundaries, len(times)]
    return [slice(int(start), int(end)) for start, end in zip(starts, ends)]


def _smooth_segments(values: np.ndarray, times: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    for segment in _continuous_slices(times):
        result[segment] = _smooth(result[segment])
    return result


def _range(values: np.ndarray) -> float:
    return float(np.percentile(values, 95) - np.percentile(values, 5))


def _gait_arm_swing(points: np.ndarray, image: np.ndarray, scale: np.ndarray) -> float | None:
    """Require usable observations of each arm; missing movement is not zero.

    Gait's main visibility gate does not require wrists. Use normalized image
    bounds before aspect correction and exclude unreliable samples from the
    range itself, rather than only checking a recording-wide confidence mean.
    """
    ranges = []
    for shoulder, wrist in ((11, 15), (12, 16)):
        selected = points[:, [shoulder, wrist], :4]
        valid = np.all(np.isfinite(selected), axis=(1, 2))
        valid &= np.all((selected[:, :, :2] >= 0) & (selected[:, :, :2] <= 1), axis=(1, 2))
        valid &= np.all(selected[:, :, 3] >= 0.5, axis=1)
        valid &= np.isfinite(scale) & (scale > 0)
        usable = int(np.count_nonzero(valid))
        if usable < 20 or usable / len(points) < 0.7:
            return None
        displacement = (image[valid, wrist, 0] - image[valid, shoulder, 0]) / scale[valid]
        ranges.append(_range(displacement))
    return float(np.mean(ranges))


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
    segments = _continuous_slices(times)
    values = _smooth_segments(signal, times)
    duration = sum(float(times[segment][-1] - times[segment][0]) for segment in segments if len(times[segment]) > 1)
    amplitude = _range(values)
    peak_count = 0
    good = []
    for segment in segments:
        segment_times = times[segment]
        if len(segment_times) < 3:
            continue
        dt = float(np.median(np.diff(segment_times)))
        prominence = max(_range(values[segment]) * 0.2, 0.025)
        # Resolve numerically equal flat peaks consistently after translation
        # or filtering, rather than letting floating-point noise choose a frame.
        peak_values = np.round(values[segment] - values[segment][0], decimals=12)
        peaks, _ = find_peaks(peak_values, prominence=prominence, distance=max(1, round(0.2 / dt)))
        peak_count += len(peaks)
        # Both extrema and rhythm intervals must belong to one tracked run.
        # Smoothing a concatenated track invents peaks beside missing frames.
        good.extend(np.diff(segment_times[peaks]).tolist())
    n = max(3, len(values) // 3)
    early = _range(values[:n])
    late = _range(values[-n:])
    out = {
        f"{prefix}_cycle_count_proxy": float(peak_count),
        f"{prefix}_frequency_hz_proxy": float(peak_count / max(duration, 1e-6)),
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
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
        return {}, {}, ["Recording timestamps are invalid. Repeat or re-export the recording."], {}
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
        wrist = np.column_stack([_smooth_segments(image[:, 0, i], times) for i in range(2)])
        # Divide wrist path by the recording's median hand length, not a moving scale.
        path = np.linalg.norm(np.diff(wrist, axis=0), axis=1)
        contiguous = np.diff(times) <= 2.5 * np.median(np.diff(times))
        out["wrist_path_hand_lengths_proxy"] = float(np.sum(path[contiguous]) / np.median(scale))
        if task == "object_transfer":
            if out["wrist_path_hand_lengths_proxy"] < 0.3:
                issues.append("Little wrist travel was detected. Repeat the transfer with the whole hand visible.")
        elif max(_range(_smooth(signal[segment])) for segment in _continuous_slices(times)) < 0.08:
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
        if task != "reach":
            # Reach requires shoulders, arms and hips, not legs. A detector may
            # still predict occluded knees; those predictions cannot become
            # supported knee measurements in an upper-body recording.
            left_knee = joint_angle(angle_points, 23, 25, 27)
            right_knee = joint_angle(angle_points, 24, 26, 28)
            curves.update({"left_knee_angle_deg_proxy": left_knee.tolist(), "right_knee_angle_deg_proxy": right_knee.tolist()})
            out.update({"left_knee_range_deg_proxy": _range(left_knee), "right_knee_range_deg_proxy": _range(right_knee)})
        hip_y = _smooth_segments((image[:, 23, 1] + image[:, 24, 1]) / 2, times)
        out["hip_vertical_range_trunk_lengths_proxy"] = _range(hip_y) / float(np.median(scale))
        if task == "gait":
            separation = (image[:, 27, 0] - image[:, 28, 0]) / scale
            out.update(cycle_features(separation, times, "gait"))
            # A separation peak occurs once per gait cycle; both feet contribute steps.
            out["cadence_steps_per_min_proxy"] = out.pop("gait_frequency_hz_proxy") * 120
            left_range = _range(image[:, 27, 0] / scale)
            right_range = _range(image[:, 28, 0] / scale)
            out["ankle_range_asymmetry_proxy"] = float(abs(left_range - right_range) / max(left_range + right_range, 0.01))
            arm_swing = _gait_arm_swing(points, image, scale)
            if arm_swing is not None:
                out["arm_swing_trunk_lengths_proxy"] = arm_swing
            curves["ankle_separation_trunk_lengths_proxy"] = separation.tolist()
            if _range(separation) < 0.1 and max(_range(left_knee), _range(right_knee)) < 8:
                issues.append("Little stepping activity was visible. Repeat walking with the full body in view.")
        elif task == "turning":
            shoulder = angle_points[:, 12, :3] - angle_points[:, 11, :3]
            heading = np.degrees(np.arctan2(shoulder[:, 2].astype(float), shoulder[:, 0].astype(float)))
            active_duration = 0.0
            segment_ranges = []
            for segment in _continuous_slices(times):
                segment_times = times[segment]
                local = _smooth(np.degrees(np.unwrap(np.radians(heading[segment]))))
                heading[segment] = local
                segment_ranges.append(_range(local))
                if len(segment_times) > 1:
                    active = np.abs(np.gradient(local, segment_times)) > 15
                    active_duration += float(np.sum(np.diff(segment_times) * (active[:-1] & active[1:])))
            out["shoulder_orientation_range_deg_proxy"] = max(segment_ranges)
            curves["shoulder_orientation_deg_proxy"] = heading.tolist()
            out["turn_active_duration_s_proxy"] = active_duration
            if max(segment_ranges) < 25:
                issues.append("A clear turning movement was not visible. Repeat the selected turning task.")
        elif task == "sit_to_stand":
            knee = _smooth_segments((left_knee + right_knee) / 2, times)
            out["knee_extension_range_deg_proxy"] = _range(knee)
            curves["mean_knee_angle_deg_proxy"] = knee.tolist()
            angle_change = float(np.percentile(knee, 90) - np.percentile(knee, 10))
            if angle_change >= 12:
                low, high = np.percentile(knee, [10, 90])
                # First observed low-to-high transition. Not a validated sit/stand classifier.
                for segment in _continuous_slices(times):
                    local = knee[segment]
                    starts = np.flatnonzero(local <= low + 0.15 * (high - low))
                    if not len(starts):
                        continue
                    start = int(starts[0])
                    ends = np.flatnonzero((local >= high - 0.15 * (high - low)) & (np.arange(len(local)) > start))
                    if len(ends):
                        local_times = times[segment]
                        out["extension_transition_duration_s_proxy"] = float(local_times[ends[0]] - local_times[start])
                        break
                if "extension_transition_duration_s_proxy" not in out:
                    issues.append("A continuous knee extension transition was not visible. Repeat sit-to-stand with hips and legs in view throughout the movement.")
            else:
                issues.append("A clear knee extension transition was not visible. Repeat sit-to-stand safely with hips and legs in view.")
        elif task == "reach":
            displacements = []
            for side, shoulder, wrist in [("left", 11, 15), ("right", 12, 16)]:
                reach = np.linalg.norm(image[:, wrist] - image[:, shoulder], axis=1) / scale
                out[f"{side}_reach_range_trunk_lengths_proxy"] = _range(_smooth_segments(reach, times))
                curves[f"{side}_reach_trunk_lengths_proxy"] = reach.tolist()
                displacements.append(max(_range(_smooth(reach[segment])) for segment in _continuous_slices(times)))
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
