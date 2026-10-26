"""Authorized application services. Session state is never the data store.

The actor_id must come from the authenticated server-side session. Every patient
resource is checked independently; role-aware navigation alone is insufficient.
"""

from datetime import timedelta, timezone
import hashlib
import json
import math
import re
from threading import RLock
from uuid import UUID

from sqlalchemy import JSON, cast, delete, func, literal_column, select, text, type_coerce
from sqlalchemy.exc import IntegrityError

from backend.db import configure_db as configure_db, get_engine as get_engine, init_db as init_db, transaction
from backend.db.models import (
    ADLResponse, Assessment, AssessmentFile, AuditLog, Clinician, ClinicalMeasurement,
    Consent, Explanation, ModelOutput, ModelRun, ModuleResult, Patient,
    PatientClinicianLink, Report, User, utc_now,
)
from backend.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from backend.storage import resolve_key, write_upload

LANGUAGES = {"english": "English", "urdu": "Urdu", "pashto": "Pashto", "mixed": "Mixed", "roman urdu": "Roman Urdu"}
MODULES = {
    "gait", "walking", "turning", "hand", "hand_left", "hand_right", "finger_left", "finger_right",
    "finger_tapping", "finger_tapping_left", "finger_tapping_right", "hand_open_close", "open_close",
    "sit_to_stand", "reach_grasp", "reach", "grasp", "object_transfer", "voice", "voice_vowel", "voice_sentence", "voice_natural", "speech", "audio", "nlp", "adl",
    "spiral_left", "spiral_right", "touch_tap_left", "touch_tap_right",
}
_bootstrap_lock = RLock()


