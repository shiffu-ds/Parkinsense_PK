"""Professional 3D descriptive graphs for every implemented analysis module.

The third dimension encodes an actual measurement, never artificial disease
severity. Recording curves preserve gaps. Scalar bars and visit markers retain
native units. All patient values come from accepted persisted/draft results.
"""
from __future__ import annotations

import hashlib

import plotly.graph_objects as go
import streamlit as st

from ml.common.statistics import (
    accepted, bounded_curve, compatible_history, descriptive_rows,
    measurements, recording_curves, safe_label, source_note,
)

COLORS = ("#63aaa5", "#859fbd", "#bea47a", "#96b596", "#ab99ba", "#b88982")
CAMERAS = {
    "Isometric": {"x": 2.0, "y": -2.0, "z": 1.45},
    "Front": {"x": 0.05, "y": -2.8, "z": 0.85},
    "Top": {"x": 0.05, "y": -0.1, "z": 2.8},
}
VIEWS = {"curves": "Recording curves", "measurements": "Measurement summary", "history": "Visit history"}


def _view(result, task, view):
    aliases = {label: key for key, label in VIEWS.items()}
    view = aliases.get(view, view)
    if view == "auto":
        return "curves" if recording_curves(result, task) else "measurements"
    return view if view in VIEWS else "measurements"


def module_statistics_groups(result: dict, task: str, *, view: str = "auto", history=None) -> list[str]:
    """Units available in the selected graph; incompatible units stay separate."""
    view = _view(result, task, view)
    if view == "curves":
        units = [curve.unit for curve in recording_curves(result, task)]
    elif view == "history":
        units = [row.unit for visit in compatible_history(result, task, history) for row in visit["measurements"]]
    else:
        units = [row.unit for row in measurements(result, task)]
    ordered = list(dict.fromkeys(units))
    if "rule match (0 or 1)" in ordered:
        ordered.remove("rule match (0 or 1)")
        ordered.insert(0, "rule match (0 or 1)")
    return ordered


def _empty(message="Accepted measurements are needed before this graph can be drawn."):
    figure = go.Figure()
    figure.add_annotation(text=safe_label(message, limit=220), showarrow=False, font={"size": 15, "color": "#aab8c5"})
    figure.update_layout(template="plotly_dark", paper_bgcolor="#101b27", plot_bgcolor="#101b27", height=360,
                         xaxis={"visible": False}, yaxis={"visible": False}, margin={"l": 15, "r": 15, "t": 35, "b": 35},
                         meta={"available": False})
    return figure


def _compact_tick(label):
    # Axis captions may be shortened; exact source labels remain in hover and
    # the measurement table. Long labels otherwise escape the WebGL viewport.
    compact = {"Household activities": "Household", "Mean of patient ratings": "Mean rating",
               "Spectral centroid · mean": "Centroid mean", "Spectral centroid · SD": "Centroid SD",
               "Estimated pitch · median": "Pitch median", "Estimated pitch · SD": "Pitch SD",
               "Autocorrelation periodicity": "Periodicity", "Signal-active fraction": "Signal active",
               "Left knee angle": "Knee · left", "Right knee angle": "Knee · right",
               "Mean knee angle": "Knee · mean", "Shoulder orientation": "Shoulder angle"}
    value = compact.get(label, label)
    return value if len(value) <= 18 else value[:17] + "…"


def _style(figure, *, unit, x_title, y_title, camera, title, tickvals_x=None, ticktext_x=None, tickvals_y=None, ticktext_y=None, y_range=None):
    axis = {"showbackground": True, "backgroundcolor": "#13202d", "gridcolor": "#2a3b49", "zerolinecolor": "#64798b",
            "color": "#b8c7d4", "showspikes": False, "tickfont": {"size": 10}, "title_font": {"size": 11}}
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#101b27", plot_bgcolor="#101b27", height=490,
        title={"text": title, "font": {"size": 16, "color": "#d9e5eb"}, "x": 0.02},
        font={"family": "Inter, Arial, sans-serif", "color": "#c3d2dd", "size": 12},
        margin={"l": 45, "r": 50, "t": 55, "b": 85}, hoverlabel={"bgcolor": "#253744", "font_size": 12},
        scene={"xaxis": {**axis, "title": {"text": x_title}, "tickvals": tickvals_x, "ticktext": [_compact_tick(label) for label in ticktext_x] if ticktext_x else None},
               "yaxis": {**axis, "title": {"text": y_title}, "tickvals": tickvals_y, "ticktext": [_compact_tick(label) for label in ticktext_y] if ticktext_y else None, "range": y_range},
               "zaxis": {**axis, "title": {"text": unit}, "rangemode": "tozero"},
               "camera": {"eye": CAMERAS.get(camera, CAMERAS["Isometric"])},
               "aspectmode": "manual", "aspectratio": {"x": 1.6, "y": 0.85, "z": 1.05}, "dragmode": "orbit"},
        legend={"orientation": "h", "yanchor": "top", "y": -0.15, "x": 0.01, "font": {"size": 10}},
        meta={"available": True, "unit": unit, "source": "accepted_module_measurements", "clinical_score": False},
    )


