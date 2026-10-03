"""Live display geometry tests; fixtures do not validate clinical accuracy."""

from copy import deepcopy
import json

import numpy as np
import pytest

from app.components.live_3d_viewer import build_live_3d_figure
from ml.vision.live_overlay import (
    draw_live_overlay,
    focus_definition,
    recent_observations,
)
from ml.vision.tasks import TASKS


def observation(task="finger_left", timestamp=0.0):
    hand = TASKS[task]["kind"] == "hand"
    count = 21 if hand else 33
    image = np.ones((count, 4))
    world = np.ones((count, 4))
    image[:, :3] = [0.5, 0.5, 0]
    world[:, :3] = [0, 0, 0]
    if hand:
        image[0, :2] = [0.5, 0.8]
        world[0, :3] = [0, 0.065, 0]
        for finger, first in enumerate((1, 5, 9, 13, 17)):
            for joint in range(4):
                image[first + joint, :2] = [0.25 + finger * 0.12, 0.65 - joint * 0.12]
                world[first + joint, :3] = [-0.04 + finger * 0.02, 0.025 - joint * 0.025, joint * 0.002]
    else:
        for joint, values in {
            11: (-0.2, -0.48, 0), 12: (0.2, -0.48, 0), 13: (-0.28, -0.25, 0), 14: (0.28, -0.25, 0),
            15: (-0.3, 0, -0.1), 16: (0.3, 0, -0.1), 23: (-0.12, 0, 0), 24: (0.12, 0, 0),
            25: (-0.13, 0.4, 0), 26: (0.13, 0.4, 0), 27: (-0.13, 0.78, 0), 28: (0.13, 0.78, 0),
            29: (-0.13, 0.81, 0.03), 30: (0.13, 0.81, 0.03), 31: (-0.13, 0.81, -0.12), 32: (0.13, 0.81, -0.12),
        }.items():
            world[joint, :3] = values
            image[joint, :2] = [0.5 + values[0] * 0.65, 0.2 + (values[1] + 0.48) * 0.45]
    result = {"timestamp_s": timestamp, "landmarks": image.tolist(), "world_landmarks": world.tolist()}
    if hand:
        result.update(hand_side=TASKS[task].get("side", "Left"), handedness_confidence=0.95)
    return result


@pytest.mark.parametrize("task", TASKS)
def test_every_task_has_same_observed_focus_for_camera_and_world_view(task):
    focus = focus_definition(task)
    assert focus["label"] and focus["edges"] and focus["trail_joints"]
    assert all(a in focus["joints"] and b in focus["joints"] for a, b in focus["edges"])
    assert all(joint in focus["joints"] for joint in focus["trail_joints"])
    current = observation(task)
    frame = np.full((480, 640, 3), 20, dtype=np.uint8)
    assert np.any(draw_live_overlay(frame, current, task) != frame)
    figure = build_live_3d_figure(current, task)
    assert figure.layout.meta["available"]
    assert figure.layout.meta["focus"] == focus["label"]


def test_finger_focus_uses_thumb_index_and_other_fingers_are_context():
    focus = focus_definition("finger_left")
    assert focus["joints"] == tuple(range(9))
    assert focus["trail_joints"] == (4, 8)
    assert 20 not in focus["joints"]
    assert 20 in focus_definition("hand_open_close")["joints"]
    assert focus_definition("reach")["trail_joints"] == (15, 16)
    assert focus_definition("gait")["trail_joints"] == (27, 28)


@pytest.mark.parametrize("problem", ["missing_world", "nan_world", "confidence", "wrong_hand", "offscreen", "invisible"])
def test_invalid_or_wrong_body_part_draws_no_lines_and_no_stale_3d(problem):
    current = observation()
    if problem == "missing_world":
        del current["world_landmarks"]
    elif problem == "nan_world":
        for point in current["world_landmarks"]:
            point[0] = float("nan")
    elif problem == "confidence":
        current["handedness_confidence"] = 0.2
    elif problem == "wrong_hand":
        current["hand_side"] = "Right"
    elif problem == "offscreen":
        for point in current["landmarks"]:
            point[0] = 1.1
    elif problem == "invisible":
        for point in current["landmarks"]:
            point[3] = 0.1
    frame = np.full((480, 640, 3), 20, dtype=np.uint8)
    assert np.array_equal(draw_live_overlay(frame, current, "finger_left"), frame)
    figure = build_live_3d_figure(current, "finger_left", history=[observation()])
    assert not figure.data and not figure.layout.meta["available"]
    assert not figure.frames


def test_live_viewer_uses_current_world_xyz_without_initial_replay_frame_or_image_depth():
    earlier = observation(timestamp=0)
    current = observation(timestamp=0.1)
    current["world_landmarks"][8][2] = -0.03
    current["world_landmarks"][8][0] = 0.015
    figure = build_live_3d_figure(current, "finger_left", history=[earlier, current])
    nodes = next(trace for trace in figure.data if trace.name == "Current focused joints")
    node = list(nodes.customdata).index(8)
    assert nodes.x[node] == pytest.approx(0.015)
    assert nodes.y[node] == pytest.approx(-current["world_landmarks"][8][1])
    assert nodes.z[node] == pytest.approx(-0.03)
    assert figure.layout.meta["timestamp_s"] == 0.1
    assert not figure.frames and not figure.layout.sliders and not figure.layout.updatemenus
    changed = deepcopy(current)
    for point in changed["landmarks"]:
        point[2] = 9000
    assert build_live_3d_figure(changed, "finger_left").to_json() == build_live_3d_figure(current, "finger_left").to_json()
    assert figure.layout.scene.aspectmode == "data"
    assert figure.layout.scene.camera.up.y == 1
    assert figure.layout.scene.camera.projection.type == "orthographic"


