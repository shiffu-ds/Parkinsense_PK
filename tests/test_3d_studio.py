"""Geometry/display tests; synthetic fixtures do not validate model accuracy."""

from __future__ import annotations

from copy import deepcopy
import json

import numpy as np
import pytest

from app.components.pose_3d_viewer import build_motion_figure, build_motion_html
from ml.vision.pipeline import LandmarkRecorder
from ml.vision.spatial import motion_frame_summary, prepare_motion, world_coordinates


def hand_result(count=100):
    points = np.ones((21, 4))
    points[0, :3] = [0, 0.065, 0]
    for finger, first in enumerate((1, 5, 9, 13, 17)):
        for joint in range(4):
            points[first + joint, :3] = [-0.04 + finger * 0.02, 0.025 - joint * 0.025, joint * 0.002]
    frames = []
    for n in range(count):
        world = points.copy()
        world[8, 2] += 0.012 * np.sin(n * 0.2)
        image = np.ones((21, 4))
        image[:, :3] = [0.5, 0.5, 0]
        frames.append({"timestamp_s": n / 20, "landmarks": image.tolist(), "world_landmarks": world.tolist(), "hand_side": "Left", "handedness_confidence": 0.95})
    return {"task": "finger_left", "landmark_frames": frames, "media_metadata": {"width": 640, "height": 480}}


def body_result(count=3):
    points = np.ones((33, 4))
    points[:, :3] = [0, -0.6, 0]
    for index in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        points[index, :3] = [(index % 3 - 1) * 0.035, -0.65, -0.025]
    for index, xyz in {11: [-0.2, -0.48, 0], 12: [0.2, -0.48, 0], 13: [-0.28, -0.25, 0], 14: [0.28, -0.25, 0],
                       15: [-0.28, -0.02, 0], 16: [0.28, -0.02, 0], 23: [-0.12, 0, 0], 24: [0.12, 0, 0],
                       25: [-0.13, 0.4, 0], 26: [0.13, 0.4, 0], 27: [-0.13, 0.78, 0], 28: [0.13, 0.78, 0],
                       29: [-0.13, 0.81, 0.03], 30: [0.13, 0.81, 0.03], 31: [-0.13, 0.81, -0.12], 32: [0.13, 0.81, -0.12]}.items():
        points[index, :3] = xyz
    frames = []
    for n in range(count):
        world = points.copy()
        world[15, 2] -= n * 0.03
        frames.append({"timestamp_s": n / 10, "world_landmarks": world.tolist(), "landmarks": points.tolist()})
    return {"task": "reach", "landmark_frames": frames}


def test_world_xyz_is_independent_of_image_aspect_and_normalized_depth():
    result = hand_result(5)
    changed = deepcopy(result)
    changed["media_metadata"] = {"width": 9000, "height": 3}
    for frame in changed["landmark_frames"]:
        for point in frame["landmarks"]:
            point[:3] = [0.9, 0.1, 5000]
    assert build_motion_figure(result).to_json() == build_motion_figure(changed).to_json()
    motion = prepare_motion(result)
    assert motion.points[0, 0, 1] == pytest.approx(-0.065)
    assert motion.points[0, 8, 2] == pytest.approx(result["landmark_frames"][0]["world_landmarks"][8][2])


def test_missing_world_coordinates_never_become_pseudo_3d():
    result = hand_result(5)
    for frame in result["landmark_frames"]:
        del frame["world_landmarks"]
    figure = build_motion_figure(result)
    assert not figure.frames
    assert not figure.data
    assert "World landmarks" in figure.layout.annotations[0].text
    assert motion_frame_summary(result)["available"] is False


def test_finite_confident_joints_only_and_no_interpolation_through_occlusions():
    result = hand_result(8)
    result["landmark_frames"][2]["world_landmarks"][8] = [1000, 1000, 1000, 0.1]
    result["landmark_frames"][3]["world_landmarks"][8][0] = float("nan")
    points, valid = world_coordinates(result["landmark_frames"][2], 21)
    assert not valid[8] and np.all(np.isnan(points[8]))
    motion = prepare_motion(result, smooth=True)
    assert not motion.valid[2, 8]
    assert motion.breaks[4, 8]
    figure = build_motion_figure(result)
    assert figure.layout.scene.xaxis.range[1] < 1
    assert None in figure.frames[-1].data[-1].x
    json.dumps(figure.to_plotly_json(), default=lambda value: value.tolist(), allow_nan=False)


