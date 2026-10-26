"""Visual primitives for the ParkinSense workspace.

The look is a calm clinic chart: cool paper, deep ink, one green for actions,
ochre for "waiting" and brick red for "repeat". Colour always carries state,
never decoration. The single expressive element is the spiral mark — the
bedside spiral-drawing test, redrawn with a slight tremor in its outer turn.

Native widgets keep their semantics; Streamlit's own theme (see
.streamlit/config.toml) colours inputs and alerts, so this stylesheet only adds
structure, rhythm, touch targets and bilingual reading direction. Dynamic text
is escaped before it enters HTML.
"""

from functools import lru_cache
from html import escape
from pathlib import Path
import re

import streamlit as st

from app.components.palette import DARK, LIGHT, theme_type

BRAND_DIR = Path(__file__).resolve().parents[1] / "static" / "brand"


def _token_block(t):
    return (
        f"--ps-paper:{t.paper};--ps-surface:{t.surface};--ps-sunken:{t.sunken};--ps-ink:{t.ink};"
        f"--ps-muted:{t.ink_muted};--ps-line:{t.rule};--ps-line-strong:{t.rule_strong};--ps-accent:{t.accent};"
        f"--ps-accent-ink:{t.accent_ink};--ps-accent-soft:{t.accent_soft};--ps-ochre:{t.ochre};"
        f"--ps-ochre-soft:{t.ochre_soft};--ps-alert:{t.alert};--ps-alert-soft:{t.alert_soft};"
    )


