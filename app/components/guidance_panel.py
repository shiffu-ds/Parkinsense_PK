"""Plain-language next steps, rendered from the fixed local guidance catalogue."""

from __future__ import annotations

import streamlit as st

from .patient_language import prose_html, write_patient
from ml.common.guidance import build_guidance


def render_guidance(result=None, task=None, *, error=None, language="English", identity="guidance"):
    """Show separate recording, processing and reported-concern next steps."""
    entries = build_guidance(result, task, error=error, language=language)
    if not entries:
        return []
    roman = entries[0]["language"] == "roman urdu"
    urdu = entries[0]["language"] == "urdu"
    st.subheader("اگلا قدم" if urdu else "Agla qadam" if roman else "Your next steps")
    note = entries[0].get("translation_note")
    if note:
        st.caption(note)
    labels = {
        "recording": "Recording setup" if not roman else "Recording ka setup",
        "processing": "App processing" if not roman else "App ki processing",
        "follow_up": "Reported concern · clinician follow-up" if not roman else "Batayi hui mushkil · clinician ka follow-up",
    }
    if urdu:
        labels = {"recording": "ریکارڈنگ کی تیاری", "processing": "ایپ کا تجزیہ", "follow_up": "بتائی ہوئی مشکل · معالج سے بات"}
    for entry in entries:
        with st.container(border=True, key=f"{identity}_{entry['code']}"):
            st.caption(labels[entry["kind"]])
            if urdu:
                write_patient(entry["title"], "Urdu")
                write_patient(entry["reason"], "Urdu")
                st.markdown(prose_html(entry["steps"], "Urdu", ordered=True), unsafe_allow_html=True)
            else:
                st.markdown(f"**{entry['title']}**")
                st.write(entry["reason"])
                for number, step in enumerate(entry["steps"], start=1):
                    st.markdown(f"{number}. {step}")
            source = entry.get("source")
            if source:
                source_label = "ماخذ دیکھیں" if urdu else "Read the source"
                st.markdown(f"[{source_label}: {source['title']}]({source['url']})")
    return entries
