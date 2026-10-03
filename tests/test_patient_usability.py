"""Patient language flows against isolated storage, without a camera or microphone."""

from html import unescape
import json
import re
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from app.components import patient_language as copy
from backend import services
from backend.db import configure_db, init_db
from ml.tabular.adl import ADL_ITEMS, ADL_SCALE
from ml.vision.tasks import TASKS


@pytest.fixture
def patient_visit(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'patient-language.sqlite'}", allow_sqlite=True)
    init_db()

    def make(language):
        patient = services.register_patient("Language Patient", "language@example.test", "test-password-123", language=language, consent=True)
        return patient, services.create_assessment(patient["id"])

    return make


def run_page(patient, visit, source):
    # AppTest creates a fresh component registry for each runtime. Production
    # retains one registry; clear only test-local component factories here.
    from app.components.live_plot import _library_loader, _live_host
    _library_loader.cache_clear()
    _live_host.cache_clear()
    app = AppTest.from_string(source, default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    return app.run()


def ui_text(app):
    return unescape("\n".join(item.value for category in (app.markdown, app.caption, app.info, app.warning, app.success) for item in category))


@pytest.mark.parametrize("language", copy.SUPPORTED_LANGUAGES)
def test_every_task_has_specific_local_instructions_and_preserves_recording_limits(language):
    assert set(copy.TASK_STEPS) == set(TASKS)
    for task, spec in TASKS.items():
        instructions = copy.task_steps(task, language)
        assert len(instructions) == 3 and all(step.strip() for step in instructions)
        assert str(spec["min_seconds"]) in instructions[-1] and "45" in instructions[-1]
        assert copy.task_label(task, language).strip()
    assert set(copy.VOICE_PROMPTS) == {"vowel", "sentence", "natural"}
    assert set(copy.ADL_LABELS) == set(ADL_ITEMS)
    assert set(copy.ADL_CHOICES) == set(ADL_SCALE)
    for row in (copy.COPY, copy.TASK_LABELS, copy.ADL_LABELS, copy.ADL_CHOICES, copy.VOICE_PROMPTS):
        assert all(len(values) == 3 and all(value.strip() for value in values) for values in row.values())
    if language == "English":
        assert {value: copy.adl_choice(value, language) for value in ADL_SCALE} == ADL_SCALE


@pytest.mark.parametrize("language", copy.SUPPORTED_LANGUAGES)
def test_translated_adl_controls_save_numeric_answers_under_original_ids(patient_visit, language):
    patient, visit = patient_visit(language)
    app = run_page(patient, visit, "from app.views import adl_page\nadl_page()")
    assert not app.exception
    assert app.title[0].value == copy.text("adl_title", language)
    assert [control.label for control in app.selectbox] == [copy.adl_label(item, language) for item in ADL_ITEMS]
    assert all(control.value is None for control in app.selectbox)
    for index, control in enumerate(app.selectbox):
        control.set_value(index % 5)
    next(button for button in app.button if button.label == copy.text("save_adl", language)).click().run()
    assert not app.exception
    saved = services.get_assessment(patient["id"], visit["id"])["modules"]["adl"]
    assert saved["responses"] == {key: index % 5 for index, key in enumerate(ADL_ITEMS)}
    assert saved["scale"] == ADL_SCALE or saved["scale"] == {str(key): value for key, value in ADL_SCALE.items()}
    assert copy.text("adl_saved", language) in ui_text(app)
    assert saved["provenance"]["instrument"] == "custom_unvalidated_0_to_4_questionnaire"


@pytest.mark.parametrize("language", copy.SUPPORTED_LANGUAGES)
def test_movement_instructions_follow_profile_but_task_and_source_values_are_stable(patient_visit, language):
    patient, visit = patient_visit(language)
    app = run_page(patient, visit, "from app.views import movement_page\nmovement_page(['finger_left', 'finger_right'])")
    assert not app.exception
    task = next(control for control in app.selectbox if control.label == copy.text("movement_task", language))
    assert task.value == "finger_left"
    task.set_value("finger_right").run()
    assert not app.exception
    assert app.title[0].value == copy.task_label("finger_right", language)
    assert all(step in ui_text(app) for step in copy.task_steps("finger_right", language))
    source = next(control for control in app.radio if control.label == copy.text("recording_source", language))
    assert source.value == "Upload Recorded Video"
    assert copy.text("mobile_recording", language) in ui_text(app)
    assert not services.get_assessment(patient["id"], visit["id"])["modules"]


@pytest.mark.parametrize("language", copy.SUPPORTED_LANGUAGES)
def test_voice_prompt_uses_selected_speech_language_independently_of_ui_language(patient_visit, language):
    patient, visit = patient_visit(language)
    app = run_page(patient, visit, "from app.views import voice_page\nvoice_page()")
    assert not app.exception
    task = next(control for control in app.selectbox if control.label == copy.text("voice_task", language))
    task.set_value("sentence").run()
    assert not app.exception
    assert copy.voice_prompt("sentence", language) in ui_text(app)
    speech = next(control for control in app.selectbox if control.label == copy.text("speech_language", language))
    speech.set_value("English" if language != "English" else "Urdu").run()
    selected = "English" if language != "English" else "Urdu"
    assert not app.exception
    assert copy.voice_prompt("sentence", selected) in ui_text(app)
    assert app.title[0].value == copy.text("voice_title", language)
    assert copy.text("audio_stop", language) in ui_text(app)


def test_profile_language_change_is_persisted_and_applies_on_rerun(patient_visit):
    patient, visit = patient_visit("English")
    app = run_page(patient, visit, "from app.views import profile_page\nprofile_page()")
    next(control for control in app.selectbox if control.label == "Preferred language").set_value("Urdu")
    next(button for button in app.button if button.label == "Save profile").click().run()
    assert not app.exception
    assert services.get_user(patient["id"])["language"] == "Urdu"
    assert app.title[0].value == copy.text("profile", "Urdu")
    assert any(button.label == copy.text("save_profile", "Urdu") for button in app.button)
    assert 'lang="ur"' in ui_text(app)


def test_unsupported_language_retains_preference_with_explicit_english_ui_fallback(patient_visit):
    patient, visit = patient_visit("Pashto")
    app = run_page(patient, visit, "from app.views import movement_page\nmovement_page(['gait'])")
    assert not app.exception
    assert app.title[0].value == "Walking / gait"
    assert "Patient instructions are shown in English" in ui_text(app)
    assert services.get_user(patient["id"])["language"] == "Pashto"


def test_native_urdu_prose_is_rtl_and_escapes_dynamic_content():
    rendered = copy.prose_html('<script>alert("private")</script>', "Urdu")
    assert 'lang="ur" dir="rtl"' in rendered
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert 'dir="ltr"' in copy.prose_html("Roman Urdu prose", "Roman Urdu")
    numbered = copy.prose_html(["<img src=x>", "second"], "Urdu", ordered=True)
    assert "<ol>" in numbered and "<li>" in numbered and "&lt;img src=x&gt;" in numbered


def test_mobile_styles_include_touch_targets_wrapping_and_single_column_layout():
    from app.components.design import _STYLES
    assert "min-height: 48px" in _STYLES
    assert "white-space: normal" in _STYLES and "text-overflow: clip" in _STYLES
    assert "@media (max-width: 720px)" in _STYLES
    assert "flex: 1 1 100% !important" in _STYLES
    assert "direction: ltr" in _STYLES and '.ps-patient-copy[lang="ur"]' in _STYLES
    assert "@import" not in _STYLES and "fonts.googleapis.com" not in _STYLES


@pytest.mark.parametrize("language", copy.SUPPORTED_LANGUAGES)
def test_mobile_camera_preferences_and_device_messages_reach_webrtc_without_accessing_camera(patient_visit, monkeypatch, language):
    import streamlit_webrtc
    calls = []

    def camera(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(video_processor=None, state=SimpleNamespace(playing=False))

    monkeypatch.setattr(streamlit_webrtc, "webrtc_streamer", camera)
    patient, visit = patient_visit(language)
    app = run_page(patient, visit, "from app.views import movement_page\nmovement_page(['gait'])")
    next(control for control in app.radio if control.label == copy.text("recording_source", language)).set_value("Live Camera").run()
    assert not app.exception
    lens = next(control for control in app.selectbox if control.label == copy.text("camera_lens", language))
    lens.set_value("rear").run()
    assert not app.exception
    assert calls[-1]["media_stream_constraints"]["audio"] is False
    video = calls[-1]["media_stream_constraints"]["video"]
    assert video["facingMode"] == {"ideal": "environment"}
    assert video["frameRate"]["max"] == 30
    assert calls[-1]["video_html_attrs"]["playsInline"] is True
    assert calls[-1]["translations"] == copy.camera_translations(language)
    assert copy.text("mobile_live", language) in ui_text(app)


def test_all_fault_codes_have_native_urdu_without_changing_source_or_classification():
    from ml.common.guidance import _catalogue, build_guidance
    from ml.common.guidance_urdu import urdu_catalogue
    catalogue = _catalogue("finger_right")
    assert set(urdu_catalogue(minimum=5, side="Right")) == set(catalogue)
    for code, original in catalogue.items():
        translated = original["urdu"]
        assert len(translated["steps"]) == 3
        assert all(re.search(r"[\u0600-\u06ff]", line) for line in [translated["title"], translated["reason"], *translated["steps"]])
        if original["kind"] == "follow_up":
            continue
        result = {"status": "repeat", "quality": {"accepted": False, "issue_codes": [code]}}
        native = build_guidance(result, "finger_right", language="Urdu")
        english = build_guidance(result, "finger_right", language="English")
        assert len(native) == len(english) == 1
        assert native[0]["code"] == english[0]["code"] == code
        assert native[0]["kind"] == english[0]["kind"]
        assert native[0]["source"] == english[0]["source"]
        assert native[0]["translation_note"] is None and native[0]["language"] == "urdu"
        assert native[0]["steps"] == translated["steps"]
    assert "5 سیکنڈ" in catalogue["duration_short"]["urdu"]["steps"][0]
    assert "دائیں" in catalogue["hand_view"]["urdu"]["steps"][0]
    assert "بائیں" in _catalogue("finger_left")["hand_view"]["urdu"]["steps"][0]
    assert "2 سیکنڈ" in _catalogue("vowel")["duration_short"]["urdu"]["steps"][0]


def test_urdu_followups_still_require_explicit_self_report_and_faults_never_echo_private_text():
    from ml.common.guidance import build_guidance
    from ml.nlp.functional import analyze_text
    reported = build_guidance(analyze_text("I fell today. My feet freeze when turning."), "nlp", language="Urdu")
    assert [entry["code"] for entry in reported] == ["self_reported_falls", "self_reported_freezing"]
    assert all(entry["language"] == "urdu" and entry["kind"] == "follow_up" for entry in reported)
    assert build_guidance(analyze_text("I have no falls or freezing."), "nlp", language="Urdu") == []
    private = "Traceback /private/patient-name.mp4 <script> https://evil.test I fall often"
    guidance = build_guidance(task="gait", error=private, language="Urdu")
    assert [entry["code"] for entry in guidance] == ["analysis_retry"]
    serialized = json.dumps(guidance, ensure_ascii=False)
    assert "patient-name.mp4" not in serialized and "evil.test" not in serialized and "<script>" not in serialized


def test_native_urdu_unanswered_adl_has_rtl_numbered_steps_and_does_not_save(patient_visit):
    patient, visit = patient_visit("Urdu")
    app = run_page(patient, visit, "from app.views import adl_page\nadl_page()")
    next(button for button in app.button if button.label == copy.text("save_adl", "Urdu")).click().run()
    assert not app.exception
    assert any(heading.value == "اگلا قدم" for heading in app.subheader)
    rendered = ui_text(app)
    assert '<ol>' in rendered and 'dir="rtl"' in rendered and "روزمرہ کے تمام جواب دیں" in rendered
    assert "Urdu translation is not available" not in rendered
    assert services.get_assessment(patient["id"], visit["id"])["modules"] == {}
