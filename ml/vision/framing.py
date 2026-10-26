"""How a recording was framed, so repeat recordings can be set up the same way.

Video measurements change with camera distance, angle and phone orientation.
This module summarizes framing from the stored image-plane landmarks and names
the differences between two recordings. It never adjusts a measurement.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any

from ml.vision.tasks import TASKS

SIZE_RATIO_LIMIT = 1.3
POSITION_LIMIT = 0.18
VIEW_RATIO_LIMIT = 0.3


def _visible(landmarks: Any, indexes: list[int]) -> list[tuple[float, float]]:
    if not isinstance(landmarks, list):
        return []
    points = []
    for index in indexes:
        if index >= len(landmarks):
            continue
        point = landmarks[index]
        if (isinstance(point, list) and len(point) >= 4 and all(isinstance(v, (int, float)) for v in point[:4])
                and all(math.isfinite(v) for v in point[:4]) and point[3] >= 0.5):
            points.append((float(point[0]), float(point[1])))
    return points


def framing_summary(result: dict) -> dict | None:
    """Median framing over the recording's frames, or None when it cannot be told."""
    if not isinstance(result, dict):
        return None
    spec = TASKS.get(result.get("task"))
    frames = result.get("landmark_frames")
    metadata = result.get("media_metadata") if isinstance(result.get("media_metadata"), dict) else {}
    width, height = metadata.get("width"), metadata.get("height")
    if not spec or not isinstance(frames, list) or not frames or not (isinstance(width, (int, float)) and isinstance(height, (int, float))) \
            or width <= 0 or height <= 0:
        return None
    long_side = max(width, height)
    sizes, centres_x, centres_y, views = [], [], [], []
    for frame in frames:
        landmarks = frame.get("landmarks") if isinstance(frame, dict) else None
        points = _visible(landmarks, spec["joints"])
        if len(points) < max(3, len(spec["joints"]) // 2):
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        sizes.append(max((max(xs) - min(xs)) * width, (max(ys) - min(ys)) * height) / long_side)
        centres_x.append((max(xs) + min(xs)) / 2)
        centres_y.append((max(ys) + min(ys)) / 2)
        if spec["kind"] == "pose":
            torso = _visible(landmarks, [11, 12, 23, 24])
            if len(torso) == 4:
                (lsx, lsy), (rsx, rsy), (lhx, lhy), (rhx, rhy) = torso
                shoulders = math.hypot((lsx - rsx) * width, (lsy - rsy) * height)
                length = math.hypot(((lsx + rsx) - (lhx + rhx)) / 2 * width, ((lsy + rsy) - (lhy + rhy)) / 2 * height)
                if length > 0:
                    views.append(shoulders / length)
    if len(sizes) < 3:
        return None
    summary = {"kind": spec["kind"], "size": round(median(sizes), 4), "centre_x": round(median(centres_x), 4),
               "centre_y": round(median(centres_y), 4), "orientation": "portrait" if height > width else "landscape",
               "frames": len(sizes)}
    if views:
        ratio = median(views)
        summary["view_ratio"] = round(ratio, 3)
        summary["view"] = "front" if ratio >= 0.5 else "side" if ratio <= 0.3 else "angled"
    return summary


def framing_differences(current: dict | None, reference: dict | None) -> list[str]:
    """Codes for setup differences that make two recordings less comparable."""
    if not current or not reference or current.get("kind") != reference.get("kind"):
        return []
    differences = []
    if current["orientation"] != reference["orientation"]:
        differences.append("orientation")
    if reference["size"] > 0:
        ratio = current["size"] / reference["size"]
        if ratio > SIZE_RATIO_LIMIT:
            differences.append("closer")
        elif ratio < 1 / SIZE_RATIO_LIMIT:
            differences.append("farther")
    if math.hypot(current["centre_x"] - reference["centre_x"], current["centre_y"] - reference["centre_y"]) > POSITION_LIMIT:
        differences.append("position")
    if "view_ratio" in current and "view_ratio" in reference and (
            current["view"] != reference["view"] or abs(current["view_ratio"] - reference["view_ratio"]) > VIEW_RATIO_LIMIT):
        differences.append("view")
    return differences


def touch_device_differences(current: dict, reference: dict) -> list[str]:
    """A different screen size or input makes touch measurements less comparable."""
    now, before = current.get("device"), reference.get("device")
    if not isinstance(now, dict) or not isinstance(before, dict):
        return []
    differences = []
    try:
        ratio = now["canvas_px"][0] / before["canvas_px"][0]
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        ratio = 1
    if not 0.8 <= ratio <= 1.25:
        differences.append("screen")
    if now.get("pointer") != before.get("pointer"):
        differences.append("pointer")
    return differences


def median_pose(result: dict) -> list[list[float]] | None:
    """Per-landmark median image position, for drawing how a recording was framed."""
    frames = result.get("landmark_frames") if isinstance(result, dict) else None
    if not isinstance(frames, list) or not frames:
        return None
    columns: dict[int, list[tuple[float, float]]] = {}
    for frame in frames:
        landmarks = frame.get("landmarks") if isinstance(frame, dict) else None
        for index in range(len(landmarks) if isinstance(landmarks, list) else 0):
            point = _visible(landmarks, [index])
            if point:
                columns.setdefault(index, []).append(point[0])
    if not columns:
        return None
    count = max(columns) + 1
    output = []
    for index in range(count):
        values = columns.get(index)
        output.append([median(v[0] for v in values), median(v[1] for v in values)] if values and len(values) >= 3 else None)
    return output
