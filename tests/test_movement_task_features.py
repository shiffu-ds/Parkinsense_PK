"""All movement tasks using invented geometry; no clinical accuracy claims."""

from copy import deepcopy
import json

import numpy as np
import pytest

from ml.vision.features import cycle_features, extract_features
from ml.vision.pipeline import frame_visible
from ml.vision.tasks import TASKS


TASK_FEATURE = {
    "finger_left": "tap_cycle_count_proxy",
    "finger_right": "tap_cycle_count_proxy",
    "hand_open_close": "opening_cycle_count_proxy",
    "grasp": "grip_aperture_range_ratio",
    "object_transfer": "wrist_path_hand_lengths_proxy",
    "gait": "cadence_steps_per_min_proxy",
    "turning": "shoulder_orientation_range_deg_proxy",
    "sit_to_stand": "extension_transition_duration_s_proxy",
    "reach": "left_reach_range_trunk_lengths_proxy",
}


def task_frames(task, count=120):
    frames = []
    for index in range(count):
        time = index / 20
        phase = np.sin(2 * np.pi * 1.5 * time)
        if TASKS[task]["kind"] == "hand":
            points = np.tile([0.5, 0.4, 0.0, 1.0], (21, 1))
            points[0, :2], points[9, :2] = [0.5, 0.75], [0.5, 0.5]
            points[4, :2] = [0.4, 0.4]
            points[8, :2] = [0.45 + 0.08 * (1 + phase), 0.4]
            if task == "hand_open_close":
                points[[8, 12, 16, 20], 1] = 0.55 - 0.12 * phase
            elif task == "object_transfer":
                points[:, 0] += 0.08 * phase
            world = points.copy()
        else:
            points = np.tile([0.5, 0.5, 0.0, 1.0], (33, 1))
            for joint, xy in {
                11: (0.42, 0.25), 12: (0.58, 0.25), 13: (0.35, 0.4), 14: (0.65, 0.4),
                15: (0.32, 0.5), 16: (0.68, 0.5), 23: (0.45, 0.55), 24: (0.55, 0.55),
                25: (0.45, 0.72), 26: (0.55, 0.72), 27: (0.45, 0.93), 28: (0.55, 0.93),
                31: (0.43, 0.95), 32: (0.57, 0.95),
            }.items():
                points[joint, :2] = xy
            if task == "gait":
                points[27, 0] += 0.07 * phase
                points[28, 0] -= 0.07 * phase
                points[15, 0] += 0.04 * phase
                points[16, 0] -= 0.04 * phase
            elif task == "reach":
                points[15, :2] = [0.35 - 0.12 * phase, 0.3]
            world = points.copy()
            if task == "turning":
                angle = np.radians(-50 + index / (count - 1) * 100)
                direction = np.asarray([0.15 * np.cos(angle), 0, 0.15 * np.sin(angle)])
                world[11, :3], world[12, :3] = np.asarray([0.5, 0.25, 0]) - direction, np.asarray([0.5, 0.25, 0]) + direction
            elif task == "sit_to_stand":
                angle = np.radians(90 + index / (count - 1) * 85)
                for hip, knee, ankle in ((23, 25, 27), (24, 26, 28)):
                    world[hip, :3] = world[knee, :3] + [0, -0.2, 0]
                    world[ankle, :3] = world[knee, :3] + [0.2 * np.sin(angle), -0.2 * np.cos(angle), 0]
        frame = {"timestamp_s": time, "landmarks": points.tolist(), "world_landmarks": world.tolist()}
        if TASKS[task]["kind"] == "hand":
            frame.update(hand_side=TASKS[task].get("side", "Left"), handedness_confidence=0.95)
        frames.append(frame)
    return frames


@pytest.mark.parametrize("task", TASKS)
def test_every_task_produces_its_own_finite_features_for_visible_test_motion(task):
    frames = task_frames(task)
    assert all(frame_visible(frame, task) for frame in frames)
    features, metadata, issues, curves = extract_features(frames, task)
    assert not issues
    assert TASK_FEATURE[task] in features
    assert features[TASK_FEATURE[task]] > 0
    assert set(features) == set(metadata)
    assert all(definition["unit"] for definition in metadata.values())
    assert len(curves["timestamp_s"]) == len(frames)
    json.dumps([features, metadata, curves], allow_nan=False)


