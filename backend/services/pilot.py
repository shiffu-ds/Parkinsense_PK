"""Authorized clinic feasibility pilots, never invented clinical evidence."""

from datetime import date, datetime, timezone
import math
from statistics import median

from sqlalchemy import select

from backend.db import transaction
from backend.db.models import User, utc_now
from backend.db.pilot_models import ClinicPilot, PilotEnrollment, PilotObservation, PilotPaymentIntent, PilotReviewTimer

DEFAULT_TARGETS = {
    "minimum_patients": 10, "minimum_review_pairs": 10,
    "minimum_usability_responses": 10, "minimum_review_saving_fraction": 0.20,
    "minimum_completion_fraction": 0.85, "minimum_usable_recording_fraction": 0.85,
    "minimum_usability_rating": 4.0,
}
DEVICE_CATEGORIES = ("mobile", "desktop", "other", "unknown")
RESPONDENT_ROLES = ("clinic_owner", "procurement", "clinician", "other")
CURRENCIES = ("PKR", "USD", "EUR", "GBP")
PAYMENT_PERIODS = ("monthly", "yearly", "per_assessment")


def _svc():
    from backend import services
    return services


def _today():
    return datetime.now(timezone.utc).date()


def _text(value, label, limit=2000, required=False):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ValueError(f"{label} must be text of {'1 to ' if required else 'at most '}{limit} characters.")
    return value.strip()


def _date(value, label):
    try:
        result = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        result = None
    if result is None or value != result.isoformat() or not 2000 <= result.year <= 2100:
        raise ValueError(f"{label} must be an ISO date between 2000 and 2100.")
    return result


def _integer(value, label, low=0, high=100):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be a whole number from {low} to {high}.")
    return value


def _number(value, label, low=0, high=14400, optional=False):
    if optional and value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be a finite number from {low} to {high}.")
    return float(value)


def _targets(value=None):
    value = dict(DEFAULT_TARGETS) if value is None else value
    if not isinstance(value, dict) or set(value) != set(DEFAULT_TARGETS):
        raise ValueError("Specify every predefined pilot target and no additional targets.")
    result = {}
    for key in DEFAULT_TARGETS:
        if key in ("minimum_patients", "minimum_review_pairs", "minimum_usability_responses"):
            result[key] = _integer(value[key], key, 1, 10000)
        elif key == "minimum_usability_rating":
            result[key] = _number(value[key], key, 1, 5)
        else:
            result[key] = _number(value[key], key, 0, 1)
    return result


def _clinician(session, actor_id):
    actor = _svc()._actor(session, actor_id)
    if actor.role != "clinician":
        raise PermissionError("An active clinician account is required for clinic pilots.")
    return actor


def _pilot_access(session, actor_id, pilot_id, *, lock=False, writable=False):
    actor = _clinician(session, actor_id)
    query = select(ClinicPilot).where(ClinicPilot.id == _svc()._id(pilot_id))
    pilot = session.scalar(query.with_for_update() if lock else query)
    if pilot is None:
        raise LookupError("Clinic pilot was not found.")
    if pilot.owner_id != actor.id:
        raise PermissionError("Only the clinician who owns this pilot can access it.")
    if writable and pilot.status == "closed":
        raise ValueError("This pilot is closed; its observations are finalized.")
    return actor, pilot


def _patient_access(session, actor, patient_id):
    patient = _svc()._patient_access(session, actor, patient_id)
    patient_user = session.get(User, patient.user_id)
    if patient_user is None or not patient_user.active:
        raise PermissionError("An active patient account is required.")
    _svc()._consented(session, patient.id)
    return patient


