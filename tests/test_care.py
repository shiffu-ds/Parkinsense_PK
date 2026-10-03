"""Patient-written context and clinician follow-up stay private and separate."""

from datetime import date
import json
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from backend import services as svc
from backend.services import care
from backend.db import get_engine, transaction
from backend.db.models import (
    Assessment, Base, CarePlan, ClinicalMeasurement, Consent, DailyCheckin, ModuleResult,
    PersonalGoal, User, utc_now,
)

PASSWORD = "Care workflow test passphrase 2026"
RATINGS = {"energy": 2, "sleep_quality": 3, "movement_ease": 1, "mood": 4}


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    test_url = os.getenv("PARKINSENSE_TEST_DATABASE_URL")
    if test_url:
        if not (make_url(test_url).database or "").startswith("parkinsense_test_"):
            raise ValueError("Integration tests require a dedicated parkinsense_test_* database.")
        svc.configure_db(test_url)
        Base.metadata.drop_all(get_engine())
    else:
        svc.configure_db(f"sqlite:///{tmp_path / 'care.sqlite3'}", allow_sqlite=True)
    svc.init_db()
    monkeypatch.setattr(care, "_today", lambda: date(2026, 10, 3))
    admin = svc.bootstrap_admin("Administrator", "admin@example.test", PASSWORD)
    patient = svc.register_patient("Patient One", "patient@example.test", PASSWORD, consent=True)
    other = svc.register_patient("Patient Two", "other@example.test", PASSWORD, consent=True)
    clinician = svc.create_staff(admin["id"], "Dr Followup", "clinician@example.test", PASSWORD)
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return admin, patient, other, clinician


def test_daily_checkin_explicit_self_report_and_same_day_update(accounts):
    _, patient, _, clinician = accounts
    saved = care.save_checkin(patient["id"], RATINGS | {"note": "I want to walk to the garden."})
    assert saved["date"] == "2026-10-03"
    assert saved["responses"] == RATINGS | {"falls": None, "note": "I want to walk to the garden."}
    assert saved["source"] == "patient_self_report"
    assert saved["recorded_by_role"] == "patient"
    changed = care.save_checkin(clinician["id"], RATINGS | {"energy": 4, "falls": False},
                                patient["patient_id"])
    assert changed["id"] == saved["id"]
    assert changed["created_at"] == saved["created_at"]
    assert changed["responses"]["energy"] == 4
    assert changed["responses"]["falls"] is False
    assert changed["recorded_by_role"] == "clinician"
    assert changed["author_name"] == "Dr Followup"
    assert len(care.list_checkins(patient["id"])) == 1
    with transaction() as session:
        assert session.scalar(select(func.count(DailyCheckin.id))) == 1
        for model in (Assessment, ModuleResult, ClinicalMeasurement):
            assert session.scalar(select(func.count(model.id))) == 0


def test_records_persist_and_additive_init_keeps_existing_assessments(accounts):
    _, patient, _, clinician = accounts
    assessment = svc.create_assessment(patient["id"])
    checkin = care.save_checkin(patient["id"], RATINGS)
    goal = care.save_personal_goal(patient["id"], "Walk to the garden", "My own priority")
    plan = care.save_care_plan(clinician["id"], patient["patient_id"], "Review recording setup",
                               "Bring the walking recording for a conversation.", "2026-10-20", assessment["id"])
    database_url = get_engine().url.render_as_string(hide_password=False)
    svc.configure_db(database_url, allow_sqlite=True)
    svc.init_db()
    assert svc.get_assessment(patient["id"], assessment["id"])["id"] == assessment["id"]
    assert care.list_checkins(patient["id"])[0]["id"] == checkin["id"]
    assert care.list_goals(patient["id"])[0]["id"] == goal["id"]
    assert care.list_care_plans(patient["id"])[0]["id"] == plan["id"]
    assert care.list_care_plans(patient["id"])[0]["source"] == "clinician"
    assert plan["assessment_id"] == assessment["id"]


@pytest.mark.parametrize("value", [None, True, False, 1.5, "2", -1, 5])
def test_checkin_does_not_infer_missing_or_invalid_ratings(accounts, value):
    _, patient, *_ = accounts
    with pytest.raises(ValueError, match="explicit"):
        care.save_checkin(patient["id"], RATINGS | {"energy": value})
    assert care.list_checkins(patient["id"]) == []


