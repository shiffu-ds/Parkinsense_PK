"""Fault guidance must preserve evidence, remain private, and be actionable."""

from copy import deepcopy
import json

import numpy as np
import pytest
import soundfile as sf
from streamlit.testing.v1 import AppTest

from ml.audio.features import analyze_audio
from ml.common.guidance import SOURCES, build_guidance
from ml.nlp.functional import analyze_text
from ml.tabular.adl import ADL_ITEMS, analyze_adl
from ml.vision.pipeline import CVError, LandmarkDetector, validate_video


def codes(entries):
    return [entry["code"] for entry in entries]


def test_missing_model_guidance_is_setup_issue_without_paths(tmp_path):
    with pytest.raises(CVError) as caught:
        LandmarkDetector("finger_left", tmp_path)
    entries = build_guidance(task="finger_left", error=caught.value)
    assert codes(entries) == ["model_unavailable"]
    assert entries[0]["kind"] == "processing"
    assert "again will not install" in entries[0]["steps"][0]
    serialized = json.dumps(entries)
    assert str(tmp_path) not in serialized
    assert "uv run" not in serialized
    assert "scripts/" not in serialized
    assert entries[0]["source"] == SOURCES["hand"]


def test_actual_empty_and_corrupt_video_exceptions_get_specific_instructions(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.touch()
    with pytest.raises(CVError) as caught:
        validate_video(empty, "gait")
    assert codes(build_guidance(task="gait", error=caught.value)) == ["empty_recording"]
    corrupt = tmp_path / "renamed.mp4"
    corrupt.write_bytes(b"Not video data" * 20)
    with pytest.raises(CVError) as caught:
        validate_video(corrupt, "gait")
    entries = build_guidance(task="gait", error=caught.value)
    assert codes(entries) == ["video_format"]
    assert "renaming" in entries[0]["steps"][1]


def test_actual_audio_faults_and_vowel_minimum(tmp_path):
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(16000 * 3), 16000)
    result = analyze_audio(silent, task="natural")
    assert codes(build_guidance(result, "voice_natural")) == ["silence"]
    assert result["features"] == {}
    clipped = tmp_path / "clipped.wav"
    sf.write(clipped, np.tile([1.0, -1.0], 24000), 16000)
    assert codes(build_guidance(analyze_audio(clipped))) == ["clipping"]
    short = tmp_path / "short.wav"
    sf.write(short, np.zeros(16000), 16000)
    entries = build_guidance(analyze_audio(short, task="vowel"), "voice_vowel")
    assert codes(entries) == ["duration_short"]
    assert "2 seconds" in entries[0]["steps"][0]
    invalid_rate = tmp_path / "invalid_rate.wav"
    sf.write(invalid_rate, np.zeros(4000 * 3), 4000)
    entries = build_guidance(analyze_audio(invalid_rate, task="natural"), "voice_natural")
    assert codes(entries) == ["audio_sample_rate"]
    assert "8 to 192 kHz" in entries[0]["reason"]


@pytest.mark.parametrize("message,expected", [
    ("Lighting is unsuitable. Use even light and avoid strong backlighting.", "lighting"),
    ("The recording is very blurred or featureless. Stabilize the camera and refocus.", "blur"),
    ("Keep all required joints visible. Move the camera far enough away and avoid occlusion.", "body_view"),
    ("Keep the complete selected hand visible; use an unmirrored video and check the requested left/right side.", "hand_view"),
    ("Too few usable landmark frames were detected.", "landmarks_lost"),
    ("Video orientation appears incorrect. Use an upright recording.", "orientation"),
    ("Landmarks were lost for more than a second. Repeat with less occlusion.", "occlusion"),
    ("The live recording had frame gaps or too few unique camera frames. Repeat with a stable connection and sufficient frame rate.", "stream_gaps"),
    ("Camera connection gaps during recording", "stream_gaps"),
    ("Recording is missing or empty", "empty_recording"),
    ("Little opening/closing activity was detected. Repeat the selected finger/hand task.", "movement_not_visible"),
    ("A clear knee extension transition was not visible. Repeat sit-to-stand safely with hips and legs in view.", "movement_not_visible"),
    ("Use a recording with a valid frame rate from 8 to 120 fps.", "frame_rate"),
    ("Use a video at least 240 pixels on each side and no larger than 4K.", "resolution"),
    ("Trim the video to 45 seconds or less before analysis.", "duration_long"),
    ("Audio file exceeds the 72 MB processing limit.", "file_size"),
])
def test_local_recording_failures_explain_the_exact_setup_issue(message, expected):
    result = {"status": "repeat", "quality": {"accepted": False, "issues": [message]}, "features": {}}
    before = deepcopy(result)
    entries = build_guidance(result, "finger_right")
    assert codes(entries) == [expected]
    assert all(len(entry["steps"]) == 3 and all(entry["steps"]) for entry in entries)
    assert all(entry["kind"] == "recording" for entry in entries)
    assert result == before


