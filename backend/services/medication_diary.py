"""Patient-reported ON/OFF medicine diary and usual medicine times.

Context for reading recordings, never advice: no drug names, doses or
instructions are stored or shown. The patient or a linked clinician may write,
and new entries need current monitoring consent. Moments are stored in UTC and
shown in Pakistan time.
"""

from datetime import datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.db import transaction
from backend.db.context_models import DIARY_STATES, MedicationDiaryEntry, MedicineTimes
from backend.db.models import utc_now

LOCAL = ZoneInfo("Asia/Karachi")
BACKDATE_LIMIT = timedelta(days=7)
DUE_WINDOW = timedelta(hours=2)
MAX_TIMES = 8
_CLOCK = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


def _svc():
    from backend import services
    return services


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _entry(row) -> dict:
    return {"id": row.id, "patient_id": row.patient_id, "observed_at": _svc()._iso(row.observed_at),
            "state": row.state, "note": row.note, "recorded_by_role": row.recorded_by_role, "source": "patient_report"}


def save_diary_entry(actor_id, state, *, observed_at=None, note="", patient_id=None) -> dict:
    if state not in DIARY_STATES:
        raise ValueError("Choose how your medicine is working.")
    note = "" if note is None else note
    if not isinstance(note, str) or len(note) > 300:
        raise ValueError("Keep the diary note under 300 characters.")
    now = utc_now()
    if observed_at is not None and not isinstance(observed_at, datetime):
        raise ValueError("Choose a time for this diary entry.")
    moment = now if observed_at is None else _aware(observed_at).astimezone(timezone.utc)
    if moment > now + timedelta(minutes=5):
        raise ValueError("A diary entry cannot be in the future.")
    if moment < now - BACKDATE_LIMIT:
        raise ValueError("Diary entries can be added for the last 7 days.")
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        row = MedicationDiaryEntry(patient_id=patient.id, observed_at=moment, state=state, note=note.strip(),
                                   recorded_by=actor.id, recorded_by_role=actor.role)
        session.add(row)
        svc._audit(session, actor.id, "medication_diary.saved", "patient", patient.id)
        session.flush()
        return _entry(row)


def list_diary(actor_id, patient_id=None, *, days=7) -> list[dict]:
    """Entries from the last ``days`` days, newest first."""
    if type(days) is not int or not 1 <= days <= 90:
        raise ValueError("Choose 1 to 90 days of diary.")
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        rows = session.scalars(select(MedicationDiaryEntry).where(
            MedicationDiaryEntry.patient_id == patient.id,
            MedicationDiaryEntry.observed_at >= utc_now() - timedelta(days=days),
        ).order_by(MedicationDiaryEntry.observed_at.desc(), MedicationDiaryEntry.id)).all()
        svc._audit(session, actor.id, "medication_diary.read", "patient", patient.id, count=len(rows))
        return [_entry(row) for row in rows]


def save_medicine_times(actor_id, times, patient_id=None) -> list[str]:
    if (not isinstance(times, (list, tuple)) or len(times) > MAX_TIMES
            or not all(isinstance(value, str) and _CLOCK.fullmatch(value) for value in times)):
        raise ValueError("Choose up to 8 usual medicine times.")
    values = sorted(set(times))
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        svc._consented(session, patient.id)
        row = session.get(MedicineTimes, patient.id)
        if row is None:
            row = MedicineTimes(patient_id=patient.id, times=values, updated_by=actor.id)
            session.add(row)
        row.times, row.updated_by, row.updated_at = values, actor.id, utc_now()
        svc._audit(session, actor.id, "medicine_times.saved", "patient", patient.id, count=len(values))
        return values


def get_medicine_times(actor_id, patient_id=None) -> list[str]:
    svc = _svc()
    with transaction() as session:
        actor = svc._actor(session, actor_id)
        patient = svc._patient_access(session, actor, patient_id)
        row = session.get(MedicineTimes, patient.id)
        return list(row.times) if row else []


def due_medicine_time(times, entries, now=None) -> str | None:
    """The latest usual time in the last two hours with no diary entry since it."""
    now = _aware(now or utc_now()).astimezone(LOCAL)
    latest = max((datetime.fromisoformat(entry["observed_at"]) for entry in entries), default=None)
    due = None
    for value in times:
        if not isinstance(value, str) or not _CLOCK.fullmatch(value):
            continue
        hour, minute = map(int, value.split(":"))
        for day in (now.date(), now.date() - timedelta(days=1)):
            moment = datetime.combine(day, time(hour, minute), LOCAL)
            if timedelta(0) <= now - moment <= DUE_WINDOW and (latest is None or latest < moment):
                if due is None or moment > due[0]:
                    due = (moment, value)
    return due[1] if due else None


def diary_counts(entries, *, days=7, now=None) -> dict:
    now = _aware(now or utc_now())
    counts = dict.fromkeys(DIARY_STATES, 0)
    for entry in entries:
        if entry.get("state") in counts and now - datetime.fromisoformat(entry["observed_at"]) <= timedelta(days=days):
            counts[entry["state"]] += 1
    return counts
