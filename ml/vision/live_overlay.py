"""Focused live capture guides anchored to observed image landmarks.

The camera overlay is an image projection of detected joints. Its depth styling
uses genuine world XYZ, while the separate live viewer renders those coordinates
in meters. Neither display changes the recording or analysis measurements.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

import cv2
import numpy as np

from ml.vision.spatial import GAP_SECONDS, world_coordinates
from ml.vision.tasks import HAND_CONNECTIONS, POSE_CONNECTIONS, TASKS

MAX_LIVE_HISTORY = 45
MAX_TRAIL_SECONDS = 3.0
_TEAL = np.asarray((174, 234, 84), dtype=float)  # BGR; restrained luminous teal.
_BLUE = np.asarray((255, 182, 99), dtype=float)
_CONTEXT = (151, 137, 121)


def focus_definition(task: str) -> dict:
    """Return the same anatomically observed focus for camera and 3D displays."""
    spec = TASKS.get(task)
    if spec is None:
        raise ValueError("Select a supported movement task for the live guide.")
    if spec["kind"] == "hand":
        if task.startswith("finger_"):
            joints = tuple(range(9))
            edges = tuple((a, b) for a, b in HAND_CONNECTIONS if a in joints and b in joints)
            label = f"Thumb + index · {spec['side'].lower()} hand"
            trails = (4, 8)
        else:
            joints, edges = tuple(range(21)), tuple(HAND_CONNECTIONS)
            label = {
                "hand_open_close": "Palm + all five fingers",
                "grasp": "Palm + grasping fingers",
                "object_transfer": "Selected hand + fingertips",
            }.get(task, "Selected hand")
            trails = (4, 8, 12, 16, 20) if task == "hand_open_close" else (4, 8, 12)
    else:
        if task == "reach":
            joints = (11, 12, 13, 14, 15, 16)
            label, trails = "Shoulders + reaching arms", (15, 16)
        elif task == "gait":
            joints = (23, 24, 25, 26, 27, 28, 29, 30, 31, 32)
            label, trails = "Hips + knees + ankles", (27, 28)
        elif task == "sit_to_stand":
            joints = (11, 12, 23, 24, 25, 26, 27, 28)
            label, trails = "Trunk + hips + knees", (23, 24, 25, 26)
        else:
            joints = (11, 12, 23, 24, 25, 26, 27, 28)
            label, trails = "Shoulders + hips + turning legs", (11, 12, 23, 24)
        edges = tuple((a, b) for a, b in POSE_CONNECTIONS if a in joints and b in joints)
    return {"task": task, "kind": spec["kind"], "label": label, "joints": joints,
            "edges": edges, "trail_joints": trails}


def observation_geometry(observation: dict | None, task: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Require finite confident world XYZ and a visible image projection.

    Image Z never enters the geometry. Image X/Y are used only to hide joints
    outside the camera frame; a missing coordinate is never reconstructed.
    """
    if not isinstance(observation, dict) or task not in TASKS:
        return None
    spec = TASKS[task]
    count = 21 if spec["kind"] == "hand" else 33
    try:
        timestamp = float(observation.get("timestamp_s", float("nan")))
        image = np.asarray(observation.get("landmarks", []), dtype=float)
        if not np.isfinite(timestamp) or image.ndim != 2 or image.shape[0] != count or image.shape[1] < 3:
            return None
        if spec["kind"] == "hand":
            side = observation.get("hand_side")
            confidence = float(observation.get("handedness_confidence", float("nan")))
            if side not in {"Left", "Right"} or not np.isfinite(confidence) or confidence < 0.7:
                return None
            if spec.get("side") and side != spec["side"]:
                return None
    except (TypeError, ValueError):
        return None
    geometry = world_coordinates(observation, count)
    if geometry is None:
        return None
    points, valid = geometry
    valid &= np.all(np.isfinite(image[:, :2]), axis=1)
    valid &= np.all((image[:, :2] >= 0) & (image[:, :2] <= 1), axis=1)
    points[~valid] = np.nan
    if not any(valid[a] and valid[b] for a, b in focus_definition(task)["edges"]):
        return None
    return points, valid


def recent_observations(observation: dict | None, task: str,
                        history: Iterable[dict] | None = None) -> list[dict]:
    """Keep only the current bounded continuous sequence; do not bridge loss."""
    if observation_geometry(observation, task) is None:
        return []
    current_time = float(observation["timestamp_s"])
    # Snapshot lists are already bounded. Also bound arbitrary external input.
    supplied = list(deque(history or (), maxlen=MAX_LIVE_HISTORY))
    if not supplied or supplied[-1] is not observation:
        supplied.append(observation)
    collected = []
    for item in supplied[-MAX_LIVE_HISTORY:]:
        geometry = observation_geometry(item, task)
        if geometry is None:
            collected = []
            continue
        timestamp = float(item["timestamp_s"])
        if timestamp > current_time or current_time - timestamp > MAX_TRAIL_SECONDS:
            collected = []
            continue
        if collected:
            previous = collected[-1]
            delta = timestamp - float(previous["timestamp_s"])
            if delta == 0:
                collected[-1] = item
                continue
            if delta < 0 or delta > GAP_SECONDS or item.get("hand_side") != previous.get("hand_side"):
                collected = []
        collected.append(item)
    return collected[-MAX_LIVE_HISTORY:]


