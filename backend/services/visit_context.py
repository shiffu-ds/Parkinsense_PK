"""Medicine-timing context for a visit, reported by the patient.

The record is context for comparing recordings, not a clinical measurement:
it never feeds features, models or reports' measured values, and the app
gives no medication advice. Access follows the visit: the patient or a linked
clinician may read it; either may record it while the visit is still open
(a clinician may also add it to a completed visit when transcribing).
"""

from sqlalchemy import select

from backend.db import transaction
from backend.db.context_models import DOSE_WINDOWS, DYSKINESIA, MEDICATION_STATES, VisitContext
from backend.db.models import utc_now


def _svc():
    from backend import services
    return services


def _as_dict(row):
    if row is None:
        return None
    svc = _svc()
    return {
        "assessment_id": row.assessment_id, "medication_state": row.medication_state,
        "dose_window": row.dose_window, "dyskinesia": row.dyskinesia, "note": row.note,
        "recorded_by_role": row.recorded_by_role, "updated_at": svc._iso(row.updated_at),
        "source": "patient_report",
    }


def save_visit_context(actor_id, assessment_id, *, medication_state, dose_window=None, dyskinesia=None, note=""):
    if medication_state not in MEDICATION_STATES:
        raise ValueError("Choose how your Parkinson's medicine is working right now.")
    if medication_state == "none":
        dose_window = None  # No dose to time.
    elif dose_window is not None and dose_window not in DOSE_WINDOWS:
        raise ValueError("Choose when you took your last dose, or 'Not sure'.")
    if dyskinesia is not None and dyskinesia not in DYSKINESIA:
        raise ValueError("Choose yes, no or not sure for extra movements.")
    note = "" if note is None else note
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError("Keep the medicine note under 1,000 characters.")
    svc = _svc()
    with transaction() as session:
        actor, record = svc._assessment_access(session, actor_id, assessment_id, lock=True)
        svc._consented(session, record.patient_id)
        if record.status == "abandoned":
            raise ValueError("Medicine timing cannot be added to an abandoned visit.")
        if record.status != "draft" and actor.role != "clinician":
            raise ValueError("This visit is closed. Medicine timing can be added while a visit is open.")
        row = session.scalar(select(VisitContext).where(VisitContext.assessment_id == record.id))
        if row is None:
            row = VisitContext(assessment_id=record.id, medication_state=medication_state,
                               recorded_by=actor.id, recorded_by_role=actor.role)
            session.add(row)
        row.medication_state, row.dose_window, row.dyskinesia = medication_state, dose_window, dyskinesia
        row.note, row.recorded_by, row.recorded_by_role, row.updated_at = note.strip(), actor.id, actor.role, utc_now()
        svc._audit(session, actor.id, "visit_context.saved", "assessment", record.id)
        session.flush()
        return _as_dict(row)


def get_visit_context(actor_id, assessment_id):
    svc = _svc()
    with transaction() as session:
        _, record = svc._assessment_access(session, actor_id, assessment_id)
        return _as_dict(session.scalar(select(VisitContext).where(VisitContext.assessment_id == record.id)))


def list_visit_contexts(actor_id, assessment_ids):
    """Context for several visits at once; every visit is access-checked."""
    svc = _svc()
    ids = [str(value) for value in assessment_ids][:500]
    with transaction() as session:
        for assessment_id in ids:
            svc._assessment_access(session, actor_id, assessment_id)
        rows = session.scalars(select(VisitContext).where(VisitContext.assessment_id.in_(ids))).all() if ids else []
        return {row.assessment_id: _as_dict(row) for row in rows}


def _assistance_dict(row):
    if row is None:
        return None
    return {"assessment_id": row.assessment_id, "helper": row.helper, "walking_aid": row.walking_aid,
            "recorded_by_role": row.recorded_by_role, "updated_at": _svc()._iso(row.updated_at), "source": "patient_report"}


def save_visit_assistance(actor_id, assessment_id, *, helper, walking_aid):
    """Who helped and which walking aid was used; same open-visit rules as medicine timing."""
    from backend.db.context_models import HELPERS, WALKING_AIDS, VisitAssistance
    if helper not in HELPERS:
        raise ValueError("Choose who helped with this visit.")
    if walking_aid not in WALKING_AIDS:
        raise ValueError("Choose the walking aid used, or none.")
    svc = _svc()
    with transaction() as session:
        actor, record = svc._assessment_access(session, actor_id, assessment_id, lock=True)
        svc._consented(session, record.patient_id)
        if record.status == "abandoned":
            raise ValueError("Help and walking aid cannot be added to an abandoned visit.")
        if record.status != "draft" and actor.role != "clinician":
            raise ValueError("This visit is closed. Help and walking aid can be added while a visit is open.")
        row = session.scalar(select(VisitAssistance).where(VisitAssistance.assessment_id == record.id))
        if row is None:
            row = VisitAssistance(assessment_id=record.id, helper=helper, walking_aid=walking_aid,
                                  recorded_by=actor.id, recorded_by_role=actor.role)
            session.add(row)
        row.helper, row.walking_aid = helper, walking_aid
        row.recorded_by, row.recorded_by_role, row.updated_at = actor.id, actor.role, utc_now()
        svc._audit(session, actor.id, "visit_assistance.saved", "assessment", record.id)
        session.flush()
        return _assistance_dict(row)


def get_visit_assistance(actor_id, assessment_id):
    from backend.db.context_models import VisitAssistance
    svc = _svc()
    with transaction() as session:
        _, record = svc._assessment_access(session, actor_id, assessment_id)
        return _assistance_dict(session.scalar(select(VisitAssistance).where(VisitAssistance.assessment_id == record.id)))


def list_visit_assistance(actor_id, assessment_ids):
    """Assistance for several visits; every visit is access-checked."""
    from backend.db.context_models import VisitAssistance
    svc = _svc()
    ids = [str(value) for value in assessment_ids][:500]
    with transaction() as session:
        for assessment_id in ids:
            svc._assessment_access(session, actor_id, assessment_id)
        rows = session.scalars(select(VisitAssistance).where(VisitAssistance.assessment_id.in_(ids))).all() if ids else []
        return {row.assessment_id: _assistance_dict(row) for row in rows}
