"""Patient words, personal goals and clinician-authored follow-up.

These panels intentionally keep self-reported experiences apart from movement
measurements. No rating is a diagnostic scale or an automated recommendation.
Authorization and consent are enforced by the care service on every request.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from backend.services import care

from .design import empty_state, section_header, status_pill


_RATINGS = {
    "energy": ("Energy", ["Very low", "Low", "Some energy", "Good", "Very good"]),
    "sleep_quality": ("Sleep last night", ["Very poor", "Poor", "Mixed", "Good", "Restful"]),
    "movement_ease": ("Ease of everyday movement", ["Very difficult", "Difficult", "Mixed", "Comfortable", "Very comfortable"]),
    "mood": ("Mood", ["Very low", "Low", "Mixed", "Good", "Very good"]),
}
_GOAL_STATUSES = {"active": "In progress", "completed": "Completed", "paused": "Paused"}


def _today():
    return datetime.now(ZoneInfo("Asia/Karachi")).date()


def _date_label(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "Date unavailable"


def _record_checkin(user, patient_id, *, clinician=False):
    prefix = f"checkin_{patient_id}"
    caption = (
        "Record the patient's own answers. These are experiences they report, separate from recorded movement."
        if clinician else
        "A short record of how your day felt. Your own words help your care team understand the recordings."
    )
    st.caption(caption)
    if not clinician and user.get("language") == "Roman Urdu":
        st.caption("Aaj ka din kaisa raha? Jo aap ne mehsoos kiya, woh yahan likh dein.")
    with st.form(prefix, clear_on_submit=True):
        day = st.date_input("Day of check-in", value=_today(), max_value=_today(), key=f"{prefix}_date")
        responses = {}
        columns = st.columns(2)
        for index, (key, (label, values)) in enumerate(_RATINGS.items()):
            with columns[index % 2]:
                responses[key] = st.selectbox(
                    label,
                    list(range(5)),
                    index=None,
                    format_func=lambda value, choices=values: choices[value],
                    placeholder="Choose your answer" if not clinician else "Choose the patient's answer",
                    key=f"{prefix}_{key}",
                )
        responses["falls"] = st.selectbox(
            "Any falls on this day? (optional)",
            [False, True],
            index=None,
            format_func=lambda value: "Yes, a fall" if value else "No falls",
            placeholder="Leave blank if unknown",
            key=f"{prefix}_falls",
        )
        responses["note"] = st.text_area(
            "Anything you'd like your care team to know?" if not clinician else "Patient's words / relevant context",
            max_chars=2000,
            placeholder="For example, an activity that felt easier or a question for your next visit.",
            key=f"{prefix}_note",
        )
        st.caption("Choose all four answers. A second check-in for the same day updates that day's entry. These questions do not produce a clinical score.")
        if st.form_submit_button("Save daily check-in", type="primary"):
            try:
                care.save_checkin(user["id"], {**responses, "date": day.isoformat()}, patient_id=patient_id)
                st.success("Check-in saved. Your care team can read it alongside your assessments.")
            except (ValueError, PermissionError, LookupError) as exc:
                st.error(str(exc))


def _checkin_history(records):
    if not records:
        empty_state("No check-ins yet", "When a day feels different, a short note can help you remember it at your next visit.")
        return
    latest = records[0]
    with st.container(border=True):
        st.write(f"**Latest check-in · {_date_label(latest['date'])}**")
        status_pill("Patient self-report")
        responses = latest["responses"]
        rows = []
        for key, (label, choices) in _RATINGS.items():
            value = responses.get(key)
            rows.append({"Experience": label, "Answer": choices[value] if isinstance(value, int) and 0 <= value <= 4 else "Not recorded"})
        falls = responses.get("falls")
        rows.append({"Experience": "Falls", "Answer": "Not recorded" if falls is None else ("Reported a fall" if falls else "No falls reported")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if responses.get("note"):
            st.write(responses["note"])
        st.caption(f"Recorded by {latest['author_name']} · {_date_label(latest.get('updated_at', latest.get('created_at')))}")
    if len(records) > 1:
        with st.expander(f"Earlier check-ins ({len(records) - 1})"):
            for item in records[1:]:
                values = item["responses"]
                st.write(f"**{_date_label(item['date'])}**")
                labels = []
                for key, (label, choices) in _RATINGS.items():
                    value = values.get(key)
                    if isinstance(value, int) and 0 <= value <= 4:
                        labels.append(f"{label}: {choices[value]}")
                st.caption(" · ".join(labels))
                if values.get("falls") is True:
                    st.write("Patient reported a fall.")
                if values.get("note"):
                    st.write(values["note"])
                st.divider()


def _goals(user, patient_id, *, editable):
    records = care.list_goals(user["id"], patient_id=patient_id)
    section_header("What matters to you" if editable else "The patient's personal goals", "Everyday priorities, written by the patient. Goals stay separate from measured results.")
    if not records:
        empty_state("No personal goals saved", "A goal can be small: an everyday activity you'd like to feel more confident doing." if editable else "The patient can add priorities from their My Care page.")
    for goal in records:
        with st.container(border=True):
            st.write(f"**{goal['label']}**")
            status_pill(_GOAL_STATUSES.get(goal["status"], "Status unavailable"), "care" if goal["status"] == "completed" else "neutral")
            if goal.get("detail"):
                st.write(goal["detail"])
            st.caption(f"Written by {goal['author_name']} · {_date_label(goal['created_at'])}")
            if editable:
                with st.form(f"goal_update_{goal['id']}"):
                    status = st.selectbox("Goal status", list(_GOAL_STATUSES), index=list(_GOAL_STATUSES).index(goal["status"]), format_func=_GOAL_STATUSES.get, key=f"goal_status_{goal['id']}")
                    if st.form_submit_button("Update goal"):
                        try:
                            care.update_goal(user["id"], goal["id"], status=status)
                            st.rerun()
                        except (ValueError, PermissionError, LookupError) as exc:
                            st.error(str(exc))
    if editable:
        with st.expander("Add a personal goal", expanded=not records):
            with st.form(f"new_goal_{patient_id}", clear_on_submit=True):
                label = st.text_input("An activity or priority that matters to you", max_chars=160, placeholder="For example, feeling more comfortable getting dressed.")
                detail = st.text_area("A little more detail (optional)", max_chars=1000, placeholder="What would make a difference in your day?")
                if st.form_submit_button("Save personal goal"):
                    try:
                        care.save_personal_goal(user["id"], label, detail=detail, patient_id=patient_id)
                        st.rerun()
                    except (ValueError, PermissionError, LookupError) as exc:
                        st.error(str(exc))


def _care_plan_records(records):
    if not records:
        empty_state("A place for your care team's follow-up", "Your assigned clinician can leave a note, agreed priorities and a date to review them. No automated care plan is created.")
        return
    for index, plan in enumerate(records):
        with st.container(border=True) if index == 0 else st.expander(f"Earlier follow-up · {_date_label(plan['created_at'])}"):
            st.write(f"**{plan['focus']}**")
            status_pill("Clinician-written follow-up", "care")
            st.write(plan["notes"])
            st.caption(f"Written by {plan['author_name']} · {_date_label(plan['created_at'])}")
            if plan.get("next_review_date"):
                st.caption(f"Planned review: {_date_label(plan['next_review_date'])}")
                st.caption("This is a review date recorded by your clinician, rather than a booked appointment.")


def patient_care_panel(user):
    """Render a patient's daily check-in, own goals and assigned team notes."""
    patient_id = user["patient_id"]
    section_header("Between visits", "A few details from your day, and the people helping you make sense of them.")
    checkin, goals, followup = st.tabs(["Daily check-in", "My goals", "Care team follow-up"])
    with checkin:
        _record_checkin(user, patient_id)
        _checkin_history(care.list_checkins(user["id"], patient_id=patient_id))
    with goals:
        _goals(user, patient_id, editable=True)
    with followup:
        _care_plan_records(care.list_care_plans(user["id"], patient_id=patient_id))