def _enrollment(session, actor, pilot, patient_id, *, acknowledged=True):
    patient = _patient_access(session, actor, patient_id)
    row = session.scalar(select(PilotEnrollment).where(PilotEnrollment.pilot_id == pilot.id,
                                                     PilotEnrollment.patient_id == patient.id).with_for_update())
    if row is None:
        raise LookupError("Invite this patient to the pilot first.")
    if row.withdrawn_at is not None or (acknowledged and row.acknowledged_at is None):
        raise PermissionError("Separate current patient pilot participation is required.")
    return row


def _lock_plan(pilot):
    if pilot.plan_locked_at is None:
        pilot.plan_locked_at = utc_now()
        pilot.status = "active"


def _pilot_dict(pilot):
    return {"id": pilot.id, "name": pilot.name, "starts_on": pilot.starts_on.isoformat(),
            "ends_on": pilot.ends_on.isoformat(), "status": pilot.status,
            "targets": dict(pilot.targets), "notes": pilot.notes,
            "plan_locked_at": _svc()._iso(pilot.plan_locked_at),
            "closed_at": _svc()._iso(pilot.closed_at), "created_at": _svc()._iso(pilot.created_at)}


def create_pilot(actor_id, name, starts_on, ends_on, *, targets=None, notes=""):
    start, end = _date(starts_on, "Start date"), _date(ends_on, "End date")
    if end < start or (end - start).days > 366:
        raise ValueError("Pilot end must follow its start within 366 days.")
    name, notes, targets = _text(name, "Pilot name", 160, True), _text(notes, "Notes"), _targets(targets)
    with transaction() as session:
        actor = _clinician(session, actor_id)
        row = ClinicPilot(owner_id=actor.id, name=name, starts_on=start, ends_on=end,
                          targets=targets, notes=notes)
        session.add(row)
        session.flush()
        _svc()._audit(session, actor.id, "pilot.created", "clinic_pilot", row.id)
        return _pilot_dict(row)


def list_pilots(actor_id):
    with transaction() as session:
        actor = _clinician(session, actor_id)
        rows = session.scalars(select(ClinicPilot).where(ClinicPilot.owner_id == actor.id)
                               .order_by(ClinicPilot.created_at.desc(), ClinicPilot.id)).all()
        return [_pilot_dict(row) for row in rows]


def update_pilot_plan(actor_id, pilot_id, *, name, starts_on, ends_on, targets, notes=""):
    start, end = _date(starts_on, "Start date"), _date(ends_on, "End date")
    if end < start or (end - start).days > 366:
        raise ValueError("Pilot end must follow its start within 366 days.")
    targets, name, notes = _targets(targets), _text(name, "Pilot name", 160, True), _text(notes, "Notes")
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        if pilot.plan_locked_at is not None:
            raise ValueError("Pilot targets and dates are frozen after the first outcome or review timer.")
        pilot.name, pilot.starts_on, pilot.ends_on = name, start, end
        pilot.targets, pilot.notes = targets, notes
        _svc()._audit(session, actor.id, "pilot.plan_updated", "clinic_pilot", pilot.id)
        return _pilot_dict(pilot)


def invite_patient(actor_id, pilot_id, patient_id):
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        patient = _patient_access(session, actor, patient_id)
        row = session.scalar(select(PilotEnrollment).where(PilotEnrollment.pilot_id == pilot.id,
                                                         PilotEnrollment.patient_id == patient.id))
        if row is None:
            row = PilotEnrollment(pilot_id=pilot.id, patient_id=patient.id)
            session.add(row)
            session.flush()
        _svc()._audit(session, actor.id, "pilot.patient_invited", "clinic_pilot", pilot.id)
        return {"id": row.id, "patient_id": row.patient_id, "acknowledged": row.acknowledged_at is not None,
                "withdrawn": row.withdrawn_at is not None}


