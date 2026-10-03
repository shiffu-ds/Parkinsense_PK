"""Additive pilot records; workflow evidence is separate from clinical results."""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base, IdentityMixin


class ClinicPilot(IdentityMixin, Base):
    __tablename__ = "clinic_pilots"
    __table_args__ = (CheckConstraint("status IN ('draft', 'active', 'closed')", name="clinic_pilot_status"),)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    targets: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    plan_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PilotEnrollment(IdentityMixin, Base):
    __tablename__ = "pilot_enrollments"
    __table_args__ = (UniqueConstraint("pilot_id", "patient_id", name="pilot_patient_unique"),)
    pilot_id: Mapped[str] = mapped_column(ForeignKey("clinic_pilots.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    consent_version: Mapped[str] = mapped_column(String(40), nullable=False, default="clinic-pilot-v1")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PilotReviewTimer(IdentityMixin, Base):
    __tablename__ = "pilot_review_timers"
    __table_args__ = (CheckConstraint("mode IN ('baseline', 'app')", name="pilot_timer_mode"),)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("pilot_enrollments.id"), nullable=False, index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class PilotObservation(IdentityMixin, Base):
    __tablename__ = "pilot_observations"
    __table_args__ = (
        CheckConstraint("planned_tasks >= attempted_tasks AND attempted_tasks >= completed_tasks "
                        "AND completed_tasks >= 0 AND planned_tasks BETWEEN 1 AND 100", name="pilot_task_counts"),
        CheckConstraint("recording_attempts >= usable_recordings AND usable_recordings >= 0 "
                        "AND recording_attempts <= 100", name="pilot_recording_counts"),
        UniqueConstraint("baseline_timer_id", name="pilot_baseline_timer_once"),
        UniqueConstraint("app_timer_id", name="pilot_app_timer_once"),
    )
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("pilot_enrollments.id"), nullable=False, index=True)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    planned_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    recording_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_recordings: Mapped[int] = mapped_column(Integer, nullable=False)
    usability_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    needed_help: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    device_category: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    baseline_review_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    app_review_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_timer_id: Mapped[str | None] = mapped_column(ForeignKey("pilot_review_timers.id"), nullable=True)
    app_timer_id: Mapped[str | None] = mapped_column(ForeignKey("pilot_review_timers.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PilotPaymentIntent(IdentityMixin, Base):
    __tablename__ = "pilot_payment_intents"
    __table_args__ = (CheckConstraint("intent IN ('yes', 'no', 'undecided')", name="pilot_payment_intent"),)
    pilot_id: Mapped[str] = mapped_column(ForeignKey("clinic_pilots.id"), nullable=False, index=True)
    respondent_role: Mapped[str] = mapped_column(String(30), nullable=False)
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period: Mapped[str] = mapped_column(String(30), nullable=False)
    reported_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
