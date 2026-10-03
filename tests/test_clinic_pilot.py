"""Clinic feasibility evidence preserves authorization, missingness and provenance."""

from datetime import date, datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import func, select
from streamlit.testing.v1 import AppTest

from backend import services as svc
from backend.db import configure_db, init_db, transaction
from backend.db.models import Consent, User, utc_now
from backend.db.pilot_models import PilotObservation
from backend.services import pilot

PASSWORD = "Clinic pilot test passphrase 2026"
TARGETS = dict(pilot.DEFAULT_TARGETS, minimum_patients=1, minimum_review_pairs=1, minimum_usability_responses=1)


@pytest.fixture
def context(tmp_path, monkeypatch):
    configure_db(f"sqlite:///{tmp_path / 'pilot.sqlite'}", allow_sqlite=True)
    init_db()
    monkeypatch.setattr(pilot, "_today", lambda: date(2026, 10, 3))
    admin = svc.bootstrap_admin("Admin", "admin@example.test", PASSWORD)
    clinician = svc.create_staff(admin["id"], "Clinician", "clinic@example.test", PASSWORD)
    other_clinician = svc.create_staff(admin["id"], "Other Clinician", "otherclinic@example.test", PASSWORD)
    patient = svc.register_patient("Patient", "patient@example.test", PASSWORD, consent=True)
    other_patient = svc.register_patient("Other Patient", "otherpatient@example.test", PASSWORD, consent=True)
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    item = pilot.create_pilot(clinician["id"], "Feasibility pilot", "2026-10-01", "2026-10-31", targets=TARGETS)
    return {"admin": admin, "clinician": clinician, "other_clinician": other_clinician,
            "patient": patient, "other_patient": other_patient, "pilot": item}


def enroll(context):
    pilot.invite_patient(context["clinician"]["id"], context["pilot"]["id"], context["patient"]["patient_id"])
    pilot.acknowledge_pilot_participation(context["patient"]["id"], context["pilot"]["id"], acknowledged=True)


def observe(context, **changes):
    data = {"observed_on": "2026-10-03", "planned_tasks": 4, "attempted_tasks": 3,
            "completed_tasks": 2, "recording_attempts": 4, "usable_recordings": 1}
    return pilot.save_observation(context["clinician"]["id"], context["pilot"]["id"],
                                  context["patient"]["patient_id"], data | changes)


def read(context):
    return pilot.get_pilot(context["clinician"]["id"], context["pilot"]["id"])


def test_empty_pilot_reports_unknown_and_requires_active_owner_clinician(context):
    result = read(context)
    assert result["metrics"]["completion_fraction"] is None
    assert result["metrics"]["median_minutes_saved"] is None
    assert set(result["metrics"]["target_checks"].values()) == {"unknown"}
    for role in ("admin", "patient", "other_clinician"):
        with pytest.raises(PermissionError):
            pilot.get_pilot(context[role]["id"], context["pilot"]["id"])
        with pytest.raises(PermissionError):
            pilot.export_pilot_aggregate(context[role]["id"], context["pilot"]["id"])
    for role in ("admin", "patient"):
        with pytest.raises(PermissionError):
            pilot.create_pilot(context[role]["id"], "Forbidden", "2026-10-01", "2026-10-31")
    with transaction() as session:
        session.get(User, context["clinician"]["id"]).active = False
    with pytest.raises(PermissionError):
        read(context)


def test_patient_acknowledgement_is_separate_and_cannot_be_substituted(context):
    doctor, item, patient = context["clinician"], context["pilot"], context["patient"]
    with pytest.raises(PermissionError):
        pilot.invite_patient(doctor["id"], item["id"], context["other_patient"]["patient_id"])
    pilot.invite_patient(doctor["id"], item["id"], patient["patient_id"])
    with pytest.raises(PermissionError):
        observe(context)
    with pytest.raises(PermissionError):
        pilot.acknowledge_pilot_participation(doctor["id"], item["id"], acknowledged=True)
    with pytest.raises(ValueError):
        pilot.acknowledge_pilot_participation(patient["id"], item["id"], acknowledged=False)
    assert pilot.list_patient_invitations(context["other_patient"]["id"]) == []
    assert pilot.list_patient_invitations(patient["id"])[0]["acknowledged"] is False
    pilot.acknowledge_pilot_participation(patient["id"], item["id"], acknowledged=True)
    assert pilot.list_patient_invitations(patient["id"])[0]["acknowledged"] is True
    observe(context)


