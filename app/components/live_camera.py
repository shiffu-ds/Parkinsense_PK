"""Polling controls that resolve the asynchronously created camera processor."""

import hashlib

import streamlit as st

from .design import empty_state, status_pill
from .guidance_panel import render_guidance
from .motion_studio import live_movement_preview
from .patient_language import text


def live_camera_panel(ctx, task, *, identity, overlay=True, show_trails=True,
                      camera="Isometric", language="English", on_finish=None):
    from .live_plot import preload_live_plot_library
    preload_live_plot_library()
    _live_camera_fragment(ctx, task, identity=identity, overlay=overlay, show_trails=show_trails,
                          camera=camera, language=language, on_finish=on_finish)


@st.fragment(run_every=0.25)
def _live_camera_fragment(ctx, task, *, identity, overlay=True, show_trails=True,
                          camera="Isometric", language="English", on_finish=None):
    """Refresh the current processor even if it was absent on first render.

    This is the UI thread. Media callbacks never call Streamlit. The processor
    owns coordinate freshness and bounded history under its lock.
    """
    token = hashlib.sha256(str(identity).encode()).hexdigest()[:16]
    processor = ctx.video_processor
    playing = bool(ctx.state.playing)
    clip_key = f"live_clip_processor_{token}"
    retained = st.session_state.get(clip_key)
    pending = None
    pending_status = None
    if retained is not None and retained is not processor:
        retained_status = retained.snapshot()
        if retained_status.get("recording") or retained_status.get("recording_ready"):
            pending, pending_status = retained, retained_status
        else:
            st.session_state.pop(clip_key, None)
    if processor is not None and pending is None:
        st.session_state[clip_key] = processor
    if processor is None:
        empty_state(text("tracking_ready", language), text("tracking_start", language))
        if pending is not None:
            st.info(text("camera_stopped", language))
        left, right = st.columns(2)
        left.button(text("start_recording", language), key=f"live_record_{token}", disabled=True)
        if right.button(text("finish_analyze", language), key=f"live_finish_{token}", disabled=pending is None or on_finish is None):
            on_finish(pending)
            st.session_state.pop(clip_key, None)
            st.rerun()
        return
    st.session_state.live_processor = processor
    processor.set_display_options(overlay=overlay, show_trails=show_trails)
    snapshot = processor.snapshot(include_landmarks=True)
    status_pill(text("recording_progress" if snapshot.get("recording") else "camera_ready" if playing else "camera_paused", language), "care" if playing else "neutral")
    if snapshot.get("error"):
        render_guidance(task=task, error=snapshot["error"], language=language, identity=f"live_fault_{token}")
    live_movement_preview(snapshot, task, identity=identity, show_trails=show_trails, camera=camera)
    if snapshot.get("lighting_good") is False:
        st.caption(text("even_light", language))
    action_processor, action_status = (pending, pending_status) if pending is not None else (processor, snapshot)
    if pending is not None:
        st.info(text("pending_clip", language))
    left, right = st.columns(2)
    if left.button(text("start_recording", language), key=f"live_record_{token}", disabled=not playing or bool(snapshot.get("recording")) or pending is not None):
        processor.start_recording()
        st.rerun(scope="fragment")
    if action_status.get("recording_ready") and not action_status.get("recording"):
        st.caption(text("recording_complete", language))
    if right.button(text("finish_analyze", language), key=f"live_finish_{token}", disabled=not (action_status.get("recording") or action_status.get("recording_ready")) or on_finish is None):
        on_finish(action_processor)
        st.session_state.pop(clip_key, None)
        st.rerun()
