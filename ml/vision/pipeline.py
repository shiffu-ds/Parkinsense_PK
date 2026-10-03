"""Bounded, streaming video analysis shared by uploaded and live recordings.

The only model outputs are MediaPipe landmarks. No fabricated coordinates,
clinical risk score, laboratory distance, or diagnosis is returned.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from ml.vision.features import extract_features
from ml.vision.tasks import HAND_CONNECTIONS, POSE_CONNECTIONS, TASKS

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 45
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
LIVE_OBSERVATION_MAX_AGE_S = 0.35
LIVE_HISTORY_MAX_AGE_S = 3.0
LIVE_HISTORY_MAX_FRAMES = 45
_ANALYSIS_LOCK = threading.Lock()
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "landmarks"


class CVError(ValueError):
    """An actionable input or model availability error."""


def _task(task: str) -> dict:
    if task not in TASKS:
        raise CVError("Select a supported movement task before uploading a video.")
    return TASKS[task]


def validate_video(path: str | Path, task: str) -> dict:
    """Validate container signature and metadata before model inference."""
    spec = _task(task)
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise CVError("Use an MP4, MOV, AVI or MKV recording.")
    if not path.is_file() or path.stat().st_size < 128:
        raise CVError("The video is empty or missing. Upload a complete recording.")
    if path.stat().st_size > MAX_VIDEO_BYTES:
        raise CVError("Video exceeds 100 MB. Trim the recording and upload again.")
    with path.open("rb") as handle:
        header = handle.read(64)
    extension = path.suffix.lower()
    signatures = {
        ".avi": header[:4] == b"RIFF" and header[8:12] == b"AVI ",
        ".mkv": header[:4] == b"\x1aE\xdf\xa3",
        ".mp4": b"ftyp" in header,
        ".mov": any(marker in header for marker in (b"ftyp", b"moov", b"mdat", b"wide")),
    }
    if not signatures[extension]:
        raise CVError("The file content does not match the selected video format or is corrupt.")
    capture = cv2.VideoCapture(str(path))
    try:
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        if not capture.isOpened():
            raise CVError("The video cannot be decoded. Export it as a standard MP4 or AVI.")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not np.isfinite(fps) or not 8 <= fps <= 120:
            raise CVError("Use a recording with a valid frame rate from 8 to 120 fps.")
        if task.startswith("finger") and fps < 15:
            raise CVError("Finger tapping needs at least 15 fps to reduce missed movement cycles.")
        if not np.isfinite(count) or count <= 0:
            raise CVError("Recording duration could not be verified. Export a complete standard video.")
        duration = count / fps
        if duration < spec["min_seconds"]:
            raise CVError(f"Record at least {spec['min_seconds']} seconds for this task.")
        if duration > MAX_SECONDS + 0.1:
            raise CVError(f"Trim the video to {MAX_SECONDS} seconds or less before analysis.")
        if min(width, height) < 240 or width * height > 3840 * 2160:
            raise CVError("Use a video at least 240 pixels on each side and no larger than 4K.")
        return {"fps": fps, "frame_count": int(count), "duration_s": float(duration), "width": width, "height": height, "bytes": path.stat().st_size}
    finally:
        capture.release()


class LandmarkDetector:
    """CPU MediaPipe Tasks detector; one instance for one video stream."""

    def __init__(self, task: str, model_dir: str | Path | None = None):
        self.task = task
        self.spec = _task(task)
        self.mp = None
        self.model = None
        filename = "hand_landmarker.task" if self.spec["kind"] == "hand" else "pose_landmarker_lite.task"
        directory = Path(model_dir or os.environ.get("LANDMARK_MODEL_DIR") or DEFAULT_MODEL_DIR)
        model_path = directory / filename
        if not model_path.is_file():
            raise CVError(f"Landmark model is missing ({filename}). Run: uv run python scripts/download_landmark_models.py")
        try:
            import mediapipe as mp
            self.mp = mp
            vision = mp.tasks.vision
            options = {
                "base_options": mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                "running_mode": vision.RunningMode.VIDEO,
                "min_tracking_confidence": 0.5,
            }
            if self.spec["kind"] == "hand":
                self.model = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(num_hands=2, min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5, **options))
            else:
                self.model = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(num_poses=1, min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5, **options))
        except Exception as exc:
            self.close()
            raise CVError("MediaPipe landmark model could not be loaded. Check the installed dependencies and downloaded model files.") from exc
        self._last_ms = -1
        self._tracked_hand_side = self.spec.get("side")
        self._last_wrist = None

    def detect(self, bgr: np.ndarray, timestamp_s: float) -> dict | None:
        frame = bgr
        if max(frame.shape[:2]) > 960:
            factor = 960 / max(frame.shape[:2])
            frame = cv2.resize(frame, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        timestamp_ms = max(self._last_ms + 1, round(timestamp_s * 1000))
        self._last_ms = timestamp_ms
        result = self.model.detect_for_video(image, timestamp_ms)
        if self.spec["kind"] == "hand":
            candidates = []
            for index, landmarks in enumerate(result.hand_landmarks):
                classification = result.handedness[index][0]
                side = classification.category_name
                confidence = float(classification.score)
                if confidence < 0.7 or (self._tracked_hand_side and side != self._tracked_hand_side):
                    continue
                candidates.append((index, side, confidence, landmarks))
            if not candidates:
                return None
            # Lock side on the first frame; do not switch between different hands.
            if self._last_wrist is not None:
                candidate = min(candidates, key=lambda c: (c[3][0].x - self._last_wrist[0]) ** 2 + (c[3][0].y - self._last_wrist[1]) ** 2)
            else:
                candidate = max(candidates, key=lambda c: c[2])
            index, side, confidence, landmarks = candidate
            self._tracked_hand_side = side
            self._last_wrist = (landmarks[0].x, landmarks[0].y)
            world = result.hand_world_landmarks[index]
            frame_data = {"hand_side": side, "handedness_confidence": confidence}
        else:
            if not result.pose_landmarks:
                return None
            landmarks = result.pose_landmarks[0]
            world = result.pose_world_landmarks[0]
            frame_data = {}
        frame_data.update({"timestamp_s": float(timestamp_s), "landmarks": _serialize_landmarks(landmarks), "world_landmarks": _serialize_landmarks(world)})
        return frame_data

    def close(self) -> None:
        if self.model is not None:
            self.model.close()
            self.model = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _serialize_landmarks(points) -> list[list[float]]:
    return [[float(p.x), float(p.y), float(p.z), float(p.visibility if getattr(p, "visibility", None) is not None else 1.0)] for p in points]


def frame_visible(frame_data: dict | None, task: str) -> bool:
    if not frame_data:
        return False
    selected = np.asarray(frame_data["landmarks"], dtype=np.float32)[TASKS[task]["joints"]]
    if not np.all(np.isfinite(selected)):
        return False
    within = (selected[:, 0] >= 0) & (selected[:, 0] <= 1) & (selected[:, 1] >= 0) & (selected[:, 1] <= 1)
    return bool(np.all(within) and np.mean(selected[:, 3] >= 0.5) >= 0.85)


def frame_quality(frame: np.ndarray) -> tuple[float, float]:
    small = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray)), float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _quality_summary(metadata: dict, task: str, frames: list[dict], sampled: int, brightness: list[float], blur: list[float], decoded: int, fps: float, activity_issues: list[str]) -> dict:
    issues = []
    valid_fraction = len(frames) / max(sampled, 1)
    if valid_fraction < 0.7:
        if TASKS[task]["kind"] == "hand":
            issues.append("Keep the complete selected hand visible; use an unmirrored video and check the requested left/right side.")
        else:
            issues.append("Keep all required joints visible. Move the camera far enough away and avoid occlusion.")
    if len(frames) < 20:
        issues.append("Too few usable landmark frames were detected.")
    mean_brightness = float(np.mean(brightness)) if brightness else 0.0
    low_light_fraction = float(np.mean(np.asarray(brightness) < 35)) if brightness else 1.0
    if low_light_fraction > 0.35 or mean_brightness > 240:
        issues.append("Lighting is unsuitable. Use even light and avoid strong backlighting.")
    blur_fraction = float(np.mean(np.asarray(blur) < 8)) if blur else 1.0
    if blur_fraction > 0.6:
        issues.append("The recording is very blurred or featureless. Stabilize the camera and refocus.")
    actual_duration = decoded / fps
    if actual_duration + 0.15 < metadata["duration_s"] * 0.9:
        issues.append("The decoder could not read the complete recording. Re-export or repeat the video.")
    if frames:
        duration = frames[-1]["timestamp_s"] - frames[0]["timestamp_s"]
        if duration < TASKS[task]["min_seconds"] * 0.7:
            issues.append("Required landmarks were visible for too little of the recording.")
        if TASKS[task]["kind"] == "pose":
            points = np.asarray([f["landmarks"] for f in frames])
            upright = np.mean((points[:, 11, 1] + points[:, 12, 1]) < (points[:, 23, 1] + points[:, 24, 1]))
            if upright < 0.7:
                issues.append("Video orientation appears incorrect. Use an upright recording.")
        times = np.asarray([f["timestamp_s"] for f in frames])
        if len(times) > 1 and np.max(np.diff(times)) > 1.0:
            issues.append("Landmarks were lost for more than a second. Repeat with less occlusion.")
    issues.extend(activity_issues)
    return {"decision": "REPEAT" if issues else "ACCEPT", "accepted": not bool(issues), "issues": list(dict.fromkeys(issues)), "valid_fraction": float(valid_fraction), "sampled_frames": int(sampled), "valid_frames": len(frames), "decoded_frames": int(decoded), "mean_brightness": mean_brightness, "low_light_fraction": low_light_fraction, "blur_fraction": blur_fraction, "mean_blur_variance": float(np.mean(blur)) if blur else 0.0, "rules_version": "landmark_quality_v1", "task_confirmation": "Movement consistency checks only; task identity and completion require human review."}


def analyze_video(path: str | Path, task: str, model_dir: str | Path | None = None, capture_metadata: dict | None = None) -> dict:
    """Run one bounded video at a time; both input modes call this function.

    Exceptions are missing/corrupt media or unavailable model. Poor recordings
    return REPEAT and no features so they cannot silently become a baseline.
    """
    metadata = validate_video(path, task)
    if not _ANALYSIS_LOCK.acquire(blocking=False):
        raise CVError("Another movement recording is being analyzed. Try again when it finishes.")
    capture = None
    frames: list[dict] = []
    brightness: list[float] = []
    blur: list[float] = []
    sampled = decoded = 0
    try:
        capture = cv2.VideoCapture(str(path))
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps = metadata["fps"]
        target_fps = 20 if TASKS[task]["kind"] == "hand" else 10
        interval = max(1, round(fps / target_fps))
        with LandmarkDetector(task, model_dir) as detector:
            # Bounded by metadata and a hard duration cap, even on malformed containers.
            for index in range(min(metadata["frame_count"] + 2, int(MAX_SECONDS * fps) + 1)):
                ok, frame = capture.read()
                if not ok:
                    break
                decoded += 1
                if index % interval:
                    continue
                sampled += 1
                light, sharpness = frame_quality(frame)
                brightness.append(light)
                blur.append(sharpness)
                observation = detector.detect(frame, index / fps)
                if frame_visible(observation, task):
                    frames.append(observation)
        features, feature_metadata, activity_issues, curves = extract_features(frames, task, metadata["width"] / metadata["height"])
        if capture_metadata and capture_metadata.get("timing_valid") is False:
            activity_issues.append("The live recording had frame gaps or too few unique camera frames. Repeat with a stable connection and sufficient frame rate.")
        quality = _quality_summary(metadata, task, frames, sampled, brightness, blur, decoded, fps, activity_issues)
        accepted = quality["decision"] == "ACCEPT"
        return {
            "status": "completed" if accepted else "repeat", "task": task, "task_label": TASKS[task]["label"], "quality": quality,
            "features": features if accepted else {}, "feature_metadata": feature_metadata if accepted else {}, "curves": curves,
            "landmark_frames": frames, "media_metadata": metadata,
            "capture_metadata": {key: value for key, value in (capture_metadata or {}).items() if key in {"timing_valid", "recording_gap_count", "longest_recording_gap_s", "elapsed_s", "frames_written", "unique_camera_frames", "effective_capture_fps"}},
            "coordinate_system": {"landmarks": "Image-normalized x/right, y/down and relative z/toward camera for smaller values. Hip/wrist-relative depth has no global camera-position origin.", "world_landmarks": "MediaPipe estimated meters around hips/hand center; model estimates only, not calibrated clinical distances.", "viewer": "World XYZ only: x/right, inverted y/up, z/away. Native estimated-meter scale and model-local origin. No image-plane depth fallback or global walking route.", "viewer_source": "world_landmarks", "viewer_units": "estimated_meters", "global_translation_available": False},
            "analysis_version": "mediapipe_tasks_proxies_v1", "model_provenance": "Google MediaPipe Pose Landmarker Lite / Hand Landmarker; unvalidated task-specific feature extraction",
            "caveats": ["Single RGB camera landmarks are approximate. These measures are monitoring proxies, not a diagnosis or a validated clinical score.", "Camera distance, view, clothing and lighting affect comparisons. Match setup and task duration to the baseline.", "Left/right classification expects unmirrored input; confirm the anatomical side before saving."] + (["No object detector is configured: grasp contact, target interaction and successful object transfer are not verified."] if task in {"grasp", "object_transfer", "reach"} else []),
        }
    except CVError:
        raise
    except Exception as exc:
        raise CVError("Movement analysis failed. Check the recording and model installation, then try again.") from exc
    finally:
        if capture is not None:
            capture.release()
        _ANALYSIS_LOCK.release()


def draw_overlay(frame: np.ndarray, observation: dict | None, task: str) -> np.ndarray:
    output = frame.copy()
    if observation:
        points = observation["landmarks"]
        height, width = output.shape[:2]
        connections = HAND_CONNECTIONS if TASKS[task]["kind"] == "hand" else POSE_CONNECTIONS
        for a, b in connections:
            if points[a][3] < 0.5 or points[b][3] < 0.5:
                continue
            start = (int(points[a][0] * width), int(points[a][1] * height))
            end = (int(points[b][0] * width), int(points[b][1] * height))
            cv2.line(output, start, end, (60, 220, 180), 2)
        for point in points:
            if point[3] >= 0.5:
                cv2.circle(output, (int(point[0] * width), int(point[1] * height)), 3, (255, 190, 100), -1)
    return output


def extract_overlay_preview(path: str | Path, result: dict, timestamp_s: float | None = None) -> np.ndarray | None:
    """Decode just one real video frame and return its landmark overlay as RGB."""
    frames = result.get("landmark_frames", [])
    if not frames:
        return None
    observation = min(frames, key=lambda frame: abs(frame["timestamp_s"] - timestamp_s)) if timestamp_s is not None else frames[0]
    capture = cv2.VideoCapture(str(path))
    try:
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        capture.set(cv2.CAP_PROP_POS_MSEC, observation["timestamp_s"] * 1000)
        ok, image = capture.read()
        return cv2.cvtColor(draw_overlay(image, observation, result["task"]), cv2.COLOR_BGR2RGB) if ok else None
    finally:
        capture.release()


class LandmarkRecorder:
    """Thread-safe WebRTC recorder with one raw image and bounded landmarks.

    Model detection feeds a separate 3D studio; an image overlay is an optional
    capture aid. The original raw image is written to disk. Final analysis
    always uses analyze_video on that saved recording.
    """

    def __init__(self, task: str, output_path: str | Path, model_dir=None, *, overlay: bool = False, show_trails: bool = True):
        _task(task)
        if type(overlay) is not bool or type(show_trails) is not bool:
            raise ValueError("Live display options must be True or False.")
        self.task, self.output_path, self.model_dir = task, Path(output_path), model_dir
        self.overlay, self.show_trails = overlay, show_trails
        self._lock = threading.RLock()
        self._writer = None
        self._detector = None
        self._started = None
        self._recording = False
        self._frames_written = 0
        self._last_frame = None
        self._recording_size = None
        self._last_detection = None
        self._last_frame_received_at = None
        self._last_recording_frame_time = None
        self._last_observation = None
        self._last_observed_at = None
        self._observation_history = deque(maxlen=LIVE_HISTORY_MAX_FRAMES)
        self._clock_origin = time.monotonic()
        self._status = {"camera_active": False, "recording": False, "recording_ready": False, "detected": False, "tracking_fresh": False, "observation_age_s": None, "frame_age_s": None, "frame_size": None, "elapsed_s": 0.0, "frames_analyzed": 0, "error": None, "timing_valid": True, "recording_gap_count": 0, "longest_recording_gap_s": 0.0, "frames_written": 0, "unique_camera_frames": 0, "effective_capture_fps": 0.0}

    def set_display_options(self, *, overlay: bool, show_trails: bool = True) -> None:
        """Change display aids under the stream lock; recording is unaffected."""
        if type(overlay) is not bool or type(show_trails) is not bool:
            raise ValueError("Live display options must be True or False.")
        with self._lock:
            self.overlay, self.show_trails = overlay, show_trails

    def _clear_observation(self, *, clear_time: bool = True) -> None:
        self._last_observation = None
        self._observation_history.clear()
        if clear_time:
            self._last_observed_at = None
        self._status.update({"detected": False, "visible": False, "tracking_fresh": False})

    def _refresh_live_status(self, now: float) -> None:
        """Expire a frozen camera or detection even when no new frame arrives."""
        frame_age = now - self._last_frame_received_at if self._last_frame_received_at is not None else None
        observation_age = now - self._last_observed_at if self._last_observed_at is not None else None
        active = frame_age is not None and 0 <= frame_age <= LIVE_OBSERVATION_MAX_AGE_S
        fresh = bool(active and self._last_observation is not None and observation_age is not None and 0 <= observation_age <= LIVE_OBSERVATION_MAX_AGE_S)
        self._status.update({"camera_active": active, "detected": fresh, "visible": fresh, "tracking_fresh": fresh, "frame_age_s": round(frame_age, 3) if frame_age is not None else None, "observation_age_s": round(observation_age, 3) if observation_age is not None else None})
        if not fresh:
            self._clear_observation(clear_time=False)
        while self._observation_history and now - self._observation_history[0][0] > LIVE_HISTORY_MAX_AGE_S:
            self._observation_history.popleft()

    def start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            if self._writer is not None:
                self._writer.release()
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = None
            self._frames_written = 0
            self._last_frame = None
            self._recording_size = None
            self._started = None
            self._last_recording_frame_time = None
            self._recording = True
            self._status.update({"recording": True, "recording_ready": False, "elapsed_s": 0.0, "error": None, "timing_valid": True, "recording_gap_count": 0, "longest_recording_gap_s": 0.0, "frames_written": 0, "unique_camera_frames": 0, "effective_capture_fps": 0.0})

    def stop_recording(self) -> Path | None:
        with self._lock:
            was_recording = self._recording
            self._recording = False
            self._status["recording"] = False
            self._status["frames_written"] = self._frames_written
            elapsed = float(self._status["elapsed_s"])
            if elapsed > 0:
                unique_fps = max(self._status["unique_camera_frames"] - 1, 0) / elapsed
                self._status["effective_capture_fps"] = round(unique_fps, 2)
                minimum_fps = 15 if self.task.startswith("finger") else 8
                if unique_fps < minimum_fps:
                    self._status["timing_valid"] = False
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            self._last_frame = None
            ready = bool(self._frames_written and self.output_path.is_file())
            if was_recording:
                self._status["recording_ready"] = ready
            if ready:
                os.chmod(self.output_path, 0o600)
                return self.output_path
            return None

    def mark_recording_reviewed(self) -> None:
        """Consume current-attempt readiness after analysis, including failures.

        A later repeated stop or stream close cannot make that same attempt
        ready again. Starting and finishing a new recording creates readiness
        for the new attempt; no media path enters the status polling payload.
        """
        with self._lock:
            self._status["recording_ready"] = False

    def snapshot(self, include_landmarks: bool = False) -> dict:
        """Status by default; opt in to detached live coordinates and trail history.

        Camera buffers and recordings never enter this polling payload. Deep
        copying under the recorder lock prevents caller mutations racing with
        detection and avoids exposing coordinates to routine status clients.
        ``observation`` is None after tracking loss or a 0.35-second pause.
        ``observation_history`` contains at most 45 observations from the last
        three seconds, with the same relative ``timestamp_s`` as detection.
        A gap, hand-side change or tracking loss clears the trail; no missing
        coordinates are interpolated. Ages are measured when this method reads.
        """
        with self._lock:
            self._refresh_live_status(time.monotonic())
            snapshot = deepcopy(self._status)
            snapshot["display_options"] = {"overlay": self.overlay, "show_trails": self.show_trails}
            if include_landmarks:
                snapshot["observation"] = deepcopy(self._last_observation)
                snapshot["observation_history"] = [deepcopy(observation) for _, observation in self._observation_history]
            return snapshot

    def process(self, frame: np.ndarray) -> np.ndarray:
        with self._lock:
            now = time.monotonic()
            self._refresh_live_status(now)
            self._last_frame_received_at = now
            self._status.update({"camera_active": True, "frame_age_s": 0.0})
            if max(frame.shape[:2]) > 960:
                factor = 960 / max(frame.shape[:2])
                frame = cv2.resize(frame, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
            if self._recording:
                self._status["unique_camera_frames"] += 1
                if self._last_recording_frame_time is not None:
                    gap = now - self._last_recording_frame_time
                    self._status["longest_recording_gap_s"] = max(self._status["longest_recording_gap_s"], round(gap, 3))
                    if gap > 0.5:
                        self._status["timing_valid"] = False
                        self._status["recording_gap_count"] += 1
                self._last_recording_frame_time = now
                if self._started is None:
                    self._started = now
                    height, width = frame.shape[:2]
                    self._recording_size = (width, height)
                    self._writer = cv2.VideoWriter(str(self.output_path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (width, height))
                    if not self._writer.isOpened():
                        self._status["error"] = "Could not open local recording file."
                        self.stop_recording()
                elapsed = now - (self._started if self._started is not None else now)
                self._status["elapsed_s"] = round(elapsed, 1)
                if self._writer is not None:
                    if (frame.shape[1], frame.shape[0]) != self._recording_size:
                        frame = cv2.resize(frame, self._recording_size, interpolation=cv2.INTER_AREA)
                    target_count = min(int(elapsed * 20) + 1, MAX_SECONDS * 20)
                    # Preserve elapsed time through network jitter with one previous frame.
                    while self._frames_written < target_count:
                        self._writer.write(self._last_frame if self._last_frame is not None and self._frames_written + 1 < target_count else frame)
                        self._frames_written += 1
                    self._status["frames_written"] = self._frames_written
                    self._last_frame = frame.copy()
                    if elapsed >= MAX_SECONDS:
                        self.stop_recording()
            self._status["frame_size"] = {"width": int(frame.shape[1]), "height": int(frame.shape[0])}
            if self._last_detection is None or now - self._last_detection >= 0.1:
                self._last_detection = now
                try:
                    if self._detector is None:
                        self._detector = LandmarkDetector(self.task, self.model_dir)
                    observation = self._detector.detect(frame, now - self._clock_origin)
                    visible = frame_visible(observation, self.task)
                    expected_side = TASKS[self.task].get("side")
                    if expected_side and observation and observation.get("hand_side") != expected_side:
                        visible = False
                    if visible:
                        if self._last_observation is not None and self._last_observation.get("hand_side") != observation.get("hand_side"):
                            self._observation_history.clear()
                        self._last_observation = deepcopy(observation)
                        self._last_observed_at = now
                        self._observation_history.append((now, deepcopy(observation)))
                    else:
                        self._clear_observation()
                    self._status["frames_analyzed"] += 1
                    self._status["error"] = None
                except Exception as exc:
                    self._clear_observation()
                    self._status["error"] = str(exc) if isinstance(exc, CVError) else "Live landmarks are unavailable. Final video analysis is still required."
                light, blur = frame_quality(frame)
                self._status.update({"brightness": round(light, 1), "lighting_good": 35 <= light <= 240, "blur_variance": round(blur, 1)})
            self._refresh_live_status(time.monotonic())
            if self.overlay and self._last_observation is not None:
                from ml.vision.live_overlay import draw_live_overlay

                output = draw_live_overlay(frame.copy(), deepcopy(self._last_observation), self.task, history=[deepcopy(observation) for _, observation in self._observation_history], show_trails=self.show_trails)
            else:
                output = frame.copy()
            label = "Landmarks visible" if self._status["detected"] else "Keep the required body / hand in view"
            cv2.putText(output, label, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
            if self._recording:
                cv2.putText(output, f"Recording {self._status['elapsed_s']:.1f}s / {MAX_SECONDS}s", (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 200, 255), 1, cv2.LINE_AA)
            return output

    def close(self) -> None:
        with self._lock:
            self.stop_recording()
            self._last_frame_received_at = None
            self._clear_observation()
            self._status["camera_active"] = False
            if self._detector is not None:
                self._detector.close()
                self._detector = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def make_video_processor(task: str, output_path: str | Path, model_dir=None, *, overlay: bool = False, show_trails: bool = True):
    """Return a VideoProcessor class for webrtc_streamer(video_processor_factory=...)."""
    import av
    from streamlit_webrtc import VideoProcessorBase

    class TaskVideoProcessor(VideoProcessorBase, LandmarkRecorder):
        def __init__(self):
            LandmarkRecorder.__init__(self, task, output_path, model_dir, overlay=overlay, show_trails=show_trails)

        def recv(self, frame):
            image = self.process(frame.to_ndarray(format="bgr24"))
            return av.VideoFrame.from_ndarray(image, format="bgr24")

        def on_ended(self):
            self.close()

    return TaskVideoProcessor