def _id(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid record identifier.") from exc


def _language(value: str) -> str:
    if not isinstance(value, str) or value.lower() not in LANGUAGES:
        raise ValueError("Choose English, Urdu, Pashto, Mixed, or Roman Urdu.")
    return LANGUAGES[value.lower()]


def _identity(full_name: str, email: str, language: str) -> tuple[str, str, str]:
    if not isinstance(full_name, str) or not 2 <= len(full_name.strip()) <= 160:
        raise ValueError("Full name must contain 2 to 160 characters.")
    if not isinstance(email, str):
        raise ValueError("Enter a valid email address.")
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    return full_name.strip(), email, _language(language)


def _json(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Result must be a JSON object.")
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("Results must use JSON values and finite numbers.") from exc
    if len(encoded.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("Structured result exceeds 10 MB; reduce landmark sampling.")
    return json.loads(encoded)


def _iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value is not None and value.tzinfo is None else (value.isoformat() if value else None)


def _audit(session, actor_id, action, resource_type=None, resource_id=None, **details):
    # No emails, names, transcripts, paths, passwords, measurements or raw media.
    allowed = {"module", "status", "role", "revision", "count", "tool", "success", "active"}
    sanitized = {key: value for key, value in details.items() if key in allowed and isinstance(value, (str, int, bool))}
    session.add(AuditLog(actor_id=actor_id, action=action, resource_type=resource_type,
                         resource_id=resource_id, details=sanitized))


def _actor(session, actor_id) -> User:
    actor = session.get(User, _id(actor_id))
    if actor is None or not actor.active:
        raise PermissionError("An active authenticated account is required.")
    return actor


def _admin(session, actor_id) -> User:
    actor = _actor(session, actor_id)
    if actor.role != "admin":
        raise PermissionError("Administrator access is required.")
    return actor


def _user_dict(session, user: User) -> dict:
    patient = session.scalar(select(Patient).where(Patient.user_id == user.id))
    clinician = session.scalar(select(Clinician).where(Clinician.user_id == user.id))
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role,
            "language": user.language, "active": user.active, "created_at": _iso(user.created_at),
            "patient_id": patient.id if patient else None, "clinician_id": clinician.id if clinician else None}


def _patient_access(session, actor: User, patient_id=None) -> Patient:
    if patient_id is None:
        if actor.role != "patient":
            raise ValueError("Select a patient before opening an assessment.")
        patient = session.scalar(select(Patient).where(Patient.user_id == actor.id))
    else:
        patient = session.get(Patient, _id(patient_id))
    if patient is None:
        raise LookupError("Patient record was not found.")
    if actor.role == "patient" and patient.user_id == actor.id:
        return patient
    if actor.role == "clinician":
        clinician = session.scalar(select(Clinician).where(Clinician.user_id == actor.id))
        linked = clinician and session.scalar(select(PatientClinicianLink.id).where(
            PatientClinicianLink.patient_id == patient.id, PatientClinicianLink.clinician_id == clinician.id))
        if linked:
            return patient
    raise PermissionError("This account cannot access this patient's assessments or media.")


def _assessment_access(session, actor_id, assessment_id, *, draft=False, lock=False):
    actor = _actor(session, actor_id)
    record = session.scalar(select(Assessment).where(Assessment.id == _id(assessment_id)).with_for_update()) if draft or lock else session.get(Assessment, _id(assessment_id))
    if record is None:
        raise LookupError("Assessment was not found.")
    _patient_access(session, actor, record.patient_id)
    if draft and record.status != "draft":
        raise ValueError("This assessment is closed. Start a new assessment to repeat a module.")
    return actor, record


# Per-frame landmarks are ~98% of a movement result (about 0.5 MB each). Visit
# lists leave them in the database; get_assessment() returns them for replay.
FRAMES_OMITTED = "landmark_frames_omitted"


def _results_without_frames(session):
    """Result JSON minus landmark_frames, and whether frames existed, computed in SQL."""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB
        value = cast(ModuleResult.result, JSONB)
        return type_coerce(value.op("-")(literal_column("'landmark_frames'")), JSONB), value.has_key("landmark_frames")
    return (type_coerce(func.json_remove(ModuleResult.result, "$.landmark_frames"), JSON),
            func.json_type(ModuleResult.result, "$.landmark_frames").is_not(None))


def _module_rows(session, assessment_id, frames: bool):
    """(module, result, revision, file_id) for one assessment."""
    where = ModuleResult.assessment_id == assessment_id
    if frames:
        return [(row.module, row.result, row.revision, row.file_id)
                for row in session.scalars(select(ModuleResult).where(where)).all()]
    result, had_frames = _results_without_frames(session)
    rows = session.execute(select(ModuleResult.module, result, ModuleResult.revision, ModuleResult.file_id, had_frames).where(where))
    return [(module, {**value, FRAMES_OMITTED: True} if omitted else value, revision, file_id)
            for module, value, revision, file_id, omitted in rows]


def _assessment_dict(session, record: Assessment, *, frames: bool = True) -> dict:
    results = _module_rows(session, record.id, frames)
    files = session.scalars(select(AssessmentFile).where(AssessmentFile.assessment_id == record.id).order_by(AssessmentFile.created_at)).all()
    reports = session.scalars(select(Report).where(Report.assessment_id == record.id).order_by(Report.created_at)).all()
    measurements = session.scalars(select(ClinicalMeasurement).where(ClinicalMeasurement.assessment_id == record.id).order_by(ClinicalMeasurement.name)).all()
    revisions = {module: revision for module, _, revision, _ in results}
    return {"id": record.id, "patient_id": record.patient_id, "status": record.status,
            "created_at": _iso(record.created_at), "updated_at": _iso(record.updated_at), "completed_at": _iso(record.completed_at),
            "review_status": record.review_status, "reviewed_at": _iso(record.reviewed_at), "reviewed_by": record.reviewed_by,
            "review_note": record.review_note,
            "modules": {module: result for module, result, _, _ in results},
            "module_revisions": revisions,
            "module_file_ids": {module: file_id for module, _, _, file_id in results},
            "files": [{"id": row.id, "module": row.module, "storage_key": row.storage_key,
                       "mime_type": row.mime_type, "size_bytes": row.size_bytes, "created_at": _iso(row.created_at)} for row in files],
            "reports": [_report_dict(row, revisions) for row in reports],
            "clinical_measurements": [{"id": row.id, "name": row.name, "value": row.value,
                                       "unit": row.unit, "recorded_by": row.recorded_by,
                                       "created_at": _iso(row.created_at)} for row in measurements]}


def _report_dict(record, current_revisions=None):
    source = record.content.get("source_module_revisions")
    outdated = source != current_revisions if isinstance(source, dict) and current_revisions is not None else None
    return {"id": record.id, "assessment_id": record.assessment_id, "content": record.content,
            "language": record.language, "generator_version": record.generator_version,
            "created_at": _iso(record.created_at), "reviewed_by": record.reviewed_by,
            "source_module_revisions": source, "outdated": outdated}


def _consented(session, patient_id):
    if not session.scalar(select(Consent.id).where(Consent.patient_id == patient_id,
                                                  Consent.acknowledged.is_(True), Consent.withdrawn_at.is_(None))):
        raise PermissionError("Current monitoring consent is required.")


def register_patient(full_name, email, password, language="English", consent=False) -> dict:
    if consent is not True:
        raise ValueError("Monitoring consent must be acknowledged before registration.")
    full_name, email, language = _identity(full_name, email, language)
    encoded = hash_password(password)
    try:
        with transaction() as session:
            user = User(full_name=full_name, email=email, password_hash=encoded, role="patient", language=language)
            session.add(user)
            session.flush()
            patient = Patient(user_id=user.id)
            session.add(patient)
            session.flush()
            session.add(Consent(patient_id=patient.id, acknowledged=True))
            _audit(session, user.id, "patient.registered", "user", user.id, role="patient")
            session.flush()
            return _user_dict(session, user)
    except IntegrityError as exc:
        raise ValueError("An account with this email already exists.") from exc


LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_THROTTLED = ("Too many unsuccessful sign-in attempts for this email. Wait 15 minutes and try again, "
                   "or ask your administrator for a recovery code.")


def login_limiter_hash(email: str) -> str:
    """Throttle key for one typed email; the email itself is never stored."""
    normalized = email.strip().lower() if isinstance(email, str) else ""
    return hashlib.sha256(f"login:{normalized}".encode("utf-8")).hexdigest()


def authenticate(email, password) -> dict:
    from backend.db.production_models import AccountSecurity, LoginFailure
    normalized = email.strip().lower() if isinstance(email, str) else ""
    limiter_hash = login_limiter_hash(normalized)
    throttled, result = False, None
    with transaction() as session:
        if session.get_bind().dialect.name == "postgresql":
            # Serialize attempts for one email across app and mobile workers.
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(limiter_hash[:15], 16)})
        since = utc_now() - LOGIN_FAILURE_WINDOW
        failures = session.scalar(select(func.count(LoginFailure.id)).where(
            LoginFailure.limiter_hash == limiter_hash, LoginFailure.created_at > since))
        if failures >= LOGIN_FAILURE_LIMIT:
            # Same answer for known and unknown emails, and no password check is spent.
            _audit(session, None, "auth.login_throttled")
            throttled = True
        else:
            # Password reset locks this same row. Capture the session revision in
            # the successful password-check transaction, never in a later read.
            user = session.scalar(select(User).where(User.email == normalized).with_for_update())
            valid = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
            if user and user.active and valid:
                session.execute(delete(LoginFailure).where(LoginFailure.limiter_hash == limiter_hash))
                _audit(session, user.id, "auth.login", "user", user.id)
                result = _user_dict(session, user)
                security = session.get(AccountSecurity, user.id)
                result["_auth_revision"] = security.session_revision if security else 0
            else:
                session.execute(delete(LoginFailure).where(LoginFailure.created_at <= since))
                session.add(LoginFailure(limiter_hash=limiter_hash))
                _audit(session, None, "auth.login_failed")
    if throttled:
        raise PermissionError(LOGIN_THROTTLED)
    if result is None:
        raise PermissionError("Email or password is incorrect, or the account is inactive.")
    return result


