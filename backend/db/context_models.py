"""Additive visit context: what the patient reports about medicine timing.

Parkinson's motor performance often follows the medication cycle, so a
recording made while "OFF" is not comparable with one made while "ON". This
table only records what the patient (or a linked clinician transcribing for
them) reports. It never stores doses, drug names or advice.
"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base, IdentityMixin, utc_now

MEDICATION_STATES = ("on", "wearing_off", "off", "unsure", "none")
DOSE_WINDOWS = ("lt1", "1_2", "2_4", "gt4", "unsure")
DYSKINESIA = ("yes", "no", "unsure")


class VisitContext(IdentityMixin, Base):
    __tablename__ = "visit_contexts"
    __table_args__ = (
        CheckConstraint("medication_state IN ('on', 'wearing_off', 'off', 'unsure', 'none')", name="visit_context_state"),
        CheckConstraint("dose_window IS NULL OR dose_window IN ('lt1', '1_2', '2_4', 'gt4', 'unsure')", name="visit_context_dose"),
        CheckConstraint("dyskinesia IS NULL OR dyskinesia IN ('yes', 'no', 'unsure')", name="visit_context_dyskinesia"),
    )
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), unique=True, nullable=False, index=True)
    medication_state: Mapped[str] = mapped_column(String(20), nullable=False)
    dose_window: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dyskinesia: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


DIARY_STATES = ("on", "on_dyskinesia", "wearing_off", "off")


class MedicationDiaryEntry(IdentityMixin, Base):
    """One moment the patient reports how their medicine is working; never a drug name or dose."""
    __tablename__ = "medication_diary_entries"
    __table_args__ = (
        CheckConstraint("state IN ('on', 'on_dyskinesia', 'wearing_off', 'off')", name="medication_diary_state"),
        Index("medication_diary_patient_time", "patient_id", "observed_at"),
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_by_role: Mapped[str] = mapped_column(String(20), nullable=False)


class MedicineTimes(Base):
    """The patient's usual medicine times (HH:MM, Pakistan time), used only for on-screen reminders."""
    __tablename__ = "medicine_times"
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    times: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


PLAN_GROUPS = ("gait", "hand", "transfer", "reach", "touch", "voice", "adl")


class TaskPlan(IdentityMixin, Base):
    """A linked clinician's suggested weekly rhythm of tasks; the newest plan is current."""
    __tablename__ = "task_plans"
    __table_args__ = (Index("task_plan_patient_created", "patient_id", "created_at"),)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False)  # {"gait": [0, 3]} with Monday as 0.
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    authored_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


HELPERS = ("alone", "family", "caregiver", "clinic_staff", "other")
WALKING_AIDS = ("none", "cane", "walker", "wheelchair", "other")


class VisitAssistance(IdentityMixin, Base):
    """Who helped during a visit and which walking aid was used: context for comparing recordings."""
    __tablename__ = "visit_assistance"
    __table_args__ = (
        CheckConstraint("helper IN ('alone', 'family', 'caregiver', 'clinic_staff', 'other')", name="visit_assistance_helper"),
        CheckConstraint("walking_aid IN ('none', 'cane', 'walker', 'wheelchair', 'other')", name="visit_assistance_aid"),
    )
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), unique=True, nullable=False, index=True)
    helper: Mapped[str] = mapped_column(String(20), nullable=False)
    walking_aid: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CheckinAssistance(Base):
    """Who helped fill in one daily check-in; absent when nobody said."""
    __tablename__ = "checkin_assistance"
    __table_args__ = (CheckConstraint("helper IN ('alone', 'family', 'caregiver', 'clinic_staff', 'other')", name="checkin_assistance_helper"),)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("daily_checkins.id"), primary_key=True)
    helper: Mapped[str] = mapped_column(String(20), nullable=False)
