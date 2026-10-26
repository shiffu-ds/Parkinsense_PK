"""Setup differences between recordings are named, never corrected."""
from ml.vision.framing import framing_differences, framing_summary, median_pose, touch_device_differences


def pose_result(scale=1.0, shift=(0.0, 0.0), side=False, size=(720, 1280), frames=12):
    # A standing figure: shoulders 11/12, hips 23/24, knees 25/26, ankles 27/28, feet 31/32.
    body = {11: (-0.15, -0.2), 12: (0.15, -0.2), 23: (-0.1, 0.0), 24: (0.1, 0.0), 25: (-0.1, 0.2),
            26: (0.1, 0.2), 27: (-0.1, 0.38), 28: (0.1, 0.38), 31: (-0.11, 0.4), 32: (0.11, 0.4)}
    landmarks = []
    for index in range(33):
        x, y = body.get(index, (0.0, -0.3))
        if side:
            x *= 0.15
        landmarks.append([0.5 + shift[0] + x * scale, 0.5 + shift[1] + y * scale, 0.0, 0.99 if index in body else 0.2])
    return {"task": "gait", "media_metadata": {"width": size[0], "height": size[1]},
            "landmark_frames": [{"timestamp_s": n / 10, "landmarks": landmarks} for n in range(frames)]}


def test_matching_setups_have_no_differences():
    reference = framing_summary(pose_result())
    assert reference["kind"] == "pose" and reference["orientation"] == "portrait" and reference["view"] == "front"
    assert framing_differences(framing_summary(pose_result(scale=1.1)), reference) == []


def test_distance_position_angle_and_orientation_are_named():
    reference = framing_summary(pose_result())
    assert framing_differences(framing_summary(pose_result(scale=1.6)), reference) == ["closer"]
    assert framing_differences(framing_summary(pose_result(scale=0.6)), reference) == ["farther"]
    assert framing_differences(framing_summary(pose_result(shift=(0.25, 0.0))), reference) == ["position"]
    assert framing_differences(framing_summary(pose_result(side=True)), reference) == ["view"]
    assert "orientation" in framing_differences(framing_summary(pose_result(size=(1280, 720))), reference)


def test_unusable_inputs_give_no_summary_or_differences():
    assert framing_summary({"task": "gait"}) is None
    assert framing_summary(pose_result(frames=2)) is None
    assert framing_summary({**pose_result(), "task": "voice_vowel"}) is None
    assert framing_differences(None, framing_summary(pose_result())) == []


def test_touch_screen_or_input_changes_are_named():
    phone = {"device": {"canvas_px": [360, 360], "pointer": "touch"}}
    assert touch_device_differences(phone, phone) == []
    assert touch_device_differences({"device": {"canvas_px": [460, 460], "pointer": "pen"}}, phone) == ["screen", "pointer"]
    assert touch_device_differences({}, phone) == []


def test_median_pose_keeps_only_reliably_seen_landmarks():
    pose = median_pose(pose_result())
    assert pose[11] == [0.35, 0.3] and pose[0] is None


def test_setup_notice_and_guide_render_in_the_patients_language():
    from streamlit.testing.v1 import AppTest
    script = """
from app.components.setup_check import setup_guide, setup_notice
from tests.test_framing import pose_result
setup_notice(pose_result(scale=1.6), pose_result(), "gait", "Roman Urdu")
setup_notice(pose_result(), pose_result(), "gait", "English")
setup_guide("gait", pose_result(), "English", key="guide")
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    notice = "\n".join(block.value for block in app.markdown)
    assert "mukhtalif tarteeb" in notice and "zyada qareeb" in notice
    assert any("Set up like your earlier recording" in caption.value for caption in app.caption)
    assert app.expander and app.get("plotly_chart")