def list_patient_invitations(actor_id):
    with transaction() as session:
        actor = _svc()._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("Patient participation can only be opened by the patient.")
        patient = _svc()._patient_access(session, actor)
        rows = session.execute(select(PilotEnrollment, ClinicPilot).join(
            ClinicPilot, PilotEnrollment.pilot_id == ClinicPilot.id).where(
            PilotEnrollment.patient_id == patient.id).order_by(ClinicPilot.created_at.desc())).all()
        invitations = []
        for enrollment, pilot in rows:
            try:
                owner = _clinician(session, pilot.owner_id)
                _svc()._patient_access(session, owner, patient.id)
            except PermissionError:
                continue
            invitations.append({"id": pilot.id, "name": pilot.name, "starts_on": pilot.starts_on.isoformat(),
                                "ends_on": pilot.ends_on.isoformat(), "closed": pilot.status == "closed",
                                "acknowledged": enrollment.acknowledged_at is not None,
                                "withdrawn": enrollment.withdrawn_at is not None,
                                "consent_version": enrollment.consent_version})
        return invitations


def acknowledge_pilot_participation(actor_id, pilot_id, *, acknowledged):
    if acknowledged is not True:
        raise ValueError("Explicit separate pilot participation acknowledgement is required.")
    with transaction() as session:
        actor = _svc()._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("The patient must acknowledge their own pilot participation.")
        patient = _patient_access(session, actor, None)
        pilot = session.scalar(select(ClinicPilot).where(ClinicPilot.id == _svc()._id(pilot_id)).with_for_update())
        if pilot is None:
            raise LookupError("Clinic pilot was not found.")
        owner = _clinician(session, pilot.owner_id)
        row = _enrollment(session, owner, pilot, patient.id, acknowledged=False)
        if pilot.status == "closed":
            raise ValueError("This pilot is closed.")
        row.acknowledged_at = row.acknowledged_at or utc_now()
        _svc()._audit(session, actor.id, "pilot.participation_acknowledged", "clinic_pilot", pilot.id)
        return {"acknowledged": True, "consent_version": row.consent_version}


def withdraw_pilot_participation(actor_id, pilot_id):
    with transaction() as session:
        actor = _svc()._actor(session, actor_id)
        if actor.role != "patient":
            raise PermissionError("The patient must withdraw their own pilot participation.")
        patient = _svc()._patient_access(session, actor)
        row = session.scalar(select(PilotEnrollment).where(PilotEnrollment.pilot_id == _svc()._id(pilot_id),
                                                         PilotEnrollment.patient_id == patient.id).with_for_update())
        if row is None:
            raise LookupError("Pilot invitation was not found.")
        row.withdrawn_at = row.withdrawn_at or utc_now()
        _svc()._audit(session, actor.id, "pilot.participation_withdrawn", "clinic_pilot", row.pilot_id)
        return {"withdrawn": True}


def _observation_date(pilot, value):
    observed = _date(value, "Observation date")
    if not pilot.starts_on <= observed <= pilot.ends_on or observed > _today():
        raise ValueError("Observation date must be within the pilot and not in the future.")
    return observed


def _assessment(session, actor, enrollment, assessment_id):
    _, assessment = _svc()._assessment_access(session, actor.id, assessment_id)
    if assessment.patient_id != enrollment.patient_id:
        raise PermissionError("Review and enrollment must belong to the same patient.")
    return assessment


def _timer_dict(row):
    return {"id": row.id, "assessment_id": row.assessment_id, "mode": row.mode,
            "started_at": _svc()._iso(row.started_at), "stopped_at": _svc()._iso(row.stopped_at),
            "elapsed_seconds": row.elapsed_seconds, "source": "server_elapsed_timer"}