def test_failure_counts_denominators_and_paired_manual_minutes_are_preserved(context):
    enroll(context)
    visit = svc.create_assessment(context["patient"]["id"])
    saved = observe(context, assessment_id=visit["id"], baseline_review_seconds=120,
                    app_review_seconds=60, usability_rating=4, needed_help=True)
    metrics = read(context)["metrics"]
    assert saved["baseline_review_source"] == saved["app_review_source"] == "manually_reported"
    assert metrics["completion_fraction"] == 0.5  # 2/4 planned, not 2/3 attempted
    assert metrics["not_attempted_tasks"] == 1 and metrics["failed_or_incomplete_attempts"] == 1
    assert metrics["usable_recording_fraction"] == 0.25
    assert metrics["paired_reviews"] == 1 and metrics["median_minutes_saved"] == 1
    assert metrics["median_review_saving_fraction"] == 0.5
    assert metrics["target_checks"] == {"review_time": "met", "task_completion": "below_target",
                                         "recording_usability": "below_target", "patient_usability": "met"}


def test_missing_and_zero_review_values_never_become_fake_baselines(context):
    enroll(context)
    visit = svc.create_assessment(context["patient"]["id"])
    observe(context, assessment_id=visit["id"], app_review_seconds=0)
    metrics = read(context)["metrics"]
    assert metrics["paired_reviews"] == 0 and metrics["median_minutes_saved"] is None
    assert metrics["baseline_review_coverage"] == 0 and metrics["app_review_coverage"] == 1
    assert metrics["usability_responses"] == 0 and metrics["median_usability_rating"] is None
    assert metrics["target_checks"]["patient_usability"] == "unknown"
    observe(context, assessment_id=visit["id"], baseline_review_seconds=0, app_review_seconds=0)
    metrics = read(context)["metrics"]
    assert metrics["paired_reviews"] == 1 and metrics["median_minutes_saved"] == 0
    assert metrics["fractional_review_pairs"] == 0 and metrics["median_review_saving_fraction"] is None
    assert metrics["target_checks"]["review_time"] == "unknown"
    with pytest.raises(ValueError, match="assessment"):
        observe(context, baseline_review_seconds=10, app_review_seconds=5)


def test_bounded_counts_times_and_dates_are_validated_without_creating_evidence(context):
    enroll(context)
    invalid = [{"planned_tasks": 0}, {"planned_tasks": True}, {"attempted_tasks": 5}, {"completed_tasks": 4},
               {"recording_attempts": 101}, {"usable_recordings": 5}, {"usability_rating": 0},
               {"usability_rating": True}, {"needed_help": "yes"}, {"device_category": "iphone-model"},
               {"app_review_seconds": float("nan")}, {"baseline_review_seconds": float("inf")},
               {"app_review_seconds": -1}, {"observed_on": "2026-10-04"}, {"observed_on": "2026-09-30"},
               {"observed_on": "20261003"}, {"notes": "x" * 2001}, {"diagnosis": "unsupported"}]
    for changes in invalid:
        with pytest.raises(ValueError):
            observe(context, **changes)
    assert read(context)["metrics"]["observations"] == 0
    assert read(context)["plan_locked_at"] is None


def test_targets_and_dates_freeze_before_first_outcome_and_close_finalizes(context):
    item, doctor = context["pilot"], context["clinician"]
    changed = pilot.update_pilot_plan(doctor["id"], item["id"], name="Defined before evidence",
                                      starts_on="2026-10-01", ends_on="2026-10-30", targets=TARGETS)
    assert changed["name"] == "Defined before evidence"
    enroll(context)
    observe(context)
    assert read(context)["plan_locked_at"] is not None
    with pytest.raises(ValueError, match="frozen"):
        pilot.update_pilot_plan(doctor["id"], item["id"], name="After evidence",
                               starts_on="2026-10-01", ends_on="2026-10-31", targets=TARGETS)
    assert pilot.close_pilot(doctor["id"], item["id"])["status"] == "closed"
    with pytest.raises(ValueError, match="closed"):
        observe(context)
    assert read(context)["metrics"]["observations"] == 1


def test_server_timer_is_persistent_scoped_single_use_and_labelled(context, monkeypatch):
    enroll(context)
    visit = svc.create_assessment(context["patient"]["id"])
    now = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pilot, "utc_now", lambda: now)
    started = pilot.start_review_timer(context["clinician"]["id"], context["pilot"]["id"],
                                       context["patient"]["patient_id"], visit["id"], mode="app")
    assert read(context)["plan_locked_at"] is not None
    with pytest.raises(ValueError, match="running"):
        pilot.start_review_timer(context["clinician"]["id"], context["pilot"]["id"],
                                  context["patient"]["patient_id"], visit["id"])
    with pytest.raises(ValueError, match="Stop"):
        observe(context, assessment_id=visit["id"], app_timer_id=started["id"])
    now += timedelta(seconds=9.5)
    stopped = pilot.stop_review_timer(context["clinician"]["id"], context["pilot"]["id"], started["id"])
    assert stopped["elapsed_seconds"] == 9.5 and stopped["source"] == "server_elapsed_timer"
    now += timedelta(seconds=100)
    assert pilot.stop_review_timer(context["clinician"]["id"], context["pilot"]["id"], started["id"])["elapsed_seconds"] == 9.5
    saved = observe(context, assessment_id=visit["id"], app_timer_id=started["id"])
    assert saved["app_review_seconds"] == 9.5 and saved["app_review_source"] == "server_elapsed_timer"
    with pytest.raises(ValueError, match="already used"):
        observe(context, assessment_id=visit["id"], app_timer_id=started["id"])
    another = pilot.create_pilot(context["clinician"]["id"], "Another pilot", "2026-10-01", "2026-10-31")
    with pytest.raises(PermissionError):
        pilot.stop_review_timer(context["clinician"]["id"], another["id"], started["id"])