@pytest.mark.parametrize("changes", [
    {"date": "2026-10-04"}, {"date": "2026-02-30"}, {"date": "20261002"},
    {"date": "2026-10-03T00:00:00"}, {"date": 20261003}, {"date": "1800-01-01"},
    {"falls": "no"}, {"falls": 0}, {"note": "n" * 2001}, {"note": None},
    {"diagnosis": "Unrequested value"}, {"energy": float("nan")},
])
def test_checkin_validates_optional_context_and_dates(accounts, changes):
    _, patient, *_ = accounts
    with pytest.raises(ValueError):
        care.save_checkin(patient["id"], RATINGS | changes)
    assert care.list_checkins(patient["id"]) == []


def test_checkin_missing_fields_limits_and_date_order(accounts):
    _, patient, *_ = accounts
    with pytest.raises(ValueError, match="explicit"):
        care.save_checkin(patient["id"], {"energy": 0})
    for date_string in ("2026-10-01", "2026-10-03", "2026-10-02"):
        care.save_checkin(patient["id"], RATINGS | {"date": date_string})
    assert [row["date"] for row in care.list_checkins(patient["id"], limit=2)] == ["2026-10-03", "2026-10-02"]
    for limit in (0, 366, True, 1.5):
        with pytest.raises(ValueError, match="limit"):
            care.list_checkins(patient["id"], limit=limit)


def test_patient_owns_goal_and_human_clinician_owns_followup(accounts):
    _, patient, other, clinician = accounts
    goal = care.save_personal_goal(patient["id"], "Cook with my family", "A meaningful activity")
    assert goal["source"] == "patient" and goal["status"] == "active"
    for status in ("paused", "completed", "active"):
        assert care.update_goal(patient["id"], goal["id"], status)["status"] == status
    assert care.list_goals(clinician["id"], patient["patient_id"])[0]["id"] == goal["id"]
    for actor_id in (clinician["id"], other["id"]):
        with pytest.raises(PermissionError):
            care.update_goal(actor_id, goal["id"], "completed")
    with pytest.raises(PermissionError, match="patient"):
        care.save_personal_goal(clinician["id"], "Staff-written goal", patient_id=patient["patient_id"])
    with pytest.raises(ValueError):
        care.update_goal(patient["id"], goal["id"], "diagnosed")
    with pytest.raises(PermissionError, match="clinician"):
        care.save_care_plan(patient["id"], patient["patient_id"], "Focus", "Notes")
    plan = care.save_care_plan(clinician["id"], patient["patient_id"], "Patient's priorities",
                               "Discussed walking to the garden together.", "2026-10-02")
    assert plan["source"] == "clinician" and plan["author_name"] == "Dr Followup"
    assert plan["next_review_date"] == "2026-10-02"  # historical review dates are valid
    assert care.list_care_plans(patient["id"])[0]["notes"] == plan["notes"]


def test_private_care_data_permissions_and_revoked_links(accounts):
    admin, patient, other, clinician = accounts
    checkin = care.save_checkin(patient["id"], RATINGS)
    goal = care.save_personal_goal(patient["id"], "Keep my own routine")
    plan = care.save_care_plan(clinician["id"], patient["patient_id"], "Conversation", "Private follow-up")
    for actor in (admin, other):
        for reader in (care.list_checkins, care.list_goals, care.list_care_plans):
            with pytest.raises(PermissionError):
                reader(actor["id"], patient["patient_id"])
        with pytest.raises(PermissionError):
            care.save_checkin(actor["id"], RATINGS, patient["patient_id"])
    for reader in (care.list_checkins, care.list_goals, care.list_care_plans):
        assert reader(clinician["id"], patient["patient_id"])
    svc.unlink_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    for reader in (care.list_checkins, care.list_goals, care.list_care_plans):
        with pytest.raises(PermissionError):
            reader(clinician["id"], patient["patient_id"])
    with pytest.raises(PermissionError):
        care.save_checkin(clinician["id"], RATINGS, patient["patient_id"])
    with pytest.raises(PermissionError):
        care.save_care_plan(clinician["id"], patient["patient_id"], "Focus", "Notes")
    assert care.list_checkins(patient["id"])[0]["id"] == checkin["id"]
    assert care.list_goals(patient["id"])[0]["id"] == goal["id"]
    assert care.list_care_plans(patient["id"])[0]["id"] == plan["id"]


