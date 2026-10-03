"""Synthetic fixtures test mechanics only; they are not detector validation."""

from __future__ import annotations

import json
import os

import cv2
import numpy as np
import pytest

from app.components.pose_3d_viewer import build_motion_figure
from ml.vision.features import extract_features, joint_angle
from ml.vision.pipeline import CVError, LandmarkDetector, LandmarkRecorder, analyze_video, frame_visible, make_video_processor, validate_video


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (320, 240))
    assert writer.isOpened()
    generator = np.random.default_rng(32)
    for _ in range(120):
        writer.write(generator.integers(80, 180, (240, 320, 3), dtype=np.uint8))
    writer.release()
    return path


def synthetic_hand_frames(seconds=6, fps=20):
    # Deliberately invented TEST geometry, never used by application inference.
    frames = []
    for index in range(int(seconds * fps)):
        t = index / fps
        points = np.ones((21, 4), dtype=np.float32)
        points[:, :3] = [0.5, 0.5, 0]
        points[0, :2] = [0.5, 0.75]
        points[9, :2] = [0.5, 0.5]
        points[4, :2] = [0.45, 0.4]
        points[8, :2] = [0.5 + 0.08 * (1 + np.sin(2 * np.pi * 2 * t)), 0.4]
        frames.append({"timestamp_s": t, "landmarks": points.tolist(), "world_landmarks": points.tolist(), "hand_side": "Left"})
    return frames


def test_video_metadata_and_duration_gate(video, tmp_path):
    metadata = validate_video(video, "finger_left")
    assert metadata["fps"] == 20
    assert metadata["duration_s"] == 6
    assert metadata["width"] == 320
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(CVError, match="empty"):
        validate_video(empty, "gait")
    with pytest.raises(CVError, match="supported movement"):
        validate_video(video, "any_unknown_task")


def test_header_rejects_renamed_non_video(tmp_path):
    path = tmp_path / "forged.mp4"
    path.write_bytes(b"not a video" * 100)
    with pytest.raises(CVError, match="content does not match"):
        validate_video(path, "gait")


def test_missing_model_is_actionable(tmp_path):
    with pytest.raises(CVError, match="download_landmark_models"):
        LandmarkDetector("finger_left", tmp_path)


def test_missing_hand_repeats_and_has_no_features(video, monkeypatch):
    class NoHand:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def detect(self, *args):
            return None

    monkeypatch.setattr("ml.vision.pipeline.LandmarkDetector", NoHand)
    result = analyze_video(video, "finger_left")
    assert result["quality"]["decision"] == "REPEAT"
    assert result["quality"]["valid_fraction"] == 0
    assert result["features"] == {}
    assert result["landmark_frames"] == []
    assert "complete selected hand" in " ".join(result["quality"]["issues"])
    json.dumps(result, allow_nan=False)


def test_quality_gate_blocks_dark_video_features(video, monkeypatch):
    frames = iter(synthetic_hand_frames())

    class TestDetector:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def detect(self, *args):
            return next(frames, None)

    monkeypatch.setattr("ml.vision.pipeline.LandmarkDetector", TestDetector)
    monkeypatch.setattr("ml.vision.pipeline.frame_quality", lambda _: (10.0, 100.0))
    result = analyze_video(video, "finger_left")
    assert result["status"] == "repeat"
    assert result["features"] == {}
    assert result["landmark_frames"]
    assert any("Lighting" in issue for issue in result["quality"]["issues"])


def test_feature_frequency_proxy_and_finite_serialization():
    features, metadata, issues, curves = extract_features(synthetic_hand_frames(), "finger_left")
    assert 1.5 < features["tap_frequency_hz_proxy"] < 2.5
    assert features["tap_range_ratio"] > 0.4
    assert metadata["tap_frequency_hz_proxy"]["unit"] == "Hz (proxy)"
    assert not issues
    assert len(curves["timestamp_s"]) == 120
    json.dumps(features, allow_nan=False)


def test_static_task_rejected_and_out_of_frame_not_visible():
    frames = synthetic_hand_frames()
    for frame in frames:
        frame["landmarks"][8][:2] = [0.6, 0.4]
    _, _, issues, _ = extract_features(frames, "finger_left")
    assert any("activity" in issue or "cycles" in issue for issue in issues)
    assert frame_visible(frames[0], "finger_left")
    frames[0]["landmarks"][8][0] = -0.2
    assert not frame_visible(frames[0], "finger_left")


def test_joint_angle_geometry():
    points = np.asarray([[[1, 0, 0], [0, 0, 0], [0, 1, 0]]], dtype=float)
    assert joint_angle(points, 0, 1, 2)[0] == pytest.approx(90)


