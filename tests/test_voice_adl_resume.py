"""Visit resume and real local audio processing using synthetic test signals.

All accounts, visits and media here are temporary fixtures. A generated tone
exercises the audio pipeline; it is not a patient voice or clinical validation.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, init_db
from backend.services.reporting import get_patient_report
from ml.common.results import numeric_features
from ml.nlp import analyze_text
from ml.tabular.adl import ADL_ITEMS, analyze_adl


@pytest.fixture
def patient_visits(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'resume.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Resume Test", "resume@example.test", "test-resume-password-123", consent=True)
    return patient, services.create_assessment(patient["id"]), services.create_assessment(patient["id"])


def visit_page(name, patient, visit):
    app = AppTest.from_string(f"from app.views import {name}\n{name}()", default_timeout=25)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    return app.run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_saved_adl_answers_and_note_resume_without_resaving(patient_visits):
    patient, visit, _ = patient_visits
    answers = {name: index % 5 for index, name in enumerate(ADL_ITEMS)}
    note = "Subah buttons mein mushkil hoti hai."
    services.save_module(patient["id"], visit["id"], "adl", analyze_adl({**answers, "other_difficulty": note}))
    report = get_patient_report(patient["id"], visit["id"])
    app = visit_page("adl_page", patient, visit)
    assert not app.exception
    assert {name: app.selectbox(key=f"adl_answer_{visit['id']}_{name}").value for name in ADL_ITEMS} == answers
    assert app.text_area(key=f"adl_note_{visit['id']}").value == note
    assert get_patient_report(patient["id"], visit["id"])["id"] == report["id"]
    # An incomplete submission must preserve the edited form, including a
    # cleared answer, instead of filling it back in from the saved module.
    # AppTest's Selectbox omits the protobuf value for None, which does not
    # transmit a clear event. Set the equivalent cleared session value here.
    app.session_state[f"adl_answer_{visit['id']}_dressing"] = None
    app.text_area(key=f"adl_note_{visit['id']}").set_value("Unsaved edited note")
    next(item for item in app.button if item.label == "Save daily activities").click().run()
    assert not app.exception
    assert app.selectbox(key=f"adl_answer_{visit['id']}_dressing").value is None
    assert app.text_area(key=f"adl_note_{visit['id']}").value == "Unsaved edited note"
    assert services.get_assessment(patient["id"], visit["id"])["modules"]["adl"]["responses"] == answers


@pytest.mark.parametrize("page,field", [("adl_page", "adl_note"), ("voice_page", "transcript")])
def test_unsaved_patient_prose_is_not_copied_into_a_different_visit(patient_visits, page, field):
    patient, first, second = patient_visits
    app = visit_page(page, patient, first)
    app.text_area(key=f"{field}_{first['id']}").set_value("This draft belongs to the first visit.").run()
    assert not app.exception
    app.session_state["active_assessment_id"] = second["id"]
    app.run()
    assert not app.exception
    assert app.text_area(key=f"{field}_{second['id']}").value == ""
    if page == "adl_page":
        assert all(item.value is None for item in app.selectbox)
    assert services.get_assessment(patient["id"], first["id"])["modules"] == {}
    assert services.get_assessment(patient["id"], second["id"])["modules"] == {}


def test_reviewed_description_resumes_exactly_and_failed_edit_preserves_saved_report(patient_visits):
    patient, visit, _ = patient_visits
    source = "آج چلنے میں مشکل ہوتی ہے۔ " + ("This is my reviewed personal context. " * 12)
    result = analyze_text(source, "Urdu")
    assert result["reviewed_text"] == source.strip()
    assert "reviewed_text" not in numeric_features(result)
    assert all(isinstance(value, (float, int)) for value in numeric_features(result).values())
    services.save_module(patient["id"], visit["id"], "nlp", result)
    report = get_patient_report(patient["id"], visit["id"])
    app = visit_page("voice_page", patient, visit)
    assert not app.exception
    assert app.text_area(key=f"transcript_{visit['id']}").value == source.strip()
    assert get_patient_report(patient["id"], visit["id"])["id"] == report["id"]
    app.text_area(key=f"transcript_{visit['id']}").set_value("")
    button(app, "Save daily-life description").click().run()
    assert not app.exception
    assert not app.session_state[f"attempt_{visit['id']}_nlp"]["result"]["quality"]["accepted"]
    assert services.get_assessment(patient["id"], visit["id"])["modules"]["nlp"] == result
    assert get_patient_report(patient["id"], visit["id"])["id"] == report["id"]
    with pytest.raises(ValueError):
        analyze_text("x" * 5001)


def test_all_three_voice_tasks_use_real_pipeline_and_failed_repeat_keeps_saved_audio(patient_visits, monkeypatch):
    patient, visit, _ = patient_visits
    rate = 16000
    time = np.arange(rate * 4) / rate
    samples = 0.2 * np.sin(2 * np.pi * 180 * time)

    def wav_data(signal):
        stream = io.BytesIO()
        sf.write(stream, signal, rate, format="WAV")
        return stream.getvalue()

    supplied = {"data": wav_data(samples)}
    # AppTest cannot operate a microphone. Feed the actual UI capture branch
    # bounded fixture WAV bytes and retain its real analysis/persistence flow.
    monkeypatch.setattr("streamlit.audio_input", lambda *args, **kwargs: io.BytesIO(supplied["data"]))
    app = visit_page("voice_page", patient, visit)
    for task in ("vowel", "sentence", "natural"):
        next(item for item in app.selectbox if item.label == "Voice task").set_value(task).run()
        button(app, "Analyze and save voice recording").click().run()
        assert not app.exception
        saved = services.get_assessment(patient["id"], visit["id"])["modules"][f"voice_{task}"]
        assert saved["quality"]["accepted"]
        assert saved["task"] == f"audio_{task}"
        assert saved["quality"]["task_completion"] == "requires_human_confirmation"
        assert saved["features"]["f0_autocorrelation_median_hz"] == pytest.approx(180, abs=10)
        assert saved["asr"]["status"] == "unavailable" and saved["transcript"] is None
    before = services.get_assessment(patient["id"], visit["id"])
    report = get_patient_report(patient["id"], visit["id"])
    assert set(before["modules"]) == {"voice_vowel", "voice_sentence", "voice_natural"}
    assert set(report["content"]["source_module_revisions"]) == set(before["modules"])
    supplied["data"] = wav_data(np.zeros(rate * 4))
    button(app, "Analyze and save voice recording").click().run()
    assert not app.exception
    latest = app.session_state[f"attempt_{visit['id']}_voice_natural"]["result"]
    assert latest["status"] == "repeat" and not latest["quality"]["accepted"] and not latest["features"]
    after = services.get_assessment(patient["id"], visit["id"])
    assert after["modules"] == before["modules"]
    assert after["module_file_ids"] == before["module_file_ids"]
    assert get_patient_report(patient["id"], visit["id"])["id"] == report["id"]