def get_user(user_id) -> dict:
    with transaction() as session:
        return _user_dict(session, _actor(session, user_id))


def record_logout(actor_id) -> None:
    with transaction() as session:
        actor = _actor(session, actor_id)
        _audit(session, actor.id, "auth.logout", "user", actor.id)


def bootstrap_admin(full_name, email, password) -> dict:
    full_name, email, language = _identity(full_name, email, "English")
    encoded = hash_password(password)
    with _bootstrap_lock, transaction() as session:
        if session.bind.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(74019211)"))
        if session.scalar(select(User.id).where(User.role == "admin")):
            raise PermissionError("An administrator already exists. Use the administrator panel to create staff.")
        user = User(full_name=full_name, email=email, password_hash=encoded, role="admin", language=language)
        session.add(user)
        session.flush()
        _audit(session, user.id, "admin.bootstrapped", "user", user.id, role="admin")
        return _user_dict(session, user)


def create_staff(actor_id, full_name, email, password, role="clinician", language="English") -> dict:
    if role not in {"clinician", "admin"}:
        raise ValueError("Staff role must be clinician or admin.")
    full_name, email, language = _identity(full_name, email, language)
    encoded = hash_password(password)
    try:
        with transaction() as session:
            actor = _admin(session, actor_id)
            user = User(full_name=full_name, email=email, password_hash=encoded, role=role, language=language)
            session.add(user)
            session.flush()
            if role == "clinician":
                session.add(Clinician(user_id=user.id))
                session.flush()
            _audit(session, actor.id, "staff.created", "user", user.id, role=role)
            return _user_dict(session, user)
    except IntegrityError as exc:
        raise ValueError("An account with this email already exists.") from exc


