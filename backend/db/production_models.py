"""Security state kept separate from clinical records and media bytes."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base, IdentityMixin, utc_now


class AccountSecurity(Base):
    __tablename__ = "account_security"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    session_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MediaGrant(IdentityMixin, Base):
    __tablename__ = "media_grants"
    __table_args__ = (
        Index("media_grants_actor_session", "actor_id", "session_hash"),
        CheckConstraint("(file_id IS NOT NULL AND artifact_id IS NULL) OR "
                        "(file_id IS NULL AND artifact_id IS NOT NULL)", name="media_grant_one_resource"),
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_files.id"), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("media_artifacts.id"), nullable=True)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaArtifact(IdentityMixin, Base):
    __tablename__ = "media_artifacts"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(60), nullable=False)
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecoveryToken(IdentityMixin, Base):
    __tablename__ = "recovery_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginFailure(IdentityMixin, Base):
    """Recent wrong-password sign-ins, keyed by a hash of the typed email, never the email."""
    __tablename__ = "login_failures"
    __table_args__ = (Index("login_failures_key_time", "limiter_hash", "created_at"),)
    limiter_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RecoveryAttempt(IdentityMixin, Base):
    __tablename__ = "recovery_attempts"
    # A presented high-entropy token hash is a safe limiter key; raw token never persists.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    limiter_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
