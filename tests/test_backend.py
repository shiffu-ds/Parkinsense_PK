"""Persistence and permission checks use an explicit temporary SQLite database."""

import json
import os
from pathlib import Path
import stat

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url

from backend import services as svc
from backend.db import get_engine, transaction
from backend.db.models import Base, Consent, ModelOutput, ModelRun, ModuleResult, User, utc_now
from backend.security import verify_password


PASSWORD = "A carefully chosen passphrase 2026"


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("PARKINSENSE_MAX_UPLOAD_MB", "1")
    monkeypatch.delenv("PARKINSENSE_ALLOW_SQLITE", raising=False)
    test_url = os.getenv("PARKINSENSE_TEST_DATABASE_URL")
    if test_url:
        if not (make_url(test_url).database or "").startswith("parkinsense_test_"):
            raise ValueError("Integration tests require a dedicated parkinsense_test_* database.")
        svc.configure_db(test_url)
        Base.metadata.drop_all(get_engine())
    else:
        svc.configure_db(f"sqlite:///{tmp_path / 'database.sqlite3'}", allow_sqlite=True)
    svc.init_db()
    admin = svc.bootstrap_admin("Administrator", "admin@example.test", PASSWORD)
    patient = svc.register_patient("Patient One", "patient@example.test", PASSWORD, "Urdu", True)
    other = svc.register_patient("Patient Two", "other@example.test", PASSWORD, "Pashto", True)
    clinician = svc.create_staff(admin["id"], "Dr Clinician", "clinician@example.test", PASSWORD)
    return admin, patient, other, clinician


def test_registration_hash_consent_and_authentication(accounts):
    admin, patient, *_ = accounts
    assert svc.authenticate("  PATIENT@example.test ", PASSWORD)["id"] == patient["id"]
    assert "password" not in json.dumps(patient)
    with transaction() as session:
        user = session.get(User, patient["id"])
        assert PASSWORD != user.password_hash
        assert verify_password(PASSWORD, user.password_hash)
        consent = session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"]))
        assert consent.acknowledged
    with pytest.raises(ValueError, match="consent"):
        svc.register_patient("No Consent", "noconsent@example.test", PASSWORD)
    with pytest.raises(ValueError, match="already exists"):
        svc.register_patient("Duplicate", "PATIENT@example.test", PASSWORD, consent=True)
    for email, password in [("patient@example.test", "wrong"), ("unknown@example.test", PASSWORD)]:
        with pytest.raises(PermissionError):
            svc.authenticate(email, password)
    with pytest.raises(PermissionError):
        svc.bootstrap_admin("Second Admin", "second@example.test", PASSWORD)
    with pytest.raises(ValueError):
        svc.create_staff(admin["id"], "Research User", "research@example.test", PASSWORD, role="researcher")


def test_schema_contains_all_roadmap_tables(accounts):
    required = {"users", "patients", "clinicians", "patient_clinician_links", "consents", "assessments",
                "assessment_files", "clinical_measurements", "adl_responses", "model_runs", "model_outputs",
                "explanations", "reports", "audit_logs"}
    assert required.issubset(Base.metadata.tables)


def test_patient_clinician_and_admin_permissions(accounts):
    admin, patient, other, clinician = accounts
    assessment = svc.create_assessment(patient["id"])
    with pytest.raises(PermissionError):
        svc.get_assessment(other["id"], assessment["id"])
    with pytest.raises(PermissionError):
        svc.get_assessment(clinician["id"], assessment["id"])
    with pytest.raises(PermissionError):
        svc.get_assessment(admin["id"], assessment["id"])
    assert svc.list_patients(clinician["id"]) == []
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    assert svc.list_patients(clinician["id"])[0]["id"] == patient["patient_id"]
    assert svc.get_assessment(clinician["id"], assessment["id"])["id"] == assessment["id"]
    with pytest.raises(PermissionError):
        svc.create_assessment(clinician["id"], other["patient_id"])
    svc.unlink_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    with pytest.raises(PermissionError):
        svc.get_assessment(clinician["id"], assessment["id"])
    with pytest.raises(PermissionError):
        svc.list_users(patient["id"])
    with pytest.raises(PermissionError):
        svc.link_patient(patient["id"], patient["patient_id"], clinician["clinician_id"])


