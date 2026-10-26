"""Weekly task plans: who may write them, and how Home and the hub use them."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.engine import make_url
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, get_engine, init_db
from backend.db.models import Base
from backend.services import task_plan

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
        configure_db(f"sqlite:///{tmp_path / 'plan.sqlite'}", allow_sqlite=True)
    init_db()
    admin = services.bootstrap_admin("Plan Admin", "plan-admin@example.test", PASSWORD)
    clinician = services.create_staff(admin["id"], "Plan Clinician", "plan-doc@example.test", PASSWORD)
    other = services.create_staff(admin["id"], "Other Clinician", "plan-other@example.test", PASSWORD)
    patient = services.register_patient("Plan Patient", "plan-patient@example.test", PASSWORD, consent=True)
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return {"admin": admin, "clinician": clinician, "other": other, "patient": patient}


def test_only_a_linked_clinician_sets_the_plan_and_the_newest_counts(team):
    patient, clinician = team["patient"], team["clinician"]
    assert task_plan.get_task_plan(patient["id"]) is None
    task_plan.save_task_plan(clinician["id"], patient["patient_id"], {"gait": [0, 3], "voice": [3, 3]}, note=" Gently ")
    plan = task_plan.get_task_plan(patient["id"])
    assert plan["schedule"] == {"gait": [0, 3], "voice": [3]} and plan["note"] == "Gently"
    assert task_plan.planned_on(plan, 3) == ["gait", "voice"] and task_plan.planned_on(plan, 1) == []
    task_plan.save_task_plan(clinician["id"], patient["patient_id"], {"adl": [6]})
    assert task_plan.get_task_plan(clinician["id"], patient["patient_id"])["schedule"] == {"adl": [6]}
    task_plan.save_task_plan(clinician["id"], patient["patient_id"], {})
    assert task_plan.get_task_plan(patient["id"]) is None
    for actor in (patient, team["other"], team["admin"]):
        with pytest.raises(PermissionError):
            task_plan.save_task_plan(actor["id"], patient["patient_id"], {"gait": [1]})


@pytest.mark.parametrize("schedule", [{"surgery": [1]}, {"gait": [7]}, {"gait": "monday"}, {"gait": [True]}, ["gait"]])
def test_plan_values_are_checked(team, schedule):
    with pytest.raises(ValueError):
        task_plan.save_task_plan(team["clinician"]["id"], team["patient"]["patient_id"], schedule)


def test_home_and_hub_show_todays_planned_tasks(team):
    patient, clinician = team["patient"], team["clinician"]
    today = datetime.now(ZoneInfo("Asia/Karachi")).weekday()
    task_plan.save_task_plan(clinician["id"], patient["patient_id"], {"voice": [today], "gait": [(today + 1) % 7]})
    from backend.services import care
    care.save_checkin(patient["id"], {"energy": 2, "sleep_quality": 2, "movement_ease": 2, "mood": 2,
                                      "date": datetime.now(ZoneInfo("Asia/Karachi")).date().isoformat()})
    home = AppTest.from_string("from app.views import patient_home\npatient_home()", default_timeout=30)
    home.session_state["user_id"] = patient["id"]
    home.run()
    assert not home.exception
    assert any("plan: Voice / Speech" in block.value for block in home.markdown)  # The apostrophe is HTML-escaped.
    visit = services.create_assessment(patient["id"])
    hub = AppTest.from_string("from app.views import assessment_hub\nassessment_hub()", default_timeout=30)
    hub.session_state["user_id"] = patient["id"]
    hub.session_state["active_assessment_id"] = visit["id"]
    hub.run()
    assert not hub.exception
    assert any("Planned for today" in block.value for block in hub.markdown)


def test_clinician_follow_up_page_saves_a_plan(team):
    patient, clinician = team["patient"], team["clinician"]
    script = (f"from app.components.care_panels import clinician_care_panel\nfrom backend import services\n"
              f"clinician_care_panel(services.get_user('{clinician['id']}'), '{patient['patient_id']}')")
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    app.multiselect(key=f"plan_days_{patient['patient_id']}_gait").set_value([0, 2])
    app.button(key=f"FormSubmitter:task_plan_{patient['patient_id']}-Save weekly plan").click().run()
    assert not app.exception
    assert task_plan.get_task_plan(clinician["id"], patient["patient_id"])["schedule"] == {"gait": [0, 2]}