def clinician_care_panel(user, patient_id):
    """Render authorized patient context and a human-authored care note form."""
    section_header("Patient context & follow-up", "The patient's daily experiences and priorities help give recordings their context.")
    experiences, goals, followup = st.tabs(["Patient check-ins", "Personal goals", "Care team follow-up"])
    with experiences:
        _checkin_history(care.list_checkins(user["id"], patient_id=patient_id))
        with st.expander("Record answers shared by the patient"):
            _record_checkin(user, patient_id, clinician=True)
    with goals:
        _goals(user, patient_id, editable=False)
    with followup:
        with st.form(f"care_followup_{patient_id}", clear_on_submit=True):
            st.caption("Write the follow-up you discussed with the patient. Your name will appear with the note.")
            focus = st.text_input("Focus for follow-up", max_chars=160, placeholder="Agreed priority for the next review")
            notes = st.text_area("Care team note", max_chars=3000, placeholder="Record the discussion, agreed next steps and questions to revisit.")
            review_date = st.date_input("Planned review date (optional)", value=None)
            if st.form_submit_button("Save care team follow-up", type="primary"):
                try:
                    care.save_care_plan(user["id"], patient_id, focus, notes, next_review_date=review_date.isoformat() if review_date else None)
                    st.success("Follow-up saved with your name. It is visible to the patient and their assigned care team.")
                except (ValueError, PermissionError, LookupError) as exc:
                    st.error(str(exc))
        _care_plan_records(care.list_care_plans(user["id"], patient_id=patient_id))
