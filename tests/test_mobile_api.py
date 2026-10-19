"""Native patient API tests: isolated temporary database and synthetic signals."""
from io import BytesIO
import asyncio
import stat

from fastapi.testclient import TestClient
import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import func, select

from backend import services
from backend.db import transaction
from backend.db.models import AssessmentFile, Consent, Patient, User
from backend.db.production_models import AccountSecurity
from backend.mobile_api import create_app
from backend.mobile_auth import SESSION_SECONDS, SessionRegistry, decode_token, issue_token, load_secret
from backend.production import session_revision

PASSWORD = "A mobile test passphrase 2026"
SECRET = b"isolated-patient-api-test-secret-64-bytes-that-is-never-used-in-production"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_DATABASE_URL", f"sqlite:///{tmp_path / 'application.sqlite3'}")
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("PARKINSENSE_ALLOW_SQLITE", "1")
    monkeypatch.setenv("PARKINSENSE_MAX_UPLOAD_MB", "1")
    services.configure_db()
    services.init_db()
    app = create_app(secret=SECRET, initialize_database=False, rate_limit=False,
                     registry_path=tmp_path / "mobile-sessions.sqlite3")
    with TestClient(app) as client:
        yield client, app, tmp_path


def register(client, email="patient@example.test", **overrides):
    body = {"full_name": "Native Test Patient", "email": email, "password": PASSWORD,
            "language": "English", "consent": True} | overrides
    return client.post("/auth/register", json=body)


def login(client, email="patient@example.test"):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def headers(response):
    body = response.json() if hasattr(response, "json") else response
    return {"Authorization": "Bearer " + body["access_token"]}


