"""Live state mechanics use invented test points, never patient inference data."""

from copy import deepcopy
import sys
from types import ModuleType

import numpy as np
import pytest

from ml.vision.pipeline import LIVE_HISTORY_MAX_FRAMES, MAX_SECONDS, LandmarkRecorder, make_video_processor


def observation(timestamp=0.0, side="Left"):
    points = [[0.5, 0.5, 0.02, 1.0] for _ in range(21)]
    return {"timestamp_s": timestamp, "hand_side": side, "landmarks": points, "world_landmarks": deepcopy(points)}


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr("ml.vision.pipeline.time.monotonic", lambda: value[0])
    return value


class TestDetector:
    __test__ = False

    def __init__(self, response=None):
        self.response = observation() if response is None else response
        self.closed = False

    def detect(self, frame, timestamp_s):
        if callable(self.response):
            return self.response(timestamp_s)
        return self.response

    def close(self):
        self.closed = True


def recorder(tmp_path, task="finger_left", **kwargs):
    result = LandmarkRecorder(task, tmp_path / "live.avi", **kwargs)
    result._detector = TestDetector()
    return result


def image():
    return np.full((240, 320, 3), 100, dtype=np.uint8)


def test_coordinate_payload_is_opt_in_and_detached(tmp_path, clock):
    stream = recorder(tmp_path)
    stream.process(image())
    status = stream.snapshot()
    assert status["tracking_fresh"] is True
    assert "observation" not in status and "observation_history" not in status
    state = stream.snapshot(include_landmarks=True)
    assert state["frame_size"] == {"width": 320, "height": 240}
    assert len(state["observation_history"]) == 1
    state["observation"]["landmarks"][0][0] = 999
    state["observation_history"][0]["world_landmarks"][0][2] = 999
    state["frame_size"]["width"] = 999
    stream._detector.response["landmarks"][1][0] = 999
    latest = stream.snapshot(include_landmarks=True)
    assert latest["observation"]["landmarks"][0][0] == 0.5
    assert latest["observation"]["landmarks"][1][0] == 0.5
    assert latest["observation_history"][0]["world_landmarks"][0][2] == 0.02
    assert latest["frame_size"]["width"] == 320
    stream.close()


def test_inactive_camera_expires_landmarks_at_snapshot_without_new_frames(tmp_path, clock):
    stream = recorder(tmp_path)
    stream.process(image())
    clock[0] = 0.34
    assert stream.snapshot(include_landmarks=True)["observation"] is not None
    clock[0] = 0.36
    state = stream.snapshot(include_landmarks=True)
    assert state["camera_active"] is False
    assert state["tracking_fresh"] is False
    assert state["detected"] is False and state["visible"] is False
    assert state["observation"] is None and state["observation_history"] == []
    assert state["observation_age_s"] == pytest.approx(0.36)
    clock[0] = 0.4
    stream.process(image())
    assert len(stream.snapshot(include_landmarks=True)["observation_history"]) == 1
    stream.close()


def test_history_is_bounded_by_count_and_elapsed_time(tmp_path, clock):
    stream = recorder(tmp_path)
    stream._detector.response = lambda timestamp: observation(timestamp)
    for index in range(70):
        clock[0] = index * 0.01
        # Exercise the hard cap independently of current detector throttling.
        stream._last_detection = None
        stream.process(image())
    state = stream.snapshot(include_landmarks=True)
    assert len(state["observation_history"]) == LIVE_HISTORY_MAX_FRAMES
    assert state["observation_history"][0]["timestamp_s"] == pytest.approx(0.25)
    for index in range(7, 46):
        clock[0] = index * 0.1
        stream._last_detection = None
        stream.process(image())
    history = stream.snapshot(include_landmarks=True)["observation_history"]
    assert len(history) <= LIVE_HISTORY_MAX_FRAMES
    assert history[0]["timestamp_s"] >= clock[0] - 3.0
    assert history[-1]["timestamp_s"] == pytest.approx(clock[0])
    stream.close()


