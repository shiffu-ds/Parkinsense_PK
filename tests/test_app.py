"""User-flow checks with isolated test storage and database, never live data."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from backend import services
from backend.db import configure_db, init_db

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'app.sqlite'}", allow_sqlite=True)
    init_db()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def field(app, label):
    return next(item for item in app.text_input if item.label == label)


def click_on_page(app, label, callable_name):
    # AppTest does not retain the browser's new URL after st.switch_page on a
    # callable page. Supply the same page hash on the next interaction.
    app._page_hash = calc_hash(callable_name)
    button(app, label).click().run()


def test_register_start_resume_adl_complete_and_report(app_db):
    app = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20).run()
    assert not app.exception
    field(app, "Full name").set_value("Test Patient")
    app.text_input(key="register_email").set_value("flow@example.test")
    app.text_input(key="register_password").set_value("testing-password-123")
    field(app, "Confirm password").set_value("testing-password-123")
    app.checkbox[0].check()
    button(app, "Create patient account").click().run()
    assert not app.exception
    assert app.session_state["role"] == "patient"
    button(app, "Start or resume an assessment").click().run()
    assert not app.exception
    click_on_page(app, "Start new assessment", "assessment_hub")
    assert not app.exception
    aid = app.session_state["active_assessment_id"]
    click_on_page(app, "Open Daily Activities", "assessment_hub")
    assert not app.exception
    for choice in app.selectbox:
        choice.set_value(0)
    click_on_page(app, "Save daily activities", "adl_page")
    assert not app.exception
    stored = services.get_assessment(app.session_state["user_id"], aid)
    assert stored["modules"]["adl"]["status"] == "accepted"
    # A new Streamlit session can resume persisted draft content after logging in.
    fresh = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20).run()
    fresh.text_input(key="login_email").set_value("flow@example.test")
    fresh.text_input(key="login_password").set_value("testing-password-123")
    button(fresh, "Log in").click().run()
    assert not fresh.exception
    button(fresh, "Start or resume an assessment").click().run()
    click_on_page(fresh, "Resume selected assessment", "assessment_hub")
    assert fresh.session_state["active_assessment_id"] == aid
    click_on_page(fresh, "Complete this assessment", "assessment_hub")
    assert not fresh.exception
    assert services.get_assessment(fresh.session_state["user_id"], aid)["status"] == "completed"
    # Test report view against the same real saved module.
    report_app = AppTest.from_string("from app.views import reports_page\nreports_page()", default_timeout=20)
    report_app.session_state["user_id"] = fresh.session_state["user_id"]
    report_app.run()
    button(report_app, "Prepare and save measurement summary").click().run()
    assert not report_app.exception
    assert services.get_assessment(fresh.session_state["user_id"], aid)["reports"]
    button(fresh, "Log out").click().run()
    assert not fresh.exception
    assert any(t.value == "Movement, with everyday life in view" for t in fresh.title)


def test_registration_requires_consent_and_login_rejects_bad_password(app_db):
    app = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20).run()
    field(app, "Full name").set_value("Consent Patient")
    app.text_input(key="register_email").set_value("consent@example.test")
    app.text_input(key="register_password").set_value("testing-password-123")
    field(app, "Confirm password").set_value("testing-password-123")
    button(app, "Create patient account").click().run()
    assert app.error
    assert not app.exception
    assert "user_id" not in app.session_state
    app.text_input(key="login_email").set_value("missing@example.test")
    app.text_input(key="login_password").set_value("incorrect")
    button(app, "Log in").click().run()
    assert app.error
    assert not app.exception


def test_role_routes_no_self_selected_staff_role(app_db):
    admin = services.bootstrap_admin("Test Admin", "admin@example.test", "testing-password-123")
    clinician = services.create_staff(admin["id"], "Test Clinician", "clinician@example.test", "testing-password-123")
    for account, title in [(admin, "Administration"), (clinician, "Clinician Dashboard")]:
        app = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20)
        app.session_state["user_id"] = account["id"]
        app.session_state["auth_revision"] = 0
        app.run()
        assert not app.exception
        assert any(t.value == title for t in app.title)
    public = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20).run()
    assert all(box.label != "Role" for box in public.selectbox)


def test_adl_does_not_default_unanswered_items_to_no_difficulty(app_db):
    patient = services.register_patient("ADL Patient", "adl@example.test", "testing-password-123", consent=True)
    visit = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import adl_page\nadl_page()", default_timeout=20)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    assert all(item.value is None for item in app.selectbox)
    button(app, "Save daily activities").click().run()
    assert app.warning
    assert any(heading.value == "Your next steps" for heading in app.subheader)
    assert not app.exception
    assert "adl" not in services.get_assessment(patient["id"], visit["id"])["modules"]


def test_assigned_clinician_review_and_context_form(app_db):
    from ml.tabular import analyze_adl
    from ml.tabular.adl import ADL_ITEMS
    admin = services.bootstrap_admin("Care Admin", "care-admin@example.test", "testing-password-123")
    patient = services.register_patient("Care Patient", "care-patient@example.test", "testing-password-123", consent=True)
    clinician = services.create_staff(admin["id"], "Care Clinician", "care-clinician@example.test", "testing-password-123")
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    visit = services.create_assessment(patient["id"])
    services.save_module(patient["id"], visit["id"], "adl", analyze_adl({key: 1 for key in ADL_ITEMS}))
    services.finish_assessment(patient["id"], visit["id"])
    app = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=20)
    app.session_state["user_id"] = clinician["id"]
    app.session_state["auth_revision"] = 0
    app.run()
    assert not app.exception
    next(item for item in app.text_area if item.label == "Review note").set_value("Reviewed test measurement.")
    button(app, "Mark reviewed").click().run()
    assert not app.exception
    assert services.get_assessment(clinician["id"], visit["id"])["review_status"] == "reviewed"
    next(item for item in app.number_input if item.label == "Age (years)").set_value(61)
    button(app, "Save clinical context").click().run()
    assert not app.exception
    saved = services.get_assessment(clinician["id"], visit["id"])
    assert saved["clinical_measurements"][0]["value"] == 61
    assert saved["review_status"] == "pending"


def test_report_selection_stays_on_visit_when_summary_changes(app_db):
    from ml.tabular import ADL_ITEMS, analyze_adl
    patient = services.register_patient("Report Patient", "reports@example.test", "testing-password-123", consent=True)
    earlier = services.create_assessment(patient["id"])
    services.save_module(patient["id"], earlier["id"], "adl", analyze_adl(dict.fromkeys(ADL_ITEMS, 0)))
    services.finish_assessment(patient["id"], earlier["id"])
    later = services.create_assessment(patient["id"])
    services.save_module(patient["id"], later["id"], "adl", analyze_adl(dict.fromkeys(ADL_ITEMS, 2)))
    app = AppTest.from_string("from app.views import reports_page\nreports_page()", default_timeout=20)
    app.session_state["user_id"] = patient["id"]
    app.run()
    app.selectbox[0].set_value(earlier["id"]).run()
    button(app, "Prepare and save measurement summary").click().run()
    assert not app.exception
    assert app.selectbox[0].value == earlier["id"]
    assert len(services.get_assessment(patient["id"], earlier["id"])["reports"]) == 2
    assert len(services.get_assessment(patient["id"], later["id"])["reports"]) == 1
    app.run()
    assert app.selectbox[0].value == earlier["id"]