_STYLES = """
<style>
:root {__LIGHT__}
[data-testid="stAppViewContainer"] {background: var(--ps-paper); color: var(--ps-ink);}
[data-testid="stMainBlockContainer"] {max-width: 1120px; padding-top: 3rem; padding-bottom: 5rem;}
[data-testid="stHeader"] {background: transparent;}
body, [data-testid="stMarkdownContainer"], [data-testid="stMetricValue"], [data-testid="stDataFrame"] {
  font-variant-numeric: tabular-nums;
}

/* Headings: one family, weight and size carry the hierarchy. */
[data-testid="stHeadingWithActionElements"] h1 {
  letter-spacing: -0.012em; line-height: 1.15; margin-bottom: 0.35rem; color: var(--ps-ink);
}
[data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3 {letter-spacing: -0.006em; line-height: 1.3; color: var(--ps-ink);}
[data-testid="stHeadingWithActionElements"] a {display: none;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color: var(--ps-muted); line-height: 1.55;}
[data-testid="stMarkdownContainer"] p {line-height: 1.6;}

/* Sidebar: the current page is marked by a rule, not a filled pill. */
[data-testid="stSidebar"] {border-right: 1px solid var(--ps-line);}
[data-testid="stSidebarHeader"] {padding-bottom: 0.75rem;}
[data-testid="stSidebarNav"] a {border-radius: 0 6px 6px 0; border-left: 3px solid transparent; padding-left: 0.7rem; min-height: 36px; margin: 1px 0;}
[data-testid="stSidebarNav"] a[aria-current="page"] {border-left-color: var(--ps-accent); background: transparent;}
[data-testid="stSidebarNav"] a[aria-current="page"] span {font-weight: 700; color: var(--ps-ink);}
[data-testid="stNavSectionHeader"] {color: var(--ps-muted); font-weight: 600; letter-spacing: 0; text-transform: none;}

/* Figures are records, not tiles: a rule above, the number, then its name. */
[data-testid="stMetric"] {
  padding: 0.85rem 0 0.2rem; border-top: 2px solid var(--ps-ink); background: transparent; border-radius: 0;
}
[data-testid="stMetricLabel"] {color: var(--ps-muted); font-size: 0.9rem;}
[data-testid="stMetric"] {margin-top: 0.9rem;}
[data-testid="stMetricValue"] {font-size: 1.75rem; font-weight: 700; letter-spacing: -0.01em;}

[data-testid="stVerticalBlockBorderWrapper"] > div, [data-testid="stForm"] {border-color: var(--ps-line); border-radius: 6px;}
[data-testid="stForm"] {background: var(--ps-surface); padding: 1.25rem 1.3rem;}
[data-testid="stExpander"] details {border-color: var(--ps-line); border-radius: 6px; background: var(--ps-surface);}
[data-testid="stExpander"] summary p {font-weight: 600;}

/* Touch targets stay at least 48px for unsteady hands. */
[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stLinkButton"] a,
[data-testid="stFileUploader"] button,
[data-testid="stAudioInput"] button {
  font-weight: 600; min-height: 48px; box-shadow: none; white-space: normal; height: auto; padding: 0.65rem 1.05rem;
}
[data-testid="stButton"] button[kind^="secondary"],
[data-testid="stFormSubmitButton"] button[kind^="secondary"],
[data-testid="stDownloadButton"] button {border-color: var(--ps-line-strong); background: var(--ps-surface);}
[data-testid="stButton"] button[kind^="secondary"]:hover,
[data-testid="stFormSubmitButton"] button[kind^="secondary"]:hover {border-color: var(--ps-accent); color: var(--ps-accent);}
[data-testid="stButton"] button[kind^="primary"],
[data-testid="stFormSubmitButton"] button[kind^="primary"] {background: var(--ps-accent); border-color: var(--ps-accent); color: var(--ps-accent-ink);}
[data-testid="stButton"] button[kind^="primary"] p,
[data-testid="stFormSubmitButton"] button[kind^="primary"] p {color: var(--ps-accent-ink);}
button:focus-visible, a:focus-visible, [role="tab"]:focus-visible, summary:focus-visible {
  outline: 3px solid var(--ps-accent) !important; outline-offset: 2px;
}
[data-testid="stButton"] button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stRadio"] label p,
[data-testid="stCheckbox"] label p {
  white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; line-height: 1.5;
}
[data-testid="stRadio"] label, [data-testid="stCheckbox"] label {min-height: 48px; align-items: center;}
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] div[data-rac][role="group"],
[data-testid="stSelectbox"] button,
[data-testid="stTextInput"] [data-testid="stTextInputRootElement"] {min-height: 48px;}
[data-testid="stSelectbox"] [data-baseweb="select"] span {white-space: normal; text-overflow: clip; overflow-wrap: anywhere;}
[data-testid="stPlotlyChart"],
[data-testid="stCustomComponentV1"],
[data-testid="stBidiComponentV2"] {max-width: 100%; min-width: 0; direction: ltr;}

[data-testid="stTabs"] [role="tablist"] {gap: 1.6rem; border-bottom: 1px solid var(--ps-line);}
[data-testid="stTabs"] [role="tab"] {font-weight: 600; min-height: 44px;}
[data-testid="stAlertContainer"] {border-radius: 6px;}

/* Welcome */
.ps-lede {font-size: 1.15rem; line-height: 1.6; max-width: 46ch; margin: 0.2rem 0 1.4rem;}
.ps-hero-art {margin: 0.5rem auto 1.4rem; max-width: 340px;}
.ps-hero-art svg {width: 100%; height: auto; display: block;}
.ps-hero-art .ps-spiral {fill: none; stroke: var(--ps-ink); stroke-width: 1.5; stroke-linecap: round;
  stroke-dasharray: 1; stroke-dashoffset: 1; animation: ps-draw 3.2s cubic-bezier(.45,.05,.3,1) .15s forwards;}
.ps-hero-art .ps-pen {fill: var(--ps-accent); opacity: 0; animation: ps-pen .4s ease-out 3.2s forwards;}
.ps-hero-art figcaption {color: var(--ps-muted); font-size: 0.88rem; line-height: 1.55; margin-top: 0.75rem; max-width: 40ch;}
@keyframes ps-draw {to {stroke-dashoffset: 0;}}
@keyframes ps-pen {to {opacity: 1;}}
@media (prefers-reduced-motion: reduce) {
  .ps-hero-art .ps-spiral {animation: none; stroke-dashoffset: 0;}
  .ps-hero-art .ps-pen {animation: none; opacity: 1;}
}

/* Section headings and small structural pieces */
.ps-section {margin: 1.6rem 0 0.9rem;}
.ps-section h2 {margin: 0; color: var(--ps-ink); font-size: 1.3rem; line-height: 1.35; font-weight: 700;}
.ps-section p {margin: 0.35rem 0 0; max-width: 70ch; color: var(--ps-muted); font-size: 0.95rem; line-height: 1.6;}
.ps-eyebrow {color: var(--ps-accent); font-size: 0.9rem; font-weight: 600; margin-bottom: 0.25rem;}
.ps-status {display: inline-flex; align-items: center; gap: 0.45rem; border: 1px solid var(--ps-line-strong);
  border-radius: 4px; padding: 0.2rem 0.6rem; font-size: 0.82rem; line-height: 1.45; color: var(--ps-muted);
  background: var(--ps-surface); margin: 0.15rem 0 0.8rem; font-weight: 600;}
.ps-status-row {display: flex; flex-wrap: wrap; gap: 0.5rem;}
.ps-status::before {content: ''; width: 7px; height: 7px; border-radius: 50%; background: currentColor;}
.ps-status-care {color: var(--ps-accent); border-color: var(--ps-accent); background: var(--ps-accent-soft);}
.ps-status-waiting {color: var(--ps-ochre); border-color: var(--ps-ochre); background: var(--ps-ochre-soft);}
.ps-status-alert {color: var(--ps-alert); border-color: var(--ps-alert); background: var(--ps-alert-soft);}
.ps-empty {border-inline-start: 3px solid var(--ps-line-strong); padding-block: 0.15rem; padding-inline: 1rem 0; margin: 0.65rem 0 1.1rem;}
.ps-empty strong {font-size: 1rem; color: var(--ps-ink); font-weight: 700;}
.ps-empty p {font-size: 0.95rem; line-height: 1.6; color: var(--ps-muted); max-width: 68ch; margin: 0.3rem 0 0;}

/* The one thing to do next. A left rule in the state colour, no box shadow. */
.ps-next {border: 1px solid var(--ps-line); border-inline-start: 4px solid var(--ps-accent); background: var(--ps-surface);
  border-radius: 6px; padding: 1rem 1.2rem; margin: 0.4rem 0 0.8rem;}
.ps-next-waiting {border-inline-start-color: var(--ps-ochre);}
.ps-next-alert {border-inline-start-color: var(--ps-alert);}
.ps-next strong {display: block; font-size: 1.08rem; color: var(--ps-ink); margin-bottom: 0.2rem;}
.ps-next p {margin: 0; color: var(--ps-muted); line-height: 1.6; max-width: 70ch;}

/* Task cards show their state on the leading edge of the card itself. */
[class*="st-key-ps_task_"] {background: var(--ps-surface); border-inline-start: 4px solid var(--ps-line-strong) !important;}
[class*="st-key-ps_task_done_"] {border-inline-start-color: var(--ps-accent) !important;}
.ps-task {margin-bottom: 0.4rem;}
.ps-task h3 {margin: 0 0 0.25rem; font-size: 1.1rem; font-weight: 700; color: var(--ps-ink);}
.ps-task p {margin: 0; color: var(--ps-muted); line-height: 1.55; font-size: 0.95rem;}
.ps-task .ps-task-state {color: var(--ps-ink); font-weight: 600; font-size: 0.88rem; margin-top: 0.4rem;}
.ps-task-done .ps-task-state {color: var(--ps-accent);}

/* Visit progress: one segment per task group. */
.ps-progress {display: flex; gap: 4px; margin: 0.35rem 0 0.4rem; max-width: 420px;}
.ps-progress span {flex: 1; height: 6px; border-radius: 3px; background: var(--ps-line);}
.ps-progress span.on {background: var(--ps-accent);}

/* Account block at the foot of the sidebar */
.ps-account {padding: 0.2rem 0 0.6rem;}
.ps-account strong {display: block; color: var(--ps-ink); font-size: 0.98rem;}
.ps-account span {color: var(--ps-muted); font-size: 0.85rem;}

/* Bilingual copy */
.ps-patient-locale {display: none;}
.ps-patient-copy {font-size: 1.02rem; line-height: 1.75; max-width: 72ch;}
.ps-patient-copy p {margin: 0.25rem 0 0.8rem;}
.ps-patient-copy ol {padding-inline-start: 1.75rem;}
.ps-patient-copy li {margin-bottom: 0.65rem; padding-inline-start: 0.3rem;}
.ps-patient-copy[lang="ur"] {
  font-family: "Noto Naskh Arabic", "Noto Nastaliq Urdu", "DejaVu Sans", Arial, sans-serif;
  font-size: 1.2rem; line-height: 2.05; text-align: right;
}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) :is(
  [data-testid="stHeadingWithActionElements"], [data-testid="stWidgetLabel"],
  [data-testid="stCaptionContainer"], [data-testid="stButton"],
  [data-testid="stFormSubmitButton"], [data-testid="stRadio"],
  [data-testid="stCheckbox"], [data-testid="stSelectbox"],
  [data-testid="stTextArea"], .ps-section, .ps-empty, .ps-status, .ps-next, .ps-task, .ps-progress, [data-testid="stMetric"]
) {
  direction: rtl;
  text-align: right;
  font-family: "Noto Naskh Arabic", "Noto Nastaliq Urdu", "DejaVu Sans", Arial, sans-serif;
}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) [class*="st-key-ps_task_"] {direction: rtl;}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) [data-testid="stMetricValue"] {unicode-bidi: plaintext;}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) :is(
  [data-testid="stButton"] button p, [data-testid="stFormSubmitButton"] button p,
  [data-testid="stWidgetLabel"] p, [data-testid="stRadio"] label p,
  [data-testid="stCheckbox"] label p
) {font-size: 1.05rem; line-height: 1.9;}

@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"] {padding: 2rem 1rem 3rem;}
  [data-testid="stForm"] {padding: 1rem;}
  [data-testid="stTabs"] [role="tablist"] {gap: 0.9rem;}
  [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: 1rem;}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 0 !important;
  }
  [data-testid="stRadio"] [role="radiogroup"] {flex-wrap: wrap;}
  [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
  [data-testid="stDownloadButton"] button {width: 100%;}
  .ps-patient-copy {max-width: 100%;}
  .ps-hero-art {max-width: 220px; margin-top: 1.5rem;}
  .ps-lede {font-size: 1.05rem;}
}
</style>
""".replace("__LIGHT__", _token_block(LIGHT))