def start_review_timer(actor_id, pilot_id, patient_id, assessment_id, *, mode="app"):
    if mode not in ("baseline", "app"):
        raise ValueError("Timer mode must be baseline or app.")
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        enrollment = _enrollment(session, actor, pilot, patient_id)
        assessment_id = _assessment(session, actor, enrollment, assessment_id).id
        _observation_date(pilot, _today().isoformat())
        running = session.scalars(select(PilotReviewTimer).where(
            PilotReviewTimer.enrollment_id.in_(select(PilotEnrollment.id).where(PilotEnrollment.pilot_id == pilot.id)),
            PilotReviewTimer.stopped_at.is_(None))).all()
        for timer in running:
            timer_enrollment = session.get(PilotEnrollment, timer.enrollment_id)
            try:
                _enrollment(session, actor, pilot, timer_enrollment.patient_id)
            except (PermissionError, LookupError):
                # Revoked participants disappear from the dashboard. Their
                # abandoned timer must not trap all other patients in the pilot.
                timer.stopped_at, timer.elapsed_seconds = utc_now(), None
            else:
                raise ValueError("Stop the running review timer before starting another.")
        _lock_plan(pilot)
        row = PilotReviewTimer(enrollment_id=enrollment.id, assessment_id=assessment_id,
                               mode=mode, started_at=utc_now())
        session.add(row)
        session.flush()
        _svc()._audit(session, actor.id, "pilot.timer_started", "clinic_pilot", pilot.id)
        return _timer_dict(row)


def stop_review_timer(actor_id, pilot_id, timer_id):
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        row = session.get(PilotReviewTimer, _svc()._id(timer_id))
        enrollment = session.get(PilotEnrollment, row.enrollment_id) if row else None
        if enrollment is None or enrollment.pilot_id != pilot.id:
            raise PermissionError("This review timer does not belong to the pilot.")
        _enrollment(session, actor, pilot, enrollment.patient_id)
        _assessment(session, actor, enrollment, row.assessment_id)
        if row.stopped_at is None:
            now = utc_now()
            started = row.started_at.replace(tzinfo=timezone.utc) if row.started_at.tzinfo is None else row.started_at
            seconds = (now - started).total_seconds()
            # A forgotten timer or changed server clock produces an unusable
            # duration, not a fabricated long review or a permanently stuck timer.
            row.elapsed_seconds = seconds if math.isfinite(seconds) and 0 <= seconds <= 14400 else None
            row.stopped_at = now
            _svc()._audit(session, actor.id, "pilot.timer_stopped", "clinic_pilot", pilot.id)
        return _timer_dict(row)


def _review_value(session, data, enrollment, mode, assessment_id):
    timer_id, value = data.get(f"{mode}_timer_id"), data.get(f"{mode}_review_seconds")
    if timer_id is None:
        return _number(value, f"{mode} review seconds", optional=True), None
    if value is not None:
        raise ValueError("Use a collected timer or a manually reported duration, not both.")
    timer = session.get(PilotReviewTimer, _svc()._id(timer_id))
    if timer is None or timer.enrollment_id != enrollment.id or timer.mode != mode:
        raise PermissionError("Review timer must match this patient and review mode.")
    if timer.stopped_at is None or timer.elapsed_seconds is None:
        raise ValueError("Stop the review timer before adding it to an observation.")
    if assessment_id is None or timer.assessment_id != assessment_id:
        raise ValueError("A collected review timer must match the observation's assessment.")
    used = session.scalar(select(PilotObservation.id).where(
        getattr(PilotObservation, f"{mode}_timer_id") == timer.id))
    if used:
        raise ValueError("This collected review timer was already used in an observation.")
    return float(timer.elapsed_seconds), timer.id


