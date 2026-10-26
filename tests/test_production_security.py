"""Isolated security tests; no real users, recordings or clinic credentials."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import secrets
import stat
import tarfile
from threading import Barrier, Event, Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidTag
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from backend import services as svc
from backend.db import get_engine, transaction
from backend.db.models import Base, Consent, User, utc_now
from backend.db.production_models import MediaGrant, RecoveryAttempt, RecoveryToken
from backend.production import (
    authorize_media_token, create_artifact_grant, create_media_grant, issue_recovery_token,
    media_gateway_url, prune_expired_capabilities, redeem_recovery_token, revoke_media_grants,
    session_revision, verify_session_revision,
)
from scripts.backup_private import create_backup, decoded, _encoded
from scripts.restore_drill import restore_drill, safe_extract
from scripts.secure_media_server import MAX_RANGE_BYTES, MediaHandler, MediaHTTPServer, parse_range

PASSWORD = "A deliberately chosen test passphrase 2026"
NEW_PASSWORD = "A different deliberate test passphrase 2026"
BACKUP_PHRASE = "Separate encrypted backup phrase for tests"


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    private = tmp_path / "private"
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(private))
    monkeypatch.setenv("PARKINSENSE_MEDIA_BASE_URL", "http://127.0.0.1:8503")
    test_url = os.getenv("PARKINSENSE_SECURITY_TEST_DATABASE_URL")
    if test_url:
        if not (make_url(test_url).database or "").startswith("parkinsense_test_security_"):
            raise ValueError("Security integration tests require a dedicated parkinsense_test_security_* database.")
        svc.configure_db(test_url)
        Base.metadata.drop_all(get_engine())
    else:
        svc.configure_db(f"sqlite:///{tmp_path / 'security.sqlite3'}", allow_sqlite=True)
    svc.init_db()
    admin = svc.bootstrap_admin("Test Administrator", "admin@example.test", PASSWORD)
    patient = svc.register_patient("Test Patient", "patient@example.test", PASSWORD, consent=True)
    other = svc.register_patient("Other Patient", "other@example.test", PASSWORD, consent=True)
    clinician = svc.create_staff(admin["id"], "Test Clinician", "clinician@example.test", PASSWORD)
    assessment = svc.create_assessment(patient["id"])
    key = svc.store_upload(patient["id"], assessment["id"], "gait", "walk.mp4", b"0123456789" * 100)
    media = svc.get_assessment(patient["id"], assessment["id"])["files"][0]
    return {"admin": admin, "patient": patient, "other": other, "clinician": clinician,
            "assessment": assessment, "file": media, "key": key, "session": secrets.token_urlsafe(32)}


def grant(a, actor="patient", **kwargs):
    return create_media_grant(a[actor]["id"], a["assessment"]["id"], a["file"]["id"],
                              session_key=kwargs.pop("session_key", a["session"]), **kwargs)


def token(result):
    return result["url"].rsplit("/", 1)[1]


def test_media_grant_is_opaque_hashed_and_scope_authorized(accounts):
    a = accounts
    result = grant(a)
    raw = token(result)
    assert len(raw) == 43
    assert a["key"] not in result["url"] and a["patient"]["full_name"] not in result["url"]
    assert authorize_media_token(raw).path.read_bytes() == b"0123456789" * 100
    with transaction() as session:
        saved = session.scalar(select(MediaGrant))
        assert saved.token_hash != raw and raw not in str(saved.__dict__)
    for actor in ("other", "admin", "clinician"):
        with pytest.raises(PermissionError):
            grant(a, actor)
    svc.link_patient(a["admin"]["id"], a["patient"]["patient_id"], a["clinician"]["clinician_id"])
    clinician_grant = grant(a, "clinician")
    assert authorize_media_token(token(clinician_grant)).size_bytes == 1000
    svc.unlink_patient(a["admin"]["id"], a["patient"]["patient_id"], a["clinician"]["clinician_id"])
    with pytest.raises(PermissionError):
        authorize_media_token(token(clinician_grant))


@pytest.mark.parametrize("change", ["expire", "consent", "inactive"])
def test_live_authorization_checks_expiry_consent_and_active_actor(accounts, change):
    a = accounts
    raw = token(grant(a))
    with transaction() as session:
        if change == "expire":
            session.scalar(select(MediaGrant)).expires_at = utc_now() - timedelta(seconds=1)
        elif change == "consent":
            session.scalar(select(Consent).where(Consent.patient_id == a["patient"]["patient_id"])).withdrawn_at = utc_now()
        else:
            session.get(User, a["patient"]["id"]).active = False
    with pytest.raises(PermissionError):
        authorize_media_token(raw)


def test_refresh_and_logout_revoke_only_selected_session(accounts):
    a = accounts
    old = token(grant(a))
    current = token(grant(a))
    other_session = token(grant(a, session_key=secrets.token_urlsafe(32)))
    with pytest.raises(PermissionError):
        authorize_media_token(old)
    revoke_media_grants(a["patient"]["id"], session_key=a["session"])
    with pytest.raises(PermissionError):
        authorize_media_token(current)
    assert authorize_media_token(other_session).size_bytes == 1000


def test_media_configuration_rejects_insecure_public_origins(monkeypatch):
    for base in ("http://example.test", "https://user:secret@example.test", "https://example.test?secret=x", "file:///tmp", "https://example.test/media", "https://example.test:99999", "https://example.test\n"):
        monkeypatch.setenv("PARKINSENSE_MEDIA_BASE_URL", base)
        with pytest.raises(ValueError):
            media_gateway_url()
    monkeypatch.setenv("PARKINSENSE_MEDIA_BASE_URL", "https://media.example.test")
    assert media_gateway_url() == "https://media.example.test"


def test_generated_artifacts_use_authorized_attachment_and_cleanup(accounts):
    a = accounts
    result = create_artifact_grant(a["patient"]["id"], a["assessment"]["id"], "<h1>Private report</h1>",
                                   "patient-report.html", "text/html", session_key=a["session"])
    resource = authorize_media_token(token(result))
    assert resource.filename == "patient-report.html"
    assert resource.path.read_bytes() == b"<h1>Private report</h1>"
    assert stat.S_IMODE(resource.path.stat().st_mode) == 0o600
    with pytest.raises(PermissionError):
        create_artifact_grant(a["other"]["id"], a["assessment"]["id"], "x", "report.html", "text/html", session_key=a["session"])
    with pytest.raises(ValueError):
        create_artifact_grant(a["patient"]["id"], a["assessment"]["id"], "x", "../report.html", "text/html", session_key=a["session"])
    from backend.db.production_models import MediaArtifact
    with transaction() as session:
        session.scalar(select(MediaArtifact)).expires_at = utc_now() - timedelta(seconds=1)
    assert prune_expired_capabilities()["expired_exports_removed"] == 1
    assert not resource.path.exists()
    assert Path(svc.get_media_path(a["patient"]["id"], a["assessment"]["id"], a["key"])).exists()


def test_recovery_is_verified_admin_only_single_use_and_invalidates_sessions(accounts):
    a = accounts
    old_revision = session_revision(a["patient"]["id"])
    raw_media = token(grant(a, expected_revision=old_revision))
    with pytest.raises(PermissionError):
        issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=False)
    with pytest.raises(PermissionError):
        issue_recovery_token(a["patient"]["id"], a["patient"]["id"], identity_verified=True)
    code = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    with transaction() as session:
        saved = session.scalar(select(RecoveryToken))
        assert code not in str(saved.__dict__)
    redeem_recovery_token(code, NEW_PASSWORD, request_key="test-browser")
    assert svc.authenticate(a["patient"]["email"], NEW_PASSWORD)["id"] == a["patient"]["id"]
    assert session_revision(a["patient"]["id"]) == old_revision + 1
    with pytest.raises(PermissionError):
        svc.authenticate(a["patient"]["email"], PASSWORD)
    with pytest.raises(PermissionError):
        redeem_recovery_token(code, PASSWORD)
    with pytest.raises(PermissionError):
        verify_session_revision(a["patient"]["id"], old_revision)
    with pytest.raises(PermissionError):
        grant(a, expected_revision=old_revision)
    with pytest.raises(PermissionError):
        authorize_media_token(raw_media)


def test_authenticated_result_cannot_start_a_session_after_password_reset(accounts, monkeypatch):
    from app.components import private_access
    a = accounts
    checked_before_reset = svc.authenticate(a["patient"]["email"], PASSWORD)
    assert checked_before_reset["_auth_revision"] == 0
    code = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    redeem_recovery_token(code, NEW_PASSWORD, request_key="verified-recovery-browser")
    previous_key = secrets.token_urlsafe(32)
    state = SimpleNamespace(user_id=a["other"]["id"], auth_revision=1, media_session_key=previous_key)
    monkeypatch.setattr(private_access.st, "session_state", state)
    with pytest.raises(PermissionError):
        private_access.begin_session(checked_before_reset)
    assert state.user_id == a["other"]["id"]
    assert state.auth_revision == 1 and state.media_session_key == previous_key
    freshly_checked = svc.authenticate(a["patient"]["email"], NEW_PASSWORD)
    assert freshly_checked["_auth_revision"] == 1
    private_access.begin_session(freshly_checked)
    assert state.user_id == a["patient"]["id"] and state.auth_revision == 1
    assert len(state.media_session_key) >= 32


def test_recovery_reissue_revokes_prior_and_has_persistent_rate_limit(accounts):
    a = accounts
    old = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    current = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    with pytest.raises(PermissionError):
        redeem_recovery_token(old, NEW_PASSWORD, request_key="old-code-browser")
    for _ in range(12):
        with pytest.raises(PermissionError):
            redeem_recovery_token(secrets.token_urlsafe(32), NEW_PASSWORD, request_key="limited-browser")
    with pytest.raises(PermissionError):
        redeem_recovery_token(current, NEW_PASSWORD, request_key="limited-browser")
    with transaction() as session:
        assert session.scalar(select(func.count(RecoveryAttempt.id))) == 14
    redeem_recovery_token(current, NEW_PASSWORD, request_key="fresh-browser")


@pytest.mark.parametrize("change", ["expired", "inactive"])
def test_expired_or_inactive_recovery_is_rejected(accounts, change):
    a = accounts
    code = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    with transaction() as session:
        if change == "expired":
            session.scalar(select(RecoveryToken)).expires_at = utc_now() - timedelta(minutes=1)
        else:
            session.get(User, a["patient"]["id"]).active = False
    with pytest.raises(PermissionError):
        redeem_recovery_token(code, NEW_PASSWORD)


@pytest.mark.skipif(not os.getenv("PARKINSENSE_SECURITY_TEST_DATABASE_URL"), reason="Row-lock race requires isolated PostgreSQL.")
def test_concurrent_recovery_can_only_consume_once_on_postgresql(accounts):
    a = accounts
    code = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    barrier = Barrier(2)

    def consume(bucket):
        barrier.wait(timeout=10)
        try:
            redeem_recovery_token(code, NEW_PASSWORD, request_key=bucket)
            return "success"
        except PermissionError:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(consume, bucket) for bucket in ("first-browser", "second-browser")]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(results) == ["denied", "success"]
    assert session_revision(a["patient"]["id"]) == 1


@pytest.mark.skipif(not os.getenv("PARKINSENSE_SECURITY_TEST_DATABASE_URL"), reason="Consent/issuance race requires isolated PostgreSQL.")
def test_clinician_grant_cannot_revive_after_concurrent_withdrawal_and_renewal(accounts):
    from backend.services.privacy import set_monitoring_consent
    a = accounts
    svc.link_patient(a["admin"]["id"], a["patient"]["patient_id"], a["clinician"]["clinician_id"])
    barrier = Barrier(2)

    def issue():
        barrier.wait(timeout=10)
        try:
            return token(grant(a, "clinician"))
        except PermissionError:
            return None

    def withdraw():
        barrier.wait(timeout=10)
        set_monitoring_consent(a["patient"]["id"], acknowledged=False)

    with ThreadPoolExecutor(max_workers=2) as workers:
        issued = workers.submit(issue)
        withdrawn = workers.submit(withdraw)
        raw = issued.result(timeout=10)
        withdrawn.result(timeout=10)
    set_monitoring_consent(a["patient"]["id"], acknowledged=True)
    if raw is not None:
        with pytest.raises(PermissionError):
            authorize_media_token(raw)
    # A fresh post-renewal grant is permitted, proving the old code was revoked rather than access globally disabled.
    assert authorize_media_token(token(grant(a, "clinician"))).size_bytes == 1000


@pytest.mark.skipif(not os.getenv("PARKINSENSE_SECURITY_TEST_DATABASE_URL"), reason="Patient-owner row lock requires isolated PostgreSQL.")
def test_linked_clinician_issuance_holds_patient_owner_lock(accounts, monkeypatch):
    import backend.production as production
    a = accounts
    svc.link_patient(a["admin"]["id"], a["patient"]["patient_id"], a["clinician"]["clinician_id"])
    ready, release = Event(), Event()
    consented = production._consented

    def paused_consent_check(session, patient_id):
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("Synthetic lock test timed out.")
        return consented(session, patient_id)

    monkeypatch.setattr(production, "_consented", paused_consent_check)
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(grant, a, "clinician")
        try:
            assert ready.wait(timeout=10)
            # NOWAIT proves ownership of the exact patient-owner row without timing assumptions.
            with pytest.raises(DBAPIError) as blocked:
                with transaction() as session:
                    session.scalar(select(User).where(User.id == a["patient"]["id"]).with_for_update(nowait=True))
            assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
        finally:
            release.set()
        pending.result(timeout=10)


@pytest.mark.parametrize("header,expected", [(None, (0, 99, False)), ("bytes=10-19", (10, 19, True)),
                                            ("bytes=90-", (90, 99, True)), ("bytes=-7", (93, 99, True))])
def test_range_parsing(header, expected):
    assert parse_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=20-10", "bytes=0-1,4-5", "bytes=-0", "bytes=-", "bad"])
def test_invalid_ranges_rejected(header):
    with pytest.raises(ValueError):
        parse_range(header, 100)


def test_range_is_bounded():
    assert parse_range("bytes=0-", MAX_RANGE_BYTES * 3) == (0, MAX_RANGE_BYTES - 1, True)


def test_gateway_head_range_headers_artifacts_and_revocation(accounts):
    a = accounts
    raw = token(grant(a))
    server = MediaHTTPServer(("127.0.0.1", 0), MediaHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    url = f"{origin}/media/{raw}"
    try:
        with urlopen(Request(url, headers={"Range": "bytes=10-19"}), timeout=3) as response:
            assert response.status == 206 and response.read() == b"0123456789"
            assert response.headers["Content-Range"] == "bytes 10-19/1000"
            assert "no-store" in response.headers["Cache-Control"]
            assert response.headers["Referrer-Policy"] == "no-referrer"
        with urlopen(Request(url, method="HEAD"), timeout=3) as response:
            assert response.headers["Content-Length"] == "1000" and not response.read()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, headers={"Range": "bytes=1000-"}), timeout=3)
        assert error.value.code == 416 and error.value.headers["Content-Range"] == "bytes */1000"
        report = create_artifact_grant(a["patient"]["id"], a["assessment"]["id"], "private", "report.html", "text/html", session_key=a["session"])
        with urlopen(f"{origin}/media/{token(report)}", timeout=3) as response:
            assert response.read() == b"private"
            assert response.headers["Content-Disposition"] == 'attachment; filename="report.html"'
            assert "sandbox" in response.headers["Content-Security-Policy"]
        revoke_media_grants(a["patient"]["id"], session_key=a["session"])
        with pytest.raises(HTTPError) as error:
            urlopen(url, timeout=3)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_backup_roundtrip_checksums_database_media_and_no_production_changes(accounts, tmp_path):
    a = accounts
    safe = tmp_path / "backups"
    safe.mkdir(mode=0o700)
    backup = safe / "snapshot.pspk"
    from backend.services.care import save_checkin
    save_checkin(a["patient"]["id"], {"date": "2026-10-01", "energy": 3, "sleep_quality": 2,
                                       "movement_ease": 4, "mood": 1, "falls": None,
                                       "note": "آج بہتر محسوس ہوا"})
    svc.save_module(a["patient"]["id"], a["assessment"]["id"], "gait",
                    {"status": "accepted", "quality": {"accepted": True}, "features": {"duration_s": 10.0},
                     "custom_json": {"$type": "datetime", "value": "patient text"}})
    before = svc.get_assessment(a["patient"]["id"], a["assessment"]["id"])
    result = create_backup(backup, BACKUP_PHRASE, writes_paused=True)
    assert result["media_files"] == 1 and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert b"patient@example.test" not in backup.read_bytes()
    drill = safe / "drill"
    verified = restore_drill(backup, drill, BACKUP_PHRASE)
    assert verified["checksums_verified"] and verified["production_database_modified"] is False
    assert verified["database_counts"]["users"] == 4
    assert verified["database_counts"]["daily_checkins"] == 1
    assert (drill / "media" / a["key"]).read_bytes() == b"0123456789" * 100
    assert stat.S_IMODE((drill / "drill.sqlite3").stat().st_mode) == 0o600
    assert svc.get_assessment(a["patient"]["id"], a["assessment"]["id"]) == before
    assert not list(safe.glob(".parkinsense-*"))
    with pytest.raises(ValueError):
        restore_drill(backup, drill, BACKUP_PHRASE)


def test_backup_requires_maintenance_and_rejects_symlinks(accounts, tmp_path):
    safe = tmp_path / "backups"
    safe.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="Pause"):
        create_backup(safe / "test.pspk", BACKUP_PHRASE, writes_paused=False)
    (tmp_path / "private" / "linked-file").symlink_to(tmp_path / "outside-file")
    with pytest.raises(ValueError, match="symlinks"):
        create_backup(safe / "test.pspk", BACKUP_PHRASE, writes_paused=True)
    assert not (safe / "test.pspk").exists()


def test_wrong_passphrase_or_tampering_leaves_no_restore_directory(accounts, tmp_path):
    safe = tmp_path / "backups"
    safe.mkdir(mode=0o700)
    backup = safe / "test.pspk"
    create_backup(backup, BACKUP_PHRASE, writes_paused=True)
    with pytest.raises(InvalidTag):
        restore_drill(backup, safe / "wrong-pass", "Another sufficiently long incorrect phrase")
    assert not (safe / "wrong-pass").exists()
    encoded = bytearray(backup.read_bytes())
    encoded[-30] ^= 1
    backup.write_bytes(encoded)
    with pytest.raises(InvalidTag):
        restore_drill(backup, safe / "tampered", BACKUP_PHRASE)
    assert not (safe / "tampered").exists()


@pytest.mark.parametrize("name,type_", [("../escape", None), ("/escape", None), ("media/link", tarfile.SYMTYPE)])
def test_restore_archive_rejects_path_traversal_and_symlinks(tmp_path, name, type_):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as bundle:
        entry = tarfile.TarInfo(name)
        if type_:
            entry.type, entry.linkname = type_, "/etc/passwd"
            bundle.addfile(entry)
        else:
            entry.size = 1
            bundle.addfile(entry, BytesIO(b"x"))
    target = tmp_path / "staging"
    target.mkdir()
    with pytest.raises(ValueError):
        safe_extract(archive, target)


def test_database_json_payload_is_not_confused_with_scalar_type_metadata():
    payload = {"$type": "datetime", "value": "text typed by a patient"}
    assert decoded(_encoded(payload)) == payload


@pytest.mark.parametrize("value", [datetime(2026, 10, 3, 12, 30, tzinfo=timezone.utc), date(2026, 10, 3),
                                  Decimal("13.2500"), b"\x00\xff\x10", None, False])
def test_backup_scalar_types_round_trip(value):
    assert decoded(_encoded(value)) == value


def test_verified_recovery_lifts_a_sign_in_pause(accounts):
    a = accounts
    for _ in range(svc.LOGIN_FAILURE_LIMIT):
        with pytest.raises(PermissionError):
            svc.authenticate(a["patient"]["email"], "a wrong password")
    with pytest.raises(PermissionError, match="Too many"):
        svc.authenticate(a["patient"]["email"], PASSWORD)
    code = issue_recovery_token(a["admin"]["id"], a["patient"]["id"], identity_verified=True)
    redeem_recovery_token(code, NEW_PASSWORD, request_key="test-browser")
    assert svc.authenticate(a["patient"]["email"], NEW_PASSWORD)["id"] == a["patient"]["id"]