def test_forgotten_timer_is_unusable_and_does_not_lock_future_review_timers(context, monkeypatch):
    enroll(context)
    visit = svc.create_assessment(context["patient"]["id"])
    now = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pilot, "utc_now", lambda: now)
    started = pilot.start_review_timer(context["clinician"]["id"], context["pilot"]["id"],
                                       context["patient"]["patient_id"], visit["id"])
    now += timedelta(hours=5)
    stopped = pilot.stop_review_timer(context["clinician"]["id"], context["pilot"]["id"], started["id"])
    assert stopped["elapsed_seconds"] is None and stopped["stopped_at"] is not None
    with pytest.raises(ValueError):
        observe(context, assessment_id=visit["id"], app_timer_id=started["id"])
    assert pilot.start_review_timer(context["clinician"]["id"], context["pilot"]["id"],
                                     context["patient"]["patient_id"], visit["id"])["id"] != started["id"]


def test_withdrawn_running_timer_does_not_block_other_patient_and_finalization_discards_unfinished_time(context):
    enroll(context)
    doctor, item = context["clinician"], context["pilot"]
    visit = svc.create_assessment(context["patient"]["id"])
    pilot.start_review_timer(doctor["id"], item["id"], context["patient"]["patient_id"], visit["id"])
    pilot.withdraw_pilot_participation(context["patient"]["id"], item["id"])
    other = context["other_patient"]
    svc.link_patient(context["admin"]["id"], other["patient_id"], doctor["clinician_id"])
    pilot.invite_patient(doctor["id"], item["id"], other["patient_id"])
    pilot.acknowledge_pilot_participation(other["id"], item["id"], acknowledged=True)
    other_visit = svc.create_assessment(other["id"])
    timer = pilot.start_review_timer(doctor["id"], item["id"], other["patient_id"], other_visit["id"])
    assert timer["stopped_at"] is None
    pilot.close_pilot(doctor["id"], item["id"])
    stopped = read(context)["timers"][0]
    assert stopped["stopped_at"] is not None and stopped["elapsed_seconds"] is None
    assert read(context)["metrics"]["median_minutes_saved"] is None


def test_unlinked_withdrawn_inactive_or_monitoring_revoked_participants_are_not_read_or_exported(context):
    enroll(context)
    observe(context)
    admin, doctor, patient = context["admin"], context["clinician"], context["patient"]
    svc.unlink_patient(admin["id"], patient["patient_id"], doctor["clinician_id"])
    assert read(context)["observations"] == []
    assert pilot.export_pilot_aggregate(doctor["id"], context["pilot"]["id"])["metrics"]["observed_patients"] == 0
    with pytest.raises(PermissionError):
        observe(context)
    svc.link_patient(admin["id"], patient["patient_id"], doctor["clinician_id"])
    with transaction() as session:
        session.get(User, patient["id"]).active = False
    assert read(context)["observations"] == []
    with transaction() as session:
        session.get(User, patient["id"]).active = True
        session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"])).withdrawn_at = utc_now()
    assert read(context)["observations"] == []
    pilot.withdraw_pilot_participation(patient["id"], context["pilot"]["id"])
    with transaction() as session:
        session.scalar(select(Consent).where(Consent.patient_id == patient["patient_id"])).withdrawn_at = None
        assert session.scalar(select(func.count(PilotObservation.id))) == 1  # policy retention, no silent deletion
    assert read(context)["enrollments"] == []
    with pytest.raises(PermissionError):
        observe(context)
    with pytest.raises(PermissionError):
        pilot.acknowledge_pilot_participation(patient["id"], context["pilot"]["id"], acknowledged=True)