def test_deduplication_and_safe_stored_code_reproduction():
    result = {"status": "repeat", "quality": {"accepted": False, "issues": [
        "Little opening/closing activity was detected. Repeat the selected finger/hand task.",
        "Fewer than two distinct movement cycles were visible. Record several complete cycles.",
    ]}}
    direct = build_guidance(result, "finger_right")
    assert codes(direct) == ["movement_not_visible"]
    stored = {"status": "unavailable", "quality": {"accepted": False,
        "issue_codes": codes(direct), "messages": ["The task did not pass its local recording check."]}}
    assert build_guidance(stored, "finger_right") == direct
    injected = {"quality": {"issue_codes": ["self_reported_falls", "not_a_real_code", {"url": "https://evil.test"}]}}
    assert build_guidance(injected, "gait") == []


def test_accepted_signal_with_unconfigured_asr_remains_accepted():
    result = {"status": "accepted", "quality": {"accepted": True, "messages": ["Usable audio signal."]},
              "features": {"signal_rms_dbfs": -18.0}, "asr": {"status": "unavailable", "reason": "private text"}}
    before = deepcopy(result)
    entries = build_guidance(result, "voice_sentence")
    assert codes(entries) == ["asr_unconfigured"]
    assert entries[0]["kind"] == "processing"
    assert "still be usable" in entries[0]["reason"]
    assert "private text" not in json.dumps(entries)
    assert result == before
    assert build_guidance({"status": "accepted", "quality": {"accepted": True, "messages": ["All ADL items completed."]}}, "adl") == []


def test_unanswered_adl_and_invalid_transcript_have_concrete_steps():
    with pytest.raises(ValueError) as caught:
        analyze_adl({item: None for item in ADL_ITEMS})
    entries = build_guidance(task="adl", error=caught.value)
    assert codes(entries) == ["adl_complete"]
    assert "unanswered item" in entries[0]["reason"]
    with pytest.raises(ValueError) as caught:
        analyze_text("")
    assert codes(build_guidance(task="nlp", error=caught.value)) == ["transcript_required"]


def test_followup_requires_explicit_self_report_and_never_infers_from_proxies():
    positive = analyze_text("I fell today. My feet freeze when turning.")
    entries = build_guidance(positive, "nlp")
    assert codes(entries) == ["self_reported_falls", "self_reported_freezing"]
    assert all(entry["kind"] == "follow_up" and entry["source"]["url"].startswith("https://www.parkinson.org/") for entry in entries)
    assert "not a fall detected" in entries[0]["reason"]
    negative = analyze_text("I have no falls or freezing. Walking was mentioned only.")
    assert build_guidance(negative, "nlp") == []
    contradictory = {**negative, "review_flags": ["Self-reported falls needs clinician review."]}
    assert build_guidance(contradictory, "nlp") == []
    mentioned = analyze_text("Walking is part of my routine.")
    assert build_guidance(mentioned, "nlp") == []
    motion = {"status": "accepted", "quality": {"accepted": True}, "features": {"ankle_range_asymmetry_proxy": 0.99,
             "tap_frequency_hz_proxy": 0.1}, "review_flags": ["Self-reported falls needs clinician review."]}
    assert build_guidance(motion, "gait") == []
    forged = {**positive, "provenance": {"source": "model_prediction"}}
    assert build_guidance(forged, "nlp") == []
    rejected = {**positive, "quality": {"accepted": False}, "status": "repeat"}
    assert all(entry["kind"] != "follow_up" for entry in build_guidance(rejected, "nlp"))


def test_unknown_faults_never_echo_patient_text_stack_paths_or_urls():
    private = "Traceback /data/private/patient.wav Patient said I fall often <script>alert(1)</script> https://evil.test"
    entries = build_guidance(task="voice_natural", error=private)
    assert codes(entries) == ["analysis_retry"]
    serialized = json.dumps(entries)
    assert "patient.wav" not in serialized and "script" not in serialized and "evil.test" not in serialized
    assert all(entry["kind"] != "follow_up" for entry in entries)
    assert build_guidance({"status": {}, "quality": {"decision": [], "accepted": None}}, "gait") == []
    assert codes(build_guidance(task="gait", error="Movement analysis failed. Check the recording and model installation, then try again.")) == ["analysis_retry"]


def test_real_roman_urdu_and_native_urdu_guidance():
    roman = build_guidance(task="gait", error="Record at least 5 seconds for this task.", language="Roman Urdu")
    assert roman[0]["language"] == "roman urdu"
    assert "kam az kam 5 seconds" in roman[0]["steps"][0]
    assert roman[0]["translation_note"] is None
    urdu = build_guidance(task="gait", error="Record at least 5 seconds for this task.", language="Urdu")
    assert urdu[0]["language"] == "urdu" and urdu[0]["translation_note"] is None
    assert "5" in urdu[0]["steps"][0]


def test_rendered_fault_is_numbered_and_contains_only_catalogue_copy():
    app = AppTest.from_string("from app.components.guidance_panel import render_guidance\nrender_guidance(task='gait', error='Traceback /private/patient.mp4 lighting is unsuitable <script>')", default_timeout=20).run()
    assert not app.exception
    rendered = "\n".join(element.value for element in app.markdown)
    assert "Improve the lighting" in rendered
    assert all(f"{number}. " in rendered for number in (1, 2, 3))
    assert "patient.mp4" not in rendered and "<script>" not in rendered