@pytest.mark.parametrize("problem", ["occluded", "outside_camera", "invalid_world", "missing_world"])
def test_reach_never_reports_unrequired_knees_or_uses_them_for_acceptance(problem):
    frames = task_frames("reach")
    original, _, _, _ = extract_features(frames, "reach")
    for frame in frames:
        for joint in (25, 26, 27, 28, 29, 30, 31, 32):
            if problem == "occluded":
                frame["landmarks"][joint][3] = frame["world_landmarks"][joint][3] = 0.01
            elif problem == "outside_camera":
                frame["landmarks"][joint][:2] = [-10, -10]
            elif problem == "invalid_world":
                frame["world_landmarks"][joint][:3] = [float("nan")] * 3
        if problem == "missing_world":
            del frame["world_landmarks"]
    assert all(frame_visible(frame, "reach") for frame in frames)
    features, metadata, issues, curves = extract_features(frames, "reach")
    assert not issues
    assert features == original
    assert not any("knee" in key for values in (features, metadata, curves) for key in values)
    json.dumps([features, metadata, curves], allow_nan=False)


@pytest.mark.parametrize("shape", ["stationary_segments", "opening_only_segments"])
def test_gaps_cannot_create_cycles_when_each_observed_segment_has_none(shape):
    times = np.concatenate([np.arange(20) * 0.05 + start for start in (0, 1.4, 2.8)])
    signal = np.repeat([0.0, 1.0, 0.0], 20) if shape == "stationary_segments" else np.tile(np.linspace(0, 1, 20), 3)
    features = cycle_features(signal, times, "tap")
    assert features["tap_cycle_count_proxy"] == 0
    assert features["tap_frequency_hz_proxy"] == 0
    assert "tap_interval_cv_proxy" not in features


def test_observed_cycles_keep_frequency_and_do_not_count_unobserved_gap_time():
    first_times = np.arange(60) * 0.05
    signal = 0.3 + 0.15 * np.sin(2 * np.pi * 2 * first_times)
    first = cycle_features(signal, first_times, "tap")
    joined_times = np.concatenate([first_times, first_times + 4])
    joined = cycle_features(np.concatenate([signal, signal + 2]), joined_times, "tap")
    assert 1.8 < first["tap_frequency_hz_proxy"] < 2.2
    assert joined["tap_cycle_count_proxy"] == 2 * first["tap_cycle_count_proxy"]
    assert joined["tap_frequency_hz_proxy"] == pytest.approx(first["tap_frequency_hz_proxy"])
    assert joined["tap_interval_cv_proxy"] == pytest.approx(first["tap_interval_cv_proxy"], abs=1e-12)


def stationary_segments(task):
    source = task_frames(task)
    frames = []
    for segment, start in enumerate((0, 1.4, 2.8)):
        sample = source[0 if segment != 1 else -1]
        for index in range(20):
            frame = deepcopy(sample)
            frame["timestamp_s"] = start + index * 0.05
            if TASKS[task]["kind"] == "hand":
                for kind in ("landmarks", "world_landmarks"):
                    for point in frame[kind]:
                        point[0] += 0.2 if segment == 1 else 0
            frames.append(frame)
    return frames


def test_object_transfer_does_not_invent_wrist_travel_at_tracking_gaps():
    features, _, issues, _ = extract_features(stationary_segments("object_transfer"), "object_transfer")
    assert features["wrist_path_hand_lengths_proxy"] == pytest.approx(0, abs=1e-6)
    assert any("wrist travel" in issue for issue in issues)


def test_turning_does_not_measure_hidden_rotation_between_stationary_observations():
    features, _, issues, curves = extract_features(stationary_segments("turning"), "turning")
    assert features["shoulder_orientation_range_deg_proxy"] == pytest.approx(0, abs=1e-6)
    assert features["turn_active_duration_s_proxy"] == 0
    assert any("turning movement" in issue for issue in issues)
    assert len(curves["shoulder_orientation_deg_proxy"]) == 60


def test_sit_to_stand_requires_a_visible_transition_within_one_continuous_segment():
    features, _, issues, _ = extract_features(stationary_segments("sit_to_stand"), "sit_to_stand")
    assert features["knee_extension_range_deg_proxy"] > 70
    assert "extension_transition_duration_s_proxy" not in features
    assert any("continuous knee extension" in issue for issue in issues)


@pytest.mark.parametrize("corruption", ["duplicate", "backwards", "nonfinite"])
def test_invalid_timing_returns_actionable_issue_without_features_or_curves(corruption):
    frames = task_frames("finger_left")
    frames[10]["timestamp_s"] = {"duplicate": frames[9]["timestamp_s"], "backwards": -1, "nonfinite": float("nan")}[corruption]
    features, metadata, issues, curves = extract_features(frames, "finger_left")
    assert not features and not metadata and not curves
    assert "timestamps" in issues[0]
