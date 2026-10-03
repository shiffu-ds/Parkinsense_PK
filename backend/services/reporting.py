"""Authorized, idempotent patient-report persistence using the caller's session.

Module writes and automatic summaries share one database transaction. Rendering
uses structured data only; no media file is opened and no external API is used.
"""
from __future__ import annotations

from sqlalchemy import select

from backend.db import transaction
from backend.db.models import Assessment, ClinicalMeasurement, ModuleResult, Patient, Report, User
from ml.inference.patient_report import AUTO_SUMMARY, VERSION, build_patient_report


def _snapshot(session, record: Assessment) -> dict:
    from backend.services import _iso
    rows = session.scalars(select(ModuleResult).where(ModuleResult.assessment_id == record.id).order_by(ModuleResult.created_at, ModuleResult.module)).all()
    clinical = session.scalars(select(ClinicalMeasurement).where(ClinicalMeasurement.assessment_id == record.id).order_by(ClinicalMeasurement.name)).all()
    reviewer = session.get(User, record.reviewed_by) if record.reviewed_by else None
    return {
        "id": record.id, "patient_id": record.patient_id, "status": record.status,
        "created_at": _iso(record.created_at), "updated_at": _iso(record.updated_at),
        "modules": {row.module: row.result for row in rows}, "module_revisions": {row.module: row.revision for row in rows},
        "review_status": record.review_status, "reviewed_by": record.reviewed_by,
        "review_author_name": reviewer.full_name if reviewer else "", "reviewed_at": _iso(record.reviewed_at), "review_note": record.review_note,
        "clinical_measurements": [{"name": row.name, "value": row.value, "unit": row.unit,
                                   "recorded_by": row.recorded_by, "created_at": _iso(row.created_at)} for row in clinical],
    }


def _history(session, record: Assessment) -> list[dict]:
    from backend.services import _iso
    records = session.scalars(select(Assessment).where(Assessment.patient_id == record.patient_id,
                                                      Assessment.id != record.id,
                                                      Assessment.status != "abandoned",
                                                      Assessment.created_at < record.created_at)
                              .order_by(Assessment.created_at, Assessment.id)).all()
    if not records:
        return []
    results = session.scalars(select(ModuleResult).where(ModuleResult.assessment_id.in_([item.id for item in records]))).all()
    modules, revisions = {}, {}
    for row in results:
        modules.setdefault(row.assessment_id, {})[row.module] = row.result
        revisions.setdefault(row.assessment_id, {})[row.module] = row.revision
    return [{"id": item.id, "status": item.status, "created_at": _iso(item.created_at), "modules": modules.get(item.id, {}),
             "module_revisions": revisions.get(item.id, {})} for item in records]


def _auto_row(session, assessment_id: str) -> Report | None:
    # JSON marker filtering stays portable across PostgreSQL and explicit test SQLite.
    rows = session.scalars(select(Report).where(Report.assessment_id == assessment_id).order_by(Report.created_at)).all()
    return next((row for row in rows if row.content.get("auto_summary") == AUTO_SUMMARY), None)


def _state(snapshot: dict, language: str, history: list[dict]) -> dict:
    return {"module_revisions": snapshot["module_revisions"], "assessment_status": snapshot["status"],
            "review_status": snapshot["review_status"], "reviewed_by": snapshot["reviewed_by"],
            "review_author_name": snapshot["review_author_name"], "reviewed_at": snapshot["reviewed_at"],
            "review_note": snapshot["review_note"], "clinical_measurements": snapshot["clinical_measurements"], "language": language,
            "prior_module_revisions": [{"id": earlier["id"], "status": earlier["status"], "module_revisions": earlier["module_revisions"]} for earlier in history]}


def _outdated_reason(stored: dict | None, current: dict) -> str:
    """Describe a stale source category without exposing notes or identifiers."""
    if not isinstance(stored, dict):
        return "Report provenance needs refreshing."
    if stored.get("module_revisions") != current["module_revisions"]:
        return "Saved task results changed."
    if stored.get("prior_module_revisions") != current["prior_module_revisions"]:
        return "Earlier assessment data changed; refresh the reference comparisons."
    if stored.get("language") != current["language"]:
        return "The patient's preferred report language changed."
    if stored.get("assessment_status") != current["assessment_status"]:
        return "The assessment status changed."
    return "Clinician review or context changed."


def _accepted(result: dict) -> bool:
    quality = result.get("quality", {})
    return (result.get("status") in {"accepted", "completed", "ACCEPT"} and isinstance(quality, dict)
            and quality.get("accepted") is not False and quality.get("decision") not in {"REPEAT", "REJECT"}
            and (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"))


def upsert_auto_report(session, record: Assessment, actor_id: str, *, create=False) -> Report | None:
    """Use only after assessment authorization/lock; never start a nested service."""
    from backend.services import _audit, _json
    existing = _auto_row(session, record.id)
    snapshot = _snapshot(session, record)
    if not existing and (not create or not any(_accepted(result) for result in snapshot["modules"].values())):
        return None
    patient_user = session.scalar(select(User).join(Patient, Patient.user_id == User.id).where(Patient.id == record.patient_id))
    if patient_user is None:
        raise LookupError("Patient account was not found.")
    history = _history(session, record)
    state = _state(snapshot, patient_user.language, history)
    if existing and existing.content.get("source_report_state") == state:
        return existing
    content = _json(build_patient_report(snapshot, history, patient_user.language) | {"source_report_state": state})
    if existing:
        existing.content, existing.language, existing.generator_version = content, patient_user.language, VERSION
        existing.reviewed_by = record.reviewed_by
        row = existing
    else:
        row = Report(assessment_id=record.id, content=content, language=patient_user.language,
                     generator_version=VERSION, reviewed_by=record.reviewed_by)
        session.add(row)
    _audit(session, actor_id, "report.auto_updated" if existing else "report.auto_created", "assessment", record.id,
           count=len(snapshot["modules"]))
    session.flush()
    return row


def get_patient_report(actor_id: str, assessment_id: str, *, refresh=False) -> dict | None:
    """Read the automatic report; explicit refresh also supports older assessments.

    Historical reads follow the normal patient/link authorization rules. Creating
    or refreshing content additionally requires active monitoring consent.
    """
    if type(refresh) is not bool:
        raise ValueError("Refresh must be true or false.")
    from backend.services import _assessment_access, _audit, _consented, _report_dict
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, lock=refresh)
        if refresh:
            if record.status == "abandoned":
                raise ValueError("An abandoned assessment cannot generate a new report.")
            _consented(session, record.patient_id)
            row = upsert_auto_report(session, record, actor.id, create=True)
        else:
            row = _auto_row(session, record.id)
        if row is None:
            return None
        # Reads check all authoritative sources, including earlier reference
        # revisions and preferred language. They never regenerate the document.
        snapshot = _snapshot(session, record)
        patient_user = session.scalar(select(User).join(Patient, Patient.user_id == User.id).where(Patient.id == record.patient_id))
        if patient_user is None:
            raise LookupError("Patient account was not found.")
        current_state = _state(snapshot, patient_user.language, _history(session, record))
        stored_state = row.content.get("source_report_state")
        result = _report_dict(row, snapshot["module_revisions"])
        result["outdated"] = result.get("outdated") is True or stored_state != current_state
        result["outdated_reason"] = _outdated_reason(stored_state, current_state) if result["outdated"] else None
        _audit(session, actor.id, "report.viewed", "assessment", record.id)
        return result
