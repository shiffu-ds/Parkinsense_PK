"""Revocable media grants and administrator-verified account recovery.

UI actors must come from the authenticated server session. A media URL is a
short-lived bearer capability; it never embeds patient names or storage keys.
"""

from dataclasses import dataclass, field
from datetime import timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import delete, func, select, text, update

from backend.db import transaction
from backend.db.models import AssessmentFile, Patient, User, utc_now
from backend.db.production_models import (
    AccountSecurity, LoginFailure, MediaArtifact, MediaGrant, RecoveryAttempt, RecoveryToken,
)
from backend.security import hash_password
from backend.services import _actor, _admin, _assessment_access, _audit, _consented, _id, _iso, login_limiter_hash
from backend.storage import resolve_key

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
MEDIA_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm",
    "audio/wav", "audio/x-wav", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a",
    "audio/flac", "audio/x-flac", "application/ogg",
}
RECOVERY_ERROR = "Recovery code is invalid, expired, used, or temporarily unavailable."
ARTIFACT_TYPES = {"text/html", "application/json", "text/plain", "application/pdf", "text/csv"}


def _hash(value: str, purpose: str) -> str:
    return hashlib.sha256(f"{purpose}:{value}".encode("utf-8")).hexdigest()


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def media_gateway_url() -> str:
    base = os.getenv("PARKINSENSE_MEDIA_BASE_URL", "http://127.0.0.1:8503").rstrip("/")
    parsed = urlsplit(base)
    if any(char.isspace() or ord(char) < 32 for char in base):
        raise ValueError("Media base URL cannot contain whitespace or control characters.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Media base URL must contain only a trusted origin.")
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("Configure a valid trusted media origin.")
    try:
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid port.")
    except ValueError:
        raise ValueError("Configure a valid trusted media port.") from None
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("A public media origin must use HTTPS.")
    return base


def _revision(session, user_id: str) -> int:
    state = session.get(AccountSecurity, user_id)
    return state.session_revision if state else 0


def _lock_grant_subjects(session, actor, assessment) -> None:
    """Serialize against both actor password resets and patient consent withdrawal.

    Clinician actors and the patient owner are different users. Locking only the
    clinician would let a late-issued grant escape the patient's revoke update.
    """
    patient = session.get(Patient, assessment.patient_id)
    if patient is None:
        raise PermissionError("Media access is unavailable.")
    user_ids = sorted({actor.id, patient.user_id})
    session.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.id)
                    .with_for_update().execution_options(populate_existing=True)).all()
    if not actor.active:
        raise PermissionError("An active authenticated account is required.")


def session_revision(actor_id: str) -> int:
    with transaction() as session:
        actor = _actor(session, actor_id)
        return _revision(session, actor.id)


def verify_session_revision(actor_id: str, revision: int) -> None:
    with transaction() as session:
        actor = _actor(session, actor_id)
        if type(revision) is not int or revision != _revision(session, actor.id):
            raise PermissionError("Your password changed. Please sign in again.")


