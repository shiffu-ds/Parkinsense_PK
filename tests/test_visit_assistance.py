"""Who helped and which walking aid was used: visits and daily check-ins."""
import os
from datetime import date

import pytest
from sqlalchemy.engine import make_url
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, get_engine, init_db
from backend.db.models import Base
from backend.services import care
from backend.services.visit_context import get_visit_assistance, list_visit_assistance, save_visit_assistance

PASSWORD = "testing-password-123"
RATINGS = {"energy": 2, "sleep_quality": 3, "movement_ease": 1, "mood": 4}


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
        configure_db(f"sqlite:///{tmp_path / 'assist.sqlite'}", allow_sqlite=True)
    init_db()
    admin = services.bootstrap_admin("Assist Admin", "assist-admin@example.test", PASSWORD)
    clinician = services.create_staff(admin["id"], "Assist Clinician", "assist-doc@example.test", PASSWORD)
    other = services.create_staff(admin["id"], "Other Clinician", "assist-other@example.test", PASSWORD)
    patient = services.register_patient("Assist Patient", "assist-patient@example.test", PASSWORD, consent=True)
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return {"clinician": clinician, "other": other, "patient": patient}


def test_visit_assistance_follows_visit_access_rules(team):
    patient, clinician, other = team["patient"], team["clinician"], team["other"]
    visit = services.create_assessment(patient["id"])
    saved = save_visit_assistance(patient["id"], visit["id"], helper="family", walking_aid="cane")
    assert saved["helper"] == "family" and saved["walking_aid"] == "cane"
    save_visit_assistance(patient["id"], visit["id"], helper="alone", walking_aid="walker")
    assert get_visit_assistance(clinician["id"], visit["id"])["walking_aid"] == "walker"
    assert list(list_visit_assistance(clinician["id"], [visit["id"]])) == [visit["id"]]
    with pytest.raises(PermissionError):
        get_visit_assistance(other["id"], visit["id"])
    with pytest.raises(ValueError):
        save_visit_assistance(patient["id"], visit["id"], helper="robot", walking_aid="none")
    with pytest.raises(ValueError):
        save_visit_assistance(patient["id"], visit["id"], helper="alone", walking_aid="skateboard")
    from ml.tabular import analyze_adl
    from ml.tabular.adl import ADL_ITEMS
    services.save_module(patient["id"], visit["id"], "adl", analyze_adl({key: 1 for key in ADL_ITEMS}))
    services.finish_assessment(patient["id"], visit["id"])
    with pytest.raises(ValueError, match="closed"):
        save_visit_assistance(patient["id"], visit["id"], helper="alone", walking_aid="none")
    assert save_visit_assistance(clinician["id"], visit["id"], helper="caregiver", walking_aid="none")["recorded_by_role"] == "clinician"


def test_checkin_helper_is_saved_cleared_and_validated(team):
    patient = team["patient"]
    today = date.today().isoformat()
    care.save_checkin(patient["id"], {**RATINGS, "date": today, "helper": "family"})
    assert care.list_checkins(patient["id"])[0]["responses"]["helper"] == "family"
    care.save_checkin(patient["id"], {**RATINGS, "date": today})
    assert "helper" not in care.list_checkins(patient["id"])[0]["responses"]
    with pytest.raises(ValueError):
        care.save_checkin(patient["id"], {**RATINGS, "date": today, "helper": "neighbour's dog"})


def test_hub_records_help_and_progress_shows_it(team):
    patient = team["patient"]
    visit = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import assessment_hub\nassessment_hub()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    assert not app.exception
    app.selectbox(key=f"assist_helper_{visit['id']}").set_value("family")
    app.selectbox(key=f"assist_aid_{visit['id']}").set_value("cane")
    next(button for button in app.button if button.label == "Save help and walking aid").click().run()
    assert not app.exception
    assert get_visit_assistance(patient["id"], visit["id"])["helper"] == "family"