def test_secure_private_storage(accounts, tmp_path):
    admin, patient, other, _ = accounts
    assessment = svc.create_assessment(patient["id"])
    key = svc.store_upload(patient["id"], assessment["id"], "gait", "walk.MP4", b"media-test-bytes")
    assert patient["full_name"] not in key
    path = Path(svc.get_media_path(patient["id"], assessment["id"], key))
    assert path.read_bytes() == b"media-test-bytes"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with pytest.raises(PermissionError):
        svc.get_media_path(other["id"], assessment["id"], key)
    with pytest.raises(PermissionError):
        svc.get_media_path(admin["id"], assessment["id"], key)
    with pytest.raises(PermissionError):
        svc.get_media_path(patient["id"], assessment["id"], "../../etc/passwd")
    for filename, data in [("../escape.mp4", b"x"), ("virus.exe", b"x"), ("empty.wav", b""), ("large.mp4", b"x" * (1024 * 1024 + 1))]:
        with pytest.raises(ValueError):
            svc.store_upload(patient["id"], assessment["id"], "gait", filename, data)
    assert len(svc.get_assessment(patient["id"], assessment["id"])["files"]) == 1
    assert not list((tmp_path / "private").rglob("*.pending"))
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        svc.get_media_path(patient["id"], assessment["id"], key)


def test_module_persistence_resume_restart_and_baseline(accounts):
    _, patient, *_ = accounts
    first = svc.create_assessment(patient["id"])
    result = {"status": "accepted", "quality": {"accepted": True, "valid_fraction": .95}, "features": {"duration_s": 12.5}, "landmarks": [[1., 2., 3.]]}
    svc.save_module(patient["id"], first["id"], "gait", result)
    assert svc.get_assessment(patient["id"], first["id"])["modules"]["gait"] == result
    result["features"]["duration_s"] = 13.
    current = svc.save_module(patient["id"], first["id"], "gait", result)
    assert current["module_revisions"]["gait"] == 2
    finished = svc.finish_assessment(patient["id"], first["id"])
    assert finished["status"] == "completed"
    assert finished["completed_at"].endswith("+00:00")
    assert svc.list_patients(patient["id"])[0]["baseline_assessment_id"] == first["id"]
    with pytest.raises(ValueError, match="closed"):
        svc.save_module(patient["id"], first["id"], "gait", result)
    second = svc.restart_assessment(patient["id"], first["id"])
    third = svc.restart_assessment(patient["id"], second["id"])
    assert svc.get_assessment(patient["id"], first["id"])["status"] == "completed"
    assert svc.get_assessment(patient["id"], second["id"])["status"] == "abandoned"
    assert third["modules"] == {}
    assert [row["id"] for row in svc.get_timeline(patient["id"])] == [first["id"], second["id"], third["id"]]
    with transaction() as session:
        assert session.scalar(select(func.count(ModelRun.id))) == 2
        assert session.scalar(select(func.count(ModelOutput.id))) == 2


