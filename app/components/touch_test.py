"""Touchscreen spiral and two-circle tapping canvas for phones and tablets.

The page script collects raw touches only; ml.touch scores them. Geometry is
sent from Python so drawing and scoring always use the same guide.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

from app.components.palette import tokens
from ml.touch import SPIRAL_GEOMETRY, TAP_GEOMETRY, TAP_SECONDS

_HTML = """
<div class="ps-touch">
  <p class="ps-touch-status" aria-live="polite"></p>
  <canvas class="ps-touch-canvas"></canvas>
  <div class="ps-touch-actions">
    <button type="button" class="ps-touch-clear"></button>
    <button type="button" class="ps-touch-done"></button>
  </div>
</div>
"""
_CSS = """
.ps-touch {width: 100%; max-width: 460px; font: inherit; color: inherit;}
.ps-touch-status {min-height: 1.6em; margin: 0 0 0.6rem; font-weight: 600;}
.ps-touch-canvas {display: block; touch-action: none; user-select: none; -webkit-user-select: none;
  border: 1px solid var(--ps-line-strong, #A9B6B2); border-radius: 6px; cursor: crosshair;}
.ps-touch-actions {display: flex; gap: 0.6rem; margin-top: 0.7rem; flex-wrap: wrap;}
.ps-touch-actions button {min-height: 48px; min-width: 120px; padding: 0.6rem 1rem; border-radius: 6px; font: inherit;
  font-weight: 600; border: 1px solid var(--ps-line-strong, #A9B6B2); background: var(--ps-surface, #FFFFFF);
  color: inherit; cursor: pointer;}
.ps-touch-actions button.ps-touch-done {background: var(--ps-accent, #1D6B52); border-color: var(--ps-accent, #1D6B52);
  color: var(--ps-accent-ink, #FFFFFF);}
.ps-touch-actions button:disabled {opacity: 0.45; cursor: default;}
.ps-touch-actions button:focus-visible {outline: 3px solid var(--ps-accent, #1D6B52); outline-offset: 2px;}
"""


@lru_cache(maxsize=1)
def _component():
    return st.components.v2.component(
        "parkinsense_touch_test", html=_HTML, css=_CSS,
        js=Path(__file__).with_name("touch_test.js").read_text(encoding="utf-8"),
    )


def _submitted():
    """The trigger itself reruns the page; the payload is read from the result."""


def touch_test(mode, *, key, labels, measured=0):
    """Show the canvas; returns the raw payload once, on the run after Done or the timer ends.

    ``measured`` counts analysed submissions; a new count tells the canvas its
    latest submission has a result (an unchanged value would not redraw it).
    """
    t = tokens()
    data = {"mode": mode, "labels": labels, "measured": int(measured), "spiral": SPIRAL_GEOMETRY,
            "tapping": {**TAP_GEOMETRY, "seconds": TAP_SECONDS},
            "colors": {"surface": t.surface, "guide": t.rule_strong, "accent": t.accent, "soft": t.accent_soft,
                       "attention": t.ochre, "ink": t.ink}}
    options = {"key": key, "data": data, "on_submitted_change": _submitted}
    try:
        result = _component()(**options)
    except StreamlitAPIException:
        # A new Streamlit runtime (each AppTest) starts with an empty registry.
        _component.cache_clear()
        result = _component()(**options)
    return getattr(result, "submitted", None)
