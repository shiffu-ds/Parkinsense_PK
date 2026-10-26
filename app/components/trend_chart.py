"""A plain 2D trend of one measurement across accepted visits.

The 3D statistical review stays available; this is the first thing people see
because a line over dates is what most patients and clinicians read fastest.
Points carry the patient-reported medicine timing so like can be compared with
like. Missing visits are not interpolated: the line only joins real points.
"""

import plotly.graph_objects as go
import streamlit as st

from .palette import chart_layout, tokens

_STATE_LABEL = {"on": "ON", "wearing_off": "Wearing off", "off": "OFF", "unsure": "Unsure", "none": "No PD medicine"}


def _marker(t, state):
    if state == "on":
        return {"color": t.accent, "symbol": "circle", "line": {"color": t.accent, "width": 2}}
    if state in {"off", "wearing_off"}:
        return {"color": t.surface, "symbol": "circle", "line": {"color": t.ochre, "width": 2.5}}
    return {"color": t.ink_muted, "symbol": "circle", "line": {"color": t.ink_muted, "width": 1.5}}


def trend_figure(dates, values, label, unit, states=None):
    t = tokens()
    states = states or [None] * len(values)
    # Visits on the same day would collapse onto one date tick; label them by time instead.
    if len(dates) > 1 and (max(dates) - min(dates)).total_seconds() < 2 * 86400:
        dates = [f"{d:%d %b, %I:%M %p}" if hasattr(d, "strftime") else str(d) for d in dates]
        dates = [f"{label} ({i + 1})" if dates.count(label) > 1 else label for i, label in enumerate(dates)]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=dates, y=values, mode="lines", line={"color": t.rule_strong, "width": 2},
                                hoverinfo="skip", showlegend=False))
    hover = [f"{value:.4g} {unit}<br>Medicine timing: {_STATE_LABEL.get(state, 'not recorded')}" for value, state in zip(values, states)]
    figure.add_trace(go.Scatter(x=dates, y=values, mode="markers", showlegend=False,
                                marker={"size": 11, "color": [_marker(t, s)["color"] for s in states],
                                        "line": {"color": [_marker(t, s)["line"]["color"] for s in states],
                                                 "width": [_marker(t, s)["line"]["width"] for s in states]}},
                                hovertext=hover, hovertemplate="%{x}<br>%{hovertext}<extra></extra>"))
    if values:
        figure.add_hline(y=values[0], line={"color": t.ink_muted, "width": 1, "dash": "dot"},
                         annotation_text="First accepted visit", annotation_position="top left",
                         annotation_font={"size": 11, "color": t.ink_muted})
    figure.update_layout(**chart_layout(height=340, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                                        xaxis={"showgrid": False, "linecolor": t.rule_strong},
                                        yaxis={"title": {"text": f"{label} ({unit})", "font": {"size": 12}},
                                               "gridcolor": t.rule, "zeroline": False}))
    return figure


def render_trend(dates, values, label, unit, states=None, key=None):
    st.plotly_chart(trend_figure(dates, values, label, unit, states), width="stretch", theme=None,
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]}, key=key)
    if states and any(s in {"on", "off", "wearing_off"} for s in states):
        st.caption("Filled points were recorded while medicine was working (ON); open points while it was wearing off "
                   "or OFF; grey points have no timing recorded. Compare points of the same kind.")
