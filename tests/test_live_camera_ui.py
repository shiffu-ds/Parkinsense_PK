"""Live tracking UI with test-only geometry and no camera or WebRTC session."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest


def observation(task="gait", *, world=True, timestamp=1.0):
    """Invented XYZ used only to exercise rendering, never clinical inference."""
    count = 21 if task.startswith("finger") or task in {"grasp", "object_transfer", "hand_open_close"} else 33
    points = [
        [0.3 + (index % 5) * 0.04, 0.2 + (index // 5) * 0.055, (index % 3) * 0.024, 0.95]
        for index in range(count)
    ]
    result = {"timestamp_s": timestamp, "landmarks": points}
    if world:
        result["world_landmarks"] = deepcopy(points)
    if count == 21:
        result.update(hand_side="Right" if task == "finger_right" else "Left", handedness_confidence=0.95)
    return result


class FakeProcessor:
    def __init__(self, task="gait", *, world=True, name="initial", error=None):
        self.name = name
        self.display_options = []
        self.snapshot_calls = []
        self.start_calls = 0
        self.data = {
            "camera_active": True, "recording": False, "recording_ready": False, "detected": True,
            "lighting_good": True, "error": error,
            "observation": observation(task, world=world),
            "observation_history": [observation(task, world=world, timestamp=0.9)],
        }

    def set_display_options(self, **options):
        self.display_options.append(options)

    def snapshot(self, include_landmarks=False):
        self.snapshot_calls.append(include_landmarks)
        return deepcopy(self.data)

    def start_recording(self):
        self.start_calls += 1
        self.data["recording"] = True
        self.data["recording_ready"] = False


def panel_app(ctx, task="gait", *, identity="isolated-test-only", **options):
    # AppTest replaces the runtime/registry; real servers keep one registry.
    from app.components.live_plot import _library_loader, _live_host
    _library_loader.cache_clear()
    _live_host.cache_clear()
    source = """
import streamlit as st
from app.components.live_camera import live_camera_panel

def finish(processor):
    st.session_state['finished_processor'] = processor.name
    processor.data['recording'] = False
    processor.data['recording_ready'] = False

live_camera_panel(st.session_state['ctx'], st.session_state['task'],
                  identity=st.session_state['identity'], on_finish=finish,
                  **st.session_state['options'])