def list_users(actor_id) -> list[dict]:
    with transaction() as session:
        actor = _admin(session, actor_id)
        users = session.scalars(select(User).order_by(User.created_at)).all()
        _audit(session, actor.id, "users.listed", count=len(users))
        return [_user_dict(session, user) for user in users]


def set_user_active(actor_id, user_id, active: bool) -> dict:
    if type(active) is not bool:
        raise ValueError("Active status must be true or false.")
    with transaction() as session:
        actor = _admin(session, actor_id)
        target = session.get(User, _id(user_id))
        if target is None:
            raise LookupError("User was not found.")
        if target.id == actor.id and not active:
            raise ValueError("Administrators cannot deactivate their own account.")
        target.active = active
        _audit(session, actor.id, "user.active_changed", "user", target.id, active=active)
        return _user_dict(session, target)


def update_profile(actor_id, *, language=None, full_name=None) -> dict:
    with transaction() as session:
        actor = _actor(session, actor_id)
        if language is not None:
            actor.language = _language(language)
        if full_name is not None:
            actor.full_name, _, _ = _identity(full_name, actor.email, actor.language)
        _audit(session, actor.id, "profile.updated", "user", actor.id)
        return _user_dict(session, actor)


def link_patient(actor_id, patient_id, clinician_id) -> dict:
    with transaction() as session:
        actor = _admin(session, actor_id)
        patient = session.get(Patient, _id(patient_id))
        clinician = session.get(Clinician, _id(clinician_id)) or session.scalar(select(Clinician).where(Clinician.user_id == _id(clinician_id)))
        if patient is None or clinician is None:
            raise LookupError("Patient or clinician was not found.")
        existing = session.scalar(select(PatientClinicianLink).where(PatientClinicianLink.patient_id == patient.id,
                                                                  PatientClinicianLink.clinician_id == clinician.id))
        if existing is None:
            existing = PatientClinicianLink(patient_id=patient.id, clinician_id=clinician.id, created_by=actor.id)
            session.add(existing)
            session.flush()
        _audit(session, actor.id, "patient.linked", "patient", patient.id)
        return {"id": existing.id, "patient_id": patient.id, "clinician_id": clinician.id}


def unlink_patient(actor_id, patient_id, clinician_id) -> None:
    with transaction() as session:
        actor = _admin(session, actor_id)
        session.execute(delete(PatientClinicianLink).where(PatientClinicianLink.patient_id == _id(patient_id),
                                                         PatientClinicianLink.clinician_id == _id(clinician_id)))
        _audit(session, actor.id, "patient.unlinked", "patient", _id(patient_id))


def list_patients(actor_id) -> list[dict]:
    with transaction() as session:
        actor = _actor(session, actor_id)
        query = select(Patient, User).join(User, Patient.user_id == User.id)
        if actor.role == "patient":
            query = query.where(Patient.user_id == actor.id)
        elif actor.role == "clinician":
            query = query.join(PatientClinicianLink, PatientClinicianLink.patient_id == Patient.id).join(
                Clinician, PatientClinicianLink.clinician_id == Clinician.id).where(Clinician.user_id == actor.id)
        rows = session.execute(query.order_by(User.full_name)).all()
        _audit(session, actor.id, "patients.listed", count=len(rows))
        return [{"id": patient.id, "patient_id": patient.id, "user_id": user.id,
                 "full_name": user.full_name, "language": user.language, "active": user.active,
                 "baseline_assessment_id": patient.baseline_assessment_id if actor.role != "admin" else None} for patient, user in rows]


