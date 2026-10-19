"""Stable report bytes for one browser session, invalidated by source changes."""

import hashlib
import json

import streamlit as st


def session_report_html(key, source, build):
    """Do not regenerate timestamped downloads on unrelated widget reruns.

    This is session state, never a cross-patient/global cache. Callers include
    identity, language and all report inputs; authorization still runs normally.
    """
    stamp = hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()
    cached = st.session_state.get(key)
    if not isinstance(cached, dict) or cached.get("stamp") != stamp:
        cached = {"stamp": stamp, "html": build()}
        st.session_state[key] = cached
    return cached["html"]