_DARK_TOKENS = "<style>:root {" + _token_block(DARK) + "}</style>"


def inject_styles():
    """Apply the workspace stylesheet; dark tokens follow the viewer's theme."""
    from app.components.theme_sync import keep_theme_in_sync
    st.markdown(_STYLES, unsafe_allow_html=True)
    if theme_type() == "dark":
        st.markdown(_DARK_TOKENS, unsafe_allow_html=True)
    keep_theme_in_sync()


# Every ASCII character Markdown, GitHub autolinks, Streamlit directives
# (:red[...], :material/...:) or LaTeX ($) could act on.
_MARKDOWN_ACTIVE = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:=&])")


def plain_text(value):
    """People's own words for st.write/st.caption, shown as typed.

    No images load, nothing is formatted and no link text can hide its address.
    A bare web address still becomes clickable (GitHub-style autolinks run after
    escapes), but it always shows the real address.
    """
    return _MARKDOWN_ACTIVE.sub(r"\\\1", "" if value is None else str(value))


def logo_paths():
    """Sidebar logo and collapsed icon for the current theme."""
    suffix = "-dark" if theme_type() == "dark" else ""
    return str(BRAND_DIR / f"logo{suffix}.svg"), str(BRAND_DIR / f"mark{suffix}.svg")