def create_assessment(actor_id, patient_id=None) -> dict:
    with transaction() as session:
        actor = _actor(session, actor_id)
        patient = _patient_access(session, actor, patient_id)
        _consented(session, patient.id)
        record = Assessment(patient_id=patient.id, created_by=actor.id)
        session.add(record)
        session.flush()
        _audit(session, actor.id, "assessment.created", "assessment", record.id)
        return _assessment_dict(session, record)


def list_assessments(actor_id, patient_id=None, *, frames: bool = False) -> list[dict]:
    """Newest first. Movement results omit landmark_frames unless frames=True."""
    with transaction() as session:
        actor = _actor(session, actor_id)
        patient = _patient_access(session, actor, patient_id)
        rows = session.scalars(select(Assessment).where(Assessment.patient_id == patient.id).order_by(Assessment.created_at.desc())).all()
        _audit(session, actor.id, "assessments.listed", "patient", patient.id, count=len(rows))
        return [_assessment_dict(session, record, frames=frames) for record in rows]


def get_timeline(actor_id, patient_id=None) -> list[dict]:
    return list(reversed(list_assessments(actor_id, patient_id)))


def get_assessment(actor_id, assessment_id) -> dict:
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id)
        _audit(session, actor.id, "assessment.viewed", "assessment", record.id)
        return _assessment_dict(session, record)


def ensure_assessment_writable(actor_id, assessment_id) -> dict:
    """Check permission, consent and draft status before expensive analysis."""
    with transaction() as session:
        _, record = _assessment_access(session, actor_id, assessment_id, draft=True)
        _consented(session, record.patient_id)
        return _assessment_dict(session, record)


def _reset_review(record):
    # Review applies to the measurements reviewed, not all future draft edits.
    record.review_status = "pending"
    record.reviewed_by = None
    record.reviewed_at = None
    record.review_note = None


def store_upload(actor_id, assessment_id, module, filename, data) -> str:
    if module not in MODULES:
        raise ValueError("Choose a supported assessment module.")
    saved = None
    try:
        with transaction() as session:
            actor, record = _assessment_access(session, actor_id, assessment_id, draft=True)
            _consented(session, record.patient_id)
            saved = write_upload(record.patient_id, record.id, module, filename, data)
            session.add(AssessmentFile(assessment_id=record.id, module=module, **saved))
            _audit(session, actor.id, "media.saved", "assessment", record.id, module=module)
            return saved["storage_key"]
    except BaseException:
        if saved:
            resolve_key(saved["storage_key"]).unlink(missing_ok=True)
        raise


def get_media_path(actor_id, assessment_id, storage_key) -> str:
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id)
        stored = session.scalar(select(AssessmentFile).where(AssessmentFile.assessment_id == record.id,
                                                            AssessmentFile.storage_key == storage_key))
        if stored is None:
            raise PermissionError("This media file does not belong to this assessment.")
        path = resolve_key(stored.storage_key)
        if not path.is_file():
            raise LookupError("The private media file is unavailable.")
        _audit(session, actor.id, "media.viewed", "assessment", record.id, module=stored.module)
        return str(path)


