"""Patient-friendly controls around the model-local 3D movement renderer."""

import hashlib
import json

import streamlit as st

from .design import empty_state, section_header, status_pill
from .pose_3d_viewer import (
    CAMERAS, JOINT_NAMES, STYLES, build_motion_figure, build_motion_html,
    motion_frame_summary,
)
from ml.vision.tasks import TASKS
from ml.vision.spatial import prepare_motion


def movement_studio(result, *, baseline=None, identity="recording", export_context=None):
    """Keep geometry primary and preserve an explicit export choice."""
    summary = motion_frame_summary(result)
    if not summary["available"]:
        empty_state("No usable 3D geometry in this recording", "Repeat the recording with the relevant joints clearly visible. Older recordings without world coordinates cannot be replayed in this view.")
        return
    token = hashlib.sha256(str(identity).encode()).hexdigest()[:16]
    kind = TASKS.get(result.get("task"), {}).get("kind", "pose")
    if baseline:
        current_motion, previous_motion = prepare_motion(result), prepare_motion(baseline)
        if (baseline.get("task") != result.get("task") or previous_motion is None
                or previous_motion.kind != current_motion.kind
                or (previous_motion.side and current_motion.side and previous_motion.side != current_motion.side)):
            baseline = None
    section_header("Movement studio", "Drag the model to rotate it. Play the recording or use the time bar to inspect a moment.", eyebrow="3D review")
    status_pill("Estimated 3D · recorded movement", "care")
    a, b, c = st.columns([1, 1, 1])
    camera = a.selectbox("Camera view", list(CAMERAS), index=3, key=f"camera_{token}")
    style = b.selectbox("Model style", STYLES, key=f"style_{token}")
    speed = c.selectbox("Playback speed", [0.25, 0.5, 1.0, 1.5, 2.0], index=2, format_func=lambda value: f"{value:g}×", key=f"speed_{token}")
    with st.expander("Comparison & display options"):
        left, right = st.columns(2)
        compare = left.checkbox("Compare with first reliable recording", disabled=baseline is None, key=f"compare_{token}")
        trails = left.checkbox("Show joint movement trail", value=True, key=f"trails_{token}")
        joints = JOINT_NAMES.get(kind, JOINT_NAMES["pose"])
        selected_joint = left.selectbox("Joint to follow", [None, *joints], format_func=lambda value: "Task-specific joints" if value is None else joints[value], disabled=not trails, key=f"joint_{token}")
        grid = right.checkbox("Show reference grid", value=True, key=f"grid_{token}")
        smooth = right.checkbox("Smooth the display slightly", key=f"smooth_{token}", help="Only the displayed model is smoothed. Stored landmarks and measurements remain unchanged; tracking gaps are preserved.")
        if baseline is None:
            st.caption("Comparison becomes available after a prior accepted recording of this task with the same method.")
        elif compare:
            st.caption("Muted gold shows the first reliable recording, aligned at its local origin and matched by relative recording time. This is a visual comparison, not a clinical change score.")
        st.caption("Teal = left side · blue = right side. The grid passes through the model origin; it is not a measured floor.")
    options = {"camera": camera, "style": style, "playback_speed": speed,
               "show_trails": trails, "trail_joint": selected_joint,
               "show_grid": grid, "smooth": smooth}
    previous = baseline if compare else None
    st.plotly_chart(build_motion_figure(result, previous, **options), width="stretch", theme=None, key=f"studio_{token}", config={"displaylogo": False, "scrollZoom": True})
    st.caption(summary["note"])
    st.caption("Depth and meter scale are model estimates from a single camera. The solid shape is a visual aid around detected joints; it is not a scanned body surface.")
    with st.expander("Take this replay to your review"):
        st.write("Save a self-contained HTML replay to open offline. It includes movement landmarks. Share it with your care team only when you choose.")
        export_stamp = hashlib.sha256(json.dumps({"result": result, "baseline": previous, "options": options}, sort_keys=True, default=str).encode()).hexdigest()
        if st.button("Prepare offline 3D replay", key=f"export_{token}"):
            st.session_state[f"export_html_{token}"] = {"stamp": export_stamp, "data": build_motion_html(result, previous, **options)}
        export = st.session_state.get(f"export_html_{token}")
        if isinstance(export, dict) and export.get("stamp") == export_stamp:
            if export_context:
                from .private_access import private_download
                private_download("Download 3D replay", export["data"], user=export_context["user"],
                                 assessment_id=export_context["assessment_id"], file_name="parkinsense-3d-replay.html",
                                 mime="text/html", key=f"download_{token}")
            else:
                st.caption("Open this recording in an authenticated visit to download its private replay.")
        elif export:
            st.caption("Display options changed. Prepare the replay again to download this view.")


def live_movement_preview(snapshot, task, *, identity, show_trails=True, camera="Isometric"):
    """Display the latest focused world geometry and a bounded recent trail."""
    from .live_3d_viewer import build_live_3d_figure
    from .live_plot import render_live_plot
    from ml.vision.live_overlay import focus_definition
    focus = focus_definition(task)
    st.markdown("#### Live 3D joint tracking")
    st.caption(f"Focus: {focus['label']}")
    observation = snapshot.get("observation")
    if not observation:
        st.info("Keep the selected body part clearly in view. Freshly detected joints will appear here; tracking pauses when they are lost.")
        return
    figure = build_live_3d_figure(observation, task, history=snapshot.get("observation_history", []), show_trails=show_trails, camera=camera)
    if not figure.layout.meta or not figure.layout.meta.get("available"):
        st.info("The focused joints need a clearer view for 3D tracking. Adjust the camera to include the selected body part.")
        return
    token = hashlib.sha256(str(identity).encode()).hexdigest()[:16]
    render_live_plot(figure, key=f"live_3d_{token}")
    st.caption("Bright lines mark the task's focused joints; fading trails show recent movement. Drag to rotate this 3D view.")
    st.caption("Live estimated world XYZ. The camera overlay is its aligned screen projection; saved measurements are checked after recording.")
