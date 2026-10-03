"""Explicit monitoring withdrawal and visible human-managed data requests."""

from sqlalchemy import select, update

from backend.db import transaction
from backend.db.models import Assessment, Consent, utc_now
from backend.db.privacy_models import DataRequest
from backend.db.production_models import MediaGrant

KINDS = {"access", "export", "erasure"}
STATUSES = {"received", "reviewing", "resolved", "declined"}


def _svc():
    from backend import services
    return services


def monitoring_status(actor_id):
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("A patient account is required.")
        patient = svc._patient_access(session, actor, None)
        rows = session.scalars(select(Consent).where(Consent.patient_id == patient.id)).all()
        return {"active": any(r.acknowledged and r.withdrawn_at is None for r in rows),
                "versions": sorted({r.version for r in rows})}


def set_monitoring_consent(actor_id, *, acknowledged):
    if type(acknowledged) is not bool:
        raise ValueError("Choose monitoring consent explicitly.")
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("Only the patient may change monitoring consent.")
        patient = svc._patient_access(session, actor, None)
        # Lock the actor: grant issuance locks the same user. Any grants made
        # before this transaction commits are explicitly revoked below.
        from backend.db.models import User
        session.scalar(select(User).where(User.id == actor.id).with_for_update())
        if acknowledged:
            active = session.scalar(select(Consent.id).where(Consent.patient_id == patient.id,
                Consent.acknowledged.is_(True), Consent.withdrawn_at.is_(None)))
            if active is None:
                session.add(Consent(patient_id=patient.id, version="monitoring-v2", acknowledged=True))
        else:
            session.execute(update(Consent).where(Consent.patient_id == patient.id,
                Consent.withdrawn_at.is_(None)).values(withdrawn_at=utc_now()))
            assessments = select(Assessment.id).where(Assessment.patient_id == patient.id)
            session.execute(update(MediaGrant).where(MediaGrant.assessment_id.in_(assessments),
                MediaGrant.revoked_at.is_(None)).values(revoked_at=utc_now()))
        svc._audit(session, actor.id, "privacy.monitoring_consent", "patient", patient.id, active=acknowledged)


def _request_dict(row):
    return {"id": row.id, "patient_id": row.patient_id, "kind": row.kind, "status": row.status,
            "created_at": _svc()._iso(row.created_at), "handled_at": _svc()._iso(row.handled_at)}


def create_data_request(actor_id, kind):
    if kind not in KINDS:
        raise ValueError("Choose access, export, or erasure.")
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("Only the patient may make a data request.")
        patient = svc._patient_access(session, actor, None)
        row = session.scalar(select(DataRequest).where(DataRequest.patient_id == patient.id,
            DataRequest.kind == kind, DataRequest.status.in_(["received", "reviewing"])))
        if row is None:
            row = DataRequest(patient_id=patient.id, kind=kind)
            session.add(row)
            session.flush()
            svc._audit(session, actor.id, "privacy.data_request", "data_request", row.id)
        return _request_dict(row)


def list_data_requests(actor_id):
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        query = select(DataRequest).order_by(DataRequest.created_at.desc())
        if actor.role == "patient":
            patient = svc._patient_access(session, actor, None)
            query = query.where(DataRequest.patient_id == patient.id)
        else:
            svc._admin(session, actor.id)
        return [_request_dict(row) for row in session.scalars(query).all()]


def update_request_status(actor_id, request_id, status):
    if status not in STATUSES:
        raise ValueError("Choose a valid data-request status.")
    svc = _svc()
    with transaction() as session:
        admin = svc._admin(session, actor_id)
        row = session.get(DataRequest, svc._id(request_id))
        if row is None:
            raise LookupError("Data request was not found.")
        row.status, row.handled_by, row.handled_at = status, admin.id, utc_now()
        svc._audit(session, admin.id, "privacy.request_status", "data_request", row.id, status=status)
        return _request_dict(row)