def create_media_grant(actor_id: str, assessment_id: str, file_id: str, *,
                       session_key: str, ttl_seconds: int = 180, expected_revision: int | None = None) -> dict:
    if type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 600:
        raise ValueError("Media access must expire within 30 to 600 seconds.")
    if not isinstance(session_key, str) or not 20 <= len(session_key) <= 256:
        raise ValueError("A server-generated session key is required.")
    origin = media_gateway_url()
    token = secrets.token_urlsafe(32)
    now = utc_now()
    with transaction() as session:
        actor, assessment = _assessment_access(session, actor_id, assessment_id)
        _lock_grant_subjects(session, actor, assessment)
        revision = _revision(session, actor.id)
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision != revision):
            raise PermissionError("Your password changed. Please sign in again.")
        _consented(session, assessment.patient_id)
        media = session.get(AssessmentFile, _id(file_id))
        if media is None or media.assessment_id != assessment.id:
            raise PermissionError("This media is unavailable for the selected assessment.")
        if media.mime_type not in MEDIA_TYPES or not resolve_key(media.storage_key).is_file():
            raise ValueError("A supported stored recording is required.")
        session_hash = _hash(session_key, "session")
        # Refreshing a player replaces its previous capability rather than growing an unlimited list.
        session.execute(update(MediaGrant).where(
            MediaGrant.actor_id == actor.id, MediaGrant.session_hash == session_hash,
            MediaGrant.file_id == media.id, MediaGrant.revoked_at.is_(None),
        ).values(revoked_at=now))
        grant = MediaGrant(token_hash=_hash(token, "media"), actor_id=actor.id,
                           assessment_id=assessment.id, file_id=media.id, session_hash=session_hash,
                           session_revision=revision, expires_at=now + timedelta(seconds=ttl_seconds))
        session.add(grant)
        _audit(session, actor.id, "media.grant_issued", "assessment", assessment.id)
        return {"url": f"{origin}/media/{token}", "expires_at": _iso(grant.expires_at)}


def revoke_media_grants(actor_id: str, *, session_key: str | None = None) -> None:
    with transaction() as session:
        # Called by logout with a previously authenticated actor, even if subsequently deactivated.
        actor = session.get(User, _id(actor_id))
        if actor is None:
            return
        query = update(MediaGrant).where(MediaGrant.actor_id == actor.id, MediaGrant.revoked_at.is_(None))
        if session_key is not None:
            query = query.where(MediaGrant.session_hash == _hash(session_key, "session"))
        session.execute(query.values(revoked_at=utc_now()))
        _audit(session, actor.id, "media.grants_revoked", "user", actor.id)


@dataclass(frozen=True)
class MediaResource:
    path: Path = field(repr=False)
    mime_type: str
    size_bytes: int
    filename: str | None = None


def authorize_media_token(token: str) -> MediaResource:
    """Recheck active account, current link, current consent and revocation on every request."""
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise PermissionError("Media access is unavailable.")
    with transaction() as session:
        grant = session.scalar(select(MediaGrant).where(MediaGrant.token_hash == _hash(token, "media")))
        if grant is None or grant.revoked_at or _utc(grant.expires_at) <= utc_now():
            raise PermissionError("Media access is unavailable.")
        actor, assessment = _assessment_access(session, grant.actor_id, grant.assessment_id)
        _consented(session, assessment.patient_id)
        if grant.session_revision != _revision(session, actor.id):
            raise PermissionError("Media access is unavailable.")
        media = session.get(AssessmentFile, grant.file_id) if grant.file_id else session.get(MediaArtifact, grant.artifact_id)
        allowed_types = MEDIA_TYPES if grant.file_id else ARTIFACT_TYPES
        if media is None or media.assessment_id != assessment.id or media.mime_type not in allowed_types:
            raise PermissionError("Media access is unavailable.")
        if not grant.file_id and _utc(media.expires_at) <= utc_now():
            raise PermissionError("Media access is unavailable.")
        path = resolve_key(media.storage_key)
        if not path.is_file() or path.stat().st_size != media.size_bytes:
            raise PermissionError("Media access is unavailable.")
        return MediaResource(path=path, mime_type=media.mime_type, size_bytes=media.size_bytes,
                             filename=media.filename if not grant.file_id else None)


