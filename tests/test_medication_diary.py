"""ON/OFF diary and usual medicine times: access, validation and reminders."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.engine import make_url

from backend import services
from backend.db import configure_db, get_engine, init_db
from backend.db.models import Base
from backend.services import medication_diary as diary
from backend.services.caseload import caseload_summary

PASSWORD = "testing-password-123"


@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    test_url = os.getenv("PARKINSENSE_TEST_DATABASE_URL")
    if test_url:
        if not (make_url(test_url).database or "").startswith("parkinsense_test_"):
            raise ValueError("Integration tests require a dedicated parkinsense_test_* database.")
        configure_db(test_url)
        Base.metadata.drop_all(get_engine())
    else:
        configure_db(f"sqlite:///{tmp_path / 'diary.sqlite'}", allow_sqlite=True)
    init_db()
    admin = services.bootstrap_admin("Diary Admin", "diary-admin@example.test", PASSWORD)
    clinician = services.create_staff(admin["id"], "Diary Clinician", "diary-doc@example.test", PASSWORD)
    other = services.create_staff(admin["id"], "Other Clinician", "diary-other@example.test", PASSWORD)
    patient = services.register_patient("Diary Patient", "diary-patient@example.test", PASSWORD, consent=True)
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return {"admin": admin, "clinician": clinician, "other": other, "patient": patient}


def test_patient_and_linked_clinician_write_and_read_the_diary(team):
    patient, clinician = team["patient"], team["clinician"]
    first = diary.save_diary_entry(patient["id"], "on", note="  after breakfast ")
    assert first["note"] == "after breakfast" and first["recorded_by_role"] == "patient"
    earlier = datetime.now(timezone.utc) - timedelta(hours=3)
    diary.save_diary_entry(clinician["id"], "off", observed_at=earlier, patient_id=patient["patient_id"])
    entries = diary.list_diary(clinician["id"], patient["patient_id"])
    assert [entry["state"] for entry in entries] == ["on", "off"]
    assert entries[1]["recorded_by_role"] == "clinician"
    assert diary.diary_counts(entries) == {"on": 1, "on_dyskinesia": 0, "wearing_off": 0, "off": 1}
    assert caseload_summary(clinician["id"])[0]["off_reports_7d"] == 1


@pytest.mark.parametrize("who", ["other", "admin"])
def test_unlinked_staff_cannot_read_or_write(team, who):
    actor = team[who]
    with pytest.raises(PermissionError):
        diary.list_diary(actor["id"], team["patient"]["patient_id"])
    with pytest.raises(PermissionError):
        diary.save_diary_entry(actor["id"], "on", patient_id=team["patient"]["patient_id"])


@pytest.mark.parametrize("kwargs", [
    {"state": "sleepy"}, {"state": "on", "note": "x" * 301},
    {"state": "on", "observed_at": datetime.now(timezone.utc) + timedelta(hours=1)},
    {"state": "on", "observed_at": datetime.now(timezone.utc) - timedelta(days=8)},
    {"state": "on", "observed_at": "08:00"},
])
def test_diary_values_are_checked(team, kwargs):
    with pytest.raises(ValueError):
        diary.save_diary_entry(team["patient"]["id"], **kwargs)


def test_withdrawn_consent_blocks_new_entries(team):
    from backend.services import privacy
    patient = team["patient"]
    privacy.set_monitoring_consent(patient["id"], acknowledged=False)
    with pytest.raises(PermissionError):
        diary.save_diary_entry(patient["id"], "on")


def test_medicine_times_are_validated_and_sorted(team):
    patient = team["patient"]
    assert diary.get_medicine_times(patient["id"]) == []
    assert diary.save_medicine_times(patient["id"], ["20:00", "08:00", "08:00"]) == ["08:00", "20:00"]
    assert diary.get_medicine_times(team["clinician"]["id"], patient["patient_id"]) == ["08:00", "20:00"]
    for bad in (["8am"], ["24:00"], ["08:00"] * 9 + ["09:00"], "08:00"):
        with pytest.raises(ValueError):
            diary.save_medicine_times(patient["id"], bad)


def test_reminder_is_due_after_a_usual_time_until_an_entry_is_made():
    now = datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc)  # 14:30 in Pakistan.
    assert diary.due_medicine_time(["14:00", "20:00"], [], now=now) == "14:00"
    assert diary.due_medicine_time(["12:00"], [], now=now) is None  # More than two hours ago.
    after = [{"observed_at": "2026-10-25T09:10:00+00:00", "state": "on"}]  # 14:10 local.
    assert diary.due_medicine_time(["14:00"], after, now=now) is None
    before = [{"observed_at": "2026-10-25T08:50:00+00:00", "state": "on"}]  # 13:50 local.
    assert diary.due_medicine_time(["14:00"], before, now=now) == "14:00"
    late_night = datetime(2026, 10, 25, 19, 30, tzinfo=timezone.utc)  # 00:30 next day locally.
    assert diary.due_medicine_time(["23:30"], [], now=late_night) == "23:30"


def test_home_asks_after_a_usual_time_and_one_tap_answers(team):
    from zoneinfo import ZoneInfo
    from streamlit.testing.v1 import AppTest
    patient = team["patient"]
    now = datetime.now(ZoneInfo("Asia/Karachi"))
    usual = (now - timedelta(minutes=20)).strftime("%H:%M")
    diary.save_medicine_times(patient["id"], [usual])
    app = AppTest.from_string("from app.views import patient_home\npatient_home()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.run()
    assert not app.exception
    assert any("past your usual medicine time" in block.value for block in app.markdown)
    app.button(key="home_diary_wearing_off").click().run()
    assert not app.exception
    assert [entry["state"] for entry in diary.list_diary(patient["id"])] == ["wearing_off"]
    assert not any("past your usual medicine time" in block.value for block in app.markdown)
    assert any("Saved for" in item.value for item in app.success)


def test_care_pages_show_the_diary_for_patient_and_clinician(team):
    from streamlit.testing.v1 import AppTest
    patient, clinician = team["patient"], team["clinician"]
    diary.save_diary_entry(patient["id"], "off")
    mine = AppTest.from_string("from app.views import my_care_page\nmy_care_page()", default_timeout=30)
    mine.session_state["user_id"] = patient["id"]
    mine.run()
    assert not mine.exception
    assert any(tab.label == "Medicine diary" for tab in mine.tabs)
    assert any("1 OFF" in caption.value for caption in mine.caption)
    team_view = AppTest.from_string(
        f"from app.components.care_panels import clinician_care_panel\n"
        f"from backend import services\n"
        f"clinician_care_panel(services.get_user('{clinician['id']}'), '{patient['patient_id']}')", default_timeout=30)
    team_view.run()
    assert not team_view.exception
    assert any("Patient-reported medicine diary" in block.value for block in team_view.markdown)