def save_observation(actor_id, pilot_id, patient_id, data):
    if not isinstance(data, dict):
        raise ValueError("Observation must be a structured object.")
    allowed = {"assessment_id", "observed_on", "planned_tasks", "attempted_tasks", "completed_tasks",
               "recording_attempts", "usable_recordings", "usability_rating", "needed_help", "device_category",
               "baseline_review_seconds", "app_review_seconds", "baseline_timer_id", "app_timer_id", "notes"}
    if set(data) - allowed:
        raise ValueError("Observation contains unsupported fields.")
    counts = {key: _integer(data.get(key), key, low=1 if key == "planned_tasks" else 0) for key in
              ("planned_tasks", "attempted_tasks", "completed_tasks", "recording_attempts", "usable_recordings")}
    if not counts["planned_tasks"] >= counts["attempted_tasks"] >= counts["completed_tasks"]:
        raise ValueError("Completed tasks cannot exceed attempts; attempts cannot exceed planned tasks.")
    if counts["usable_recordings"] > counts["recording_attempts"]:
        raise ValueError("Usable recordings cannot exceed all recording attempts, including failures.")
    rating = data.get("usability_rating")
    if rating is not None:
        rating = _integer(rating, "Patient-reported usability", 1, 5)
    help_needed = data.get("needed_help")
    if help_needed is not None and type(help_needed) is not bool:
        raise ValueError("Help needed must be yes, no, or unknown.")
    device = data.get("device_category", "unknown")
    if device not in DEVICE_CATEGORIES:
        raise ValueError("Choose mobile, desktop, other, or unknown for device category.")
    notes = _text(data.get("notes", ""), "Observation notes")
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        enrollment = _enrollment(session, actor, pilot, patient_id)
        observed = _observation_date(pilot, data.get("observed_on"))
        assessment_id = data.get("assessment_id")
        if assessment_id is not None:
            assessment_id = _assessment(session, actor, enrollment, assessment_id).id
        baseline, baseline_timer = _review_value(session, data, enrollment, "baseline", assessment_id)
        app, app_timer = _review_value(session, data, enrollment, "app", assessment_id)
        if (baseline is not None or app is not None) and assessment_id is None:
            raise ValueError("Review durations require the same authorized assessment for a comparable visit.")
        _lock_plan(pilot)
        row = PilotObservation(enrollment_id=enrollment.id, assessment_id=assessment_id, observed_on=observed,
                               **counts, usability_rating=rating, needed_help=help_needed, device_category=device,
                               baseline_review_seconds=baseline, app_review_seconds=app,
                               baseline_timer_id=baseline_timer, app_timer_id=app_timer, notes=notes)
        session.add(row)
        session.flush()
        _svc()._audit(session, actor.id, "pilot.observation_saved", "clinic_pilot", pilot.id)
        return _observation_dict(row)


def _observation_dict(row):
    fields = ("id", "assessment_id", "planned_tasks", "attempted_tasks", "completed_tasks",
              "recording_attempts", "usable_recordings", "usability_rating", "needed_help", "device_category",
              "baseline_review_seconds", "app_review_seconds", "baseline_timer_id", "app_timer_id", "notes")
    result = {field: getattr(row, field) for field in fields}
    result.update({"observed_on": row.observed_on.isoformat(), "source": "clinician_observed_counts_patient_reported_usability",
                   "baseline_review_source": "server_elapsed_timer" if row.baseline_timer_id else
                   ("manually_reported" if row.baseline_review_seconds is not None else "unknown"),
                   "app_review_source": "server_elapsed_timer" if row.app_timer_id else
                   ("manually_reported" if row.app_review_seconds is not None else "unknown")})
    return result


def save_payment_intent(actor_id, pilot_id, *, respondent_role, intent, amount=None,
                        currency="PKR", period="monthly", reported_on, notes=""):
    if respondent_role not in RESPONDENT_ROLES or intent not in ("yes", "no", "undecided"):
        raise ValueError("Choose a supported respondent role and explicit payment intent.")
    if currency not in CURRENCIES or period not in PAYMENT_PERIODS:
        raise ValueError("Choose a supported currency and payment period.")
    amount = _number(amount, "Reported amount", high=1e9, optional=True)
    if amount is not None and intent != "yes":
        raise ValueError("A proposed amount only belongs to an explicit yes response.")
    notes = _text(notes, "Payment discussion notes")
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        observed = _observation_date(pilot, reported_on)
        _lock_plan(pilot)
        row = PilotPaymentIntent(pilot_id=pilot.id, respondent_role=respondent_role, intent=intent,
                                 amount=amount, currency=currency, period=period,
                                 reported_on=observed, notes=notes)
        session.add(row)
        session.flush()
        _svc()._audit(session, actor.id, "pilot.payment_intent_saved", "clinic_pilot", pilot.id)
        return {"id": row.id, "intent": intent, "source": "reported_payment_intent", "actual_payment": False}


