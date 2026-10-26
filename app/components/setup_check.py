"""Same-setup check: compare how two recordings were framed, and show the earlier framing.

A repeat recording made from a different distance, side or phone orientation
changes the measurements. The check names those differences in the patient's
language; it never corrects a value.
"""

import plotly.graph_objects as go
import streamlit as st

from ml.vision.framing import framing_differences, framing_summary, median_pose, touch_device_differences
from ml.vision.tasks import HAND_CONNECTIONS, POSE_CONNECTIONS, TASKS

from .design import next_step
from .palette import chart_layout, tokens
from .patient_language import text


def setup_differences(result, baseline, task):
    """Difference codes between this result and its comparison recording."""
    if not baseline:
        return None
    if result.get("test") in {"spiral", "tapping"}:
        return touch_device_differences(result, baseline)
    current, reference = framing_summary({**result, "task": task}), framing_summary({**baseline, "task": task})
    if current is None or reference is None:
        return None
    return framing_differences(current, reference)


def setup_notice(result, baseline, task, language="English"):
    """A plain-language note when the setup changed, or a short confirmation when it matched."""
    differences = setup_differences(result, baseline, task)
    if differences is None:
        return None
    if differences:
        items = "; ".join(text(f"setup_{code}", language) for code in differences)
        next_step(text("setup_differs", language), f"{items}. {text('setup_advice', language)}", "waiting")
    else:
        st.caption(text("setup_same", language))
    return differences


def framing_figure(reference, task):
    """The earlier recording's median pose inside its picture frame."""
    spec = TASKS.get(task)
    pose = median_pose(reference)
    metadata = reference.get("media_metadata") if isinstance(reference.get("media_metadata"), dict) else {}
    width, height = metadata.get("width"), metadata.get("height")
    if not spec or not pose or not width or not height:
        return None
    aspect = height / width
    t = tokens()
    figure = go.Figure(go.Scatter(x=[0, 1, 1, 0, 0], y=[0, 0, aspect, aspect, 0], mode="lines",
                                  line={"color": t.rule_strong, "width": 2}, hoverinfo="skip"))
    xs, ys = [], []
    for a, b in HAND_CONNECTIONS if spec["kind"] == "hand" else POSE_CONNECTIONS:
        if a < len(pose) and b < len(pose) and pose[a] and pose[b]:
            xs += [pose[a][0], pose[b][0], None]
            ys += [pose[a][1] * aspect, pose[b][1] * aspect, None]
    figure.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": t.accent, "width": 4}, hoverinfo="skip"))
    figure.update_layout(**chart_layout(height=300, margin={"l": 5, "r": 5, "t": 5, "b": 5}, showlegend=False,
                                        xaxis={"visible": False, "range": [-0.02, 1.02]},
                                        yaxis={"visible": False, "range": [aspect + 0.02, -0.02], "scaleanchor": "x", "scaleratio": 1}))
    return figure


def setup_guide(task, reference, language="English", *, key):
    """Before recording: how the person filled the picture in the comparison recording."""
    figure = framing_figure(reference, task) if reference else None
    if figure is None:
        return False
    with st.expander(text("setup_last_time", language)):
        st.caption(text("setup_last_time_detail", language))
        st.plotly_chart(figure, width="content", theme=None, key=key, config={"displaylogo": False, "staticPlot": True})
    return True
