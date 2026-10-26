"""Medicine-timing context, the clinician caseload and the refreshed pages.

Every account and visit lives in a disposable SQLite database.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, init_db
from backend.services import care
from backend.services.caseload import caseload_summary
from backend.services.visit_context import get_visit_context, list_visit_contexts, save_visit_context

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'context.sqlite'}", allow_sqlite=True)
    init_db()
    admin = services.bootstrap_admin("Context Admin", "ctx-admin@example.test", "testing-password-123")
    clinician = services.create_staff(admin["id"], "Context Clinician", "ctx-doc@example.test", "testing-password-123")
    other = services.create_staff(admin["id"], "Other Clinician", "ctx-other@example.test", "testing-password-123")
    patient = services.register_patient("Context Patient", "ctx-patient@example.test", "testing-password-123", consent=True)
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return {"admin": admin, "clinician": clinician, "other": other, "patient": patient}


def _adl():
    from ml.tabular import analyze_adl
    from ml.tabular.adl import ADL_ITEMS
    return analyze_adl({key: 1 for key in ADL_ITEMS})


def test_patient_records_medicine_timing_and_linked_clinician_reads_it(team):
    patient, clinician, other = team["patient"], team["clinician"], team["other"]
    visit = services.create_assessment(patient["id"])
    assert get_visit_context(patient["id"], visit["id"]) is None
    saved = save_visit_context(patient["id"], visit["id"], medication_state="on", dose_window="1_2", dyskinesia="no", note=" After breakfast ")
    assert saved["medication_state"] == "on" and saved["note"] == "After breakfast"
    assert saved["recorded_by_role"] == "patient"
    # A repeat save updates the same visit's record rather than adding a second.
    save_visit_context(patient["id"], visit["id"], medication_state="wearing_off", dose_window="2_4")
    assert get_visit_context(clinician["id"], visit["id"])["medication_state"] == "wearing_off"
    assert list(list_visit_contexts(clinician["id"], [visit["id"]])) == [visit["id"]]
    with pytest.raises(PermissionError):
        get_visit_context(other["id"], visit["id"])
    with pytest.raises(PermissionError):
        save_visit_context(other["id"], visit["id"], medication_state="on")


@pytest.mark.parametrize("kwargs", [
    {"medication_state": "maybe"},
    {"medication_state": "on", "dose_window": "yesterday"},
    {"medication_state": "on", "dyskinesia": "sometimes"},
    {"medication_state": "on", "note": "x" * 1001},
])
def test_medicine_timing_rejects_values_outside_the_fixed_choices(team, kwargs):
    visit = services.create_assessment(team["patient"]["id"])
    with pytest.raises(ValueError):
        save_visit_context(team["patient"]["id"], visit["id"], **kwargs)
    assert get_visit_context(team["patient"]["id"], visit["id"]) is None


def test_no_medicine_clears_the_dose_window_and_closed_visits_are_patient_read_only(team):
    patient, clinician = team["patient"], team["clinician"]
    visit = services.create_assessment(patient["id"])
    assert save_visit_context(patient["id"], visit["id"], medication_state="none", dose_window="gt4")["dose_window"] is None
    services.save_module(patient["id"], visit["id"], "adl", _adl())
    services.finish_assessment(patient["id"], visit["id"])
    with pytest.raises(ValueError):
        save_visit_context(patient["id"], visit["id"], medication_state="on")
    # A linked clinician may transcribe what the patient reported afterwards.
    assert save_visit_context(clinician["id"], visit["id"], medication_state="on")["recorded_by_role"] == "clinician"


def test_caseload_counts_only_linked_patients_and_reports_no_measurements(team):
    patient, clinician, other = team["patient"], team["clinician"], team["other"]
    visit = services.create_assessment(patient["id"])
    services.save_module(patient["id"], visit["id"], "adl", _adl())
    save_visit_context(patient["id"], visit["id"], medication_state="off", dose_window="gt4")
    services.finish_assessment(patient["id"], visit["id"])
    services.create_assessment(patient["id"])
    care.save_checkin(patient["id"], {"energy": 2, "sleep_quality": 2, "movement_ease": 2, "mood": 2, "falls": True,
                                      "date": (date.today() - timedelta(days=1)).isoformat()})
    rows = caseload_summary(clinician["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row["visits"] == 2 and row["awaiting_review"] == 1 and row["open_drafts"] == 1
    assert row["falls_14d"] == 1
    assert row["latest_medication_state"] is None  # The newest visit has no timing yet.
    assert not {"modules", "features", "note", "responses"} & set(row)
    assert caseload_summary(other["id"]) == []
    with pytest.raises(PermissionError):
        caseload_summary(patient["id"])


def test_clinician_dashboard_and_trends_render_with_caseload(team):
    patient, clinician = team["patient"], team["clinician"]
    for _ in range(2):
        visit = services.create_assessment(patient["id"])
        services.save_module(patient["id"], visit["id"], "adl", _adl())
        services.finish_assessment(patient["id"], visit["id"])
    app = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=30)
    app.session_state["user_id"] = clinician["id"]
    app.session_state["auth_revision"] = 0
    app.run()
    assert not app.exception
    assert any(metric.label == "Visits awaiting review" and metric.value == "2" for metric in app.metric)
    # Trends previously asked for the patient twice and raised a duplicate widget key.
    trends = AppTest.from_string("from app.views import progress_page\nprogress_page()", default_timeout=30)
    trends.session_state["user_id"] = clinician["id"]
    trends.run()
    assert not trends.exception
    assert any(metric.label == "Change since first" for metric in trends.metric)


def test_hub_shows_visit_progress_and_saves_medicine_timing(team):
    patient = team["patient"]
    visit = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import assessment_hub\nassessment_hub()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    assert not app.exception
    assert any("0 of 7 task groups saved" in caption.value for caption in app.caption)
    app.selectbox(key=f"med_state_{visit['id']}").set_value("on")
    app.selectbox(key=f"med_dose_{visit['id']}").set_value("lt1")
    next(button for button in app.button if button.label == "Save medicine timing").click().run()
    assert not app.exception
    assert get_visit_context(patient["id"], visit["id"])["dose_window"] == "lt1"


def test_patient_home_names_one_next_step(team):
    patient = team["patient"]
    app = AppTest.from_string("from app.views import patient_home\npatient_home()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.run()
    assert not app.exception
    assert any("How is today going?" in block.value for block in app.markdown)
    services.create_assessment(patient["id"])
    app.run()
    assert any("Carry on with your visit" in block.value for block in app.markdown)


def test_home_points_to_a_review_only_while_it_is_recent():
    from datetime import datetime, timezone
    from app.views import REVIEW_NOTICE_DAYS, fresh_review
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    reviewed = {"id": "reviewed", "status": "completed", "review_status": "reviewed",
                "created_at": "2026-10-01T09:00:00+00:00", "reviewed_at": "2026-10-20T09:00:00+00:00"}
    assert fresh_review([reviewed], now=now) is reviewed
    assert fresh_review([reviewed], now=now + timedelta(days=REVIEW_NOTICE_DAYS)) is None
    waiting = {"id": "waiting", "status": "completed", "review_status": "pending",
               "created_at": "2026-10-22T09:00:00+00:00", "reviewed_at": None}
    assert fresh_review([waiting, reviewed], now=now) is None  # The newest finished visit is still waiting.
    draft = {"id": "draft", "status": "draft", "review_status": "pending", "created_at": "2026-10-24T09:00:00+00:00"}
    assert fresh_review([draft, reviewed], now=now) is reviewed


def test_newest_follow_up_note_sets_the_planned_review(team):
    from app.views import planned_review_date
    patient, clinician = team["patient"], team["clinician"]
    today = date.today()
    care.save_care_plan(clinician["id"], patient["patient_id"], "First plan", "Review soon.",
                        next_review_date=(today + timedelta(days=5)).isoformat())
    care.save_care_plan(clinician["id"], patient["patient_id"], "Later plan", "Review moved later.",
                        next_review_date=(today + timedelta(days=30)).isoformat())
    care.save_care_plan(clinician["id"], patient["patient_id"], "Note only", "No new date.")
    expected = (today + timedelta(days=30)).isoformat()
    assert caseload_summary(clinician["id"])[0]["next_review"] == expected
    plans = care.list_care_plans(patient["id"])
    assert planned_review_date(plans, today.isoformat()) == expected
    assert planned_review_date(plans, (today + timedelta(days=31)).isoformat()) is None


def test_hub_can_switch_to_another_open_visit(team):
    patient = team["patient"]
    first = services.create_assessment(patient["id"])
    services.create_assessment(patient["id"])
    third = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import assessment_hub\nassessment_hub()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = third["id"]
    app.run()
    assert not app.exception
    assert len(app.selectbox(key="hub_other_visit").options) == 2  # The open visit is not offered again.
    app.selectbox(key="hub_other_visit").select_index(1).run()  # Newest first, so index 1 is the oldest.
    app.button(key="hub_switch_resume").click().run()
    assert not app.exception
    assert app.session_state["active_assessment_id"] == first["id"]