@pytest.mark.parametrize("lost", [None, "out_of_view", "wrong_side"])
def test_tracking_loss_never_exposes_or_connects_previous_coordinates(tmp_path, clock, lost):
    stream = recorder(tmp_path)
    stream.process(image())
    missing = None
    if lost == "out_of_view":
        missing = observation()
        missing["landmarks"][8][0] = -0.2
    elif lost == "wrong_side":
        missing = observation(side="Right")
    stream._detector.response = lambda timestamp: missing
    clock[0] = 0.11
    stream.process(image())
    state = stream.snapshot(include_landmarks=True)
    assert state["camera_active"] is True
    assert state["detected"] is False
    assert state["observation"] is None and state["observation_history"] == []
    stream._detector.response = lambda timestamp: observation(timestamp)
    clock[0] = 0.22
    stream.process(image())
    assert len(stream.snapshot(include_landmarks=True)["observation_history"]) == 1
    stream.close()


def test_hand_side_switch_and_camera_gap_restart_trails(tmp_path, clock):
    stream = recorder(tmp_path, task="hand_open_close")
    stream.process(image())
    clock[0] = 0.11
    stream._detector.response = observation(0.11, side="Right")
    stream.process(image())
    state = stream.snapshot(include_landmarks=True)
    assert state["detected"] is True
    assert state["observation"]["hand_side"] == "Right"
    assert len(state["observation_history"]) == 1
    clock[0] = 0.22
    stream.process(image())
    assert len(stream.snapshot(include_landmarks=True)["observation_history"]) == 2
    clock[0] = 0.7
    stream.process(image())
    assert len(stream.snapshot(include_landmarks=True)["observation_history"]) == 1
    stream.close()


def test_live_detector_failure_and_close_clear_coordinates(tmp_path, clock):
    stream = recorder(tmp_path)
    stream.process(image())

    def failed(timestamp):
        raise RuntimeError("not exposed to patient")

    stream._detector.response = failed
    clock[0] = 0.11
    stream.process(image())
    state = stream.snapshot(include_landmarks=True)
    assert state["observation"] is None and state["observation_history"] == []
    assert "not exposed to patient" not in state["error"]
    stream._detector.response = lambda timestamp: observation(timestamp)
    clock[0] = 0.22
    stream.process(image())
    detector = stream._detector
    stream.close()
    state = stream.snapshot(include_landmarks=True)
    assert detector.closed is True
    assert state["camera_active"] is False and state["detected"] is False
    assert state["observation"] is None and state["observation_history"] == []


def test_overlay_switch_preserves_raw_recording_and_detached_state(tmp_path, clock, monkeypatch):
    writes, calls = [], []

    class Writer:
        def __init__(self, *args):
            self.closed = False

        def isOpened(self):
            return True

        def write(self, frame):
            writes.append(frame.copy())

        def release(self):
            self.closed = True

    def renderer(frame, current, task, *, history, show_trails):
        calls.append((task, show_trails, len(history)))
        frame[:, :, :] = [10, 220, 255]
        current["landmarks"][0][0] = 999
        history[0]["world_landmarks"][0][0] = 999
        return frame

    overlay = ModuleType("ml.vision.live_overlay")
    overlay.draw_live_overlay = renderer
    monkeypatch.setitem(sys.modules, "ml.vision.live_overlay", overlay)
    monkeypatch.setattr("ml.vision.pipeline.cv2.VideoWriter", Writer)
    stream = recorder(tmp_path)
    raw = image()
    stream.start_recording()
    stream.process(raw)
    assert calls == []
    stream.set_display_options(overlay=True, show_trails=False)
    clock[0] = 0.2
    painted = stream.process(raw)
    assert calls == [("finger_left", False, 2)]
    assert not np.array_equal(painted, raw)
    assert all(np.array_equal(frame, raw) for frame in writes)
    assert np.array_equal(stream._last_frame, raw)
    assert stream.snapshot(include_landmarks=True)["observation"]["landmarks"][0][0] == 0.5
    stream.set_display_options(overlay=False, show_trails=True)
    clock[0] = 0.25
    stream.process(raw)
    assert len(calls) == 1
    assert stream.snapshot()["display_options"] == {"overlay": False, "show_trails": True}
    stream.close()


