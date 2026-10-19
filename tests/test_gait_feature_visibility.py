"""Invented geometry checks missing-data handling, not clinical accuracy."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from ml.vision.features import _gait_arm_swing, extract_features

ARM_SWING = "arm_swing_trunk_lengths_proxy"


def gait_frames(count=100):
    frames = []
    for index in range(count):
        phase = np.sin(index * 0.5)
        points = np.tile([0.5, 0.5, 0.0, 1.0], (33, 1))
        for joint, xy in {
            11: (0.42, 0.3), 12: (0.58, 0.3),
            15: (0.42 + 0.08 * phase, 0.5), 16: (0.58 - 0.06 * phase, 0.5),
            23: (0.45, 0.55), 24: (0.55, 0.55),
            25: (0.43, 0.7), 26: (0.57, 0.7),
            27: (0.43 + 0.06 * phase, 0.9), 28: (0.57 - 0.06 * phase, 0.9),
        }.items():
            points[joint, :2] = xy
        frames.append({"timestamp_s": index / 10, "landmarks": points.tolist(),
                       "world_landmarks": points.tolist()})
    return frames


def test_valid_gait_arms_preserve_actual_range_and_units():
    frames = gait_frames()
    features, definitions, issues, curves = extract_features(frames, "gait", aspect_ratio=1.5)
    points = np.asarray([frame["landmarks"] for frame in frames], dtype=np.float32)
    ranges = []
    for shoulder, wrist in ((11, 15), (12, 16)):
        displacement = (points[:, wrist, 0] - points[:, shoulder, 0]) * 1.5 / 0.25
        ranges.append(np.percentile(displacement, 95) - np.percentile(displacement, 5))
    assert features[ARM_SWING] == pytest.approx(float(np.mean(ranges)), rel=1e-6)
    assert definitions[ARM_SWING]["unit"] == "trunk lengths (relative)"
    assert not issues
    assert len(curves["timestamp_s"]) == len(frames)


@pytest.mark.parametrize("joint", [15, 16])
@pytest.mark.parametrize("corruption", ["confidence", "nan_x", "nan_y", "nan_z", "nan_confidence", "offscreen_x", "offscreen_y"])
def test_unreliable_arm_observations_omit_measurement_and_definition(joint, corruption):
    frames = gait_frames()
    for frame in frames[:31]:
        point = frame["landmarks"][joint]
        if corruption == "confidence":
            point[3] = 0.49
        elif corruption.startswith("nan_"):
            coordinate = {"x": 0, "y": 1, "z": 2, "confidence": 3}[corruption[4:]]
            point[coordinate] = float("nan")
        elif corruption == "offscreen_x":
            point[0] = -0.1
        else:
            point[1] = 1.1
    features, definitions, _, _ = extract_features(frames, "gait")
    assert ARM_SWING not in features
    assert ARM_SWING not in definitions


@pytest.mark.parametrize("shoulder", [11, 12])
@pytest.mark.parametrize("coordinate, value", [(0, float("nan")), (1, float("nan")),
                                                (2, float("nan")), (3, float("nan")),
                                                (3, 0.49), (0, -0.1), (1, 1.1)])
def test_unreliable_corresponding_shoulder_cannot_supply_arm_swing(shoulder, coordinate, value):
    points = np.asarray([frame["landmarks"] for frame in gait_frames()], dtype=np.float32)
    points[:31, shoulder, coordinate] = value
    # Nonfinite required shoulders are removed by the pipeline's visibility
    # gate before the extractor. Exercise this additional arm safeguard alone.
    assert _gait_arm_swing(points, points[:, :, :2], np.full(len(points), 0.25)) is None


@pytest.mark.parametrize("usable, expected", [(69, False), (70, True), (71, True)])
def test_both_sides_require_seventy_percent_usable_samples(usable, expected):
    frames = gait_frames()
    for frame in frames[usable:]:
        frame["landmarks"][15][3] = 0.49
    features, _, _, _ = extract_features(frames, "gait")
    assert (ARM_SWING in features) is expected


@pytest.mark.parametrize("count, expected", [(19, False), (20, True)])
def test_fully_visible_short_tracks_still_require_twenty_samples(count, expected):
    features, _, _, _ = extract_features(gait_frames(count), "gait")
    assert (ARM_SWING in features) is expected


def test_invalid_wrist_outliers_never_enter_range_and_other_outputs_are_unchanged():
    clean = gait_frames()
    dirty = deepcopy(clean)
    # Exactly 70% trustworthy samples remain. Invalid predictions may be huge,
    # but cannot affect the range computed from those trustworthy samples.
    for frame in dirty[70:]:
        frame["landmarks"][15] = [10000.0, 0.5, 0.0, 0.1]
        frame["landmarks"][16] = [-10000.0, 0.5, 0.0, 0.1]
    features, definitions, issues, curves = extract_features(dirty, "gait")
    trusted, _, _, _ = extract_features(clean[:70], "gait")
    original, original_definitions, original_issues, original_curves = extract_features(clean, "gait")
    assert features[ARM_SWING] == pytest.approx(trusted[ARM_SWING])
    assert definitions == original_definitions
    assert issues == original_issues
    assert curves == original_curves
    assert {key: value for key, value in features.items() if key != ARM_SWING} == {
        key: value for key, value in original.items() if key != ARM_SWING
    }


def test_visible_stationary_arms_keep_real_zero_instead_of_missing():
    frames = gait_frames()
    for frame in frames:
        frame["landmarks"][15][0] = 0.42
        frame["landmarks"][16][0] = 0.58
    features, definitions, _, _ = extract_features(frames, "gait")
    assert features[ARM_SWING] == 0.0
    assert ARM_SWING in definitions


def test_each_side_uses_its_own_valid_samples():
    frames = gait_frames()
    for frame in frames[:30]:
        frame["landmarks"][15][3] = 0.49
    for frame in frames[70:]:
        frame["landmarks"][16][3] = 0.49
    features, _, _, _ = extract_features(frames, "gait")
    points = np.asarray([frame["landmarks"] for frame in frames], dtype=np.float32)
    left = (points[30:, 15, 0] - points[30:, 11, 0]) / 0.25
    right = (points[:70, 16, 0] - points[:70, 12, 0]) / 0.25
    expected = ((np.percentile(left, 95) - np.percentile(left, 5))
                + (np.percentile(right, 95) - np.percentile(right, 5))) / 2
    assert features[ARM_SWING] == pytest.approx(expected, rel=1e-6)