def save_module(actor_id, assessment_id, module, result, media_path=None) -> dict:
    if module not in MODULES:
        raise ValueError("Choose a supported assessment module.")
    result = _json(result)
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, draft=True)
        _consented(session, record.patient_id)
        file_id = None
        if media_path is not None:
            media = session.scalar(select(AssessmentFile).where(AssessmentFile.assessment_id == record.id,
                                                               AssessmentFile.storage_key == media_path,
                                                               AssessmentFile.module == module))
            if media is None:
                raise PermissionError("Only this module's authorized private upload may be attached.")
            file_id = media.id
        row = session.scalar(select(ModuleResult).where(ModuleResult.assessment_id == record.id, ModuleResult.module == module))
        if row is None:
            row = ModuleResult(assessment_id=record.id, module=module, result=result, file_id=file_id)
            session.add(row)
        else:
            row.result, row.file_id, row.revision, row.updated_at = result, file_id, row.revision + 1, utc_now()
        if module == "adl":
            responses = result.get("responses", result.get("answers", {}))
            if isinstance(responses, dict):
                adl = session.scalar(select(ADLResponse).where(ADLResponse.assessment_id == record.id))
                if adl is None:
                    session.add(ADLResponse(assessment_id=record.id, responses=responses))
                else:
                    adl.responses = responses
        model = result.get("model", {})
        model = model if isinstance(model, dict) else {}
        run = ModelRun(assessment_id=record.id, module=module,
                       model_name=str(model.get("name", result.get("method", result.get("pipeline", "engineered-features"))))[:100],
                       model_version=str(model.get("version", result.get("version", result.get("method", "v1"))))[:80],
                       status=str(result.get("status", "saved"))[:30])
        session.add(run)
        session.flush()
        session.add(ModelOutput(run_id=run.id, output=result))
        if isinstance(result.get("explanation"), dict):
            session.add(Explanation(run_id=run.id, explanation=result["explanation"]))
        record.updated_at = utc_now()
        _reset_review(record)
        _audit(session, actor.id, "module.saved", "assessment", record.id, module=module, revision=row.revision)
        session.flush()
        from backend.services.reporting import upsert_auto_report
        upsert_auto_report(session, record, actor.id, create=True)
        return _assessment_dict(session, record)


def finish_assessment(actor_id, assessment_id) -> dict:
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, draft=True)
        _consented(session, record.patient_id)
        results = session.scalars(select(ModuleResult).where(ModuleResult.assessment_id == record.id)).all()
        if not results:
            raise ValueError("Save at least one module before completing the assessment.")
        if not any(row.result.get("status") in {"accepted", "ACCEPT", "completed"}
                   and isinstance(row.result.get("quality"), dict)
                   and row.result["quality"].get("accepted") is True for row in results):
            raise ValueError("Save at least one accepted module before completing the assessment.")
        now = utc_now()
        record.status, record.completed_at, record.updated_at = "completed", now, now
        patient = session.scalar(select(Patient).where(Patient.id == record.patient_id).with_for_update())
        if patient.baseline_assessment_id is None:
            patient.baseline_assessment_id = record.id
        _audit(session, actor.id, "assessment.completed", "assessment", record.id)
        session.flush()
        from backend.services.reporting import upsert_auto_report
        upsert_auto_report(session, record, actor.id)
        return _assessment_dict(session, record)


def restart_assessment(actor_id, assessment_id) -> dict:
    with transaction() as session:
        actor, previous = _assessment_access(session, actor_id, assessment_id, lock=True)
        _consented(session, previous.patient_id)
        if previous.status == "draft":
            previous.status, previous.updated_at = "abandoned", utc_now()
        record = Assessment(patient_id=previous.patient_id, created_by=actor.id)
        session.add(record)
        session.flush()
        _audit(session, actor.id, "assessment.restarted", "assessment", record.id)
        return _assessment_dict(session, record)


def save_report(actor_id, assessment_id, report: dict) -> dict:
    report = _json(report)
    # Automatic-report ownership is reserved for server-authored generation.
    report.pop("auto_summary", None)
    report.pop("source_report_state", None)
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, lock=True)
        if record.status == "abandoned":
            raise ValueError("Reports cannot be added to an abandoned assessment.")
        revisions = {row.module: row.revision for row in session.scalars(select(ModuleResult).where(ModuleResult.assessment_id == record.id)).all()}
        # Server-derived provenance cannot be supplied or overridden by a caller.
        report = report | {"source_module_revisions": revisions,
                           "source_assessment_id": record.id,
                           "source_assessment_updated_at": _iso(record.updated_at)}
        user = session.scalar(select(User).join(Patient, Patient.user_id == User.id).where(Patient.id == record.patient_id))
        row = Report(assessment_id=record.id, content=report, language=user.language,
                     generator_version=str(report.get("method", report.get("version", "deterministic-v1")))[:80])
        session.add(row)
        session.flush()
        _audit(session, actor.id, "report.saved", "assessment", record.id)
        return _report_dict(row, revisions)