def create_artifact_grant(actor_id: str, assessment_id: str, data: bytes | str, filename: str,
                          mime_type: str, *, session_key: str, ttl_seconds: int = 180,
                          expected_revision: int | None = None) -> dict:
    """Publish a server-generated report/export privately with the same live authorization checks."""
    if mime_type not in ARTIFACT_TYPES or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", filename or ""):
        raise ValueError("Choose a supported export format and a plain filename.")
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, bytes) or not 0 < len(data) <= 10 * 1024 * 1024:
        raise ValueError("Generated exports must contain 1 byte to 10 MB.")
    if not isinstance(session_key, str) or not 20 <= len(session_key) <= 256:
        raise ValueError("A server-generated session key is required.")
    if type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 600:
        raise ValueError("Export access must expire within 30 to 600 seconds.")
    origin, token, now = media_gateway_url(), secrets.token_urlsafe(32), utc_now()
    path = None
    try:
        with transaction() as session:
            actor, assessment = _assessment_access(session, actor_id, assessment_id)
            _lock_grant_subjects(session, actor, assessment)
            revision = _revision(session, actor.id)
            if expected_revision is not None and (type(expected_revision) is not int or expected_revision != revision):
                raise PermissionError("Your password changed. Please sign in again.")
            _consented(session, assessment.patient_id)
            key = f"patient_{assessment.patient_id}/assessment_{assessment.id}/export_{uuid4()}.private"
            path = resolve_key(key)
            path.parent.parent.mkdir(mode=0o700, exist_ok=True)
            path.parent.mkdir(mode=0o700, exist_ok=True)
            path.parent.parent.chmod(0o700)
            path.parent.chmod(0o700)
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600), "wb") as handle:
                handle.write(data)
            artifact = MediaArtifact(assessment_id=assessment.id, storage_key=key,
                                     mime_type=mime_type, filename=filename, size_bytes=len(data),
                                     expires_at=now + timedelta(seconds=ttl_seconds))
            session.add(artifact)
            session.flush()
            session.add(MediaGrant(token_hash=_hash(token, "media"), actor_id=actor.id,
                                   assessment_id=assessment.id, artifact_id=artifact.id,
                                   session_hash=_hash(session_key, "session"),
                                   session_revision=revision, expires_at=artifact.expires_at))
            _audit(session, actor.id, "export.grant_issued", "assessment", assessment.id)
            result = {"url": f"{origin}/media/{token}", "expires_at": _iso(artifact.expires_at)}
        return result
    except BaseException:
        if path is not None:
            path.unlink(missing_ok=True)
        raise


def prune_expired_capabilities() -> dict:
    """Local operator housekeeping; delete expired generated exports, never source recordings."""
    now = utc_now()
    count = 0
    with transaction() as session:
        artifacts = session.scalars(select(MediaArtifact).where(MediaArtifact.expires_at <= now).with_for_update()).all()
        for artifact in artifacts:
            path = resolve_key(artifact.storage_key)
            # Delete bytes before metadata, so an I/O failure does not silently orphan private material.
            path.unlink(missing_ok=True)
            session.execute(delete(MediaGrant).where(MediaGrant.artifact_id == artifact.id))
            session.delete(artifact)
            count += 1
        # Retain only a short operational window of capability hashes/failed token attempts.
        session.execute(delete(MediaGrant).where(MediaGrant.expires_at < now - timedelta(days=1)))
        session.execute(delete(RecoveryAttempt).where(RecoveryAttempt.created_at < now - timedelta(days=1)))
        session.execute(delete(RecoveryToken).where(RecoveryToken.expires_at < now - timedelta(days=1)))
    return {"expired_exports_removed": count}


def issue_recovery_token(admin_id: str, user_id: str, *, identity_verified: bool,
                         ttl_minutes: int = 20) -> str:
    """Only a verified human support workflow may issue a code; no public issue endpoint."""
    if identity_verified is not True:
        raise PermissionError("Verify the account owner's identity through the clinic first.")
    if type(ttl_minutes) is not int or not 5 <= ttl_minutes <= 30:
        raise ValueError("Recovery codes must expire within 5 to 30 minutes.")
    token = secrets.token_urlsafe(32)
    now = utc_now()
    with transaction() as session:
        admin = _admin(session, admin_id)
        target = session.scalar(select(User).where(User.id == _id(user_id)).with_for_update())
        if target is None or not target.active:
            raise PermissionError("An active verified account is required.")
        count = session.scalar(select(func.count(RecoveryToken.id)).where(
            RecoveryToken.user_id == target.id, RecoveryToken.created_at > now - timedelta(minutes=30)))
        if count >= 3:
            raise PermissionError("Recovery was already issued recently. Try again later.")
        session.execute(update(RecoveryToken).where(
            RecoveryToken.user_id == target.id, RecoveryToken.used_at.is_(None),
            RecoveryToken.revoked_at.is_(None)).values(revoked_at=now))
        session.add(RecoveryToken(token_hash=_hash(token, "recovery"), user_id=target.id,
                                  issued_by=admin.id, expires_at=now + timedelta(minutes=ttl_minutes)))
        _audit(session, admin.id, "recovery.issued_verified", "user", target.id)
    return token