@lru_cache(maxsize=1)
def _spiral_path():
    path, end = (BRAND_DIR / "spiral-path.txt").read_text(encoding="utf-8").splitlines()[:2]
    x, y = end.split()
    return path, x, y


def spiral_figure(caption=None):
    """The welcome illustration: a spiral drawn once, the way a patient draws it at the bedside."""
    path, x, y = _spiral_path()
    note = f"<figcaption>{escape(str(caption))}</figcaption>" if caption else ""
    st.markdown(
        '<figure class="ps-hero-art"><svg viewBox="0 0 320 320" role="img" aria-label="A hand-drawn spiral">'
        f'<path class="ps-spiral" pathLength="1" d="{path}"/><circle class="ps-pen" cx="{x}" cy="{y}" r="4.5"/>'
        f"</svg>{note}</figure>",
        unsafe_allow_html=True,
    )


def section_header(title, detail=None, eyebrow=None):
    """Render a compact section heading with optional plain-language context."""
    overline = f'<div class="ps-eyebrow">{escape(str(eyebrow))}</div>' if eyebrow else ""
    paragraph = f"<p>{escape(str(detail))}</p>" if detail else ""
    st.markdown(
        f'<section class="ps-section">{overline}<h2>{escape(str(title))}</h2>{paragraph}</section>',
        unsafe_allow_html=True,
    )