def test_axes_camera_and_world_metric_scale_are_stable_during_live_movement():
    first = observation("reach", 0)
    second = deepcopy(first)
    second["timestamp_s"] = 0.2
    second["world_landmarks"][15][2] -= 0.2
    earlier, later = (build_live_3d_figure(item, "reach") for item in (first, second))
    assert earlier.layout.scene == later.layout.scene
    assert earlier.layout.uirevision == later.layout.uirevision
    nodes = next(trace for trace in later.data if trace.name == "Current focused joints")
    left, right = list(nodes.customdata).index(11), list(nodes.customdata).index(12)
    assert abs(nodes.x[left] - nodes.x[right]) == pytest.approx(0.4)


def test_pose_native_downward_y_is_displayed_upright_and_top_camera_is_not_collinear():
    for camera in ("Isometric", "Front", "Side", "Top"):
        upper = build_live_3d_figure(observation("reach"), "reach", camera=camera)
        lower = build_live_3d_figure(observation("gait"), "gait", camera=camera)
        arms = next(trace for trace in upper.data if trace.name == "Current focused joints")
        legs = next(trace for trace in lower.data if trace.name == "Current focused joints")
        shoulder = list(arms.customdata).index(11)
        hip, ankle = list(legs.customdata).index(23), list(legs.customdata).index(27)
        assert arms.y[shoulder] > legs.y[hip] > legs.y[ankle]
        assert upper.layout.meta["coordinate_transform"] == "native Y sign reflection only"
        view = upper.layout.scene.camera
        up = np.asarray([view.up.x, view.up.y, view.up.z])
        eye = np.asarray([view.eye.x, view.eye.y, view.eye.z])
        assert np.linalg.norm(np.cross(up, eye)) > 1
        if camera != "Top":
            assert view.up.y == 1
        else:
            assert view.eye.y > 0 and view.up.y == 0 and abs(view.up.z) == 1


def test_copy_only_overlay_and_rendering_do_not_change_saved_landmarks_or_frame():
    current = observation()
    original = deepcopy(current)
    frame = np.full((480, 640, 3), 20, dtype=np.uint8)
    before = frame.copy()
    output = draw_live_overlay(frame, current, "finger_left", history=[current])
    build_live_3d_figure(current, "finger_left", history=[current])
    assert current == original
    assert np.array_equal(frame, before)
    assert not np.shares_memory(output, frame)


def test_overlay_invalid_image_values_never_overflow_and_blends_only_three_trail_bands(monkeypatch):
    history = [observation(timestamp=n / 20) for n in range(45)]
    history[-1]["landmarks"][20][0] = 1e308
    frame = np.full((480, 640, 3), 20, dtype=np.uint8)
    from ml.vision import live_overlay

    blend = live_overlay.cv2.addWeighted
    calls = []

    def count_blends(*args):
        calls.append(True)
        return blend(*args)

    monkeypatch.setattr(live_overlay.cv2, "addWeighted", count_blends)
    with np.errstate(over="raise", invalid="raise"):
        output = draw_live_overlay(frame, history[-1], "finger_left", history=history)
    assert np.any(output != frame)
    assert len(calls) == 5  # Context, three trail bands, focused glow.


def test_history_bounded_and_clears_detection_camera_or_hand_gaps():
    history = [observation(timestamp=n / 20) for n in range(200)]
    assert len(recent_observations(history[-1], "finger_left", history)) == 45
    current = observation(timestamp=20)
    assert recent_observations(current, "finger_left", history) == [current]
    reset = [observation(timestamp=0), None, observation(timestamp=0.1)]
    assert recent_observations(reset[-1], "finger_left", reset) == [reset[-1]]
    opposite = observation("hand_open_close", 0.1)
    opposite["hand_side"] = "Right"
    assert recent_observations(opposite, "hand_open_close", [observation("hand_open_close"), opposite]) == [opposite]
    assert recent_observations(None, "finger_left", history) == []


def test_partial_joint_loss_breaks_trail_and_never_invents_hidden_nodes():
    history = [observation(timestamp=n / 20) for n in range(4)]
    history[1]["landmarks"][8][3] = 0.1
    figure = build_live_3d_figure(history[-1], "finger_left", history=history)
    trails = [trace for trace in figure.data if trace.name == "Recent local trail"]
    assert any(None in trace.x for trace in trails)
    current = deepcopy(history[-1])
    current["world_landmarks"][8][0] = float("nan")
    current["landmarks"][8][3] = 0.1
    figure = build_live_3d_figure(current, "finger_left", history=history)
    nodes = next(trace for trace in figure.data if trace.name == "Current focused joints")
    assert 8 not in nodes.customdata
    json.dumps(figure.to_plotly_json(), allow_nan=False)


def test_long_history_payload_stays_small_with_no_video_or_private_labels():
    history = [observation("hand_open_close", n / 20) for n in range(500)]
    history[-1]["patient_name"] = "Private patient"
    figure = build_live_3d_figure(history[-1], "hand_open_close", history=history)
    assert figure.layout.meta["trail_frames"] == 45
    assert len(figure.data) <= 19
    assert len(figure.to_json()) < 100_000
    assert "Private patient" not in figure.to_json()
