"""One source of colour for pages, charts and 3D viewers.

Page and chart colours follow the active Streamlit theme. The 3D movement
viewers deliberately stay on a dark "instrument" ground in both themes, the way
an imaging monitor does, so joints and trails read the same in every room.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tokens:
    paper: str
    surface: str
    sunken: str
    ink: str
    ink_muted: str
    rule: str
    rule_strong: str
    accent: str
    accent_ink: str
    accent_soft: str
    ochre: str
    ochre_soft: str
    alert: str
    alert_soft: str
    series: tuple


LIGHT = Tokens(
    paper="#F6F7F5", surface="#FFFFFF", sunken="#ECEFED", ink="#16262A", ink_muted="#4D5E62",
    rule="#D5DCD9", rule_strong="#A9B6B2", accent="#1D6B52", accent_ink="#FFFFFF", accent_soft="#E2EFE9",
    ochre="#8F5410", ochre_soft="#F6EBDC", alert="#A3392F", alert_soft="#F7E4E1",
    series=("#1D6B52", "#3F6E9C", "#B0731E", "#7A5C99", "#A3463A", "#4F8A8B"),
)

DARK = Tokens(
    paper="#111A1C", surface="#172225", sunken="#0D1517", ink="#E7EDEA", ink_muted="#A3B2B0",
    rule="#2C3B3E", rule_strong="#47595C", accent="#6FC3A2", accent_ink="#0D2A20", accent_soft="#1B3830",
    ochre="#E0B270", ochre_soft="#352B1D", alert="#EE9A8F", alert_soft="#3A2220",
    series=("#6FC3A2", "#8DB2DA", "#E0B270", "#B9A0D6", "#E39A8E", "#8CC5C5"),
)

# The dark instrument ground used by every 3D replay and live 3D view.
VIEWPORT = {
    "ground": "#132024", "panel": "#1B2B30", "grid": "#25383D", "axis": "#4A6166",
    "text": "#B9C8C6", "text_strong": "#E3ECE9", "attention": "#E0B270",
    "left": "#5CC0A0", "right": "#86AEDD", "core": "#93A6A9", "baseline": "#D2A86A",
}


def theme_type():
    """Return "light" or "dark" for the current viewer; light when unknown."""
    try:
        import streamlit as st
        kind = st.context.theme.type
    except Exception:
        return "light"
    return "dark" if kind == "dark" else "light"


def tokens(kind=None):
    return DARK if (kind or theme_type()) == "dark" else LIGHT


def chart_layout(kind=None, **overrides):
    """Shared Plotly layout for 2D/3D data graphs that sit on the page."""
    t = tokens(kind)
    layout = {
        "template": "plotly_dark" if t is DARK else "plotly_white",
        "paper_bgcolor": t.surface,
        "plot_bgcolor": t.surface,
        "font": {"family": "Atkinson Hyperlegible Next, Arial, sans-serif", "color": t.ink, "size": 12},
        "hoverlabel": {"bgcolor": t.surface, "bordercolor": t.rule_strong, "font": {"color": t.ink, "size": 12}},
        "colorway": list(t.series),
    }
    layout.update(overrides)
    return layout


def scene_axis(kind=None, **overrides):
    """Axis styling for a 3D data scene on the page (not the movement viewport)."""
    t = tokens(kind)
    axis = {"showbackground": True, "backgroundcolor": t.sunken, "gridcolor": t.rule, "zerolinecolor": t.rule_strong,
            "color": t.ink_muted, "showspikes": False, "tickfont": {"size": 10}, "title_font": {"size": 11}}
    axis.update(overrides)
    return axis
