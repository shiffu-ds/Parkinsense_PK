"""Medicine diary: one tap records how the medicine is working right now.

Large buttons suit unsteady hands. Entries are context for reading recordings
and are never turned into advice, a dose or a score.
"""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st

from backend.db.context_models import DIARY_STATES
from backend.services import medication_diary as diary

from .design import empty_state, section_header
from .palette import chart_layout, tokens
from .patient_language import text

LOCAL = ZoneInfo("Asia/Karachi")
SLOTS = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)]


def clock(value):
    """'14:30' → '2:30 PM', kept left-to-right inside Urdu sentences."""
    return "⁦" + datetime.strptime(value, "%H:%M").strftime("%I:%M %p").lstrip("0") + "⁩"


def _local(iso_value):
    return datetime.fromisoformat(iso_value).astimezone(LOCAL)


def quick_entry(user, language="English", *, key, patient_id=None):
    """Four large buttons; a tap saves 'now' with that state."""
    columns = st.columns(2)
    for index, state in enumerate(DIARY_STATES):
        if columns[index % 2].button(text(f"diary_{state}", language), key=f"{key}_{state}", width="stretch"):
            try:
                saved = diary.save_diary_entry(user["id"], state, patient_id=patient_id)
                st.session_state[f"{key}_notice"] = saved["observed_at"]
                st.rerun()
            except (ValueError, PermissionError, LookupError) as exc:
                st.error(str(exc))
    notice = st.session_state.pop(f"{key}_notice", None)
    if notice:
        st.success(text("diary_saved", language, time=clock(_local(notice).strftime("%H:%M"))))


def diary_figure(entries, language="English"):
    t = tokens()
    colours = {"off": t.alert, "wearing_off": t.ochre, "on": t.accent, "on_dyskinesia": t.series[1]}
    order = ["off", "wearing_off", "on", "on_dyskinesia"]
    labels = {state: text(f"diary_{state}", language) for state in order}
    figure = go.Figure()
    for state in order:
        rows = [entry for entry in entries if entry["state"] == state]
        if rows:
            figure.add_trace(go.Scatter(
                x=[_local(entry["observed_at"]).replace(tzinfo=None) for entry in rows], y=[labels[state]] * len(rows),
                mode="markers", marker={"size": 13, "color": colours[state], "line": {"color": t.surface, "width": 1}},
                # Hover text is HTML to Plotly, so the patient's note is escaped and shortened.
                customdata=[escape(entry.get("note") or "")[:160] for entry in rows],
                hovertemplate="%{x|%d %b, %I:%M %p}<br>%{customdata}<extra>" + escape(labels[state]) + "</extra>",
                showlegend=False))
    figure.update_layout(**chart_layout(height=250, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                                        xaxis={"type": "date", "gridcolor": t.rule},
                                        yaxis={"categoryorder": "array", "categoryarray": [labels[state] for state in order],
                                               "gridcolor": t.rule}))
    return figure


def earlier_entry(user, language="English", *, key, patient_id=None):
    """Record a moment earlier today (or transcribe one, for a clinician)."""
    with st.form(f"{key}_earlier", clear_on_submit=True):
        at = st.time_input(text("diary_time", language), value=None, step=900, key=f"{key}_time")
        state = st.selectbox(text("diary_state", language), list(DIARY_STATES), index=None,
                             placeholder=text("diary_choose", language),
                             format_func=lambda value: text(f"diary_{value}", language), key=f"{key}_state")
        note = st.text_input(text("diary_note", language), max_chars=300, key=f"{key}_note")
        if st.form_submit_button(text("diary_save", language)):
            try:
                if at is None or state is None:
                    raise ValueError(text("diary_choose", language))
                moment = datetime.combine(datetime.now(LOCAL).date(), at, LOCAL)
                saved = diary.save_diary_entry(user["id"], state, observed_at=moment, note=note, patient_id=patient_id)
                st.success(text("diary_saved", language, time=clock(_local(saved["observed_at"]).strftime("%H:%M"))))
            except (ValueError, PermissionError, LookupError) as exc:
                st.error(str(exc))


def medicine_times_form(user, language="English", *, key, patient_id=None):
    current = diary.get_medicine_times(user["id"], patient_id=patient_id)
    with st.expander(text("times_title", language) + (" — " + ", ".join(clock(t) for t in current) if current else "")):
        st.caption(text("times_detail", language))
        with st.form(f"{key}_times"):
            chosen = st.multiselect(text("times_label", language), sorted(set(SLOTS) | set(current)), default=current,
                                    format_func=clock, max_selections=8, key=f"{key}_times_select")
            if st.form_submit_button(text("times_save", language)):
                try:
                    diary.save_medicine_times(user["id"], chosen, patient_id=patient_id)
                    st.success(text("times_saved", language))
                except (ValueError, PermissionError, LookupError) as exc:
                    st.error(str(exc))


def diary_panel(user, language="English", *, key="diary", patient_id=None, clinician=False):
    """Patient: quick entry, earlier entry, the week and usual times. Clinician: the week, transcription and times."""
    section_header(text("diary_title", language) if not clinician else "Patient-reported medicine diary",
                   text("diary_intro", language) if not clinician else
                   "ON/OFF moments the patient (or you, transcribing) recorded. Context for reading recordings, not a measurement.")
    if not clinician:
        quick_entry(user, language, key=f"{key}_now", patient_id=patient_id)
    with st.expander(text("diary_earlier", language) if not clinician else "Record a moment the patient reported"):
        earlier_entry(user, language, key=key, patient_id=patient_id)
    entries = diary.list_diary(user["id"], patient_id=patient_id, days=7)
    if entries:
        counts = diary.diary_counts(entries)
        st.caption(text("diary_counts", language, on=counts["on"], dyskinesia=counts["on_dyskinesia"],
                        wearing=counts["wearing_off"], off=counts["off"]))
        st.plotly_chart(diary_figure(entries, language), width="stretch", theme=None, key=f"{key}_chart",
                        config={"displaylogo": False})
    else:
        empty_state(text("diary_empty", language), text("diary_empty_detail", language))
    medicine_times_form(user, language, key=key, patient_id=patient_id)