def test_rejected_results_cannot_create_baseline_and_bad_values_never_persist(accounts):
    _, patient, other, _ = accounts
    assessment = svc.create_assessment(patient["id"])
    with pytest.raises(ValueError):
        svc.finish_assessment(patient["id"], assessment["id"])
    svc.save_module(patient["id"], assessment["id"], "voice", {"status": "repeat", "features": {}})
    with pytest.raises(ValueError, match="accepted"):
        svc.finish_assessment(patient["id"], assessment["id"])
    svc.save_module(patient["id"], assessment["id"], "voice_vowel", {"status": "accepted", "quality": {"accepted": False}, "features": {"x": 1.}})
    with pytest.raises(ValueError, match="accepted"):
        svc.finish_assessment(patient["id"], assessment["id"])
    for result in [{"features": {"bad": float("nan")}}, {"features": {"bad": float("inf")}}, {"features": {"bad": object()}}]:
        with pytest.raises(ValueError):
            svc.save_module(patient["id"], assessment["id"], "gait", result)
    other_assessment = svc.create_assessment(other["id"])
    key = svc.store_upload(other["id"], other_assessment["id"], "gait", "walk.mp4", b"x")
    with pytest.raises(PermissionError):
        svc.save_module(patient["id"], assessment["id"], "gait", {"status": "accepted"}, media_path=key)
    assert "gait" not in svc.get_assessment(patient["id"], assessment["id"])["modules"]