"""
    app = AppTest.from_string(source, default_timeout=25)
    app.session_state["ctx"] = ctx
    app.session_state["task"] = task
    app.session_state["identity"] = identity
    app.session_state["options"] = options
    return app.run()


def control(app, label):
    return next(button for button in app.button if button.label == label)


def live_charts(app):
    return [node for node in app.get("bidi_component") if node.proto.json and "figure" in json.loads(node.proto.json)]


def figure(app):
    return json.loads(live_charts(app)[0].proto.json)["figure"]


def ui_text(app):
    return "\n".join(item.value for category in (app.markdown, app.caption, app.info, app.warning) for item in category)


def test_polling_panel_exists_before_async_processor_and_reads_late_processor():
    ctx = SimpleNamespace(video_processor=None, state=SimpleNamespace(playing=False))
    app = panel_app(ctx)
    assert not app.exception
    assert "Ready for live tracking" in ui_text(app)
    assert control(app, "Start recording").disabled
    assert control(app, "Finish & analyze").disabled
    assert not live_charts(app)
    # The initial absence must still register a polling fragment. AppTest does
    # not advance automatic timer ticks, so the next run simulates one poll.
    assert len(app._fragment_storage._fragments) == 1
    ctx.video_processor = FakeProcessor()
    ctx.state.playing = True
    app.run()
    assert not app.exception
    assert not control(app, "Start recording").disabled
    assert control(app, "Finish & analyze").disabled
    assert live_charts(app)
    assert ctx.video_processor.snapshot_calls == [True]
    assert ctx.video_processor.display_options[-1] == {"overlay": True, "show_trails": True}
    assert {trace["type"] for trace in figure(app)["data"]} <= {"scatter3d", "mesh3d"}


def test_disconnect_and_reconnect_never_reuse_previous_processor_or_geometry():
    old = FakeProcessor(name="old")
    ctx = SimpleNamespace(video_processor=old, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    assert not app.exception and live_charts(app)
    old_polls = len(old.snapshot_calls)
    ctx.video_processor = None
    ctx.state.playing = False
    app.run()
    assert not app.exception
    assert not live_charts(app)
    assert control(app, "Start recording").disabled
    assert old.snapshot_calls[old_polls:] == [False]
    replacement = FakeProcessor(name="replacement")
    ctx.video_processor = replacement
    ctx.state.playing = True
    app.run()
    assert not app.exception and live_charts(app)
    assert old.snapshot_calls[old_polls:] == [False]
    assert replacement.snapshot_calls == [True]


@pytest.mark.parametrize("task", ["finger_left", "finger_right", "gait", "reach", "sit_to_stand"])
def test_each_live_task_has_actual_3d_plot_and_an_explicit_body_part_focus(task):
    processor = FakeProcessor(task)
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))
    app = panel_app(ctx, task)
    assert not app.exception
    assert live_charts(app)
    assert "Live 3D joint tracking" in ui_text(app)
    assert any(item.value.startswith("Focus: ") for item in app.caption)
    assert "world XYZ" in ui_text(app)
    assert "aligned screen projection" in ui_text(app)
    assert not app.get("download_button")


def test_display_preferences_apply_to_current_processor_and_3d_camera():
    processor = FakeProcessor()
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))
    app = panel_app(ctx, overlay=False, show_trails=False, camera="Side")
    assert not app.exception
    assert processor.display_options[-1] == {"overlay": False, "show_trails": False}
    from app.components.live_3d_viewer import CAMERAS
    assert figure(app)["layout"]["scene"]["camera"]["eye"] == CAMERAS["Side"]
    assert not any("trail" in trace.get("name", "").lower() for trace in figure(app)["data"])


@pytest.mark.parametrize("issue", ["lost_tracking", "world_coordinates_missing"])
def test_lost_or_unusable_world_geometry_shows_guidance_without_fabricated_lines(issue):
    processor = FakeProcessor(world=issue != "world_coordinates_missing")
    if issue == "lost_tracking":
        processor.data.update(observation=None, detected=False, observation_history=[])
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    assert not app.exception
    assert not live_charts(app)
    assert "in view" in ui_text(app) or "clearer view" in ui_text(app)


def test_model_fault_shows_actionable_guidance_without_exposing_internal_path():
    processor = FakeProcessor(error="Landmark model is missing. Private path: /private/patient-stream.task")
    processor.data.update(observation=None, detected=False, observation_history=[], lighting_good=False)
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    assert not app.exception
    text = ui_text(app)
    assert "patient-stream.task" not in text and "/private/" not in text
    assert "Your next steps" in "\n".join(item.value for item in app.subheader)
    assert "1. " in text and "2. " in text
    assert "even light" in text
    assert not live_charts(app)


def test_paused_or_currently_recording_camera_has_consistent_record_controls():
    processor = FakeProcessor()
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=False))
    app = panel_app(ctx)
    assert not app.exception
    assert control(app, "Start recording").disabled
    assert control(app, "Finish & analyze").disabled
    ctx.state.playing = True
    processor.data["recording"] = True
    app.run()
    assert not app.exception
    assert control(app, "Start recording").disabled
    assert not control(app, "Finish & analyze").disabled


@pytest.mark.parametrize("playing", [False, True])
def test_automatically_completed_clip_stays_available_to_analyze(playing):
    """The 45-second cap or a paused stream must not strand a completed clip."""
    processor = FakeProcessor()
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=playing))
    app = panel_app(ctx)
    assert not app.exception
    assert control(app, "Finish & analyze").disabled
    processor.data.update(recording=False, recording_ready=True, frames_written=900)
    app.run()
    assert not app.exception
    assert not control(app, "Finish & analyze").disabled
    assert "Recording complete" in ui_text(app)
    # Readiness is an explicit current-attempt state. A frame count left over
    # from a reviewed clip must not make that recording available again.
    processor.data["recording_ready"] = False
    app.run()
    assert not app.exception
    assert control(app, "Finish & analyze").disabled


def test_start_uses_current_processor_and_finish_reviews_pending_clip_first(monkeypatch):
    from app.components import live_camera
    reruns = []
    # AppTest normally performs full script reruns for widget actions. Capture
    # the production requested scope here; timer/fragment execution is tested
    # by Streamlit itself, not by this hardware-free UI fixture.
    monkeypatch.setattr(live_camera.st, "rerun", lambda **kwargs: reruns.append(kwargs))
    old = FakeProcessor(name="old")
    ctx = SimpleNamespace(video_processor=old, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    control(app, "Start recording").click().run()
    assert not app.exception
    assert old.start_calls == 1
    assert reruns[-1] == {"scope": "fragment"}
    replacement = FakeProcessor(name="replacement")
    replacement.data["recording"] = True
    ctx.video_processor = replacement
    app.run()
    assert control(app, "Start recording").disabled
    control(app, "Finish & analyze").click().run()
    assert not app.exception
    assert app.session_state["finished_processor"] == "old"
    assert old.data["recording"] is False
    assert replacement.data["recording"] is True
    assert reruns[-1] == {}
    app.run()
    control(app, "Finish & analyze").click().run()
    assert not app.exception
    assert app.session_state["finished_processor"] == "replacement"
    assert replacement.data["recording"] is False


def test_camera_stop_keeps_ready_clip_reviewable_without_showing_old_geometry():
    old = FakeProcessor(name="stopped-clip")
    old.data["recording_ready"] = True
    ctx = SimpleNamespace(video_processor=old, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    assert not app.exception and live_charts(app)
    old_polls = len(old.snapshot_calls)
    ctx.video_processor = None
    ctx.state.playing = False
    app.run()
    assert not app.exception
    assert not live_charts(app)
    assert control(app, "Start recording").disabled
    assert not control(app, "Finish & analyze").disabled
    assert "Your recorded clip is ready" in ui_text(app)
    # A retained recorder is polled for status only after STOP. Its prior
    # landmarks must not be requested or rendered as live camera geometry.
    assert old.snapshot_calls[old_polls:] == [False]
    control(app, "Finish & analyze").click().run()
    assert not app.exception
    assert app.session_state["finished_processor"] == "stopped-clip"
    assert not old.data["recording_ready"]
    assert control(app, "Finish & analyze").disabled
    assert not live_charts(app)


def test_reconnect_displays_new_geometry_while_reviewing_old_pending_clip():
    old = FakeProcessor(name="pending-before-reconnect")
    old.data["recording_ready"] = True
    ctx = SimpleNamespace(video_processor=old, state=SimpleNamespace(playing=True))
    app = panel_app(ctx)
    replacement = FakeProcessor(name="fresh-camera")
    replacement.data["observation"]["timestamp_s"] = 2.0
    replacement.data["observation_history"] = []
    old_polls = len(old.snapshot_calls)
    ctx.video_processor = replacement
    app.run()
    assert not app.exception and live_charts(app)
    assert figure(app)["layout"]["meta"]["timestamp_s"] == 2.0
    assert old.snapshot_calls[old_polls:] == [False]
    assert replacement.snapshot_calls == [True]
    assert control(app, "Start recording").disabled
    assert not control(app, "Finish & analyze").disabled
    assert "before the camera reconnected" in ui_text(app)
    control(app, "Finish & analyze").click().run()
    assert not app.exception
    assert app.session_state["finished_processor"] == "pending-before-reconnect"
    assert not old.data["recording_ready"]
    assert not control(app, "Start recording").disabled
    assert control(app, "Finish & analyze").disabled
    assert figure(app)["layout"]["meta"]["timestamp_s"] == 2.0


def test_a_different_task_identity_cannot_recover_another_tasks_recording():
    old = FakeProcessor(name="gait-pending")
    old.data["recording_ready"] = True
    ctx = SimpleNamespace(video_processor=old, state=SimpleNamespace(playing=True))
    app = panel_app(ctx, identity="visit-gait")
    ctx.video_processor = None
    ctx.state.playing = False
    app.session_state["identity"] = "visit-reach"
    app.session_state["task"] = "reach"
    old_polls = len(old.snapshot_calls)
    app.run()
    assert not app.exception
    assert control(app, "Finish & analyze").disabled
    assert not live_charts(app)
    assert "Your recorded clip is ready" not in ui_text(app)
    assert len(old.snapshot_calls) == old_polls
    # Returning to that exact assessment/task identity restores only its clip.
    app.session_state["identity"] = "visit-gait"
    app.session_state["task"] = "gait"
    app.run()
    assert not app.exception
    assert not control(app, "Finish & analyze").disabled
    assert not live_charts(app)


@pytest.fixture
def movement_visit(tmp_path, monkeypatch):
    from app.components.live_plot import _library_loader, _live_host
    _library_loader.cache_clear()
    _live_host.cache_clear()
    from backend import services
    from backend.db import configure_db, init_db
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'live-ui.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Live UI Fixture", "live-ui@example.test", "test-password-123", consent=True)
    return patient, services.create_assessment(patient["id"])


def test_live_movement_page_enables_focused_lines_and_propagates_user_options(movement_visit, monkeypatch):
    """Exercise the production task page with its actual controls, no devices."""
    import streamlit_webrtc
    from ml.vision import pipeline
    from app.components.live_3d_viewer import CAMERAS

    factory_calls = []
    webrtc_calls = []
    processor = FakeProcessor("gait")
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))

    def factory(task, output_path, **options):
        factory_calls.append({"task": task, "output_path": output_path, **options})
        return type("UnusedTestProcessor", (), {})

    def streamer(**options):
        webrtc_calls.append(options)
        return ctx

    monkeypatch.setattr(pipeline, "make_video_processor", factory)
    monkeypatch.setattr(streamlit_webrtc, "webrtc_streamer", streamer)
    patient, visit = movement_visit
    app = AppTest.from_string("from app.views import movement_page\nmovement_page(['gait'])", default_timeout=25)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    next(item for item in app.radio if item.label == "Recording source").set_value("Live Camera").run()
    assert not app.exception
    assert factory_calls[-1]["overlay"] is True and factory_calls[-1]["show_trails"] is True
    line_control = next(item for item in app.checkbox if item.label == "Show focused joint lines on camera")
    trail_control = next(item for item in app.checkbox if item.label == "Show short movement trails")
    assert line_control.value and trail_control.value
    assert "Focus: " in ui_text(app)
    assert live_charts(app)
    assert webrtc_calls[-1]["media_stream_constraints"]["audio"] is False
    assert webrtc_calls[-1]["video_html_attrs"]["style"]["transform"] == "none"
    line_control.uncheck()
    trail_control.uncheck()
    next(item for item in app.selectbox if item.label == "Live 3D viewpoint").set_value("Side").run()
    assert not app.exception
    assert factory_calls[-1]["overlay"] is False and factory_calls[-1]["show_trails"] is False
    assert processor.display_options[-1] == {"overlay": False, "show_trails": False}
    assert figure(app)["layout"]["scene"]["camera"]["eye"] == CAMERAS["Side"]
    # Turning off the projected camera annotation keeps genuine 3D available.
    assert live_charts(app)


def test_live_chart_keeps_its_host_identity_when_new_world_frames_arrive():
    processor = FakeProcessor("reach")
    ctx = SimpleNamespace(video_processor=processor, state=SimpleNamespace(playing=True))
    app = panel_app(ctx, "reach")
    assert not app.exception
    first_id = live_charts(app)[0].proto.id
    first_geometry = figure(app)
    processor.data["observation"]["timestamp_s"] = 1.2
    processor.data["observation"]["world_landmarks"][15][2] += 0.05
    app.run()
    assert not app.exception
    assert live_charts(app)[0].proto.id == first_id
    assert figure(app) != first_geometry
    assert figure(app)["layout"]["uirevision"] == first_geometry["layout"]["uirevision"]
    # The offline vendor bundle is outside the changing fragment payload.
    assert len(live_charts(app)[0].proto.js_content) < 5000
