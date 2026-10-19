"""Route every assessment section through a real isolated login and draft.

This checks UI navigation and task isolation, not model accuracy. All account
and visit data belong to a disposable SQLite test database.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from backend import services
from backend.db import configure_db, init_db


@pytest.mark.parametrize("card,page,tasks", [
    ("gait", "gait_page", ["gait", "turning"]),
    ("hand", "hand_page", ["finger_left", "finger_right", "hand_open_close"]),
    ("transfer", "transfer_page", ["sit_to_stand"]),
    ("reach", "reach_page", ["reach", "grasp", "object_transfer"]),
    ("voice", "voice_page", ["vowel", "sentence", "natural"]),
    ("adl", "adl_page", []),
])
def test_each_section_resumes_the_same_draft_without_creating_or_saving_data(tmp_path, monkeypatch, card, page, tasks):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'sections.sqlite'}", allow_sqlite=True)
    init_db()
    user = services.register_patient("Section Test", "sections@example.test", "test-password-123", consent=True)
    visit = services.create_assessment(user["id"])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "Home.py"), default_timeout=30).run()
    app.text_input(key="login_email").set_value("sections@example.test")
    app.text_input(key="login_password").set_value("test-password-123")
    next(button for button in app.button if button.label == "Log in").click().run()
    assert not app.exception
    assert app.session_state["user_id"] == user["id"]
    next(button for button in app.button if button.label == "Start or resume an assessment").click().run()
    app._page_hash = calc_hash("assessment_hub")
    next(button for button in app.button if button.label == "Resume selected assessment").click().run()
    assert app.session_state["active_assessment_id"] == visit["id"]
    app._page_hash = calc_hash("assessment_hub")
    app.button(key=f"hub_open_{card}").click().run()
    assert not app.exception
    app._page_hash = calc_hash(page)
    if tasks:
        selector = next(box for box in app.selectbox if box.label in {"Movement task", "Voice task"})
        for task in tasks:
            selector.set_value(task).run()
            assert not app.exception
            selector = next(box for box in app.selectbox if box.label in {"Movement task", "Voice task"})
            assert selector.value == task
            assert app.session_state["active_assessment_id"] == visit["id"]
        if card != "voice":
            assert len(app.get("file_uploader")) == 1
    else:
        assert all(box.value is None for box in app.selectbox)
    saved = services.get_assessment(user["id"], visit["id"])
    assert saved["status"] == "draft" and saved["modules"] == {}
    assert saved["reports"] == []
