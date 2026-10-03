"""Automatic reports, provenance, fault exclusion, and private printable output."""
from __future__ import annotations

from datetime import timedelta
import json
import os

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url

from backend import services as svc
from backend.db import get_engine, transaction
from backend.db.models import Base, Consent, ModelOutput, ModelRun, ModuleResult, Report, utc_now
from backend.services.reporting import get_patient_report
from ml.inference.patient_report import AUTO_SUMMARY, build_patient_report, render_patient_report_html
from ml.nlp import analyze_text
from ml.tabular import ADL_ITEMS, analyze_adl

PASSWORD = "A testing passphrase only for this fixture"


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    test_url = os.getenv("PARKINSENSE_TEST_DATABASE_URL")
    if test_url:
        if not (make_url(test_url).database or "").startswith("parkinsense_test_"):
            raise ValueError("Report integration tests require a dedicated parkinsense_test_* database.")
        svc.configure_db(test_url)
        Base.metadata.drop_all(get_engine())
    else:
        svc.configure_db(f"sqlite:///{tmp_path / 'reports.sqlite'}", allow_sqlite=True)
    svc.init_db()
    admin = svc.bootstrap_admin("Administrator", "admin@example.test", PASSWORD)
    patient = svc.register_patient("Patient One", "patient@example.test", PASSWORD, "English", True)
    other = svc.register_patient("Patient Two", "other@example.test", PASSWORD, "English", True)
    clinician = svc.create_staff(admin["id"], "Dr Human Author", "clinician@example.test", PASSWORD)
    return admin, patient, other, clinician


def _result(value=12, method="measurement-v1", task="gait"):
    return {"status": "accepted", "task": task, "method": method, "quality": {"accepted": True, "messages": ["Recording passed local quality checks."]},
            "features": {"duration_seconds": value}, "feature_metadata": {"duration_seconds": {"label": "Recording duration", "unit": "seconds"}},
            "limitations": ["Measured proxy; recording setup affects comparison."]}


def _reports_count():
    with transaction() as session:
        return session.scalar(select(func.count(Report.id)))


