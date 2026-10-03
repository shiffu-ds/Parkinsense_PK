"""Real UI fault paths against isolated storage; no patient data or camera use."""

from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, init_db
from backend.services.reporting import get_patient_report
from ml.tabular.adl import ADL_ITEMS


@pytest.fixture
def patient_visit(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'feedback.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Feedback Patient", "feedback@example.test", "test-password-123", consent=True)
    visit = services.create_assessment(patient["id"])
    return patient, visit


@pytest.fixture
def rendered_reports(monkeypatch):
    from ml.inference import patient_report
    renderer = patient_report.render_patient_report_html
    captured = []

    def capture(report, **kwargs):
        html = renderer(report, **kwargs)
        captured.append({"report": deepcopy(report), "html": html})
        return html

    monkeypatch.setattr(patient_report, "render_patient_report_html", capture)
    return captured


def adl_app(patient, visit):
    app = AppTest.from_string("from app.views import adl_page\nadl_page()", default_timeout=25)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    return app.run()


def save_adl(app):
    next(button for button in app.button if button.label == "Save daily activities").click().run()


def download_labels(app):
    assert not app.get("download_button")  # Private bytes never use public Streamlit media URLs.
    return [item.label for item in app.button if item.label.startswith("Download")]


def test_accepted_adl_creates_persisted_report_and_printable_download(patient_visit, rendered_reports):
    patient, visit = patient_visit
    app = adl_app(patient, visit)
    for item in app.selectbox:
        item.set_value(1)
    app.text_area[0].set_value("A personal note <script>alert('private')</script>")
    save_adl(app)
    assert not app.exception
    persisted = services.get_assessment(patient["id"], visit["id"])
    report = get_patient_report(patient["id"], visit["id"])
    assert persisted["modules"]["adl"]["quality"]["accepted"] is True
    assert report["content"]["accepted"] is True and report["outdated"] is False
    assert report["content"]["source_module_revisions"] == {"adl": 1}
    assert report["content"]["sections"][0]["responses"] == [
        {"name": name, "label": label, "value": 1, "description": "Slight difficulty"}
        for name, label in ADL_ITEMS.items()
    ]
    assert "Download patient report" in download_labels(app)
    assert "Download analysis report" not in download_labels(app)
    assert all(item["report"]["report_type"] == "patient_analysis" for item in rendered_reports)
    saved = next(item for item in reversed(rendered_reports) if item["report"]["report_type"] == "patient_analysis")
    assert "<script>" not in saved["html"] and "&lt;script&gt;" in saved["html"]
    # A fresh session can read the persisted report without re-running analysis.
    fresh = adl_app(patient, visit)
    assert not fresh.exception
    assert "Download patient report" in download_labels(fresh)
    assert get_patient_report(patient["id"], visit["id"])["id"] == report["id"]


def test_unanswered_adl_shows_numbered_steps_and_downloadable_fault_report(patient_visit, rendered_reports):
    patient, visit = patient_visit
    app = adl_app(patient, visit)
    assert all(item.value is None for item in app.selectbox)
    save_adl(app)
    assert not app.exception
    assert app.warning
    text = "\n".join(item.value for item in app.markdown)
    assert "Complete the daily activities answers" in text
    assert all(f"{number}. " in text for number in (1, 2, 3))
    assert "Download analysis report" in download_labels(app)
    assert "Download patient report" not in download_labels(app)
    persisted = services.get_assessment(patient["id"], visit["id"])
    assert persisted["modules"] == {} and persisted["reports"] == []
    attempt = rendered_reports[-1]
    assert attempt["report"]["report_type"] == "attempt_preview"
    assert attempt["report"]["accepted"] is False
    section = attempt["report"]["sections"][0]
    assert section["measurements"] == [] and section["responses"] == []
    assert section["guidance"][0]["code"] == "adl_complete"
    assert "<ol>" in attempt["html"] and "Recording quality report" in attempt["html"]


def test_failed_adl_reanalysis_replaces_latest_preview_but_preserves_saved_evidence(patient_visit, rendered_reports):
    patient, visit = patient_visit
    app = adl_app(patient, visit)
    for item in app.selectbox:
        item.set_value(2)
    save_adl(app)
    assert not app.exception
    saved_report = get_patient_report(patient["id"], visit["id"])
    saved_result = deepcopy(services.get_assessment(patient["id"], visit["id"])["modules"]["adl"])
    # Changing one answer to unanswered creates a failed new attempt. It must
    # not be shown as the previous accepted result or silently overwrite it.
    next(item for item in app.selectbox if item.label == "Dressing").set_value(None)
    save_adl(app)
    assert not app.exception
    latest = app.session_state[f"attempt_{visit['id']}_adl"]["result"]
    assert latest["quality"]["accepted"] is False and latest["features"] == {}
    assert latest["quality"]["issue_codes"] == ["adl_complete"]
    assert "Complete the daily activities answers" in "\n".join(item.value for item in app.markdown)
    persisted = services.get_assessment(patient["id"], visit["id"])
    assert persisted["modules"]["adl"] == saved_result
    current_report = get_patient_report(patient["id"], visit["id"])
    assert current_report["id"] == saved_report["id"] and current_report["content"] == saved_report["content"]
    latest_preview = next(item for item in reversed(rendered_reports) if item["report"]["report_type"] == "attempt_preview")
    assert latest_preview["report"]["accepted"] is False
    assert latest_preview["report"]["sections"][0]["measurements"] == []
    assert {"Download analysis report", "Download patient report"} <= set(download_labels(app))


def test_movement_handler_clears_stale_accepted_preview_on_failed_reanalysis(patient_visit, rendered_reports, monkeypatch):
    patient, visit = patient_visit
    from ml.vision import pipeline
    accepted = {"status": "completed", "task": "gait", "quality": {"accepted": True, "decision": "ACCEPT"},
                "features": {"observed_duration_s": 6.0}, "analysis_version": "handler-test-only"}
    outcome = {"fail": False}

    def analyze(*args, **kwargs):
        if outcome["fail"]:
            raise pipeline.CVError("Landmark model is missing (private-model.task). Private path: /data/private/secret.mp4")
        return deepcopy(accepted)

    monkeypatch.setattr(pipeline, "analyze_video", analyze)
    # File uploader interaction is not supported by AppTest. Drive the same
    # production handler using a button, then render the actual movement page.
    source = """
import streamlit as st
from app.views import active_assessment, _analyze_media, movement_page
item = active_assessment()
if st.button('Analyze test-only clip'):
    _analyze_media(item, 'gait', 'test-only.mp4', b'fixture video data')
movement_page(['gait'])
"""
    app = AppTest.from_string(source, default_timeout=25)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    next(item for item in app.button if item.label == "Analyze test-only clip").click().run()
    assert not app.exception
    assert app.session_state[f"draft_{visit['id']}_gait"]["result"]["status"] == "completed"
    assert not next(item for item in app.button if item.label == "Save result").disabled
    outcome["fail"] = True
    next(item for item in app.button if item.label == "Analyze test-only clip").click().run()
    assert not app.exception
    result = app.session_state[f"draft_{visit['id']}_gait"]["result"]
    assert result["quality"]["accepted"] is False and result["features"] == {}
    assert result["quality"]["issue_codes"] == ["model_unavailable"]
    assert next(item for item in app.button if item.label == "Save result").disabled
    rendered = "\n".join(item.value for item in app.markdown)
    assert "private-model.task" not in rendered and "secret.mp4" not in rendered
    assert services.get_assessment(patient["id"], visit["id"])["modules"] == {}
    assert "Download analysis report" in download_labels(app)
    assert rendered_reports[-1]["report"]["accepted"] is False
    assert "secret.mp4" not in rendered_reports[-1]["html"]