def test_replay_has_connections_slider_and_matching_baseline():
    result = {"task": "finger_left", "landmark_frames": synthetic_hand_frames(), "media_metadata": {"width": 640, "height": 480}}
    figure = build_motion_figure(result, result)
    assert len(figure.frames) == 90
    assert len(figure.layout.sliders[0].steps) == 90
    assert figure.data[1].name.startswith("Baseline")
    assert figure.data[0].type == "mesh3d"
    assert "estimated" in figure.layout.scene.zaxis.title.text.lower()
    assert figure.layout.scene.xaxis.autorange is False
    assert figure.layout.scene.xaxis.range[0] < min(value for value in figure.data[0].x if value is not None)
    assert list(figure.frames[-1].traces) == [0, 1, 2, 3]
    assert len(build_motion_figure({}).layout.annotations) == 1


def test_live_recording_tracks_camera_gaps_and_releases_writer(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("ml.vision.pipeline.time.monotonic", lambda: clock[0])
    recorder = LandmarkRecorder("finger_left", tmp_path / "live.avi")
    class Detector:
        def detect(self, *args):
            return None

        def close(self):
            pass

    recorder._detector = Detector()
    recorder.start_recording()
    image = np.full((240, 320, 3), 100, dtype=np.uint8)
    recorder.process(image)
    clock[0] = 0.7
    recorder.process(image)
    path = recorder.stop_recording()
    status = recorder.snapshot()
    assert path.is_file()
    assert recorder._writer is None
    assert recorder._last_frame is None
    assert status["recording_gap_count"] == 1
    assert status["timing_valid"] is False
    assert status["unique_camera_frames"] == 2
    assert status["effective_capture_fps"] < 15
    assert path.stat().st_mode & 0o777 == 0o600
    recorder.start_recording()
    assert recorder.snapshot()["timing_valid"] is True
    assert recorder.snapshot()["recording_gap_count"] == 0
    recorder.close()


def test_live_timing_guard_blocks_even_visible_motion(video, monkeypatch):
    frames = iter(synthetic_hand_frames())

    class TestDetector:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def detect(self, *args):
            return next(frames, None)

    monkeypatch.setattr("ml.vision.pipeline.LandmarkDetector", TestDetector)
    result = analyze_video(video, "finger_left", capture_metadata={"timing_valid": False, "recording_gap_count": 2, "effective_capture_fps": 10.0})
    assert result["quality"]["accepted"] is False
    assert result["features"] == {}
    assert result["capture_metadata"]["effective_capture_fps"] == 10.0
    assert any("frame gaps" in issue for issue in result["quality"]["issues"])


def test_live_stream_end_closes_model_and_writer(tmp_path):
    processor = make_video_processor("gait", tmp_path / "live.avi")()

    class Detector:
        closed = False

        def close(self):
            self.closed = True

    detector = Detector()
    processor._detector = detector
    processor.start_recording()
    processor.on_ended()
    assert detector.closed
    assert processor._detector is None
    assert processor.snapshot()["recording"] is False
    assert processor.snapshot()["camera_active"] is False


def test_baseline_overlay_rejects_other_task_and_body_graph_stays_separate():
    hand = {"task": "finger_left", "landmark_frames": synthetic_hand_frames(), "media_metadata": {"width": 640, "height": 480}}
    wrong_task = dict(hand, task="finger_right")
    figure = build_motion_figure(hand, wrong_task)
    assert not any("Baseline" in trace.name for trace in figure.data)
    assert list(figure.frames[-1].traces) == [0, 1, 2]
    frames = []
    for t in [0.0, 1.0]:
        points = np.ones((33, 4))
        points[:, :3] = np.column_stack((np.linspace(0.2, 0.8, 33), np.linspace(0.1, 0.9, 33), np.zeros(33)))
        frames.append({"timestamp_s": t, "landmarks": points.tolist(), "world_landmarks": points.tolist()})
    body = build_motion_figure({"task": "gait", "landmark_frames": frames})
    assert "body" in body.layout.title.text
    assert any("ankle" in trace.name for trace in body.data)
    assert not any("fingertip" in trace.name for trace in body.data)


@pytest.mark.skipif(os.environ.get("PARKINSENSE_RUN_MODEL_TESTS") != "1", reason="Explicit opt-in requires downloaded official landmark models")
def test_official_models_blank_frame_and_video_smoke(video):
    """Real model invocation; blank/noise TEST input must not create a person."""
    image = np.full((240, 320, 3), 128, dtype=np.uint8)
    for task in ("gait", "finger_left"):
        with LandmarkDetector(task) as detector:
            assert detector.detect(image, 0.0) is None
            assert detector.detect(image, 0.1) is None
    result = analyze_video(video, "finger_left")
    assert result["quality"]["accepted"] is False
    assert result["landmark_frames"] == []
    assert result["features"] == {}
