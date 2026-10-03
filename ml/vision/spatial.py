"""Truthful, bounded model-local 3D geometry for display only.

MediaPipe world coordinates estimate meters around the hips or hand center.
They contain articulated 3D geometry, not a calibrated global walking route.
Display processing never modifies feature extraction or persisted observations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml.vision.tasks import TASKS

MAX_REPLAY_FRAMES = 90
VISIBILITY_THRESHOLD = 0.5
GAP_SECONDS = 0.35


@dataclass(frozen=True)
class SpatialMotion:
    points: np.ndarray
    valid: np.ndarray
    timestamps: np.ndarray
    breaks: np.ndarray
    kind: str
    side: str
    source_count: int
    usable_count: int
    origin: np.ndarray


def world_coordinates(frame: dict, expected_count: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Require actual world XYZ. Image-normalized XYZ is never a substitute."""
    try:
        values = np.asarray(frame.get("world_landmarks", []), dtype=float)
    except (TypeError, ValueError):
        return None
    if values.ndim != 2 or values.shape[0] != expected_count or values.shape[1] < 3:
        return None
    points = values[:, :3].copy()
    valid = np.all(np.isfinite(points), axis=1)
    if values.shape[1] >= 4:
        valid &= np.isfinite(values[:, 3]) & (values[:, 3] >= VISIBILITY_THRESHOLD)
    # Pose world visibility should mirror image visibility. Conservatively use
    # both when present; image XYZ and aspect ratio never enter the 3D geometry.
    try:
        image = np.asarray(frame.get("landmarks", []), dtype=float)
        if image.ndim == 2 and image.shape[0] == expected_count and image.shape[1] >= 4:
            valid &= np.isfinite(image[:, 3]) & (image[:, 3] >= VISIBILITY_THRESHOLD)
    except (TypeError, ValueError):
        pass
    if expected_count == 21:
        confidence = frame.get("handedness_confidence", 1.0)
        try:
            if not np.isfinite(float(confidence)) or float(confidence) < 0.7:
                valid[:] = False
        except (ValueError, TypeError):
            valid[:] = False
    # Render x right, y up and z away. This is a rigid reflection, not a scale
    # conversion or camera-calibration estimate.
    points[:, 1] *= -1
    points[~valid] = np.nan
    return points, valid


def prepare_motion(result: dict, *, center: bool = True, smooth: bool = False) -> SpatialMotion | None:
    """Center once, preserve native metric scale and break detection gaps."""
    source = result.get("landmark_frames", [])
    kind = TASKS.get(result.get("task"), {}).get("kind")
    if kind is None:
        first = next((frame.get("world_landmarks") for frame in source if frame.get("world_landmarks")), [])
        kind = "hand" if len(first) == 21 else "pose"
    count = 21 if kind == "hand" else 33
    collected = []
    for frame in source:
        geometry = world_coordinates(frame, count)
        try:
            timestamp = float(frame.get("timestamp_s", float("nan")))
        except (TypeError, ValueError):
            continue
        if geometry is None or not np.isfinite(timestamp) or np.count_nonzero(geometry[1]) < 2:
            continue
        if collected and timestamp <= collected[-1][0]:
            continue
        # A local hand may be selected independently. Do not blend two sides.
        side = frame.get("hand_side", "")
        side = side if side in {"Left", "Right"} else ""
        if kind == "hand" and collected and side and collected[0][3] and side != collected[0][3]:
            continue
        collected.append((timestamp, *geometry, side))
    if not collected:
        return None
    timestamps = np.asarray([entry[0] for entry in collected])
    points = np.stack([entry[1] for entry in collected])
    valid = np.stack([entry[2] for entry in collected])
    origin = np.zeros(3)
    if center:
        if kind == "pose":
            # Require both hips; using a shoulder/ankle as origin would change
            # the coordinate meaning when an occluded hip reappears.
            root_frame = next((n for n, mask in enumerate(valid) if mask[23] and mask[24]), None)
            if root_frame is not None:
                origin = np.mean(points[root_frame, [23, 24]], axis=0)
        else:
            # Native world origin is the model's hand center. Keep it, rather
            # than inventing a moving wrist-relative global coordinate system.
            origin = np.zeros(3)
        points = points - origin
    raw_breaks = np.zeros(valid.shape, dtype=bool)
    raw_breaks[0] = True
    for n in range(1, len(points)):
        raw_breaks[n] = (~valid[n - 1]) | (~valid[n]) | (timestamps[n] - timestamps[n - 1] > GAP_SECONDS)
        if smooth:
            continuous = ~raw_breaks[n]
            # Mild causal display smoothing only; no interpolation through gaps.
            points[n, continuous] = 0.7 * points[n, continuous] + 0.3 * points[n - 1, continuous]
    indexes = np.linspace(0, len(points) - 1, min(MAX_REPLAY_FRAMES, len(points)), dtype=int)
    breaks = np.zeros((len(indexes), count), dtype=bool)
    breaks[0] = True
    for n in range(1, len(indexes)):
        breaks[n] = np.any(raw_breaks[indexes[n - 1] + 1:indexes[n] + 1], axis=0)
    return SpatialMotion(points[indexes], valid[indexes], timestamps[indexes], breaks, kind,
                         collected[0][3], len(source), len(collected), origin)


def motion_frame_summary(result: dict) -> dict:
    motion = prepare_motion(result)
    hand = TASKS.get(result.get("task"), {}).get("kind") == "hand"
    note = (
        "Hand-centered 3D articulation; the wrist trail is local to the hand, not its route through the room."
        if hand else
        "Hip-centered 3D articulation; this view cannot measure a global walking path, travel distance or floor contact."
    )
    summary = {
        "available": motion is not None,
        "source": "MediaPipe world_landmarks",
        "units": "Estimated meters",
        "axes": "X right · Y up · Z away",
        "reference": "Hand center" if hand else "Hip center",
        "model_local": True,
        "note": note,
        "source_frames": len(result.get("landmark_frames", [])),
        "usable_frames": 0 if motion is None else motion.usable_count,
        "replay_frames": 0 if motion is None else len(motion.timestamps),
        "range_m": None,
    }
    if motion is not None:
        selected = motion.points[motion.valid]
        summary["range_m"] = {axis: round(float(np.ptp(selected[:, n])), 4)
                              for n, axis in enumerate(("x", "y", "z"))}
    return summary
