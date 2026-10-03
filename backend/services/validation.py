"""Owner-controlled validation protocol and immutable source measurements."""

import math

from sqlalchemy import select

from backend.db import transaction
from backend.db.models import AssessmentFile, ModuleResult, Patient, utc_now
from backend.db.validation_models import ValidationCase, ValidationParticipation, ValidationStudy
from ml.common.statistics import measurements, module_family
from ml.validation.evaluation import evaluate


def _svc():
    from backend import services
    return services


def _method(result):
    return result.get("method") or result.get("analysis_version") or ""


def _text(value, field, limit=120, required=True):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ValueError(f"{field} must contain {'1 to' if required else 'up to'} {limit} characters.")
    return value.strip()


def _owner(session, actor_id, study_id=None):
    svc = _svc()
    actor = svc._actor(session, actor_id)
    if actor.role != "clinician":
        raise PermissionError("An active clinician must manage validation.")
    study = session.get(ValidationStudy, svc._id(study_id)) if study_id else None
    if study_id and (study is None or study.owner_id != actor.id):
        raise PermissionError("This validation study is unavailable.")
    return actor, study


def create_study(actor_id, name, *, task, metric, unit, method_version, reference_method,
                 minimum_participants, tolerance_mae, protocol_notes):
    if module_family(task) not in {"movement", "audio"}:
        raise ValueError("Validate a defined movement or audio measurement.")
    if type(minimum_participants) is not int or not 3 <= minimum_participants <= 10000:
        raise ValueError("Plan between 3 and 10,000 independent participants.")
    if isinstance(tolerance_mae, bool) or not isinstance(tolerance_mae, (float, int)) or not math.isfinite(tolerance_mae) or tolerance_mae < 0:
        raise ValueError("Prespecify a finite, nonnegative MAE tolerance in the measurement's units.")
    protocol = {"task": task, "metric": _text(metric, "Metric"), "unit": _text(unit, "Unit"),
                "method_version": _text(method_version, "Method version"),
                "reference_method": _text(reference_method, "Reference method"),
                "minimum_participants": minimum_participants, "tolerance_mae": float(tolerance_mae),
                "notes": _text(protocol_notes, "Protocol notes", 4000), "version": "validation-consent-v1"}
    if protocol["unit"].startswith("Unit not specified"):
        raise ValueError("Choose a measurement with a defined native unit.")
    name = _text(name, "Study name", 160)
    with transaction() as session:
        actor, _ = _owner(session, actor_id)
        study = ValidationStudy(owner_id=actor.id, name=name, protocol=protocol)
        session.add(study)
        session.flush()
        _svc()._audit(session, actor.id, "validation.study_created", "validation_study", study.id)
        return {"id": study.id, "name": name, "protocol": protocol}


def list_studies(actor_id):
    with transaction() as session:
        actor, _ = _owner(session, actor_id)
        return [{"id": s.id, "name": s.name, "protocol": s.protocol, "locked": s.locked_at is not None}
                for s in session.scalars(select(ValidationStudy).where(ValidationStudy.owner_id == actor.id)
                                         .order_by(ValidationStudy.created_at.desc())).all()]


def invite_patient(actor_id, study_id, patient_id):
    svc = _svc()
    with transaction() as session:
        actor, study = _owner(session, actor_id, study_id)
        patient = svc._patient_access(session, actor, patient_id)
        svc._actor(session, patient.user_id)
        svc._consented(session, patient.id)
        row = session.scalar(select(ValidationParticipation).where(
            ValidationParticipation.study_id == study.id, ValidationParticipation.patient_id == patient.id))
        if row is None:
            row = ValidationParticipation(study_id=study.id, patient_id=patient.id)
            session.add(row)
            session.flush()
        svc._audit(session, actor.id, "validation.invited", "validation_participation", row.id)
        return row.id


def _patient_participation(session, actor_id, participation_id):
    svc = _svc()
    actor = svc._actor(session, actor_id)
    if actor.role != "patient":
        raise PermissionError("The patient must choose participation personally.")
    row = session.get(ValidationParticipation, svc._id(participation_id))
    if row is None:
        raise LookupError("Validation invitation was not found.")
    svc._patient_access(session, actor, row.patient_id)
    return actor, row


