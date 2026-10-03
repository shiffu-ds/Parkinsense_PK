"""Persistent WebGL host: update live data without remounting the plot.

Streamlit's regular Plotly element includes the changing spec in its identity.
V2 component keys preserve the host; Plotly.react preserves its camera. Vendor
code loads once per full page run from the installed offline Plotly package.
"""

from functools import lru_cache
import json
from pathlib import Path

import streamlit as st
from plotly.offline import get_plotlyjs


@lru_cache(maxsize=1)
def _library_loader():
    return st.components.v2.component(
        "parkinsense_live_plotly_library",
        js=get_plotlyjs() + "\nexport default function() { window.__parkinsenseLivePlotly = window.Plotly || window.moduleName; }",
    )


@lru_cache(maxsize=1)
def _live_host():
    return st.components.v2.component(
        "parkinsense_live_3d_host",
        html='<div class="live-graph" role="group" aria-label="Live focused 3D joint tracking"></div>',
        css='.live-graph { width: 100%; height: 450px; overflow: hidden; border-radius: 12px; background: #101e2c; }',
        js=Path(__file__).with_name("live_plot.js").read_text(),
        isolate_styles=False,
    )


def preload_live_plot_library():
    """Call outside the polling fragment; the vendor bundle is not frame data."""
    _library_loader()(key="live_plot_library", height=0)


def render_live_plot(figure, *, key):
    """Only numeric geometry and fixed renderer labels enter component data."""
    _live_host()(key=key, data={"figure": json.loads(figure.to_json())}, height=450)