def redeem_recovery_token(token: str, new_password: str, *, request_key: str = "local-recovery") -> None:
    """Consume once, invalidate sessions/grants, then require normal sign-in.

    request_key is a stable server-side client bucket, never a submitted email.
    Deployments must also rate-limit the recovery route at their reverse proxy.
    """
    if not isinstance(request_key, str) or not 1 <= len(request_key) <= 256:
        raise ValueError("Recovery request context is invalid.")
    if isinstance(token, str):
        token = token.strip()
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        token = "invalid"
    encoded = hash_password(new_password)
    token_hash = _hash(token, "recovery")
    limiter_hash = _hash(request_key, "recovery-client")
    now = utc_now()
    success = False
    with transaction() as session:
        if session.bind.dialect.name == "postgresql":
            # Serialize the persistent limiter across workers, without storing client identifiers.
            limiter_id = int(limiter_hash[:15], 16)
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": limiter_id})
        recent = RecoveryAttempt.created_at > now - timedelta(minutes=15)
        client_count = session.scalar(select(func.count(RecoveryAttempt.id)).where(
            recent, RecoveryAttempt.limiter_hash == limiter_hash))
        token_count = session.scalar(select(func.count(RecoveryAttempt.id)).where(
            recent, RecoveryAttempt.token_hash == token_hash))
        if client_count < 12 and token_count < 5:
            candidate = session.scalar(select(RecoveryToken).where(RecoveryToken.token_hash == token_hash))
            if candidate is not None:
                # Match issuance's user-before-token lock order to avoid a reset/reissue deadlock.
                user = session.scalar(select(User).where(User.id == candidate.user_id).with_for_update())
                recovery = session.scalar(select(RecoveryToken).where(
                    RecoveryToken.id == candidate.id).with_for_update().execution_options(populate_existing=True))
                if (user is not None and user.active and recovery is not None and recovery.used_at is None
                        and recovery.revoked_at is None and _utc(recovery.expires_at) > now):
                    user.password_hash = encoded
                    recovery.used_at = now
                    state = session.get(AccountSecurity, user.id)
                    if state is None:
                        state = AccountSecurity(user_id=user.id, session_revision=0)
                        session.add(state)
                    state.session_revision += 1
                    state.updated_at = now
                    session.execute(update(RecoveryToken).where(
                        RecoveryToken.user_id == user.id, RecoveryToken.id != recovery.id,
                        RecoveryToken.revoked_at.is_(None)).values(revoked_at=now))
                    session.execute(update(MediaGrant).where(
                        MediaGrant.actor_id == user.id, MediaGrant.revoked_at.is_(None)).values(revoked_at=now))
                    # A verified recovery lets the person sign in straight away with the new password.
                    session.execute(delete(LoginFailure).where(LoginFailure.limiter_hash == login_limiter_hash(user.email)))
                    _audit(session, user.id, "recovery.completed", "user", user.id)
                    success = True
        session.add(RecoveryAttempt(token_hash=token_hash, limiter_hash=limiter_hash, succeeded=int(success)))
        if not success:
            _audit(session, None, "recovery.failed")
    if not success:
        raise PermissionError(RECOVERY_ERROR)
