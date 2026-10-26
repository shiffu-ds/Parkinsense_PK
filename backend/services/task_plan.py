"""A clinician's suggested weekly rhythm of tasks for one patient.

Only a linked clinician writes a plan; the patient and their linked clinicians
read it. The newest plan is the current one, so history stays visible in the
audit trail. A plan is a suggestion with days of the week, not a prescription.
"""

from sqlalchemy import select

from backend.db import transaction
from backend.db.context_models import PLAN_GROUPS, TaskPlan


def _svc():
    from backend import services
    return services


def _plan(row) -> dict:
    return {"id": row.id, "patient_id": row.patient_id, "schedule": {group: list(days) for group, days in row.schedule.items()},
            "note": row.note, "created_at": _svc()._iso(row.created_at), "source": "clinician_suggestion"}


def _schedule(schedule) -> dict:
    if not isinstance(schedule, dict) or set(schedule) - set(PLAN_GROUPS):
        raise ValueError("Choose task groups from the list.")
    clean = {}
    for group in PLAN_GROUPS:
        days = schedule.get(group, [])
        if not isinstance(days, (list, tuple)) or not all(type(day) is int and 0 <= day <= 6 for day in days):
            raise ValueError("Choose days of the week for each task.")
        if days:
            clean[group] = sorted(set(days))
    return clean


def save_task_plan(actor_id, patient_id, schedule, note="") -> dict:
    """Replace the current plan. An empty schedule clears it."""
    clean = _schedule(schedule)
    note = "" if note is None else note
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError("Keep the plan note under 500 characters.")
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "clinician":
            raise PermissionError("Only a linked clinician can set a task plan.")
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        row = TaskPlan(patient_id=patient.id, schedule=clean, note=note.strip(), authored_by=actor.id)
        session.add(row)
        svc._audit(session, actor.id, "task_plan.saved", "patient", patient.id, count=len(clean))
        session.flush()
        return _plan(row)


def get_task_plan(actor_id, patient_id=None) -> dict | None:
    """The current plan, or None when there is none or it was cleared."""
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        row = session.scalar(select(TaskPlan).where(TaskPlan.patient_id == patient.id)
                             .order_by(TaskPlan.created_at.desc(), TaskPlan.id.desc()).limit(1))
        return _plan(row) if row is not None and row.schedule else None


def planned_on(plan, weekday) -> list[str]:
    """Task groups the plan suggests for a weekday (Monday is 0), in plan order."""
    if not plan:
        return []
    return [group for group in PLAN_GROUPS if weekday in plan["schedule"].get(group, [])]
