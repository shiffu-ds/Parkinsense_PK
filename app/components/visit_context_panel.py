"""Patient-reported medicine timing for a visit.

Shown in the patient's own language. Stored values are stable IDs; translated
labels never reach the service. Nothing here gives or implies medication advice.
"""

import streamlit as st

from backend.db.context_models import DOSE_WINDOWS, DYSKINESIA, MEDICATION_STATES
from backend.services import visit_context

from .design import next_step
from .patient_language import text, write_patient

_STATE_KEYS = {state: f"med_{state}" for state in MEDICATION_STATES}
_DOSE_KEYS = {window: f"dose_{window}" for window in DOSE_WINDOWS}
_DYSK_KEYS = {value: f"dysk_{value}" for value in DYSKINESIA}


_LAST_DOSE = {"English": "last dose {when}", "Urdu": "آخری خوراک: {when}", "Roman Urdu": "aakhri khuraak: {when}"}
_EXTRA = {"English": "extra movements reported", "Urdu": "اضافی حرکت بتائی گئی", "Roman Urdu": "izafi harkat batayi gayi"}


def describe(context, language="English"):
    """One readable line for a saved context, or None when nothing is saved."""
    if not context:
        return None
    language = language if language in _LAST_DOSE else "English"
    parts = [text(_STATE_KEYS[context["medication_state"]], language)]
    if context.get("dose_window") and context["dose_window"] != "unsure":
        when = text(_DOSE_KEYS[context["dose_window"]], language)
        parts.append(_LAST_DOSE[language].format(when=when[0].lower() + when[1:] if language != "Urdu" else when))
    if context.get("dyskinesia") == "yes":
        parts.append(_EXTRA[language])
    return "; ".join(parts)


def _index(options, value):
    return options.index(value) if value in options else None


def medication_form(user, item, language="English", *, expanded=None):
    """Record or update medicine timing for an open visit."""
    try:
        saved = visit_context.get_visit_context(user["id"], item["id"])
    except (PermissionError, LookupError):
        return None
    summary = describe(saved, language)
    label = text("med_title", language) + (f" — {summary}" if summary else f" — {text('med_missing', language)}")
    with st.expander(label, expanded=(saved is None) if expanded is None else expanded):
        write_patient(text("med_intro", language), language)
        with st.form(f"visit_context_{item['id']}"):
            state = st.selectbox(text("med_state", language), list(MEDICATION_STATES),
                                 index=_index(list(MEDICATION_STATES), (saved or {}).get("medication_state")),
                                 placeholder=text("med_choose", language),
                                 format_func=lambda value: text(_STATE_KEYS[value], language), key=f"med_state_{item['id']}")
            dose = st.selectbox(text("med_dose", language), list(DOSE_WINDOWS),
                                index=_index(list(DOSE_WINDOWS), (saved or {}).get("dose_window")),
                                placeholder=text("med_choose", language),
                                format_func=lambda value: text(_DOSE_KEYS[value], language), key=f"med_dose_{item['id']}")
            dysk = st.selectbox(text("med_dyskinesia", language), list(DYSKINESIA),
                                index=_index(list(DYSKINESIA), (saved or {}).get("dyskinesia")),
                                placeholder=text("med_choose", language),
                                format_func=lambda value: text(_DYSK_KEYS[value], language), key=f"med_dysk_{item['id']}")
            note = st.text_input(text("med_note", language), value=(saved or {}).get("note", ""), max_chars=1000,
                                 key=f"med_note_{item['id']}")
            if st.form_submit_button(text("med_save", language)):
                try:
                    if state is None:
                        raise ValueError(text("med_state", language))
                    saved = visit_context.save_visit_context(user["id"], item["id"], medication_state=state,
                                                             dose_window=dose, dyskinesia=dysk, note=note)
                    st.success(text("med_saved", language))
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
    return saved


def timing_reminder(user, item, language="English"):
    """On a task page: show the saved timing, or ask for it once."""
    try:
        saved = visit_context.get_visit_context(user["id"], item["id"])
    except (PermissionError, LookupError):
        return
    if saved:
        st.caption(text("med_context_line", language, summary=describe(saved, language)))
    else:
        next_step(text("med_reminder", language), text("med_reminder_detail", language), "waiting")


def describe_assistance(assistance, language="English"):
    """'Family member · Walking stick', or None when nothing was recorded."""
    if not assistance:
        return None
    return f"{text('helper_' + assistance['helper'], language)} · {text('aid_' + assistance['walking_aid'], language)}"


def assistance_form(user, item, language="English"):
    """Who helped with this visit and which walking aid was used."""
    from backend.db.context_models import HELPERS, WALKING_AIDS
    try:
        saved = visit_context.get_visit_assistance(user["id"], item["id"])
    except (PermissionError, LookupError):
        return None
    summary = describe_assistance(saved, language)
    with st.expander(text("assist_title", language) + (f" — {summary}" if summary else "")):
        write_patient(text("assist_intro", language), language)
        with st.form(f"visit_assistance_{item['id']}"):
            helper = st.selectbox(text("assist_helper", language), list(HELPERS),
                                  index=list(HELPERS).index(saved["helper"]) if saved else 0,
                                  format_func=lambda value: text(f"helper_{value}", language), key=f"assist_helper_{item['id']}")
            aid = st.selectbox(text("assist_aid", language), list(WALKING_AIDS),
                               index=list(WALKING_AIDS).index(saved["walking_aid"]) if saved else 0,
                               format_func=lambda value: text(f"aid_{value}", language), key=f"assist_aid_{item['id']}")
            if st.form_submit_button(text("assist_save", language)):
                try:
                    saved = visit_context.save_visit_assistance(user["id"], item["id"], helper=helper, walking_aid=aid)
                    st.success(text("assist_saved", language))
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
    return saved