def _metrics(observations, targets):
    n = len(observations)
    patients = len({row.enrollment_id for row in observations})
    planned = sum(row.planned_tasks for row in observations)
    attempted = sum(row.attempted_tasks for row in observations)
    completed = sum(row.completed_tasks for row in observations)
    recording_attempts = sum(row.recording_attempts for row in observations)
    usable = sum(row.usable_recordings for row in observations)
    pairs = [row for row in observations if row.baseline_review_seconds is not None and row.app_review_seconds is not None]
    saving_minutes = [(row.baseline_review_seconds - row.app_review_seconds) / 60 for row in pairs]
    saving_fractions = [(row.baseline_review_seconds - row.app_review_seconds) / row.baseline_review_seconds
                        for row in pairs if row.baseline_review_seconds > 0]
    ratings = [row.usability_rating for row in observations if row.usability_rating is not None]
    paired_patients = len({row.enrollment_id for row in pairs})
    fractional_review_patients = len({row.enrollment_id for row in pairs if row.baseline_review_seconds > 0})
    usability_patients = len({row.enrollment_id for row in observations if row.usability_rating is not None})
    recording_patients = len({row.enrollment_id for row in observations if row.recording_attempts > 0})
    completion = completed / planned if planned else None
    recording_rate = usable / recording_attempts if recording_attempts else None
    median_saving = median(saving_minutes) if saving_minutes else None
    median_saving_fraction = median(saving_fractions) if saving_fractions else None
    median_rating = median(ratings) if ratings else None
    enough_patients = patients >= targets["minimum_patients"]
    gates = {
        "review_time": (len(saving_fractions) >= targets["minimum_review_pairs"] and
                        fractional_review_patients >= targets["minimum_patients"], median_saving_fraction,
                        targets["minimum_review_saving_fraction"]),
        "task_completion": (planned > 0, completion, targets["minimum_completion_fraction"]),
        "recording_usability": (recording_attempts > 0 and recording_patients >= targets["minimum_patients"],
                                recording_rate, targets["minimum_usable_recording_fraction"]),
        "patient_usability": (len(ratings) >= targets["minimum_usability_responses"] and
                              usability_patients >= targets["minimum_patients"], median_rating,
                              targets["minimum_usability_rating"]),
    }
    return {
        "observations": n, "observed_patients": patients, "planned_tasks": planned, "attempted_tasks": attempted,
        "completed_tasks": completed, "not_attempted_tasks": planned - attempted,
        "failed_or_incomplete_attempts": attempted - completed,
        "completion_fraction": completion, "recording_attempts": recording_attempts,
        "usable_recordings": usable, "usable_recording_fraction": recording_rate,
        "paired_reviews": len(pairs), "fractional_review_pairs": len(saving_fractions),
        "paired_review_patients": paired_patients, "fractional_review_patients": fractional_review_patients,
        "usability_patients": usability_patients, "recording_patients": recording_patients,
        "median_minutes_saved": median_saving, "median_review_saving_fraction": median_saving_fraction,
        "baseline_review_coverage": sum(row.baseline_review_seconds is not None for row in observations),
        "app_review_coverage": sum(row.app_review_seconds is not None for row in observations),
        "usability_responses": len(ratings), "median_usability_rating": median_rating,
        "help_responses": sum(row.needed_help is not None for row in observations),
        "needed_help_count": sum(row.needed_help is True for row in observations),
        "target_checks": {key: "unknown" if not enough_patients or not enough or value is None else
                          ("met" if value >= threshold else "below_target")
                          for key, (enough, value, threshold) in gates.items()},
        "evidence_type": "feasibility_observations_and_reports_not_clinical_validation",
    }


