"""Portable SQLAlchemy schema; PostgreSQL is the runtime persistence engine."""

from datetime import date as calendar_date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class IdentityMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class User(IdentityMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('patient', 'clinician', 'admin')", name="users_role"),)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(30), default="English", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Patient(IdentityMixin, Base):
    __tablename__ = "patients"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    baseline_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Clinician(IdentityMixin, Base):
    __tablename__ = "clinicians"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)


class PatientClinicianLink(IdentityMixin, Base):
    __tablename__ = "patient_clinician_links"
    __table_args__ = (UniqueConstraint("patient_id", "clinician_id", name="patient_clinician_unique"),)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("clinicians.id"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class Consent(IdentityMixin, Base):
    __tablename__ = "consents"
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="monitoring-v1")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Assessment(IdentityMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (CheckConstraint("status IN ('draft', 'completed', 'abandoned')", name="assessment_status"),)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssessmentFile(IdentityMixin, Base):
    __tablename__ = "assessment_files"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ModuleResult(IdentityMixin, Base):
    __tablename__ = "module_results"
    __table_args__ = (UniqueConstraint("assessment_id", "module", name="assessment_module_unique"),)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_files.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ClinicalMeasurement(IdentityMixin, Base):
    __tablename__ = "clinical_measurements"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class ADLResponse(IdentityMixin, Base):
    __tablename__ = "adl_responses"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), unique=True, nullable=False)
    responses: Mapped[dict] = mapped_column(JSON, nullable=False)
    scale_name: Mapped[str] = mapped_column(String(80), default="nonvalidated-self-report-v1", nullable=False)


class ModelRun(IdentityMixin, Base):
    __tablename__ = "model_runs"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class ModelOutput(IdentityMixin, Base):
    __tablename__ = "model_outputs"
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), nullable=False, index=True)
    output: Mapped[dict] = mapped_column(JSON, nullable=False)


class Explanation(IdentityMixin, Base):
    __tablename__ = "explanations"
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, nullable=False)


class Report(IdentityMixin, Base):
    __tablename__ = "reports"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AuditLog(IdentityMixin, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DailyCheckin(IdentityMixin, Base):
    """Patient self-report, kept separate from automated assessments and scales."""

    __tablename__ = "daily_checkins"
    __table_args__ = (
        UniqueConstraint("patient_id", "date", name="daily_checkin_patient_date_unique"),
        CheckConstraint("energy BETWEEN 0 AND 4 AND sleep_quality BETWEEN 0 AND 4 "
                        "AND movement_ease BETWEEN 0 AND 4 AND mood BETWEEN 0 AND 4",
                        name="daily_checkin_response_bounds"),
        CheckConstraint("recorded_by_role IN ('patient', 'clinician')", name="daily_checkin_author_role"),
        Index("daily_checkin_patient_date", "patient_id", "date"),
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    date: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    energy: Mapped[int] = mapped_column(Integer, nullable=False)
    sleep_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_ease: Mapped[int] = mapped_column(Integer, nullable=False)
    mood: Mapped[int] = mapped_column(Integer, nullable=False)
    falls: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PersonalGoal(IdentityMixin, Base):
    __tablename__ = "personal_goals"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'paused')", name="personal_goal_status"),
        Index("personal_goal_patient_created", "patient_id", "created_at"),
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    authored_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CarePlan(IdentityMixin, Base):
    """Human clinician notes; no model-generated advice or prescribing logic."""

    __tablename__ = "care_plans"
    __table_args__ = (Index("care_plan_patient_created", "patient_id", "created_at"),)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    focus: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    next_review_date: Mapped[calendar_date | None] = mapped_column(Date, nullable=True)
    authored_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
