"""A clinician's caseload at a glance, without loading recordings or results.

Only linked patients are included and only counts, dates and the
patient-reported medicine state are returned: no measurements, notes,
transcripts or media. One audit event records the read.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from backend.db import transaction
from backend.db.context_models import MedicationDiaryEntry, VisitContext
from backend.db.models import Assessment, CarePlan, Clinician, DailyCheckin, Patient, PatientClinicianLink, User, utc_now


def _svc():
    from backend import services
    return services


def caseload_summary(actor_id) -> list[dict]:
    svc = _svc()
    today = datetime.now(ZoneInfo("Asia/Karachi")).date()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "clinician":
            raise PermissionError("The caseload is available to clinicians for their linked patients.")
        patients = session.execute(
            select(Patient, User).join(User, Patient.user_id == User.id)
            .join(PatientClinicianLink, PatientClinicianLink.patient_id == Patient.id)
            .join(Clinician, PatientClinicianLink.clinician_id == Clinician.id)
            .where(Clinician.user_id == actor.id).order_by(User.full_name)).all()
        rows = []
        for patient, user in patients:
            visits = session.scalars(select(Assessment).where(Assessment.patient_id == patient.id,
                                                              Assessment.status != "abandoned")
                                     .order_by(Assessment.created_at.desc())).all()
            latest = visits[0] if visits else None
            context = session.scalar(select(VisitContext).where(VisitContext.assessment_id == latest.id)) if latest else None
            last_checkin = session.scalar(select(func.max(DailyCheckin.date)).where(DailyCheckin.patient_id == patient.id))
            falls = session.scalar(select(func.count(DailyCheckin.id)).where(
                DailyCheckin.patient_id == patient.id, DailyCheckin.falls.is_(True),
                DailyCheckin.date >= today - timedelta(days=14)))
            # The newest follow-up note that sets a date is the plan; older dates are superseded.
            next_review = session.scalar(select(CarePlan.next_review_date).where(
                CarePlan.patient_id == patient.id, CarePlan.next_review_date.is_not(None))
                .order_by(CarePlan.created_at.desc(), CarePlan.id).limit(1))
            if next_review is not None and next_review < today:
                next_review = None
            off_reports = session.scalar(select(func.count(MedicationDiaryEntry.id)).where(
                MedicationDiaryEntry.patient_id == patient.id, MedicationDiaryEntry.state.in_(("off", "wearing_off")),
                MedicationDiaryEntry.observed_at >= utc_now() - timedelta(days=7)))
            rows.append({
                "patient_id": patient.id, "full_name": user.full_name, "active": user.active,
                "visits": len(visits),
                "last_visit_at": svc._iso(latest.created_at) if latest else None,
                "awaiting_review": sum(v.status == "completed" and v.review_status != "reviewed" for v in visits),
                "open_drafts": sum(v.status == "draft" for v in visits),
                "last_checkin": last_checkin.isoformat() if last_checkin else None,
                "falls_14d": int(falls or 0),
                "next_review": next_review.isoformat() if next_review else None,
                "latest_medication_state": context.medication_state if context else None,
                "off_reports_7d": int(off_reports or 0),
            })
        svc._audit(session, actor.id, "caseload.read", count=len(rows))
        return rows
