"""Pictures of a saved touch test: the drawing over its guide, or where the taps landed.

Clinicians read a spiral by eye as much as by number, so the trace is shown in
drawing-width units with the guide underneath. Nothing is interpolated.
"""

import math

import plotly.graph_objects as go
import streamlit as st

from ml.touch import spiral_template

from .palette import chart_layout, tokens


def spiral_figure(result):
    t = tokens()
    guide = spiral_template(600)
    figure = go.Figure(go.Scatter(x=guide[:, 0], y=guide[:, 1], mode="lines", line={"color": t.rule_strong, "width": 6},
                                  name="Guide", hoverinfo="skip"))
    trace = result.get("trace") if isinstance(result.get("trace"), list) else []
    xs, ys, times = [], [], []
    previous = None
    for point in trace:
        if not (isinstance(point, list) and len(point) == 4):
            continue
        if previous is not None and point[3] != previous:
            xs.append(None)
            ys.append(None)
            times.append(None)
        xs.append(point[0])
        ys.append(point[1])
        times.append(point[2])
        previous = point[3]
    figure.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": t.accent, "width": 2.5}, name="Drawing",
                                customdata=times, hovertemplate="%{customdata:.2f} s<extra>Drawing</extra>"))
    figure.update_layout(**chart_layout(height=380, margin={"l": 10, "r": 10, "t": 10, "b": 10}, showlegend=False,
                                        xaxis={"visible": False, "range": [0, 1]},
                                        yaxis={"visible": False, "range": [1, 0], "scaleanchor": "x", "scaleratio": 1}))
    return figure


def tapping_figure(result):
    t = tokens()
    geometry = result.get("geometry", {}) if isinstance(result.get("geometry"), dict) else {}
    radius = geometry.get("radius", 0.12)
    figure = go.Figure()
    for cx, cy in geometry.get("targets", []):
        angles = [2 * math.pi * n / 60 for n in range(61)]
        figure.add_trace(go.Scatter(x=[cx + radius * math.cos(a) for a in angles], y=[cy + radius * math.sin(a) for a in angles],
                                    mode="lines", fill="toself", fillcolor=t.accent_soft, line={"color": t.accent, "width": 2},
                                    hoverinfo="skip", showlegend=False))
    taps = [tap for tap in result.get("taps", []) if isinstance(tap, list) and len(tap) == 3]
    figure.add_trace(go.Scatter(x=[tap[0] for tap in taps], y=[tap[1] for tap in taps], mode="markers",
                                marker={"size": 7, "color": [tap[2] for tap in taps], "colorscale": [[0, t.ink_muted], [1, t.ochre]],
                                        "line": {"width": 0}},
                                customdata=[tap[2] for tap in taps], hovertemplate="%{customdata:.2f} s<extra>Tap</extra>", showlegend=False))
    height = geometry.get("height", 0.6)
    figure.update_layout(**chart_layout(height=280, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                                        xaxis={"visible": False, "range": [0, 1]},
                                        yaxis={"visible": False, "range": [height, 0], "scaleanchor": "x", "scaleratio": 1}))
    return figure


def render_touch_result(result, *, key):
    """The picture that goes with a touch test, when the raw touches were kept."""
    if result.get("test") == "spiral" and result.get("trace"):
        st.plotly_chart(spiral_figure(result), width="stretch", theme=None, key=f"{key}_spiral",
                        config={"displaylogo": False, "staticPlot": True})
        st.caption("Green is the drawing; the grey guide is what was traced. Distances use the drawing width as the unit.")
    elif result.get("test") == "tapping" and result.get("taps"):
        st.plotly_chart(tapping_figure(result), width="stretch", theme=None, key=f"{key}_taps",
                        config={"displaylogo": False, "staticPlot": True})
        st.caption("Each dot is a tap; later taps are lighter. The circles are the two targets.")
    device = result.get("device") if isinstance(result.get("device"), dict) else {}
    if device.get("canvas_px"):
        width, height = device["canvas_px"]
        st.caption(f"Recorded on a {width}×{height} px drawing area using {device.get('pointer', 'unknown')} input.")