def test_patient_id_is_not_an_actor_id_and_resource_ids_are_scoped(accounts):
    _, patient, other, _ = accounts
    with pytest.raises(PermissionError):
        care.save_checkin(patient["patient_id"], RATINGS)
    foreign_assessment = svc.create_assessment(other["id"])
    goal = care.save_personal_goal(patient["id"], "My goal")
    # IDs can overlap across tables. Authorization follows the goal's patient,
    # even if an unrelated assessment has the very same UUID.
    with transaction() as session:
        row = session.get(PersonalGoal, goal["id"])
        row.id = foreign_assessment["id"]
    assert care.update_goal(patient["id"], foreign_assessment["id"], "completed")["status"] == "completed"
    with pytest.raises(PermissionError):
        care.update_goal(other["id"], foreign_assessment["id"], "active")


def test_followup_assessment_must_match_patient_and_does_not_modify_reports(accounts):
    admin, patient, other, clinician = accounts
    svc.link_patient(admin["id"], other["patient_id"], clinician["clinician_id"])
    other_assessment = svc.create_assessment(other["id"])
    with pytest.raises(PermissionError, match="same patient"):
        care.save_care_plan(clinician["id"], patient["patient_id"], "Focus", "Notes",
                            assessment_id=other_assessment["id"])
    with transaction() as session:
        assert session.scalar(select(func.count(CarePlan.id))) == 0
    plan = care.save_care_plan(clinician["id"], patient["patient_id"], "Focus", "Clinician's words")
    assert plan["assessment_id"] is None
    assert svc.get_assessment(other["id"], other_assessment["id"])["reports"] == []


def test_inactive_actor_and_withdrawn_consent_block_collection(accounts):
    admin, patient, other, clinician = accounts
    goal = care.save_personal_goal(patient["id"], "Priorities")
    care.save_checkin(patient["id"], RATINGS)
    with transaction() as session:
        consent = session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"]))
        consent.withdrawn_at = utc_now()
    for writer in (
        lambda: care.save_checkin(patient["id"], RATINGS),
        lambda: care.save_personal_goal(patient["id"], "New goal"),
        lambda: care.update_goal(patient["id"], goal["id"], "completed"),
        lambda: care.save_care_plan(clinician["id"], patient["patient_id"], "Focus", "Notes"),
    ):
        with pytest.raises(PermissionError, match="consent"):
            writer()
    assert care.list_checkins(patient["id"])  # retained history can still be read
    svc.set_user_active(admin["id"], other["id"], False)
    for action in (
        lambda: care.list_checkins(other["id"]), lambda: care.list_goals(other["id"]),
        lambda: care.list_care_plans(other["id"]), lambda: care.save_checkin(other["id"], RATINGS),
        lambda: care.save_personal_goal(other["id"], "A goal"),
    ):
        with pytest.raises(PermissionError, match="active"):
            action()
    with transaction() as session:
        session.get(User, clinician["id"]).active = False
    with pytest.raises(PermissionError, match="active"):
        care.save_care_plan(clinician["id"], patient["patient_id"], "Focus", "Notes")


def test_text_limits_and_audits_do_not_store_personal_words(accounts):
    admin, patient, _, clinician = accounts
    for label, detail in (("", ""), (" " * 3, ""), ("g" * 161, ""), ("goal", "d" * 2001)):
        with pytest.raises(ValueError):
            care.save_personal_goal(patient["id"], label, detail)
    for focus, notes, next_date in (("", "notes", None), ("f" * 161, "notes", None),
                                    ("focus", "", None), ("focus", "n" * 4001, None),
                                    ("focus", "notes", "2026-13-01")):
        with pytest.raises(ValueError):
            care.save_care_plan(clinician["id"], patient["patient_id"], focus, notes, next_date)
    private_note = "Private patient concern about the garden"
    private_goal = "Private priority about cooking with family"
    private_plan = "Private clinician conversation about the next visit"
    care.save_checkin(patient["id"], RATINGS | {"note": private_note})
    goal = care.save_personal_goal(patient["id"], private_goal, "Personal detail")
    care.update_goal(patient["id"], goal["id"], "completed")
    care.save_care_plan(clinician["id"], patient["patient_id"], "Review", private_plan)
    logs = json.dumps(svc.list_audit_logs(admin["id"], limit=500))
    for private in (private_note, private_goal, private_plan, "Personal detail"):
        assert private not in logs
    assert "care.goal_updated" in logs and "completed" in logs