def test_module_result_and_model_output_are_one_transaction(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    engine = get_engine()
    def reject_output(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO model_outputs"):
            raise RuntimeError("Simulated output persistence failure")
    event.listen(engine, "before_cursor_execute", reject_output)
    try:
        with pytest.raises(RuntimeError):
            svc.save_module(patient["id"], assessment["id"], "gait", {"status": "accepted"})
    finally:
        event.remove(engine, "before_cursor_execute", reject_output)
    assert svc.get_assessment(patient["id"], assessment["id"])["modules"] == {}
    with transaction() as session:
        assert session.scalar(select(func.count(ModuleResult.id))) == 0
        assert session.scalar(select(func.count(ModelRun.id))) == 0


def test_reports_review_profile_deactivation_and_sanitized_audits(accounts):
    admin, patient, other, clinician = accounts
    assessment = svc.create_assessment(patient["id"])
    report = {"patient_summary": "Movement measure saved.", "clinician_summary": "Review quality."}
    saved = svc.save_report(patient["id"], assessment["id"], report)
    assert svc.get_assessment(patient["id"], assessment["id"])["reports"][0]["id"] == saved["id"]
    with pytest.raises(PermissionError):
        svc.review_assessment(patient["id"], assessment["id"])
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    clinical = svc.save_clinical_measurements(clinician["id"], assessment["id"], {"age_years": {"value": 61, "unit": "years"}})
    assert clinical["clinical_measurements"][0]["value"] == 61
    with pytest.raises(PermissionError):
        svc.save_clinical_measurements(patient["id"], assessment["id"], {"age_years": 60})
    with pytest.raises(ValueError):
        svc.save_clinical_measurements(clinician["id"], assessment["id"], {"age_years": 200})
    reviewed = svc.review_assessment(clinician["id"], assessment["id"], note="Private clinician note")
    assert reviewed["review_status"] == "reviewed"
    assert reviewed["reviewed_by"] == clinician["id"]
    assert svc.update_profile(patient["id"], language="Pashto")["language"] == "Pashto"
    svc.record_tool_audit(patient["id"], "get_assessment", assessment["id"])
    logs = json.dumps(svc.list_audit_logs(admin["id"], 500))
    for private in [PASSWORD, patient["email"], "Private clinician note", report["patient_summary"], patient["full_name"]]:
        assert private not in logs
    svc.set_user_active(admin["id"], other["id"], False)
    with pytest.raises(PermissionError):
        svc.authenticate(other["email"], PASSWORD)
    with pytest.raises(PermissionError):
        svc.create_assessment(other["id"])
    with pytest.raises(ValueError):
        svc.set_user_active(admin["id"], admin["id"], False)


def test_sqlite_requires_explicit_development_choice(monkeypatch):
    monkeypatch.setenv("PARKINSENSE_ALLOW_SQLITE", "0")
    with pytest.raises(ValueError, match="SQLite"):
        svc.configure_db("sqlite:///:memory:")
    svc.configure_db("sqlite:///:memory:", allow_sqlite=True)
    svc.init_db()


def test_saved_module_references_its_source_recording_not_newest_upload(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    source = svc.store_upload(patient["id"], assessment["id"], "gait", "first.mp4", b"original recording")
    result = {"status": "completed", "quality": {"accepted": True}, "features": {"duration_s": 5}}
    saved = svc.save_module(patient["id"], assessment["id"], "gait", result, media_path=source)
    source_id = next(row["id"] for row in saved["files"] if row["storage_key"] == source)
    rejected_upload = svc.store_upload(patient["id"], assessment["id"], "gait", "replacement.mp4", b"poor replacement")
    current = svc.get_assessment(patient["id"], assessment["id"])
    assert current["files"][-1]["storage_key"] == rejected_upload
    assert current["module_file_ids"]["gait"] == source_id
    assert next(row["storage_key"] for row in current["files"] if row["id"] == current["module_file_ids"]["gait"]) == source


def test_review_invalidated_by_edits_and_closed_assessment_guards(accounts):
    admin, patient, _, clinician = accounts
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    assessment = svc.create_assessment(patient["id"])
    result = {"status": "accepted", "quality": {"accepted": True}, "features": {"duration_s": 5}}
    svc.save_module(patient["id"], assessment["id"], "gait", result)
    report = svc.save_report(patient["id"], assessment["id"], {"patient_summary": "Original summary", "source_module_revisions": {"gait": 99}})
    assert report["source_module_revisions"] == {"gait": 1}
    assert report["outdated"] is False
    svc.review_assessment(clinician["id"], assessment["id"], note="Reviewed initial result")
    changed = svc.save_module(patient["id"], assessment["id"], "gait", result | {"features": {"duration_s": 10}})
    assert changed["review_status"] == "pending"
    assert changed["reviewed_by"] is None and changed["reviewed_at"] is None and changed["review_note"] is None
    original = next(row for row in changed["reports"] if row["id"] == report["id"])
    assert original["outdated"] is True
    assert original["content"]["patient_summary"] == "Original summary"
    fresh = svc.save_report(patient["id"], assessment["id"], {"patient_summary": "Updated summary"})
    assert fresh["outdated"] is False and fresh["source_module_revisions"] == {"gait": 2}
    svc.review_assessment(clinician["id"], assessment["id"])
    changed = svc.save_clinical_measurements(clinician["id"], assessment["id"], {"age_years": 61})
    assert changed["review_status"] == "pending"
    svc.finish_assessment(patient["id"], assessment["id"])
    assert svc.review_assessment(clinician["id"], assessment["id"])["review_status"] == "reviewed"
    for action in [lambda: svc.ensure_assessment_writable(patient["id"], assessment["id"]),
                   lambda: svc.save_module(patient["id"], assessment["id"], "adl", result),
                   lambda: svc.store_upload(patient["id"], assessment["id"], "gait", "clip.mp4", b"x")]:
        with pytest.raises(ValueError, match="closed"):
            action()
    draft = svc.create_assessment(patient["id"])
    svc.restart_assessment(patient["id"], draft["id"])
    with pytest.raises(ValueError, match="Abandoned"):
        svc.review_assessment(clinician["id"], draft["id"])
    with pytest.raises(ValueError, match="abandoned"):
        svc.save_report(patient["id"], draft["id"], {"patient_summary": "Summary"})


def test_withdrawn_consent_prevents_further_collection_and_analysis(accounts):
    _, patient, *_ = accounts
    assessment = svc.create_assessment(patient["id"])
    with transaction() as session:
        consent = session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"]))
        consent.withdrawn_at = utc_now()
    for action in [lambda: svc.ensure_assessment_writable(patient["id"], assessment["id"]),
                   lambda: svc.create_assessment(patient["id"]),
                   lambda: svc.save_module(patient["id"], assessment["id"], "gait", {"status": "accepted"}),
                   lambda: svc.store_upload(patient["id"], assessment["id"], "gait", "clip.mp4", b"x")]:
        with pytest.raises(PermissionError, match="consent"):
            action()
    assert svc.get_assessment(patient["id"], assessment["id"])["modules"] == {}