def get_pilot(actor_id, pilot_id):
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id)
        rows = session.scalars(select(PilotEnrollment).where(PilotEnrollment.pilot_id == pilot.id)
                               .order_by(PilotEnrollment.created_at, PilotEnrollment.id)).all()
        enrollments, observations, timers = [], [], []
        for row in rows:
            try:
                patient = _patient_access(session, actor, row.patient_id)
            except PermissionError:
                continue
            if row.withdrawn_at is not None:
                continue
            user = session.get(User, patient.user_id)
            enrollments.append({"id": row.id, "patient_id": row.patient_id, "patient_name": user.full_name,
                                "acknowledged": row.acknowledged_at is not None})
            if row.acknowledged_at is None:
                continue
            for observation in session.scalars(select(PilotObservation).where(PilotObservation.enrollment_id == row.id)
                                              .order_by(PilotObservation.observed_on, PilotObservation.id)).all():
                observations.append(observation)
            timers.extend(_timer_dict(timer) | {"patient_id": row.patient_id} for timer in
                          session.scalars(select(PilotReviewTimer).where(PilotReviewTimer.enrollment_id == row.id)
                                          .order_by(PilotReviewTimer.created_at)).all())
        payments = session.scalars(select(PilotPaymentIntent).where(PilotPaymentIntent.pilot_id == pilot.id)
                                   .order_by(PilotPaymentIntent.reported_on, PilotPaymentIntent.id)).all()
        result = _pilot_dict(pilot)
        result.update({"enrollments": enrollments,
                       "observations": [_observation_dict(row) for row in observations], "timers": timers,
                       "metrics": _metrics(observations, pilot.targets),
                       "payment_intents": [{"respondent_role": row.respondent_role, "intent": row.intent,
                                            "amount": row.amount, "currency": row.currency, "period": row.period,
                                            "reported_on": row.reported_on.isoformat(), "notes": row.notes,
                                            "source": "reported_payment_intent", "actual_payment": False} for row in payments]})
        _svc()._audit(session, actor.id, "pilot.read", "clinic_pilot", pilot.id, count=len(observations))
        return result


def export_pilot_aggregate(actor_id, pilot_id):
    pilot = get_pilot(actor_id, pilot_id)
    return {"schema_version": "clinic-pilot-aggregate-v1", "status": pilot["status"],
            "plan_frozen": pilot["plan_locked_at"] is not None or pilot["status"] == "closed",
            "targets": pilot["targets"], "metrics": pilot["metrics"],
            "payment_discussions": {intent: sum(row["intent"] == intent for row in pilot["payment_intents"])
                                    for intent in ("yes", "no", "undecided")},
            "limitations": ["Aggregate feasibility evidence; not clinical validation.",
                            "Payment discussions are reported intentions, not transactions.",
                            "Only currently authorized participating patients contribute; missing values remain unknown."]}


def close_pilot(actor_id, pilot_id):
    with transaction() as session:
        actor, pilot = _pilot_access(session, actor_id, pilot_id, lock=True, writable=True)
        now = utc_now()
        # Finalizing discards unfinished timing intervals. It must never turn
        # an idle or abandoned timer into a measured review duration.
        running = session.scalars(select(PilotReviewTimer).where(
            PilotReviewTimer.enrollment_id.in_(select(PilotEnrollment.id).where(PilotEnrollment.pilot_id == pilot.id)),
            PilotReviewTimer.stopped_at.is_(None))).all()
        for timer in running:
            timer.stopped_at, timer.elapsed_seconds = now, None
        pilot.status, pilot.closed_at = "closed", now
        _svc()._audit(session, actor.id, "pilot.closed", "clinic_pilot", pilot.id)
        return _pilot_dict(pilot)