def review_assessment(actor_id, assessment_id, status="reviewed", note="") -> dict:
    if status not in {"reviewed", "follow_up", "pending"}:
        raise ValueError("Review status must be reviewed, follow_up, or pending.")
    if not isinstance(note, str) or len(note) > 4000:
        raise ValueError("Review note must contain at most 4000 characters.")
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, lock=True)
        if actor.role != "clinician":
            raise PermissionError("Only a linked clinician can review assessments.")
        if record.status == "abandoned":
            raise ValueError("Abandoned assessments cannot be marked reviewed.")
        record.review_status, record.review_note = status, note.strip()
        record.reviewed_by, record.reviewed_at = actor.id, utc_now()
        _audit(session, actor.id, "assessment.reviewed", "assessment", record.id, status=status)
        session.flush()
        from backend.services.reporting import upsert_auto_report
        upsert_auto_report(session, record, actor.id)
        return _assessment_dict(session, record)


def save_clinical_measurements(actor_id, assessment_id, measurements: dict) -> dict:
    """Linked clinicians record reference/context values separately from AI features.

    Values may be numbers or {"value": number, "unit": "..."} objects. They are
    clinician-entered metadata; recording them does not validate an AI model.
    """
    if not isinstance(measurements, dict) or not 1 <= len(measurements) <= 100:
        raise ValueError("Provide between 1 and 100 clinical measurements.")
    prepared = {}
    for name, item in measurements.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", name):
            raise ValueError("Clinical measurement names must use lowercase letters, digits, or underscores.")
        value, unit = (item.get("value"), item.get("unit")) if isinstance(item, dict) else (item, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 10_000_000:
            raise ValueError("Clinical measurements must be finite numeric values within the supported range.")
        if name in {"age_years", "disease_duration_years"} and not 0 <= value <= 120:
            raise ValueError("Age and disease duration must be between 0 and 120 years.")
        if unit is not None and (not isinstance(unit, str) or len(unit) > 40):
            raise ValueError("Clinical measurement units must contain at most 40 characters.")
        prepared[name] = float(value), unit
    with transaction() as session:
        actor, record = _assessment_access(session, actor_id, assessment_id, lock=True)
        if actor.role != "clinician":
            raise PermissionError("Only a linked clinician can record clinical measurements.")
        if record.status == "abandoned":
            raise ValueError("Clinical measurements cannot be added to abandoned assessments.")
        for name, (value, unit) in prepared.items():
            row = session.scalar(select(ClinicalMeasurement).where(ClinicalMeasurement.assessment_id == record.id,
                                                                  ClinicalMeasurement.name == name))
            if row is None:
                session.add(ClinicalMeasurement(assessment_id=record.id, name=name, value=value, unit=unit, recorded_by=actor.id))
            else:
                row.value, row.unit, row.recorded_by = value, unit, actor.id
        _reset_review(record)
        _audit(session, actor.id, "clinical_measurements.saved", "assessment", record.id, count=len(prepared))
        session.flush()
        from backend.services.reporting import upsert_auto_report
        upsert_auto_report(session, record, actor.id)
        return _assessment_dict(session, record)


def list_audit_logs(actor_id, limit=100) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Audit limit must be between 1 and 500.")
    with transaction() as session:
        _admin(session, actor_id)
        logs = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
        return [{"id": row.id, "actor_id": row.actor_id, "action": row.action,
                 "resource_type": row.resource_type, "resource_id": row.resource_id,
                 "details": row.details, "created_at": _iso(row.created_at)} for row in logs]


def record_tool_audit(actor_id, tool, assessment_id=None, success=True) -> None:
    if not isinstance(tool, str) or not re.fullmatch(r"[a-z_]{1,60}", tool):
        raise ValueError("Invalid tool name.")
    with transaction() as session:
        actor = _actor(session, actor_id)
        if assessment_id is not None:
            _assessment_access(session, actor.id, assessment_id)
        _audit(session, actor.id, "mcp.tool", "assessment" if assessment_id else None,
               _id(assessment_id) if assessment_id else None, tool=tool, success=bool(success))


def system_status(actor_id) -> dict:
    with transaction() as session:
        _admin(session, actor_id)
        session.execute(text("SELECT 1"))
        return {"database": "connected", "engine": session.bind.dialect.name,
                "users": session.scalar(select(func.count(User.id))),
                "assessments": session.scalar(select(func.count(Assessment.id)))}