def _image_coordinates(observation: dict, width: int, height: int) -> np.ndarray:
    values = np.asarray(observation["landmarks"], dtype=float)[:, :2]
    # Invalid entries are excluded by the geometry mask before conversion.
    values = np.clip(np.nan_to_num(values, nan=0, posinf=1, neginf=0), 0, 1)
    return np.rint(values * np.asarray((width - 1, height - 1))).astype(int)


def _depth_color(depth: float, low: float, span: float) -> tuple[int, int, int]:
    blend = float(np.clip((depth - low) / max(span, 1e-6), 0, 1))
    return tuple(np.rint(_TEAL * (1 - blend) + _BLUE * blend).astype(int).tolist())


def draw_live_overlay(frame: np.ndarray, observation: dict | None, task: str, *,
                      history: Iterable[dict] | None = None, show_trails: bool = True) -> np.ndarray:
    """Copy a BGR frame and draw a bounded, depth styled focused capture guide."""
    output = frame.copy()
    if output.ndim != 3 or output.shape[2] != 3 or output.dtype != np.uint8:
        return output
    geometry = observation_geometry(observation, task)
    if geometry is None:
        return output
    points, valid = geometry
    focus = focus_definition(task)
    height, width = output.shape[:2]
    image = _image_coordinates(observation, width, height)
    thickness = max(2, min(5, round(min(width, height) / 200)))
    focus_depth = points[list(focus["joints"])][valid[list(focus["joints"])]][:, 2]
    low, span = float(np.min(focus_depth)), float(np.ptp(focus_depth))
    focused = {tuple(sorted(edge)) for edge in focus["edges"]}
    connections = HAND_CONNECTIONS if focus["kind"] == "hand" else POSE_CONNECTIONS
    context = output.copy()
    for a, b in connections:
        if valid[a] and valid[b] and tuple(sorted((a, b))) not in focused:
            cv2.line(context, tuple(image[a]), tuple(image[b]), _CONTEXT, max(1, thickness - 1), cv2.LINE_AA)
    output = cv2.addWeighted(context, 0.38, output, 0.62, 0)
    if show_trails:
        observations = recent_observations(observation, task, history)
        prepared = [(observation_geometry(item, task), _image_coordinates(item, width, height))
                    for item in observations]
        # Three band layers give a fading trail without allocating and blending
        # a full video frame for every historical observation.
        for band, indexes in enumerate(np.array_split(np.arange(1, len(prepared)), 3)):
            if not len(indexes):
                continue
            layer = output.copy()
            for n in indexes:
                previous_geometry, previous_image = prepared[n - 1]
                current_geometry, current_image = prepared[n]
                for joint in focus["trail_joints"]:
                    if previous_geometry[1][joint] and current_geometry[1][joint]:
                        color = _depth_color(float(current_geometry[0][joint, 2]), low, span)
                        cv2.line(layer, tuple(previous_image[joint]), tuple(current_image[joint]), color,
                                 max(1, thickness - 1), cv2.LINE_AA)
            fade = 0.14 + 0.18 * band
            output = cv2.addWeighted(layer, fade, output, 1 - fade, 0)
    glow = output.copy()
    for a, b in focus["edges"]:
        if valid[a] and valid[b]:
            color = _depth_color(float((points[a, 2] + points[b, 2]) / 2), low, span)
            cv2.line(glow, tuple(image[a]), tuple(image[b]), color, thickness + 7, cv2.LINE_AA)
    output = cv2.addWeighted(glow, 0.17, output, 0.83, 0)
    for a, b in focus["edges"]:
        if valid[a] and valid[b]:
            color = _depth_color(float((points[a, 2] + points[b, 2]) / 2), low, span)
            cv2.line(output, tuple(image[a]), tuple(image[b]), color, thickness, cv2.LINE_AA)
    for joint in focus["joints"]:
        if valid[joint]:
            color = _depth_color(float(points[joint, 2]), low, span)
            cv2.circle(output, tuple(image[joint]), thickness + 1, color, -1, cv2.LINE_AA)
            cv2.circle(output, tuple(image[joint]), max(1, thickness - 1), (243, 247, 244), -1, cv2.LINE_AA)
    return output