def status_pill(label, tone="neutral"):
    """Label provenance or workflow state; colour is never the only indicator."""
    safe_tone = tone if tone in {"care", "waiting", "alert"} else "neutral"
    st.markdown(
        f'<span class="ps-status ps-status-{safe_tone}">{escape(str(label))}</span>',
        unsafe_allow_html=True,
    )


def status_row(items):
    """Several state labels on one line, e.g. visit status and review status."""
    pills = "".join(
        f'<span class="ps-status ps-status-{tone if tone in {"care", "waiting", "alert"} else "neutral"}">{escape(str(label))}</span>'
        for label, tone in items)
    st.markdown(f'<div class="ps-status-row">{pills}</div>', unsafe_allow_html=True)


def empty_state(title, detail):
    """Give a useful next step when there is no saved patient information."""
    st.markdown(
        f'<div class="ps-empty"><strong>{escape(str(title))}</strong>'
        f'<p>{escape(str(detail))}</p></div>',
        unsafe_allow_html=True,
    )


def next_step(title, detail, tone="care"):
    """One clearly stated next action, with its state on the leading edge."""
    safe_tone = tone if tone in {"care", "waiting", "alert"} else "care"
    st.markdown(
        f'<div class="ps-next ps-next-{safe_tone}"><strong>{escape(str(title))}</strong>'
        f'<p>{escape(str(detail))}</p></div>',
        unsafe_allow_html=True,
    )


def task_card(title, detail, state, done=False):
    """A task group in the visit; the edge turns green once something is saved."""
    st.markdown(
        f'<div class="ps-task{" ps-task-done" if done else ""}"><h3>{escape(str(title))}</h3>'
        f'<p>{escape(str(detail))}</p><div class="ps-task-state">{escape(str(state))}</div></div>',
        unsafe_allow_html=True,
    )


def visit_progress(done, total, label):
    """Segmented progress for the task groups in one visit."""
    segments = "".join('<span class="on"></span>' if index < done else "<span></span>" for index in range(total))
    st.markdown(f'<div class="ps-progress" role="img" aria-label="{escape(str(label))}">{segments}</div>',
                unsafe_allow_html=True)


def account_block(name, role_label):
    st.markdown(f'<div class="ps-account"><strong>{escape(str(name))}</strong><span>{escape(str(role_label))}</span></div>',
                unsafe_allow_html=True)