def test_export_has_only_aggregate_counts_and_reported_payment_intention(context):
    enroll(context)
    observe(context, notes="Private patient note")
    saved = pilot.save_payment_intent(context["clinician"]["id"], context["pilot"]["id"],
                                      respondent_role="clinic_owner", intent="yes", amount=1200,
                                      reported_on="2026-10-03", notes="Private respondent note")
    assert saved["source"] == "reported_payment_intent" and saved["actual_payment"] is False
    exported = pilot.export_pilot_aggregate(context["clinician"]["id"], context["pilot"]["id"])
    encoded = json.dumps(exported, allow_nan=False)
    assert exported["payment_discussions"] == {"yes": 1, "no": 0, "undecided": 0}
    for private in ("Private", context["patient"]["id"], context["patient"]["patient_id"], context["pilot"]["id"],
                    "patient@example.test", "Feasibility pilot", "storage_key", "assessment_id"):
        assert private not in encoded
    for changes in ({"intent": "no", "amount": 100}, {"amount": float("inf")}, {"currency": "BTC"},
                    {"reported_on": "2026-10-04"}, {"respondent_role": "invented"}):
        args = {"respondent_role": "clinic_owner", "intent": "yes", "reported_on": "2026-10-03"} | changes
        with pytest.raises(ValueError):
            pilot.save_payment_intent(context["clinician"]["id"], context["pilot"]["id"], **args)


def test_repeated_pairs_from_one_patient_do_not_replace_patient_coverage(context):
    enroll(context)
    visit = svc.create_assessment(context["patient"]["id"])
    # Set the intended patient coverage before the first observation.
    two = dict(TARGETS, minimum_patients=2)
    pilot.update_pilot_plan(context["clinician"]["id"], context["pilot"]["id"], name="Coverage test",
                           starts_on="2026-10-01", ends_on="2026-10-31", targets=two)
    for _ in range(3):
        observe(context, assessment_id=visit["id"], baseline_review_seconds=120, app_review_seconds=60,
                usability_rating=5, planned_tasks=1, attempted_tasks=1, completed_tasks=1,
                recording_attempts=1, usable_recordings=1)
    assert read(context)["metrics"]["paired_reviews"] == 3
    assert read(context)["metrics"]["paired_review_patients"] == 1
    assert set(read(context)["metrics"]["target_checks"].values()) == {"unknown"}


def test_patient_participation_ui_is_explicit_and_roman_urdu(context):
    pilot.invite_patient(context["clinician"]["id"], context["pilot"]["id"], context["patient"]["patient_id"])
    svc.update_profile(context["patient"]["id"], language="Roman Urdu")
    app = AppTest.from_string("""
import streamlit as st
from backend import services
from app.components.clinic_pilot import pilot_participation_panel
pilot_participation_panel(services.get_user(st.session_state['user_id']))
""", default_timeout=20)
    app.session_state["user_id"] = context["patient"]["id"]
    app.run()
    assert not app.exception
    join = next(button for button in app.button if "razamandi dein" in button.label)
    assert join.disabled is True
    app.checkbox[0].check().run()
    next(button for button in app.button if "razamandi dein" in button.label).click().run()
    assert not app.exception
    assert pilot.list_patient_invitations(context["patient"]["id"])[0]["acknowledged"] is True
    next(button for button in app.button if "wapas lein" in button.label).click().run()
    assert not app.exception
    assert pilot.list_patient_invitations(context["patient"]["id"])[0]["withdrawn"] is True


def test_clinic_ui_saves_failed_attempts_then_displays_actual_native_unit_graph(context):
    enroll(context)
    app = AppTest.from_string("from app.components.clinic_pilot import clinic_pilot_page\nclinic_pilot_page()", default_timeout=25)
    app.session_state["user_id"] = context["clinician"]["id"]
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 0
    next(item for item in app.date_input if item.label == "Observation date").set_value(date(2026, 10, 3))
    next(item for item in app.number_input if item.label == "Tasks planned before visit").set_value(4)
    next(item for item in app.number_input if item.label == "Tasks attempted (including failures)").set_value(3)
    next(item for item in app.number_input if item.label == "Tasks completed").set_value(2)
    next(item for item in app.button if item.label == "Save pilot observation").click().run()
    assert not app.exception
    assert read(context)["metrics"]["completion_fraction"] == 0.5
    assert len(app.get("plotly_chart")) == 1  # no invented review graph when pairs are missing
    assert any(item.label == "Download deidentified aggregate" for item in app.get("download_button"))
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert figure["data"][0]["type"] == "scatter3d"
    assert figure["data"][0]["x"] == [4] and figure["data"][0]["y"] == [3] and figure["data"][0]["z"] == [2]
    assert "Planned tasks (count)" == figure["layout"]["scene"]["xaxis"]["title"]["text"]


def test_admin_ui_never_opens_clinic_evidence(context):
    app = AppTest.from_string("from app.components.clinic_pilot import clinic_pilot_page\nclinic_pilot_page()", default_timeout=20)
    app.session_state["user_id"] = context["admin"]["id"]
    app.run()
    assert not app.exception
    assert app.error and not app.get("plotly_chart")