def patient_invitations(actor_id):
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("A patient account is required.")
        patient = svc._patient_access(session, actor, None)
        rows = session.scalars(select(ValidationParticipation).where(ValidationParticipation.patient_id == patient.id)).all()
        result = []
        for row in rows:
            study = session.get(ValidationStudy, row.study_id)
            eligible = True
            try:
                owner = svc._actor(session, study.owner_id)
                svc._patient_access(session, owner, patient.id)
                svc._consented(session, patient.id)
            except (PermissionError, LookupError):
                eligible = False
            result.append({"id": row.id, "name": study.name if eligible else "Unavailable validation invitation",
                           "protocol": study.protocol if eligible else {"reference_method": ""},
                           "active": row.acknowledged_at is not None and row.withdrawn_at is None,
                           "withdrawn": row.withdrawn_at is not None, "eligible": eligible})
        return result


def choose_participation(actor_id, participation_id, *, agree):
    if type(agree) is not bool:
        raise ValueError("Choose participation explicitly.")
    with transaction() as session:
        actor, row = _patient_participation(session, actor_id, participation_id)
        if agree:
            if row.withdrawn_at is not None:
                raise PermissionError("Withdrawal is final for this study. A new study invitation is required.")
            _svc()._consented(session, row.patient_id)
            study = session.get(ValidationStudy, row.study_id)
            owner = _svc()._actor(session, study.owner_id)
            _svc()._patient_access(session, owner, row.patient_id)
            row.acknowledged_at, row.withdrawn_at = utc_now(), None
        else:
            row.withdrawn_at = utc_now()
        _svc()._audit(session, actor.id, "validation.participation_changed", "validation_participation", row.id, active=agree)


def source_options(actor_id, assessment_id):
    """Server-authorized, defined measures, with exact extractor versions."""
    assessment = _svc().get_assessment(actor_id, assessment_id)
    return [{"task": task, "metric": m.key, "unit": m.unit, "measured": m.value,
             "method_version": _method(result)}
            for task, result in assessment["modules"].items() if module_family(task) in {"movement", "audio"}
            for m in measurements(result, task)
            if not m.unit.startswith("Unit not specified") and _method(result)
            and any(f["id"] == assessment["module_file_ids"].get(task) and f["module"] == task
                    for f in assessment["files"])]