def _bar(x, y, value, color, label):
    # Explicit box geometry; no triangulation, interpolated surfaces or data
    # generation. Negative measured values extend below the zero reference.
    x0, x1, y0, y1 = x - 0.28, x + 0.28, y - 0.25, y + 0.25
    return go.Mesh3d(x=[x0, x1, x1, x0, x0, x1, x1, x0],
                     y=[y0, y0, y1, y1, y0, y0, y1, y1],
                     z=[0, 0, 0, 0, value, value, value, value],
                     i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3],
                     j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
                     k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                     color=color, name=label, flatshading=True, opacity=0.82,
                     lighting={"ambient": 0.75, "diffuse": 0.55, "roughness": 0.95, "specular": 0.05},
                     showlegend=False, hoverinfo="skip")


def build_module_statistics_figure(result: dict, task: str, *, unit: str | None = None,
                                   view: str = "auto", history=None, camera: str = "Isometric",
                                   selected_keys: list[str] | None = None) -> go.Figure:
    """Pure graph builder; charts require explicit acceptance and known units.

    Curves use elapsed seconds × measurement series × recorded value. Summary
    bars use measurement × this analysis × recorded value. History uses visit
    order × measurement × value, with markers only, including blank visit rows
    where recordings were missing, rejected or incompatible.
    """
    if not accepted(result):
        return _empty("This result has no accepted measurements. Follow the recording guidance and repeat the task.")
    view = _view(result, task, view)
    units = module_statistics_groups(result, task, view=view, history=history)
    if unit is None:
        unit = units[0] if units else None
    if unit not in units:
        return _empty("No finite measurements with a defined unit are available for this graph.")
    keyset = set(selected_keys) if selected_keys is not None else None
    figure = go.Figure()
    if view == "curves":
        curves = [curve for curve in recording_curves(result, task) if curve.unit == unit and (keyset is None or curve.key in keyset)]
        for number, curve in enumerate(curves):
            timestamps, values = bounded_curve(curve)
            series = [number if time is not None else None for time in timestamps]
            figure.add_trace(go.Scatter3d(x=timestamps, y=series, z=values, mode="lines+markers", connectgaps=False,
                                         marker={"color": COLORS[number % len(COLORS)], "size": 2.6},
                                         line={"color": COLORS[number % len(COLORS)], "width": 4}, name=curve.label,
                                         hovertemplate=f"{curve.label}<br>Time %{{x:.2f}} s<br>Value %{{z:.4g}} {unit}<extra>Recorded movement proxy</extra>"))
        _style(figure, unit=unit, x_title="Elapsed time (seconds)", y_title="Measurement series", camera=camera,
               title="Movement over the recording", tickvals_y=list(range(len(curves))), ticktext_y=[curve.label for curve in curves])
        figure.update_layout(meta={**figure.layout.meta, "display_sampling": "At most 300 actual samples and gap separators per series; no interpolation"})
    elif view == "history":
        visits = compatible_history(result, task, history)
        definitions = {}
        for visit in visits:
            for row in visit["measurements"]:
                if row.unit == unit and (keyset is None or row.key in keyset):
                    definitions.setdefault(row.key, row)
        definitions = dict(list(definitions.items())[:32])
        for number, (key, definition) in enumerate(definitions.items()):
            x, z, dates = [], [], []
            for index, visit in enumerate(visits):
                row = next((row for row in visit["measurements"] if row.key == key and row.unit == unit), None)
                if row is not None:
                    x.append(index)
                    z.append(row.value)
                    dates.append(visit["date"])
            figure.add_trace(go.Scatter3d(x=x, y=[number] * len(x), z=z, mode="markers", connectgaps=False,
                                         marker={"color": COLORS[number % len(COLORS)], "size": 5}, name=definition.label,
                                         customdata=dates,
                                         hovertemplate=f"{definition.label}<br>Visit %{{customdata}}<br>Value %{{z:.4g}} {unit}<extra>{definition.source}</extra>"))
        # Sparse ticks keep a long history legible. All visits remain positions
        # in the scene, including a gap in an otherwise compatible sequence.
        step = max(1, (len(visits) + 5) // 6)
        ticks = list(range(0, len(visits), step))
        if visits and len(visits) - 1 not in ticks:
            ticks.append(len(visits) - 1)
        _style(figure, unit=unit, x_title="Assessment visit", y_title="Measurement", camera=camera,
               title="Recorded visits · matching task, method and language",
               tickvals_x=ticks, ticktext_x=[visits[index]["date"][:10] for index in ticks],
               tickvals_y=list(range(len(definitions))), ticktext_y=[row.label for row in definitions.values()])
        figure.update_layout(meta={**figure.layout.meta, "empty_visits": sum(not visit["measurements"] for visit in visits), "history_connections": False})
    else:
        rows = [row for row in measurements(result, task) if row.unit == unit and (keyset is None or row.key in keyset)][:32]
        for number, row in enumerate(rows):
            figure.add_trace(_bar(number, 0, row.value, COLORS[number % len(COLORS)], row.label))
        # Top markers keep actual zero values visible without fabricating a
        # bar height, and hold one exact value per measurement in the hover.
        figure.add_trace(go.Scatter3d(x=list(range(len(rows))), y=[0] * len(rows), z=[row.value for row in rows], mode="markers",
                                     marker={"color": [COLORS[i % len(COLORS)] for i in range(len(rows))], "size": 5},
                                     customdata=[[row.label, row.unit, row.source] for row in rows], name="Recorded value", showlegend=False,
                                     hovertemplate="%{customdata[0]}<br>Value %{z:.4g} %{customdata[1]}<extra>%{customdata[2]}</extra>"))
        _style(figure, unit=unit, x_title="Measurement", y_title="Analysis", camera=camera,
               title="Measurements from this analysis", tickvals_x=list(range(len(rows))), ticktext_x=[row.label for row in rows],
               tickvals_y=[0], ticktext_y=["This analysis"], y_range=[-1, 1])
    if not any(len(trace.z) for trace in figure.data):
        return _empty("Choose at least one measurement to draw the graph.")
    figure.update_layout(uirevision=f"statistics-v2-{task}-{view}-{unit}-{camera}")
    return figure


def module_statistics_panel(result: dict, task: str, *, identity, history=None, default_view: str = "auto") -> None:
    """Render controls, genuine 3D graph and native-unit descriptive summary."""
    st.markdown("#### 3D statistical review")
    st.caption(source_note(task))
    if not accepted(result):
        st.info("This graph will be available after the recording or responses pass the quality check. Missing measurements are not shown as zero.")
        return
    prefix = "statistics_" + hashlib.sha256(f"{identity}:{task}".encode()).hexdigest()[:18]
    views = []
    if recording_curves(result, task):
        views.append("Recording curves")
    if measurements(result, task):
        views.append("Measurement summary")
    if any(visit["measurements"] for visit in compatible_history(result, task, history)):
        views.append("Visit history")
    if not views:
        st.info("No finite measurements with defined units are available for this module yet.")
        return
    preferred = VIEWS.get(_view(result, task, default_view))
    default_index = views.index(preferred) if preferred in views else 0
    view = st.radio("Statistical view", views, index=default_index, horizontal=True, key=prefix + "_view") if len(views) > 1 else views[0]
    groups = module_statistics_groups(result, task, view=view, history=history)
    left, right = st.columns([2, 1])
    with left:
        unit = st.selectbox("Measurement unit", groups, key=prefix + "_unit_" + _view(result, task, view)) if len(groups) > 1 else groups[0]
        if len(groups) == 1:
            st.caption(f"Value axis: {unit}")
    with right:
        camera = st.selectbox("Graph viewpoint", list(CAMERAS), key=prefix + "_camera")
    figure = build_module_statistics_figure(result, task, unit=unit, view=view, history=history, camera=camera)
    st.plotly_chart(figure, width="stretch", theme=None, key=prefix + "_plot_" + _view(result, task, view),
                    config={"displaylogo": False, "scrollZoom": False, "modeBarButtonsToRemove": ["toImage"],
                            "modeBarButtonsToAdd": ["resetCameraDefault3d"]})
    st.caption("Drag to rotate; use the camera reset button in the graph toolbar to restore the chosen viewpoint. Each graph keeps one measurement unit.")
    if _view(result, task, view) == "history":
        st.caption("Dots represent accepted matching results. Blank visits stay blank; changes are descriptive and do not establish clinical improvement or deterioration.")
    else:
        curves = _view(result, task, view) == "curves"
        rows = descriptive_rows(result, task, unit, curves=curves)
        if rows:
            with st.expander("Descriptive statistics" if curves else "Exact measurement values", expanded=False):
                st.dataframe(rows, hide_index=True, width="stretch")
                if curves:
                    st.caption("Statistics use all finite extracted samples, with population SD. The graph shows at most 300 actual samples and separators per series; gaps are not filled.")