@pytest.mark.parametrize("option", [0, 1, "false", None, np.bool_(True)])
def test_display_options_require_explicit_booleans(tmp_path, clock, option):
    with pytest.raises(ValueError, match="True or False"):
        LandmarkRecorder("finger_left", tmp_path / "live.avi", overlay=option)
    with pytest.raises(ValueError, match="True or False"):
        LandmarkRecorder("finger_left", tmp_path / "live.avi", show_trails=option)
    stream = recorder(tmp_path)
    with pytest.raises(ValueError, match="True or False"):
        stream.set_display_options(overlay=option)
    with pytest.raises(ValueError, match="True or False"):
        stream.set_display_options(overlay=True, show_trails=option)
    assert stream.snapshot()["display_options"] == {"overlay": False, "show_trails": True}
    stream.close()


def test_processor_factory_forwards_display_options_and_stream_end(tmp_path, clock):
    processor = make_video_processor("finger_left", tmp_path / "live.avi", overlay=True, show_trails=False)()
    assert processor.snapshot()["display_options"] == {"overlay": True, "show_trails": False}
    processor.on_ended()
    assert processor.snapshot(include_landmarks=True)["observation_history"] == []


def test_automatic_duration_stop_remains_ready_until_reviewed(tmp_path, clock, monkeypatch):
    class Writer:
        def __init__(self, path, *args):
            from pathlib import Path

            Path(path).write_bytes(b"isolated recorder readiness test")
            self.closed = False

        def isOpened(self):
            return True

        def write(self, frame):
            pass

        def release(self):
            self.closed = True

    monkeypatch.setattr("ml.vision.pipeline.cv2.VideoWriter", Writer)
    stream = recorder(tmp_path)
    assert stream.snapshot()["recording_ready"] is False
    stream.start_recording()
    stream.process(image())
    clock[0] = MAX_SECONDS
    stream.process(image())
    status = stream.snapshot()
    assert status["recording"] is False
    assert status["recording_ready"] is True
    assert status["frames_written"] == MAX_SECONDS * 20
    assert status["elapsed_s"] == MAX_SECONDS
    assert stream._writer is None
    assert not any("path" in key for key in status)
    # Stream-end and repeated stop preserve an unconsumed finished recording.
    stream.stop_recording()
    stream.close()
    assert stream.snapshot()["recording_ready"] is True
    stream.mark_recording_reviewed()
    stream.stop_recording()
    stream.close()
    assert stream.snapshot()["recording_ready"] is False
    # Starting over cannot revive the previous file before a new frame arrives.
    stream.start_recording()
    assert stream.snapshot()["recording_ready"] is False
    assert stream.snapshot()["frames_written"] == 0
    stream._detector = TestDetector()
    clock[0] += 0.1
    stream.process(image())
    assert stream.snapshot()["recording_ready"] is False
    stream.stop_recording()
    assert stream.snapshot()["recording_ready"] is True
    stream.start_recording()
    assert stream.snapshot()["recording_ready"] is False
    stream.stop_recording()
    assert stream.snapshot()["recording_ready"] is False
    stream.close()


def test_empty_recording_never_becomes_ready(tmp_path, clock):
    stream = recorder(tmp_path)
    stream.start_recording()
    assert stream.stop_recording() is None
    assert stream.snapshot()["recording_ready"] is False
    stream.mark_recording_reviewed()
    stream.close()
    assert stream.snapshot()["recording_ready"] is False