def start(client, auth):
    response = client.post("/sessions", json={}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_registration_atomic_consent_role_normalization_and_private_errors(api):
    client, _, _ = api
    for override in ({"consent": False}, {"consent": "true"}, {"role": "admin"}, {"password": "short"}):
        assert register(client, **override).status_code == 422
    with transaction() as session:
        assert session.scalar(select(func.count(User.id))) == 0
        assert session.scalar(select(func.count(Patient.id))) == 0
        assert session.scalar(select(func.count(Consent.id))) == 0
    response = register(client, email=" PATIENT@example.test ")
    assert response.status_code == 201
    body = response.json()
    assert body["expires_in"] == SESSION_SECONDS
    assert body["user"]["role"] == "patient"
    assert body["user"]["email"] == "patient@example.test"
    assert "password" not in response.text and "clinician_id" not in response.text
    assert register(client).status_code == 422
    assert client.get("/profile", headers=headers(response)).json()["monitoring_consent"]["active"] is True
    sensitive = "this-secret-rejected-input-must-not-appear"
    rejected = client.post("/auth/register", json={"password": sensitive})
    assert sensitive not in rejected.text
    assert response.headers["cache-control"] == "no-store"


def test_only_patient_auth_and_resource_ownership(api):
    client, _, _ = api
    first = register(client)
    second = register(client, email="other@example.test")
    auth = headers(first)
    identifier = start(client, auth)
    assert client.get("/sessions").status_code == 401
    assert client.get("/sessions", headers=headers(second)).json() == []
    assert client.get(f"/sessions/{identifier}", headers=headers(second)).status_code == 403
    assert client.post(f"/sessions/{identifier}/notes", json={"text": "Walking is difficult"}, headers=headers(second)).status_code == 403
    assert client.get(f"/sessions/{identifier}/report", headers=headers(second)).status_code == 403
    admin = services.bootstrap_admin("Test Administrator", "admin@example.test", PASSWORD)
    services.create_staff(admin["id"], "Test Clinician", "doctor@example.test", PASSWORD)
    for email in ("admin@example.test", "doctor@example.test", "unknown@example.test"):
        response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 401
        assert "access_token" not in response.text
    for path in ("/research", "/admin", "/staff", "/docs", "/openapi.json"):
        assert client.get(path, headers=auth).status_code == 404


def test_sessions_notes_activities_completion_reports_and_no_private_paths(api):
    client, _, _ = api
    auth = headers(register(client))
    identifier = start(client, auth)
    assert client.post(f"/sessions/{identifier}/complete", json={}, headers=auth).status_code == 422
    assert client.get(f"/sessions/{identifier}/report", headers=auth).status_code == 404
    notes = client.post(f"/sessions/{identifier}/notes", json={"text": "Walking is difficult today"}, headers=auth)
    assert notes.status_code == 200
    assert notes.json()["modules"]["nlp"]["provenance"]["source"] == "manual_transcript_or_self_report"
    activities = {name: 1 for name in ("dressing", "feeding", "grooming", "bathing", "writing", "phone_use", "walking", "transfers", "household_activities")}
    assert client.post(f"/sessions/{identifier}/activities", json={"responses": activities | {"dressing": True}}, headers=auth).status_code == 422
    saved = client.post(f"/sessions/{identifier}/activities", json={"responses": activities}, headers=auth)
    assert saved.status_code == 200 and saved.json()["modules"]["adl"]["quality"]["accepted"]
    assert client.post(f"/sessions/{identifier}/complete", json={}, headers=auth).json()["status"] == "completed"
    report = client.get(f"/sessions/{identifier}/report", headers=auth)
    assert report.status_code == 200
    assert {section["task"] for section in report.json()["sections"]} == {"nlp", "adl"}
    assert report.json()["accepted"] is True
    assert "clinical_measurements" not in report.json()
    assert "storage_key" not in saved.text and "password_hash" not in saved.text
    assert client.post(f"/sessions/{identifier}/notes", json={"text": "Updated note"}, headers=auth).status_code == 422


def test_logout_is_durable_and_does_not_change_web_or_other_mobile_sessions(api):
    client, app, tmp_path = api
    first = register(client).json()
    second = login(client)
    actor_id = first["user"]["id"]
    revision = session_revision(actor_id)
    assert client.post("/auth/logout", json={}, headers=headers(first)).status_code == 200
    assert client.get("/profile", headers=headers(first)).status_code == 401
    assert client.get("/profile", headers=headers(second)).status_code == 200
    assert session_revision(actor_id) == revision
    # A new registry instance simulates API restart; sign-out is still effective.
    app.state.registry = SessionRegistry(tmp_path / "mobile-sessions.sqlite3")
    assert client.get("/profile", headers=headers(first)).status_code == 401
    assert client.get("/profile", headers=headers(second)).status_code == 200


def test_password_revision_active_account_and_token_integrity_checked_every_time(api):
    client, _, _ = api
    response = register(client).json()
    auth = headers(response)
    tampered = response["access_token"][:-1] + ("A" if response["access_token"][-1] != "A" else "B")
    assert client.get("/profile", headers={"Authorization": "Bearer " + tampered}).status_code == 401
    with transaction() as session:
        session.add(AccountSecurity(user_id=response["user"]["id"], session_revision=1))
    assert client.get("/profile", headers=auth).status_code == 401
    fresh = login(client)
    assert client.get("/profile", headers=headers(fresh)).status_code == 200
    with transaction() as session:
        session.get(User, fresh["user"]["id"]).active = False
    assert client.get("/profile", headers=headers(fresh)).status_code == 401


def test_signed_tokens_expire_and_unknown_signed_sessions_are_rejected(api, monkeypatch):
    client, _, _ = api
    response = register(client).json()
    payload = decode_token(response["access_token"], SECRET)
    with monkeypatch.context() as clock:
        clock.setattr("backend.mobile_auth.time.time", lambda: payload["exp"] + 1)
        assert client.get("/profile", headers=headers(response)).status_code == 401
    actor = services.authenticate("patient@example.test", PASSWORD)
    invented = issue_token(actor, SECRET)  # Not issued into the durable session registry.
    assert client.get("/profile", headers={"Authorization": "Bearer " + invented}).status_code == 401


def wav_bytes(*, silent=False):
    rate = 16000
    samples = np.zeros(rate * 4) if silent else 0.2 * np.sin(2 * np.pi * 180 * np.arange(rate * 4) / rate)
    stream = BytesIO()
    sf.write(stream, samples, rate, format="WAV", subtype="PCM_16")
    return stream.getvalue()


def test_actual_audio_analysis_save_authenticated_media_and_failed_attempt_cleanup(api):
    client, _, tmp_path = api
    auth = headers(register(client))
    other = headers(register(client, email="other@example.test"))
    identifier = start(client, auth)
    silence = client.post(f"/sessions/{identifier}/audio", data={"task": "vowel"},
                          files={"file": ("voice.wav", wav_bytes(silent=True), "audio/wav")}, headers=auth)
    assert silence.status_code == 200 and silence.json()["accepted"] is False
    assert silence.json()["session"]["files"] == []
    corrupt = client.post(f"/sessions/{identifier}/audio", data={"task": "vowel"},
                          files={"file": ("voice.wav", b"corrupt WAV container", "audio/wav")}, headers=auth)
    assert corrupt.status_code == 200 and corrupt.json()["accepted"] is False
    assert str(tmp_path) not in corrupt.text
    assert not list((tmp_path / "private").glob("mobile-analysis-*"))
    result = client.post(f"/sessions/{identifier}/audio", data={"task": "vowel"},
                         files={"file": ("voice.wav", wav_bytes(), "audio/wav")}, headers=auth)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["accepted"] is True
    assert 160 < body["result"]["features"]["f0_autocorrelation_median_hz"] < 200
    assert len(body["session"]["files"]) == 1
    assert "storage_key" not in result.text and str(tmp_path) not in result.text
    file_id = body["session"]["files"][0]["id"]
    url = f"/sessions/{identifier}/media/{file_id}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=other).status_code == 403
    media = client.get(url, headers=auth)
    assert media.status_code == 200 and media.content == wav_bytes()
    assert media.headers["cache-control"] == "no-store"
    assert client.post(f"/sessions/{identifier}/complete", json={}, headers=auth).status_code == 200


def test_consent_withdrawal_blocks_new_records_uploads_and_media(api):
    client, _, _ = api
    auth = headers(register(client))
    identifier = start(client, auth)
    result = client.post(f"/sessions/{identifier}/audio", data={"task": "vowel"},
                         files={"file": ("voice.wav", wav_bytes(), "audio/wav")}, headers=auth)
    file_id = result.json()["session"]["files"][0]["id"]
    assert client.post("/profile/consent", json={"acknowledged": False}, headers=auth).json()["active"] is False
    assert client.post("/sessions", json={}, headers=auth).status_code == 403
    assert client.post(f"/sessions/{identifier}/notes", json={"text": "Walking is difficult"}, headers=auth).status_code == 403
    assert client.get(f"/sessions/{identifier}/media/{file_id}", headers=auth).status_code == 403
    assert client.get("/sessions", headers=auth).status_code == 200
    assert client.post("/profile/consent", json={"acknowledged": True}, headers=auth).json()["active"] is True
    assert client.get(f"/sessions/{identifier}/media/{file_id}", headers=auth).status_code == 200


def test_limits_and_rejected_video_do_not_save_files(api):
    client, _, tmp_path = api
    auth = headers(register(client))
    identifier = start(client, auth)
    response = client.post(f"/sessions/{identifier}/video", data={"task": "gait"},
                           files={"file": ("walk.mp4", b"bad container" * 100, "video/mp4")}, headers=auth)
    assert response.status_code == 422
    assert str(tmp_path) not in response.text
    assert client.get(f"/sessions/{identifier}", headers=auth).json()["files"] == []
    with transaction() as session:
        assert session.scalar(select(func.count(AssessmentFile.id))) == 0
    huge = client.post(f"/sessions/{identifier}/notes", content=b"x" * 33000,
                       headers=auth | {"Content-Type": "application/json"})
    assert huge.status_code == 413
    upload = client.post(f"/sessions/{identifier}/audio", data={"task": "natural"},
                         files={"file": ("voice.wav", b"x" * (1024 * 1024 + 1), "audio/wav")}, headers=auth)
    assert upload.status_code == 413
    assert not list((tmp_path / "private").glob("mobile-analysis-*"))


def test_login_throttle_and_secret_file_durability_permissions(api, monkeypatch, tmp_path):
    _, _, _ = api
    application = create_app(secret=SECRET, initialize_database=False, rate_limit=True,
                             registry_path=tmp_path / "limited-sessions.sqlite3")
    with TestClient(application) as client:
        for _ in range(10):
            assert client.post("/auth/login", json={"email": "unknown@example.test", "password": "wrong"}).status_code == 401
        response = client.post("/auth/login", json={"email": "unknown@example.test", "password": "wrong"})
        assert response.status_code == 429 and response.headers["retry-after"] == "60"
    monkeypatch.delenv("PARKINSENSE_MOBILE_SECRET", raising=False)
    first = load_secret()
    assert first == load_secret() and len(first) == 64
    key = tmp_path / "private" / "mobile-api.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(key.parent.stat().st_mode) == 0o700
    monkeypatch.setenv("PARKINSENSE_MOBILE_SECRET", "short")
    with pytest.raises(ValueError):
        load_secret()


def test_chunked_oversized_multipart_closes_already_spooled_files(api, monkeypatch):
    """Exercise streaming limits after the multipart parser has opened a file."""
    client, application, tmp_path = api
    auth = headers(register(client))
    identifier = start(client, auth)
    import starlette.formparsers as formparsers
    original = formparsers.SpooledTemporaryFile
    opened = []

    def track(*args, **kwargs):
        handle = original(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", track)
    boundary = "mobile-boundary"
    opening = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"task\"\r\n\r\nnatural\r\n"
               f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.wav\"\r\n"
               "Content-Type: audio/wav\r\n\r\n").encode()
    chunks = [opening] + [b"x" * (256 * 1024) for _ in range(10)] + [f"\r\n--{boundary}--\r\n".encode()]
    messages = []

    async def exercise():
        events = iter(chunks)
        count = 0

        async def receive():
            nonlocal count
            chunk = next(events)
            count += 1
            return {"type": "http.request", "body": chunk, "more_body": count < len(chunks)}

        async def send(message):
            messages.append(message)

        path = f"/sessions/{identifier}/audio"
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
                 "root_path": "", "query_string": b"", "server": ("testserver", 80),
                 "client": ("127.0.0.1", 1234), "headers": [
                     (b"authorization", auth["Authorization"].encode()),
                     (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
                     (b"transfer-encoding", b"chunked")], "state": {}}
        await application(scope, receive, send)

    asyncio.run(exercise())
    assert next(message for message in messages if message["type"] == "http.response.start")["status"] == 413
    assert opened and all(handle.closed for handle in opened)
    assert client.get(f"/sessions/{identifier}", headers=auth).json()["files"] == []
    assert not list((tmp_path / "private").glob("mobile-analysis-*"))