def test_every_accepted_modality_auto_updates_one_report_with_real_details(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    modules = {
        "gait": _result(),
        "voice_vowel": _result(4, "acoustic-features-1.0", "audio_vowel") | {"language": "english"},
        "nlp": analyze_text("Walking is difficult in the morning."),
        "adl": analyze_adl({name: 2 for name in ADL_ITEMS} | {"other_difficulty": "Buttons take longer."}),
    }
    report_id = None
    for task, result in modules.items():
        saved = svc.save_module(patient["id"], assessment["id"], task, result)
        row = get_patient_report(patient["id"], assessment["id"])
        assert row is not None and row["outdated"] is False
        assert len(saved["reports"]) == 1
        report_id = report_id or row["id"]
        assert row["id"] == report_id
    content = row["content"]
    assert _reports_count() == 1
    assert content["source_module_revisions"] == dict.fromkeys(modules, 1)
    assert content["fusion"]["missing_modalities"] == []
    assert content["accepted"] is True
    assert content["generated_at_local"].endswith("PKT")
    sections = {section["task"]: section for section in content["sections"]}
    assert sections["gait"]["measurements"][0]["value"] == 12
    assert sections["gait"]["measurements"][0]["unit"] == "seconds"
    assert sections["voice_vowel"]["measurements"][0]["unit"] == "seconds"
    assert len(sections["adl"]["responses"]) == 9
    assert sections["adl"]["patient_note"] == "Buttons take longer."
    assert sections["nlp"]["reported_entities"][0]["activity"] == "walking"
    assert content["safety"]["unsupported_clinical_scores"] is False
    assert "landmark_frames" not in json.dumps(content)


def test_reads_and_explicit_refresh_are_idempotent_and_manual_history_survives(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    manual = svc.save_report(patient["id"], assessment["id"], {"patient_summary": "Original human-requested report", "auto_summary": AUTO_SUMMARY})
    assert "auto_summary" not in manual["content"]
    svc.save_module(patient["id"], assessment["id"], "gait", _result())
    first = get_patient_report(patient["id"], assessment["id"])
    for refresh in [False, False, True, True]:
        assert get_patient_report(patient["id"], assessment["id"], refresh=refresh)["content"] == first["content"]
    changed = svc.save_module(patient["id"], assessment["id"], "gait", _result(15))
    auto = get_patient_report(patient["id"], assessment["id"])
    assert auto["id"] == first["id"]
    assert auto["content"]["source_module_revisions"] == {"gait": 2}
    assert auto["content"]["sections"][0]["measurements"][0]["value"] == 15
    historical = next(row for row in changed["reports"] if row["id"] == manual["id"])
    assert historical["content"] == manual["content"]
    assert historical["outdated"] is True
    assert _reports_count() == 2


def test_rejected_attempt_has_guidance_and_never_reuses_old_measurements(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    rejected = {"status": "repeat", "quality": {"accepted": False, "messages": ["Recording is silent or too quiet. Move closer and record again."]},
                "features": {"duration_seconds": 999}, "method": "acoustic-features-1.0"}
    svc.save_module(patient["id"], assessment["id"], "voice_vowel", rejected)
    assert get_patient_report(patient["id"], assessment["id"]) is None
    svc.save_module(patient["id"], assessment["id"], "voice_vowel", _result(5, "acoustic-features-1.0", "audio_vowel"))
    first = get_patient_report(patient["id"], assessment["id"])
    svc.save_module(patient["id"], assessment["id"], "voice_vowel", rejected)
    current = get_patient_report(patient["id"], assessment["id"])
    assert current["id"] == first["id"] and current["outdated"] is False
    section = current["content"]["sections"][0]
    assert section["accepted"] is False and section["measurements"] == []
    assert section["guidance"] and all(item["steps"] for item in section["guidance"])
    assert current["content"]["fusion"]["available_modalities"] == []


@pytest.mark.parametrize("statement_prefix,existing", [("INSERT INTO reports", False), ("UPDATE reports", True)])
def test_report_failure_rolls_back_module_result_model_output_and_revision(accounts, statement_prefix, existing):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    if existing:
        svc.save_module(patient["id"], assessment["id"], "gait", _result(10))
    def reject_report(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith(statement_prefix):
            raise RuntimeError("Simulated report persistence failure")
    engine = get_engine()
    event.listen(engine, "before_cursor_execute", reject_report)
    try:
        with pytest.raises(RuntimeError, match="report persistence"):
            svc.save_module(patient["id"], assessment["id"], "gait", _result(20))
    finally:
        event.remove(engine, "before_cursor_execute", reject_report)
    current = svc.get_assessment(patient["id"], assessment["id"])
    assert current["module_revisions"] == ({"gait": 1} if existing else {})
    with transaction() as session:
        for model in [ModuleResult, ModelRun, ModelOutput, Report]:
            assert session.scalar(select(func.count(model.id))) == int(existing)
    if existing:
        assert current["modules"]["gait"]["features"]["duration_seconds"] == 10


def test_authorization_revocation_deactivation_and_consent_for_report_writes(accounts):
    admin, patient, other, clinician = accounts
    assessment = svc.create_assessment(patient["id"])
    svc.save_module(patient["id"], assessment["id"], "gait", _result())
    for person in [admin, other, clinician]:
        for refresh in [False, True]:
            with pytest.raises(PermissionError):
                get_patient_report(person["id"], assessment["id"], refresh=refresh)
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    assert get_patient_report(clinician["id"], assessment["id"])
    svc.unlink_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    with pytest.raises(PermissionError):
        get_patient_report(clinician["id"], assessment["id"])
    with transaction() as session:
        consent = session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"]))
        consent.withdrawn_at = utc_now()
    assert get_patient_report(patient["id"], assessment["id"])
    with pytest.raises(PermissionError, match="consent"):
        get_patient_report(patient["id"], assessment["id"], refresh=True)
    svc.set_user_active(admin["id"], patient["id"], False)
    with pytest.raises(PermissionError):
        get_patient_report(patient["id"], assessment["id"])


def test_actual_human_review_and_completion_refresh_existing_report(accounts):
    admin, patient, _, clinician = accounts
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    assessment = svc.create_assessment(patient["id"])
    svc.save_module(patient["id"], assessment["id"], "gait", _result())
    first = get_patient_report(patient["id"], assessment["id"])
    note = "Actual clinician note <script>alert('private')</script>"
    svc.review_assessment(clinician["id"], assessment["id"], "follow_up", note)
    reviewed = get_patient_report(patient["id"], assessment["id"])
    review = reviewed["content"]["clinician_review"]
    assert reviewed["id"] == first["id"]
    assert review["author_name"] == "Dr Human Author" and review["source"] == "human_clinician" and review["note"] == note
    html = render_patient_report_html(reviewed["content"], patient_name="Patient <img src=x onerror=alert(1)>")
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    assert "Dr Human Author" in html
    svc.finish_assessment(patient["id"], assessment["id"])
    assert get_patient_report(patient["id"], assessment["id"])["content"]["assessment_status"] == "completed"
    svc.save_clinical_measurements(clinician["id"], assessment["id"], {"age_years": {"value": 61, "unit": "years"}})
    context = get_patient_report(patient["id"], assessment["id"])["content"]
    assert context["clinician_review"]["source"] == "not_reviewed"
    assert context["clinical_measurements"][0]["value"] == 61
    assert "Clinician-entered context" in render_patient_report_html(context)
    assert note not in json.dumps(svc.list_audit_logs(admin["id"], 500))


def test_reference_uses_first_compatible_prior_visit_skipping_changed_method(accounts):
    _, patient, *_ = accounts
    visits = []
    for value, method in [(99, "measurement-v1"), (10, "measurement-v2"), (12, "measurement-v2")]:
        visit = svc.create_assessment(patient["id"])
        svc.save_module(patient["id"], visit["id"], "gait", _result(value, method))
        visits.append(visit)
        svc.finish_assessment(patient["id"], visit["id"])
    section = get_patient_report(patient["id"], visits[-1]["id"])["content"]["sections"][0]
    assert section["reference"]["baseline_assessment_id"] == visits[1]["id"]
    assert section["measurements"][0]["reference"] == 10
    assert section["measurements"][0]["delta"] == 2
    assert section["measurements"][0]["percent_change"] == 20
    assert get_patient_report(patient["id"], visits[-1]["id"])["content"]["source_reference_revisions"] == {"gait": {"assessment_id": visits[1]["id"], "revision": 1}}


def test_explicit_refresh_updates_a_reference_that_was_reanalysed(accounts):
    _, patient, *_ = accounts
    earlier = svc.create_assessment(patient["id"])
    svc.save_module(patient["id"], earlier["id"], "gait", _result(10))
    current = svc.create_assessment(patient["id"])
    svc.save_module(patient["id"], current["id"], "gait", _result(12))
    first = get_patient_report(patient["id"], current["id"])
    assert first["outdated"] is False and first["outdated_reason"] is None
    svc.save_module(patient["id"], earlier["id"], "gait", _result(8))
    # A normal read retains the generated snapshot; explicit refresh recomputes.
    stale = get_patient_report(patient["id"], current["id"])
    assert stale["content"] == first["content"]
    assert stale["outdated"] is True
    assert stale["outdated_reason"] == "Earlier assessment data changed; refresh the reference comparisons."
    with transaction() as session:
        assert session.get(Report, first["id"]).content == first["content"]
    assert _reports_count() == 2
    refreshed = get_patient_report(patient["id"], current["id"], refresh=True)
    assert refreshed["id"] == first["id"]
    assert refreshed["outdated"] is False and refreshed["outdated_reason"] is None
    row = refreshed["content"]["sections"][0]["measurements"][0]
    assert row["reference"] == 8 and row["delta"] == 4
    assert refreshed["content"]["source_reference_revisions"]["gait"]["revision"] == 2
    svc.update_profile(patient["id"], language="Roman Urdu")
    language_changed = get_patient_report(patient["id"], current["id"])
    assert language_changed["outdated"] is True
    assert language_changed["outdated_reason"] == "The patient's preferred report language changed."
    assert language_changed["content"] == refreshed["content"]
    translated = get_patient_report(patient["id"], current["id"], refresh=True)
    assert translated["id"] == first["id"] and translated["outdated"] is False
    assert translated["content"]["language"] == "roman urdu"
    assert _reports_count() == 2


def test_pure_attempt_preview_ignores_injected_guidance_and_hides_private_decoder_text():
    now = utc_now()
    guidance = {"title": "<script>bad</script>", "reason": "Recording failed", "steps": ["Check the microphone.", "Try again."],
                "source": {"title": "Unsafe source", "url": "javascript:alert(1)"}}
    result = {"status": "unavailable", "quality": {"accepted": False, "issue_codes": ["audio_format"],
                                                   "messages": ["Cannot decode WAV recording: /private/patient/record.wav"]},
              "features": {"duration_seconds": 123}, "guidance": [guidance]}
    assessment = {"id": "attempt", "created_at": now.isoformat(), "status": "draft", "report_type": "attempt_preview", "modules": {"voice_vowel": result}}
    content = build_patient_report(assessment)
    assert content["accepted"] is False and content["sections"][0]["measurements"] == []
    assert content["sections"][0]["guidance"] != [guidance]
    assert content["sections"][0]["guidance"][0]["code"] == "audio_format"
    html = render_patient_report_html(content)
    assert "Recording quality report" in html and "real WAV file" in html
    assert "Unsaved analysis attempt preview" in html
    assert "<script>" not in html and "javascript:" not in html and "Unsafe source" not in html
    assert "/private/patient" not in html
    assert 'src="http' not in html and "<script " not in html
    assert "123" not in html


def test_missing_reference_zero_and_future_visit_are_not_invented():
    now = utc_now()
    assessment = {"id": "current", "created_at": now.isoformat(), "modules": {"gait": _result(0)}}
    history = [{"id": "future", "created_at": (now + timedelta(days=1)).isoformat(), "modules": {"gait": _result(8)}}]
    content = build_patient_report(assessment, history)
    measurement = content["sections"][0]["measurements"][0]
    assert measurement["value"] == 0 and measurement["reference"] is None and measurement["delta"] is None
    assert set(content["fusion"]["missing_modalities"]) == {"text", "audio", "adl"}
    assert content["fusion"]["model_outputs"] == {}
    bad = _result() | {"quality": {"accepted": False, "decision": "ACCEPT"}}
    section = build_patient_report({"modules": {"gait": bad}})["sections"][0]
    assert section["accepted"] is False and section["measurements"] == []
