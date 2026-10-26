"""Human-authored daily context, personal priorities and clinician follow-up.

These records never enter a model, disease severity score or diagnostic report.
The authenticated server-side actor is checked on every read and write. New
tables are additive, so existing assessments remain intact when init_db runs.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.db import transaction
from backend.db.models import CarePlan, DailyCheckin, Patient, PersonalGoal, User, utc_now

CHECKIN_FIELDS = ("energy", "sleep_quality", "movement_ease", "mood")
GOAL_STATUSES = frozenset({"active", "completed", "paused"})


def _services():
    # Defer access to the central authorization layer to avoid import cycles.
    from backend import services
    return services


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Karachi")).date()


def _date(value, *, field, default=None):
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).") from exc
    if value != parsed.isoformat() or not 1900 <= parsed.year <= 2100:
        raise ValueError(f"{field} must be an ISO date between 1900 and 2100.")
    return parsed


def _text(value, *, field, limit, required=False):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    cleaned = value.strip()
    if len(cleaned) > limit or (required and not cleaned):
        minimum = "1 to " if required else "up to "
        raise ValueError(f"{field} must contain {minimum}{limit} characters.")
    return cleaned


def _author_name(session, user_id):
    author = session.get(User, user_id)
    return author.full_name if author else "Unknown author"


def _helper(session, checkin_id):
    from backend.db.context_models import CheckinAssistance
    row = session.get(CheckinAssistance, checkin_id)
    return row.helper if row else None


def _checkin_dict(session, row):
    svc = _services()
    return {
        "id": row.id, "patient_id": row.patient_id, "date": row.date.isoformat(),
        "responses": {field: getattr(row, field) for field in CHECKIN_FIELDS}
        | {"falls": row.falls, "note": row.note}
        | ({"helper": helper} if (helper := _helper(session, row.id)) else {}),
        "source": "patient_self_report", "recorded_by": row.recorded_by,
        "recorded_by_role": row.recorded_by_role, "author_name": _author_name(session, row.recorded_by),
        "created_at": svc._iso(row.created_at), "updated_at": svc._iso(row.updated_at),
    }


def _goal_dict(session, row):
    svc = _services()
    return {
        "id": row.id, "patient_id": row.patient_id, "label": row.label,
        "detail": row.detail, "status": row.status, "source": "patient",
        "authored_by": row.authored_by, "author_name": _author_name(session, row.authored_by),
        "created_at": svc._iso(row.created_at), "updated_at": svc._iso(row.updated_at),
    }


def _plan_dict(session, row):
    svc = _services()
    return {
        "id": row.id, "patient_id": row.patient_id, "assessment_id": row.assessment_id,
        "focus": row.focus, "notes": row.notes,
        "next_review_date": row.next_review_date.isoformat() if row.next_review_date else None,
        "source": "clinician", "authored_by": row.authored_by,
        "author_name": _author_name(session, row.authored_by), "created_at": svc._iso(row.created_at),
    }


def save_checkin(actor_id, responses: dict, patient_id=None) -> dict:
    """Save one dated self-report per patient; a repeat save updates that day.

    All four ratings must be explicitly supplied as integers from 0 to 4;
    higher values mean better wellbeing/easier movement, never PD severity.
    A linked clinician may transcribe a patient's report; author role remains
    visible. Missing falls is unknown, so it is not converted to False.
    """
    svc = _services()
    responses = svc._json(responses)
    unknown = set(responses) - set(CHECKIN_FIELDS) - {"date", "falls", "note", "helper"}
    if unknown:
        raise ValueError("Check-in contains unsupported fields.")
    values = {}
    for field in CHECKIN_FIELDS:
        value = responses.get(field)
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError(f"Choose an explicit whole-number {field} rating from 0 to 4.")
        values[field] = value
    falls = responses.get("falls")
    if falls is not None and type(falls) is not bool:
        raise ValueError("Falls must be yes, no, or unknown.")
    from backend.db.context_models import HELPERS, CheckinAssistance
    helper = responses.get("helper")
    if helper is not None and helper not in HELPERS:
        raise ValueError("Choose who helped from the list, or leave it blank.")
    note = _text(responses.get("note", ""), field="Note", limit=2000)
    checkin_date = _date(responses.get("date"), field="Check-in date", default=_today())
    if checkin_date > _today():
        raise ValueError("Check-in date cannot be in the future.")
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        # PostgreSQL serializes simultaneous saves for this patient, avoiding a
        # duplicate first insert. The unique key also enforces the invariant.
        session.scalar(select(Patient.id).where(Patient.id == patient.id).with_for_update())
        row = session.scalar(select(DailyCheckin).where(
            DailyCheckin.patient_id == patient.id, DailyCheckin.date == checkin_date))
        if row is None:
            row = DailyCheckin(patient_id=patient.id, date=checkin_date)
            session.add(row)
        for field, value in values.items():
            setattr(row, field, value)
        row.falls, row.note = falls, note
        row.recorded_by, row.recorded_by_role = actor.id, actor.role
        row.updated_at = utc_now()
        session.flush()
        assistance = session.get(CheckinAssistance, row.id)
        if helper is None and assistance is not None:
            session.delete(assistance)
        elif helper is not None:
            if assistance is None:
                session.add(CheckinAssistance(checkin_id=row.id, helper=helper))
            else:
                assistance.helper = helper
        session.flush()
        svc._audit(session, actor.id, "care.checkin_saved", "daily_checkin", row.id, role=actor.role)
        return _checkin_dict(session, row)


def list_checkins(actor_id, patient_id=None, limit=30) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 365:
        raise ValueError("Choose a check-in limit from 1 to 365.")
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        rows = session.scalars(select(DailyCheckin).where(DailyCheckin.patient_id == patient.id)
                               .order_by(DailyCheckin.date.desc(), DailyCheckin.id).limit(limit)).all()
        svc._audit(session, actor.id, "care.checkins_read", "patient", patient.id, count=len(rows))
        return [_checkin_dict(session, row) for row in rows]


def save_personal_goal(actor_id, label, detail="", patient_id=None) -> dict:
    """Patients write their own priorities in their own words."""
    label = _text(label, field="Goal", limit=160, required=True)
    detail = _text(detail, field="Goal detail", limit=2000)
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("Personal goals must be written by the patient.")
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        row = PersonalGoal(patient_id=patient.id, label=label, detail=detail, authored_by=actor.id)
        session.add(row)
        session.flush()
        svc._audit(session, actor.id, "care.goal_created", "personal_goal", row.id, status=row.status)
        return _goal_dict(session, row)


def list_goals(actor_id, patient_id=None) -> list[dict]:
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        rows = session.scalars(select(PersonalGoal).where(PersonalGoal.patient_id == patient.id)
                               .order_by(PersonalGoal.created_at.desc(), PersonalGoal.id)).all()
        svc._audit(session, actor.id, "care.goals_read", "patient", patient.id, count=len(rows))
        return [_goal_dict(session, row) for row in rows]


def update_goal(actor_id, goal_id, status="active") -> dict:
    if not isinstance(status, str) or status not in GOAL_STATUSES:
        raise ValueError("Choose active, completed, or paused for the goal.")
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("Only the patient may update their personal goals.")
        row = session.get(PersonalGoal, svc._id(goal_id))
        if row is None:
            raise LookupError("Personal goal was not found.")
        patient = svc._patient_access(session, actor, row.patient_id)
        svc._consented(session, patient.id)
        row.status, row.updated_at = status, utc_now()
        session.flush()
        svc._audit(session, actor.id, "care.goal_updated", "personal_goal", row.id, status=status)
        return _goal_dict(session, row)


def save_care_plan(actor_id, patient_id, focus, notes, next_review_date=None, assessment_id=None) -> dict:
    """Record a linked clinician's follow-up verbatim, with visible authorship.

    The date may describe an earlier planned visit in a historical note. No
    notification, appointment booking or generated prescription is triggered.
    """
    focus = _text(focus, field="Follow-up focus", limit=160, required=True)
    notes = _text(notes, field="Clinician notes", limit=4000, required=True)
    review_date = _date(next_review_date, field="Next review date")
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "clinician":
            raise PermissionError("A linked clinician must write the follow-up note.")
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        if assessment_id is not None:
            _, assessment = svc._assessment_access(session, actor.id, assessment_id)
            if assessment.patient_id != patient.id:
                raise PermissionError("Follow-up and assessment must belong to the same patient.")
            assessment_id = assessment.id
        row = CarePlan(patient_id=patient.id, assessment_id=assessment_id, focus=focus, notes=notes,
                       next_review_date=review_date, authored_by=actor.id)
        session.add(row)
        session.flush()
        svc._audit(session, actor.id, "care.plan_created", "care_plan", row.id, role="clinician")
        return _plan_dict(session, row)


def list_care_plans(actor_id, patient_id=None) -> list[dict]:
    svc = _services()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        rows = session.scalars(select(CarePlan).where(CarePlan.patient_id == patient.id)
                               .order_by(CarePlan.created_at.desc(), CarePlan.id)).all()
        svc._audit(session, actor.id, "care.plans_read", "patient", patient.id, count=len(rows))
        return [_plan_dict(session, row) for row in rows]