def test_initial_centering_preserves_subsequent_motion_and_scale():
    result = body_result(3)
    for n, frame in enumerate(result["landmark_frames"]):
        for point in frame["world_landmarks"]:
            point[0] += 3 + n * 0.1
    motion = prepare_motion(result)
    assert np.mean(motion.points[0, [23, 24], 0]) == pytest.approx(0)
    assert np.mean(motion.points[2, [23, 24], 0]) == pytest.approx(0.2)
    assert np.linalg.norm(motion.points[0, 11] - motion.points[0, 12]) == pytest.approx(0.4)


def test_baseline_same_origin_same_scale_and_task_side_isolation():
    result = body_result()
    baseline = deepcopy(result)
    for frame in baseline["landmark_frames"]:
        for point in frame["world_landmarks"]:
            point[0] += 2
    figure = build_motion_figure(result, baseline, style="Skeleton", show_trails=False)
    for axis in ("x", "y", "z"):
        current = [value for value in getattr(figure.data[0], axis) if value is not None]
        previous = [value for value in getattr(figure.data[3], axis) if value is not None]
        assert current == pytest.approx(previous)
    assert figure.layout.scene.aspectmode == "data"
    assert figure.layout.meta["baseline_alignment"] == "initial origins; unchanged scale; relative time"
    baseline["task"] = "gait"
    assert not any(trace.name.startswith("Baseline") for trace in build_motion_figure(result, baseline).data)
    hand = hand_result(5)
    other = deepcopy(hand)
    for frame in other["landmark_frames"]:
        frame["hand_side"] = "Right"
    assert not any(trace.name.startswith("Baseline") for trace in build_motion_figure(hand, other).data)


def test_mesh_replay_is_bounded_fixed_axes_and_controlled():
    result = hand_result(900)
    figure = build_motion_figure(result, playback_speed=0.5, camera="Top")
    assert len(figure.frames) == 90
    assert len(figure.layout.sliders[0].steps) == 90
    assert figure.data[0].type == "mesh3d"
    assert len(figure.data[0].i) > 400
    assert len(figure.data) <= 6
    assert len(figure.to_json()) < 3_000_000
    assert all(list(frame.traces) == [0, 1, 2] for frame in figure.frames)
    assert figure.layout.scene.camera.up.y == 1
    assert figure.layout.scene.xaxis.autorange is False
    assert figure.layout.scene.camera.projection.type == "orthographic"
    assert "not measured floor" in figure.data[-2].name
    assert figure.layout.meta["coordinate_source"] == "world_landmarks"


def test_recording_gaps_remain_broken_after_downsampling():
    result = hand_result(900)
    for n, frame in enumerate(result["landmark_frames"]):
        if n >= 450:
            frame["timestamp_s"] += 1.0
    motion = prepare_motion(result)
    assert np.any(motion.breaks[1:, 8])
    assert motion_frame_summary(result)["model_local"] is True
    assert "not its route through the room" in motion_frame_summary(result)["note"]


def test_snapshot_opt_in_copy_is_detached_and_does_not_contain_video(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.vision.pipeline.time.monotonic", lambda: 10.0)
    recorder = LandmarkRecorder("finger_left", tmp_path / "live.avi")
    recorder._last_observation = hand_result(1)["landmark_frames"][0]
    # This fixture represents an observation from an active camera. Without
    # these receipt times, the new freshness gate correctly rejects it.
    recorder._last_frame_received_at = recorder._last_observed_at = 10.0
    assert "observation" not in recorder.snapshot()
    snapshot = recorder.snapshot(include_landmarks=True)
    assert snapshot["observation"]["world_landmarks"]
    snapshot["observation"]["world_landmarks"][0][0] = 999
    assert recorder.snapshot(include_landmarks=True)["observation"]["world_landmarks"][0][0] != 999
    assert recorder.overlay is False
    json.dumps(snapshot, allow_nan=False)
    recorder.close()


def test_standalone_export_contains_coordinates_and_no_patient_labels_media_or_cdn():
    result = hand_result(2)
    result["patient_name"] = "Sensitive Test Name"
    result["notes"] = "</script><script>alert('test');</script>"
    result["media_metadata"]["path"] = "/private/patient.mp4"
    html = build_motion_html(result)
    assert "Sensitive Test Name" not in html
    assert "alert('test')" not in html
    assert "/private/patient.mp4" not in html
    assert '<script src="https://cdn.plot.ly' not in html
    assert "plotly.js" in html
    assert "Model-local estimate" in html
    assert "This file contains movement landmarks" in html
    assert "Plotly.newPlot" in html
