"""A Listen button that reads fixed instructions aloud with the browser's own voices.

Urdu and Roman Urdu readers hear the Urdu-script version with an Urdu voice;
when a device has no Urdu voice the button says so instead of mispronouncing
the text with another language. Only app instructions are spoken, never
patient data.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

from .patient_language import resolved_language, text

_HTML = '<div class="ps-listen-wrap"><button type="button" class="ps-listen"></button><span class="ps-listen-note" aria-live="polite"></span></div>'
_CSS = """
.ps-listen-wrap {display: flex; gap: 0.7rem; align-items: center; flex-wrap: wrap; margin: 0.2rem 0 0.6rem; font: inherit;}
.ps-listen {min-height: 44px; padding: 0.5rem 0.9rem; border-radius: 6px; font: inherit; font-weight: 600; cursor: pointer;
  border: 1px solid var(--ps-line-strong, #A9B6B2); background: var(--ps-surface, #FFFFFF); color: inherit;}
.ps-listen:focus-visible {outline: 3px solid var(--ps-accent, #1D6B52); outline-offset: 2px;}
.ps-listen-note {color: var(--ps-muted, #4D5E62); font-size: 0.9rem;}
"""


@lru_cache(maxsize=1)
def _component():
    return st.components.v2.component(
        "parkinsense_read_aloud", html=_HTML, css=_CSS,
        js=Path(__file__).with_name("read_aloud.js").read_text(encoding="utf-8"),
    )


def speech_for(texts, language):
    """(words, BCP-47 language) to speak: Urdu script for Urdu and Roman Urdu readers."""
    english, urdu, _roman = texts
    return (urdu, "ur-PK") if resolved_language(language) in {"Urdu", "Roman Urdu"} else (english, "en-US")


def listen_button(texts, language="English", *, key):
    """``texts`` holds the (English, Urdu, Roman Urdu) versions of what to read."""
    words, lang = speech_for(texts, language)
    options = {"key": key, "data": {"text": " ".join(words) if isinstance(words, (list, tuple)) else words, "lang": lang,
                                    "labels": {"listen": text("listen", language), "no_voice": text("no_urdu_voice", language),
                                               "unavailable": text("no_speech", language)}}}
    try:
        _component()(**options)
    except StreamlitAPIException:
        _component.cache_clear()
        _component()(**options)
