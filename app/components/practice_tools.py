"""Browser-only practice aids: a walking beat and loud-voice feedback.

Neither tool records, stores or sends anything; both are practice, not
measurement. The walking beat can start from the patient's last measured
cadence so the pace feels familiar.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

_CSS = """
.ps-practice {max-width: 520px; font: inherit; color: inherit;}
.ps-practice-big {font-size: 1.6rem; font-weight: 700; margin: 0.2rem 0 0.6rem; font-variant-numeric: tabular-nums;}
.ps-practice-status {min-height: 1.6em; font-weight: 600; margin: 0 0 0.6rem;}
.ps-practice-zone {margin: 0.5rem 0; font-variant-numeric: tabular-nums;}
.ps-practice-pulse {width: 64px; height: 64px; border-radius: 50%; border: 3px solid var(--ps-accent, #1D6B52);
  margin: 0.4rem 0 0.8rem; transition: background 60ms linear;}
.ps-practice-pulse.on {background: var(--ps-accent, #1D6B52);}
.ps-practice-meter {position: relative; height: 28px; border-radius: 6px; overflow: hidden;
  background: var(--ps-sunken, #ECEFED); border: 1px solid var(--ps-line-strong, #A9B6B2);}
.ps-practice-fill {position: absolute; inset: 0 auto 0 0; width: 0; background: var(--ps-muted, #4D5E62); transition: width 60ms linear;}
.ps-practice-fill.in-zone {background: var(--ps-accent, #1D6B52);}
.ps-practice-mark {position: absolute; top: 0; bottom: 0; width: 3px; background: var(--ps-ink, #16262A);}
.ps-practice-target {background: var(--ps-ochre, #8F5410);}
.ps-practice-actions {display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.6rem;}
.ps-practice-actions button {min-height: 48px; min-width: 110px; padding: 0.6rem 1rem; border-radius: 6px; font: inherit;
  font-weight: 600; border: 1px solid var(--ps-line-strong, #A9B6B2); background: var(--ps-surface, #FFFFFF); color: inherit; cursor: pointer;}
.ps-practice-actions button.ps-practice-primary {background: var(--ps-accent, #1D6B52); border-color: var(--ps-accent, #1D6B52);
  color: var(--ps-accent-ink, #FFFFFF);}
.ps-practice-actions button:focus-visible {outline: 3px solid var(--ps-accent, #1D6B52); outline-offset: 2px;}
"""


@lru_cache(maxsize=1)
def _component():
    return st.components.v2.component(
        "parkinsense_practice", html='<div class="ps-practice"></div>', css=_CSS,
        js=Path(__file__).with_name("practice.js").read_text(encoding="utf-8"),
    )


def _mount(**options):
    try:
        return _component()(**options)
    except StreamlitAPIException:
        # A new Streamlit runtime (each AppTest) starts with an empty registry.
        _component.cache_clear()
        return _component()(**options)


def cadence_bpm(visits):
    """Steps per minute from the newest accepted walking recording, rounded to 5; None if there is none."""
    from ml.common.results import numeric_features
    for visit in visits:
        if visit.get("status") == "abandoned":
            continue
        value = numeric_features(visit.get("modules", {}).get("gait", {})).get("cadence_steps_per_min_proxy")
        if value and 40 <= value <= 160:
            return int(max(40, min(140, round(value / 5) * 5)))
    return None


def metronome(*, default_bpm, labels, key):
    _mount(key=key, data={"mode": "metronome", "default_bpm": default_bpm, "labels": labels})


def loudness_practice(*, labels, key):
    _mount(key=key, data={"mode": "loudness", "labels": labels})
