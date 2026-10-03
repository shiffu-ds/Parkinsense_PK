"""3D studio controls with synthetic test geometry, never detector validation."""

import json

import pytest
from streamlit.testing.v1 import AppTest

from app.components import motion_studio


def _geometry(task="gait", *, world=True):
    """Small invented joint sets used only to exercise the UI renderer."""
    count = 21 if task == "finger_left" else 33
    frames = []
    for frame_index in range(3):
        joints = [
            [(index % 5) * 0.05, (index // 5) * 0.07, (index % 3) * 0.025 + frame_index * 0.01, 0.95]
            for index in range(count)
        ]
        frame = {"timestamp_s": frame_index * 0.1, "landmarks": joints, "hand_side": "Left" if count == 21 else ""}
        if world:
            frame["world_landmarks"] = joints
        frames.append(frame)
    return {"task": task, "landmark_frames": frames}


def _studio(result, baseline=None, identity="test-recording"):
    app = AppTest.from_string(
        "from app.components.motion_studio import movement_studio\n"
        "import streamlit as st\n"
        "movement_studio(st.session_state['result'], baseline=st.session_state['baseline'], identity=st.session_state['identity'])",
        default_timeout=20,
    )
    app.session_state["result"] = result
    app.session_state["baseline"] = baseline
    app.session_state["identity"] = identity
    return app.run()


def _figure(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)


def test_image_coordinates_alone_show_empty_state_without_replay_controls():
    app = _studio(_geometry(world=False))
    assert not app.exception
    assert any("No usable 3D geometry" in item.value for item in app.markdown)
    assert not app.selectbox
    assert not app.get("plotly_chart")
    assert not app.get("download_button")
    assert not app.slider


@pytest.mark.parametrize("task,joint", [("gait", "Left ankle"), ("finger_left", "Index fingertip")])
def test_pose_and_hand_replay_have_world_3d_controls_and_no_2d_overlay(task, joint):
    app = _studio(_geometry(task))
    assert not app.exception
    controls = {item.label: item for item in app.selectbox}
    assert controls["Camera view"].value == "Isometric"
    assert controls["Model style"].value == "Solid avatar"
    assert controls["Playback speed"].value == 1.0
    assert joint in controls["Joint to follow"].options
    comparison = next(item for item in app.checkbox if item.label == "Compare with first reliable recording")
    assert comparison.disabled
    assert not comparison.value
    assert not app.slider
    assert all("overlay" not in item.label.lower() for item in app.checkbox)
    figure = _figure(app)
    assert figure["layout"]["meta"]["coordinate_source"] == "world_landmarks"
    assert figure["layout"]["meta"]["baseline_alignment"] is None
    assert {trace["type"] for trace in figure["data"]} <= {"mesh3d", "scatter3d"}
    assert any(trace["type"] == "mesh3d" for trace in figure["data"])
    assert len(figure["frames"]) == 3
    assert len(figure["layout"]["sliders"][0]["steps"]) == 3
    assert [item["label"] for item in figure["layout"]["updatemenus"][0]["buttons"]] == ["▶ Play", "Pause"]
    controls["Camera view"].set_value("Side")
    controls["Model style"].set_value("Skeleton")
    controls["Playback speed"].set_value(0.5).run()
    assert not app.exception
    changed = _figure(app)
    assert changed["layout"]["scene"]["camera"]["eye"] == motion_studio.CAMERAS["Side"]
    assert all(trace["type"] == "scatter3d" for trace in changed["data"])
    assert changed["layout"]["updatemenus"][0]["buttons"][0]["args"][1]["frame"]["duration"] == 200


def test_baseline_is_only_rendered_after_user_chooses_comparison():
    result = _geometry()
    app = _studio(result, baseline=result)
    assert not app.exception
    comparison = next(item for item in app.checkbox if item.label == "Compare with first reliable recording")
    assert not comparison.disabled
    assert _figure(app)["layout"]["meta"]["baseline_alignment"] is None
    comparison.check().run()
    assert not app.exception
    figure = _figure(app)
    assert figure["layout"]["meta"]["baseline_alignment"]
    assert any(trace["name"].startswith("Baseline") for trace in figure["data"])


@pytest.mark.parametrize("issue", ["image_coordinates_only", "different_task", "different_hand"])
def test_unusable_or_incompatible_baselines_keep_comparison_disabled(issue):
    current = _geometry("finger_left" if issue == "different_hand" else "gait")
    baseline = _geometry(current["task"], world=issue != "image_coordinates_only")
    if issue == "different_task":
        baseline["task"] = "turning"
    elif issue == "different_hand":
        for frame in baseline["landmark_frames"]:
            frame["hand_side"] = "Right"
    app = _studio(current, baseline=baseline)
    assert not app.exception
    comparison = next(item for item in app.checkbox if item.label == "Compare with first reliable recording")
    assert comparison.disabled
    assert not comparison.value
    assert _figure(app)["layout"]["meta"]["baseline_alignment"] is None
    assert not any(trace["name"].startswith("Baseline") for trace in _figure(app)["data"])


def test_offline_export_is_user_triggered_with_fixed_safe_filename(monkeypatch):
    exported = []
    export_function = motion_studio.build_motion_html

    def observe_export(*args, **kwargs):
        html = export_function(*args, **kwargs)
        exported.append(html)
        return html

    monkeypatch.setattr(motion_studio, "build_motion_html", observe_export)
    app = _studio(_geometry(), identity='../../<private patient name>".html')
    assert not app.exception
    assert exported == []
    assert not app.get("download_button")
    next(item for item in app.button if item.label == "Prepare offline 3D replay").click().run()
    assert not app.exception
    assert len(exported) == 1
    assert exported[0].startswith("<!doctype html>")
    assert "<private patient name>" not in exported[0]
    # Standalone geometry has no authenticated visit, so it may be previewed
    # but private landmarks must not enter public Streamlit media storage.
    assert not app.get("download_button")
    assert any("authenticated visit" in item.value for item in app.caption)
    # Changing an inspection control must not silently generate another export.
    next(item for item in app.selectbox if item.label == "Camera view").set_value("Front").run()
    assert not app.exception
    assert len(exported) == 1
    assert not app.get("download_button")
    assert any("Prepare the replay again" in item.value for item in app.caption)


def test_replaced_recording_hides_stale_export_until_user_prepares_current_replay():
    app = _studio(_geometry(), identity="same-assessment-revision")
    next(item for item in app.button if item.label == "Prepare offline 3D replay").click().run()
    assert not app.exception
    assert not app.get("download_button")
    assert any("authenticated visit" in item.value for item in app.caption)
    revised = _geometry()
    for frame in revised["landmark_frames"]:
        frame["world_landmarks"][27][2] += 0.2
    # The same assessment/task can acquire revised landmarks after a repeat.
    # A saved file for the prior revision must not be offered as this replay.
    app.session_state["result"] = revised
    app.run()
    assert not app.exception
    assert not app.get("download_button")
    assert any("Prepare the replay again" in item.value for item in app.caption)
    next(item for item in app.button if item.label == "Prepare offline 3D replay").click().run()
    assert not app.exception
    assert not app.get("download_button")
    assert any("authenticated visit" in item.value for item in app.caption)
