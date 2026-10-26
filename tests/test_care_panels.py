"""Care UI checks against isolated storage, with real service authorization."""

import pytest
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, init_db
from backend.services import care


@pytest.fixture
def care_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'care-ui.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Test Patient", "care-ui@example.test", "testing-password-123", consent=True)
    admin = services.bootstrap_admin("Test Admin", "care-ui-admin@example.test", "testing-password-123")
    clinician = services.create_staff(admin["id"], "Test Clinician", "care-ui-clinician@example.test", "testing-password-123")
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return patient, clinician


def _patient_panel(patient):
    app = AppTest.from_string(
        "from app.components.care_panels import patient_care_panel\n"
        "from backend import services\n"
        "import streamlit as st\n"
        "patient_care_panel(services.get_user(st.session_state['user_id']))",
        default_timeout=20,
    )
    app.session_state["user_id"] = patient["id"]
    return app.run()


def _clinician_panel(clinician, patient):
    app = AppTest.from_string(
        "from app.components.care_panels import clinician_care_panel\n"
        "from backend import services\n"
        "import streamlit as st\n"
        "clinician_care_panel(services.get_user(st.session_state['user_id']), st.session_state['patient_id'])",
        default_timeout=20,
    )
    app.session_state["user_id"] = clinician["id"]
    app.session_state["patient_id"] = patient["patient_id"]
    return app.run()


def _button(app, label):
    return next(item for item in app.button if item.label == label)


def test_checkin_requires_explicit_answers_and_preserves_unknown_falls(care_accounts):
    patient, _ = care_accounts
    app = _patient_panel(patient)
    assert not app.exception
    checkin = [item for item in app.selectbox if item.key.startswith("checkin_") and not item.key.endswith("_helper")]
    assert len(checkin) == 5  # Four ratings and falls; the medicine diary tab has its own.
    assert all(item.value is None for item in checkin)
    _button(app, "Save daily check-in").click().run()
    assert not app.exception
    assert app.error
    assert care.list_checkins(patient["id"]) == []
    for item in app.selectbox:
        if item.key.startswith("checkin_") and not item.key.endswith("_helper") and not item.label.startswith("Any falls"):
            item.set_value(0)
    next(item for item in app.text_area if item.label == "Anything you'd like your care team to know?").set_value("I would like to discuss getting dressed.")
    _button(app, "Save daily check-in").click().run()
    assert not app.exception
    saved = care.list_checkins(patient["id"])[0]
    assert saved["responses"]["energy"] == 0
    assert saved["responses"]["falls"] is None
    assert saved["responses"]["note"] == "I would like to discuss getting dressed."
    assert app.dataframe


def test_patient_goal_create_update_and_clinician_read_only(care_accounts):
    patient, clinician = care_accounts
    app = _patient_panel(patient)
    next(item for item in app.text_input if item.label == "An activity or priority that matters to you").set_value("Comfortable dressing")
    _button(app, "Save personal goal").click().run()
    assert not app.exception
    goals = care.list_goals(patient["id"])
    assert goals[0]["status"] == "active"
    next(item for item in app.selectbox if item.label == "Goal status").set_value("paused")
    _button(app, "Update goal").click().run()
    assert not app.exception
    assert care.list_goals(patient["id"])[0]["status"] == "paused"
    clinician_app = _clinician_panel(clinician, patient)
    assert not clinician_app.exception
    assert all(item.label != "Goal status" for item in clinician_app.selectbox)
    assert all(item.label != "Save personal goal" for item in clinician_app.button)
    assert any("Comfortable dressing" in item.value for item in clinician_app.markdown)


def test_clinician_followup_keeps_authorship_and_optional_review_date(care_accounts):
    patient, clinician = care_accounts
    app = _clinician_panel(clinician, patient)
    assert not app.exception
    review = next(item for item in app.date_input if item.label == "Planned review date (optional)")
    assert review.value is None
    next(item for item in app.text_input if item.label == "Focus for follow-up").set_value("Discuss daily priorities")
    next(item for item in app.text_area if item.label == "Care team note").set_value("We agreed to bring examples of daily activities to the next visit.")
    _button(app, "Save care team follow-up").click().run()
    assert not app.exception
    saved = care.list_care_plans(patient["id"])[0]
    assert saved["next_review_date"] is None
    assert saved["author_name"] == clinician["full_name"]
    patient_app = _patient_panel(patient)
    assert not patient_app.exception
    assert any(clinician["full_name"] in item.value for item in patient_app.caption)
    assert any("We agreed to bring examples" in item.value for item in patient_app.markdown)
    assert all(item.label != "Save care team follow-up" for item in patient_app.button)


def test_dynamic_design_text_is_html_escaped(monkeypatch):
    from app.components import design

    output = []
    monkeypatch.setattr(design.st, "markdown", lambda value, **kwargs: output.append(value))
    unsafe = '<script>alert("patient")</script>'
    design.section_header(unsafe, detail=unsafe, eyebrow=unsafe)
    design.status_pill(unsafe, tone='care" onclick="alert(1)')
    design.empty_state(unsafe, unsafe)
    assert all("<script>" not in value for value in output)
    assert all("&lt;script&gt;" in value for value in output)
    assert "onclick" not in output[1]


def test_peoples_words_are_shown_as_typed_not_as_markdown():
    # Browser check (25 Oct): the note renders verbatim, loads no image and any
    # remaining link is a bare address shown as itself.
    import re
    from app.components.design import plain_text
    note = "![tracker](http://example.test/p.png) [call me](javascript:alert(1)) **loud** :red[alarm] $x$ <b>hi</b>"
    escaped = plain_text(note)
    assert not re.search(r"(?<!\\)[\[\]()!*:$<>]", escaped)
    assert re.sub(r"\\(.)", r"\1", escaped) == note
    assert plain_text("آج چلنا آسان لگا") == "آج چلنا آسان لگا"
    assert plain_text(None) == ""
