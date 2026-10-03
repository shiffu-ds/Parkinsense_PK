"""Patient controls and secure downloads tested on synthetic isolated accounts."""

import secrets
from urllib.parse import urlsplit

import pytest
from streamlit.testing.v1 import AppTest

from backend import production, services as svc
from backend.db import configure_db, init_db, transaction
from backend.db.models import Consent
from backend.services import privacy
from ml.tabular import ADL_ITEMS, analyze_adl


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'privacy.sqlite'}", allow_sqlite=True)
    init_db()
    password = "fixture-password-only-123"
    admin = svc.bootstrap_admin("Fixture Admin", "admin@example.test", password)
    patient = svc.register_patient("Fixture Patient", "patient@example.test", password, consent=True)
    other = svc.register_patient("Other Fixture", "other@example.test", password, consent=True)
    clinician = svc.create_staff(admin["id"], "Fixture Clinician", "clinician@example.test", password)
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return admin, patient, other, clinician


def test_consent_withdrawal_revokes_links_and_reconsent_does_not_revive_them(accounts):
    _, patient, _, clinician = accounts
    visit = svc.create_assessment(patient["id"])
    svc.store_upload(patient["id"], visit["id"], "gait", "fixture.mp4", b"fixture bytes")
    media = svc.get_assessment(patient["id"], visit["id"])["files"][0]
    grant = production.create_media_grant(clinician["id"], visit["id"], media["id"], session_key=secrets.token_urlsafe(32))
    token = urlsplit(grant["url"]).path.rsplit("/", 1)[1]
    assert production.authorize_media_token(token).size_bytes > 0
    privacy.set_monitoring_consent(patient["id"], acknowledged=False)
    assert privacy.monitoring_status(patient["id"])["active"] is False
    with pytest.raises(PermissionError):
        production.authorize_media_token(token)
    with pytest.raises(PermissionError):
        svc.create_assessment(patient["id"])
    privacy.set_monitoring_consent(patient["id"], acknowledged=True)
    with pytest.raises(PermissionError):
        production.authorize_media_token(token)
    assert privacy.monitoring_status(patient["id"])["active"] is True
    svc.create_assessment(patient["id"])


def test_data_requests_are_patient_owned_idempotent_and_operator_managed(accounts):
    admin, patient, other, clinician = accounts
    first = privacy.create_data_request(patient["id"], "erasure")
    assert privacy.create_data_request(patient["id"], "erasure")["id"] == first["id"]
    assert privacy.list_data_requests(other["id"]) == []
    with pytest.raises(PermissionError):
        privacy.list_data_requests(clinician["id"])
    with pytest.raises(PermissionError):
        privacy.update_request_status(patient["id"], first["id"], "resolved")
    assert privacy.update_request_status(admin["id"], first["id"], "reviewing")["status"] == "reviewing"
    # Filing an erasure request does not silently erase health/account records.
    assert svc.get_user(patient["id"])["active"] is True
    assert privacy.monitoring_status(patient["id"])["active"] is True
    with pytest.raises(ValueError):
        privacy.create_data_request(patient["id"], "delete-everything")
    with pytest.raises(PermissionError):
        privacy.set_monitoring_consent(clinician["id"], acknowledged=False)


def test_all_active_consent_versions_are_withdrawn(accounts):
    _, patient, *_ = accounts
    with transaction() as session:
        session.add(Consent(patient_id=patient["patient_id"], version="another-version", acknowledged=True))
    privacy.set_monitoring_consent(patient["id"], acknowledged=False)
    assert not privacy.monitoring_status(patient["id"])["active"]


def test_private_report_button_issues_gateway_attachment_not_streamlit_public_media(accounts):
    _, patient, *_ = accounts
    visit = svc.create_assessment(patient["id"])
    svc.save_module(patient["id"], visit["id"], "adl", analyze_adl(dict.fromkeys(ADL_ITEMS, 1)))
    app = AppTest.from_string("from app.views import reports_page\nreports_page()", default_timeout=20)
    app.session_state["user_id"] = patient["id"]
    app.session_state["auth_revision"] = production.session_revision(patient["id"])
    app.session_state["media_session_key"] = secrets.token_urlsafe(32)
    app.run()
    assert not app.exception and not app.get("download_button")
    next(b for b in app.button if b.label == "Download patient report").click().run()
    assert not app.exception and not app.get("download_button")
    private_urls = [e.proto.url for e in app.get("link_button") if "/media/" in e.proto.url]
    assert len(private_urls) == 1
    token = urlsplit(private_urls[0]).path.rsplit("/", 1)[1]
    resource = production.authorize_media_token(token)
    assert resource.filename == "parkinsense-patient-report.html"
    assert resource.path.stat().st_mode & 0o077 == 0
    assert "Fixture Patient" in resource.path.read_text()
    production.revoke_media_grants(patient["id"], session_key=app.session_state["media_session_key"])
    with pytest.raises(PermissionError):
        production.authorize_media_token(token)


@pytest.mark.parametrize("language", ["English", "Urdu", "Roman Urdu"])
def test_patient_data_control_screen_is_available_in_all_three_languages(accounts, language):
    _, patient, *_ = accounts
    svc.update_profile(patient["id"], language=language)
    app = AppTest.from_string("from app.components.data_privacy import data_privacy_page\ndata_privacy_page()")
    app.session_state["user_id"] = patient["id"]
    app.run()
    assert not app.exception
    assert app.button and app.selectbox
    assert not app.get("download_button")