def record_case(actor_id, study_id, assessment_id, *, reference=None, reference_blinded=None,
                device_family="unknown", lighting="unknown", site="unknown", age_band="unknown", repeat_group=""):
    svc = _svc()
    metadata = {key: _text(value, key, required=False) or "unknown"
                for key, value in {"device_family": device_family, "lighting": lighting, "site": site,
                                   "age_band": age_band}.items()}
    metadata["repeat_group"] = _text(repeat_group, "Matched repeat group", required=False)
    if reference is not None and (isinstance(reference, bool) or not isinstance(reference, (float, int)) or not math.isfinite(reference)):
        raise ValueError("Reference must be finite or missing.")
    if reference_blinded is not None and type(reference_blinded) is not bool:
        raise ValueError("Reference blinding must be yes, no, or unknown.")
    with transaction() as session:
        actor, study = _owner(session, actor_id, study_id)
        session.scalar(select(ValidationStudy).where(ValidationStudy.id == study.id).with_for_update())
        _, assessment = svc._assessment_access(session, actor.id, assessment_id)
        patient = session.get(Patient, assessment.patient_id)
        svc._actor(session, patient.user_id)
        svc._consented(session, assessment.patient_id)
        participation = session.scalar(select(ValidationParticipation).where(
            ValidationParticipation.study_id == study.id, ValidationParticipation.patient_id == assessment.patient_id,
            ValidationParticipation.acknowledged_at.is_not(None), ValidationParticipation.withdrawn_at.is_(None)))
        if participation is None:
            raise PermissionError("The patient must accept this validation invitation first.")
        p = study.protocol
        result_row = session.scalar(select(ModuleResult).where(ModuleResult.assessment_id == assessment.id,
            ModuleResult.module == p["task"]).order_by(ModuleResult.revision.desc()).limit(1))
        if result_row is None:
            raise ValueError("Save the selected task result before recording validation evidence.")
        result = result_row.result
        source_file = session.get(AssessmentFile, result_row.file_id) if result_row.file_id else None
        if source_file is None or source_file.assessment_id != assessment.id or source_file.module != p["task"]:
            raise ValueError("An authorized source recording is required for real-recording validation.")
        if _method(result) != p["method_version"]:
            raise ValueError("Extractor method differs from the frozen study protocol.")
        measure = next((m for m in measurements(result, p["task"]) if m.key == p["metric"] and m.unit == p["unit"]), None)
        if measure is None:
            raise ValueError("No accepted measurement with the protocol's exact metric/unit is available.")
        # One assessment is one recording source for this protocol. Saving the
        # same clip again must not fabricate independent test-retest recordings.
        if session.scalar(select(ValidationCase.id).where(ValidationCase.study_id == study.id,
            ((ValidationCase.assessment_id == assessment.id) | (ValidationCase.source_sha256 == source_file.sha256)))):
            raise ValueError("This visit is already included. Use a new visit for a new recording.")
        row = ValidationCase(study_id=study.id, participation_id=participation.id, assessment_id=assessment.id,
                             module_revision=result_row.revision, measured=measure.value, reference=reference,
                             source_file_id=source_file.id, source_sha256=source_file.sha256,
                             reference_blinded=reference_blinded, metadata_values=metadata)
        study.locked_at = study.locked_at or utc_now()
        session.add(row)
        session.flush()
        svc._audit(session, actor.id, "validation.case_recorded", "validation_case", row.id, revision=row.module_revision)
        return row.id


def study_evidence(actor_id, study_id):
    svc = _svc()
    with transaction() as session:
        actor, study = _owner(session, actor_id, study_id)
        rows, included, excluded = [], [], 0
        cases = session.scalars(select(ValidationCase).where(ValidationCase.study_id == study.id)).all()
        for case in cases:
            participation = session.get(ValidationParticipation, case.participation_id)
            try:
                patient = svc._patient_access(session, actor, participation.patient_id)
                patient_user = session.get(Patient, patient.id)
                svc._actor(session, patient_user.user_id)
                svc._consented(session, patient.id)
                if participation.withdrawn_at is not None or participation.acknowledged_at is None:
                    raise PermissionError("Participation is inactive.")
            except (PermissionError, LookupError):
                excluded += 1
                continue
            p = study.protocol
            rows.append({"participant_id": participation.id, "recording_id": case.assessment_id,
                         "task": p["task"], "metric": p["metric"], "unit": p["unit"],
                         "method_version": p["method_version"], "reference_method": p["reference_method"],
                         "reference_blinded": case.reference_blinded, "split": "evaluation", "status": "accepted",
                         "measured": case.measured, "reference": case.reference, **case.metadata_values})
            included.append({"source_revision": case.module_revision, "measured": case.measured,
                             "reference": case.reference, **case.metadata_values})
        evidence = evaluate(rows, tolerance=study.protocol["tolerance_mae"],
                            minimum_participants=study.protocol["minimum_participants"])
        evidence["coverage_scope"] = "Saved, accepted study measurements only. Use the offline manifest to include every rejected/unavailable recording attempt; this dashboard alone cannot establish capture success."
        evidence["split_scope"] = "Study cases are prospectively tagged evaluation. This dashboard has no training/tuning roster; audit the offline manifest before claiming local split independence."
        svc._audit(session, actor.id, "validation.evidence_read", "validation_study", study.id, count=len(rows))
        return {"study": {"id": study.id, "name": study.name, "protocol": study.protocol,
                          "locked": study.locked_at is not None}, "evidence": evidence,
                "cases": included, "excluded_inactive_cases": excluded}
