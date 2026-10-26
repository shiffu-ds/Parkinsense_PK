"""Redraw the page once when the visible theme stops matching the drawn one.

Colours for the page, the sidebar logo and charts are chosen in Python from
``st.context.theme``, which Streamlit only refreshes on a rerun. Switching the
device or Settings theme repaints native widgets immediately, leaving custom
colours behind (unreadable labels on the login form). A tiny page script
compares the two and requests a single rerun; it never loops.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

from app.components.palette import theme_type


@lru_cache(maxsize=1)
def _watcher():
    return st.components.v2.component(
        "parkinsense_theme_sync",
        js=Path(__file__).with_name("theme_sync.js").read_text(encoding="utf-8"),
    )


def _rerun_requested():
    """The trigger itself causes the rerun; nothing else to do."""


def keep_theme_in_sync():
    options = {"key": "ps_theme_sync", "data": {"drawn": theme_type()}, "height": 0,
               "on_changed_change": _rerun_requested}
    try:
        _watcher()(**options)
    except StreamlitAPIException:
        # A new Streamlit runtime (each AppTest) starts with an empty registry.
        _watcher.cache_clear()
        _watcher()(**options)
