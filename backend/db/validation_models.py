"""Additive, consented reference-measurement studies."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base, IdentityMixin


class ValidationStudy(IdentityMixin, Base):
    __tablename__ = "validation_studies"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    protocol: Mapped[dict] = mapped_column(JSON, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ValidationParticipation(IdentityMixin, Base):
    __tablename__ = "validation_participations"
    __table_args__ = (UniqueConstraint("study_id", "patient_id", name="validation_participant_once"),)
    study_id: Mapped[str] = mapped_column(ForeignKey("validation_studies.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ValidationCase(IdentityMixin, Base):
    __tablename__ = "validation_cases"
    __table_args__ = (UniqueConstraint("study_id", "assessment_id", "module_revision", name="validation_source_once"),)
    study_id: Mapped[str] = mapped_column(ForeignKey("validation_studies.id"), nullable=False, index=True)
    participation_id: Mapped[str] = mapped_column(ForeignKey("validation_participations.id"), nullable=False)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    module_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("assessment_files.id"), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measured: Mapped[float] = mapped_column(Float, nullable=False)
    reference: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_blinded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metadata_values: Mapped[dict] = mapped_column(JSON, nullable=False)
