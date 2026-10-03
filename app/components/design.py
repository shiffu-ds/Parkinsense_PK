"""Small, accessible visual primitives for the care workspace.

The brand mark is an original code-native drawing. Dynamic text is escaped
before it enters HTML; native Streamlit form controls keep their semantics.
"""

from html import escape

import streamlit as st


_STYLES = """
<style>
:root {
  --ps-ink: #edf1ec;
  --ps-muted: #aab7bc;
  --ps-line: #2d404a;
  --ps-teal: #85d4bf;
  --ps-paper: #14212b;
}
[data-testid="stAppViewContainer"] {
  background: #0f1a23;
  color: var(--ps-ink);
}
[data-testid="stMainBlockContainer"] {
  max-width: 1220px;
  padding-top: 3.4rem;
  padding-bottom: 4rem;
}
[data-testid="stSidebar"] {
  background: #14212b;
  border-right: 1px solid var(--ps-line);
}
[data-testid="stSidebarNav"] a {
  border-radius: 7px;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: #223b40;
  color: #dff4ec;
}
[data-testid="stHeadingWithActionElements"] h1 {
  font-size: clamp(1.8rem, 3vw, 2.35rem);
  letter-spacing: -0.035em;
  font-weight: 650;
  line-height: 1.2;
  color: var(--ps-ink);
}
[data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3 {
  letter-spacing: -0.02em;
  font-weight: 600;
  color: var(--ps-ink);
}
[data-testid="stHeadingWithActionElements"] h2 {font-size: 1.4rem;}
[data-testid="stHeadingWithActionElements"] h3 {font-size: 1.12rem;}
[data-testid="stCaptionContainer"] {color: var(--ps-muted);}
[data-testid="stMetric"] {
  padding: 1.1rem 1.2rem;
  background: var(--ps-paper);
  border: 1px solid var(--ps-line);
  border-radius: 9px;
}
[data-testid="stMetricLabel"] {color: var(--ps-muted);}
[data-testid="stMetricValue"] {font-size: 1.8rem; font-weight: 600;}
[data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stForm"] {
  border-color: var(--ps-line);
  border-radius: 9px;
}
[data-testid="stForm"] {background: #14212b; padding: 1.2rem;}
[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stLinkButton"] a,
[data-testid="stFileUploader"] button,
[data-testid="stAudioInput"] button {
  border-radius: 7px;
  font-weight: 600;
  min-height: 48px;
  box-shadow: none;
  white-space: normal;
  height: auto;
  padding: 0.65rem 0.95rem;
}
[data-testid="stButton"] button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stRadio"] label p,
[data-testid="stCheckbox"] label p {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  overflow-wrap: anywhere;
  line-height: 1.5;
}
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
  min-height: 48px;
  align-items: center;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] div[data-rac][role="group"],
[data-testid="stSelectbox"] button,
[data-testid="stTextInput"] [data-testid="stTextInputRootElement"] {
  min-height: 48px;
}
[data-testid="stSelectbox"] [data-baseweb="select"] span {
  white-space: normal;
  text-overflow: clip;
  overflow-wrap: anywhere;
}
[data-testid="stPlotlyChart"],
[data-testid="stCustomComponentV1"],
[data-testid="stBidiComponentV2"] {
  max-width: 100%;
  min-width: 0;
  direction: ltr;
}
[data-testid="stButton"] button[kind^="primary"],
[data-testid="stFormSubmitButton"] button[kind^="primary"] {
  background: var(--ps-teal);
  border-color: var(--ps-teal);
  color: #102a25;
}
[data-testid="stButton"] button[kind^="primary"] p,
[data-testid="stFormSubmitButton"] button[kind^="primary"] p {
  color: #102a25;
}
[data-testid="stTextInput"] [data-testid="stTextInputRootElement"],
[data-testid="stTextArea"] [data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] div[data-rac][role="group"],
[data-testid="stMultiselect"] div[data-rac][role="group"],
[data-testid="stDateInput"] [data-testid="stDateInputField"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiselect"] [data-baseweb="select"] > div {
  background: #0e1922;
  border: 1px solid #536f7b;
  border-radius: 7px;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-rac][role="group"] input,
[data-testid="stMultiselect"] div[data-rac][role="group"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
  background: #0e1922;
  color: var(--ps-ink);
}
[data-testid="stDateInput"] [data-testid="stDateInputField"] [role="group"] {
  background: #0e1922;
}
[data-testid="stTextInput"] [data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextArea"] [data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stSelectbox"] div[data-rac][role="group"]:focus-within,
[data-testid="stMultiselect"] div[data-rac][role="group"]:focus-within,
[data-testid="stDateInput"] [data-testid="stDateInputField"]:focus-within,
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
[data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
[data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
[data-testid="stMultiselect"] [data-baseweb="select"] > div:focus-within {
  border-color: var(--ps-teal);
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
  color: #93a8b1;
}
[data-testid="stTabs"] [role="tablist"] {
  gap: 1.3rem;
  border-bottom: 1px solid var(--ps-line);
}
[data-testid="stTabs"] [role="tab"] {font-weight: 500;}
[data-testid="stAlertContainer"] {border-radius: 7px;}
.ps-brand {display: flex; align-items: center; gap: 11px; margin: 0 0 1.25rem;}
.ps-brand svg {flex: 0 0 38px; width: 38px; height: 38px;}
.ps-brand-name {font-weight: 650; letter-spacing: -0.04em; font-size: 1.27rem; line-height: 1.2;}
.ps-brand-region {color: var(--ps-teal); font-weight: 500;}
.ps-brand-description {font-size: 0.73rem; color: var(--ps-muted); margin-top: 3px; letter-spacing: 0.03em;}
.ps-brand-compact {margin-bottom: 0.55rem;}
.ps-brand-compact svg {flex-basis: 31px; width: 31px; height: 31px;}
.ps-brand-compact .ps-brand-name {font-size: 1.06rem;}
.ps-section {margin: 0.55rem 0 1rem;}
.ps-section h2 {margin: 0; color: var(--ps-ink); font-size: 1.35rem; line-height: 1.35; letter-spacing: -0.025em;}
.ps-section p {margin: 0.45rem 0 0; max-width: 72ch; color: var(--ps-muted); font-size: 0.93rem; line-height: 1.6;}
.ps-eyebrow {color: var(--ps-teal); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.45rem;}
.ps-status {display: inline-flex; align-items: center; gap: 0.45rem; border: 1px solid var(--ps-line); border-radius: 100px; padding: 0.28rem 0.68rem; font-size: 0.75rem; line-height: 1.4; color: #c5d1d2; background: #17252e; margin: 0.15rem 0 0.8rem;}
.ps-status::before {content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor;}
.ps-status-care {color: #a6e6d2; border-color: #3c6458; background: #1d3831;}
.ps-status-waiting {color: #e5cba5; border-color: #675540; background: #322c25;}
.ps-empty {border-left: 2px solid #557478; padding: 0.1rem 0 0.1rem 1rem; margin: 0.65rem 0 1.1rem;}
.ps-empty strong {font-size: 0.97rem; color: #e1e8e4; font-weight: 550;}
.ps-empty p {font-size: 0.9rem; line-height: 1.6; color: var(--ps-muted); max-width: 70ch; margin: 0.35rem 0 0;}
.ps-patient-locale {display: none;}
.ps-patient-copy {font-size: 1rem; line-height: 1.75; max-width: 76ch;}
.ps-patient-copy p {margin: 0.25rem 0 0.8rem;}
.ps-patient-copy ol {padding-inline-start: 1.75rem;}
.ps-patient-copy li {margin-bottom: 0.65rem; padding-inline-start: 0.3rem;}
.ps-patient-copy[lang="ur"] {
  font-family: "Noto Naskh Arabic", "Noto Nastaliq Urdu", "DejaVu Sans", Arial, sans-serif;
  font-size: 1.18rem;
  line-height: 2;
  text-align: right;
}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) :is(
  [data-testid="stHeadingWithActionElements"], [data-testid="stWidgetLabel"],
  [data-testid="stCaptionContainer"], [data-testid="stButton"],
  [data-testid="stFormSubmitButton"], [data-testid="stRadio"],
  [data-testid="stCheckbox"], [data-testid="stSelectbox"],
  [data-testid="stTextArea"], .ps-section, .ps-empty, .ps-status
) {
  direction: rtl;
  text-align: right;
  font-family: "Noto Naskh Arabic", "Noto Nastaliq Urdu", "DejaVu Sans", Arial, sans-serif;
}
[data-testid="stMain"]:has(.ps-patient-locale[lang="ur"]) :is(
  [data-testid="stButton"] button p, [data-testid="stFormSubmitButton"] button p,
  [data-testid="stWidgetLabel"] p, [data-testid="stRadio"] label p,
  [data-testid="stCheckbox"] label p
) {font-size: 1.05rem; line-height: 1.9;}
@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"] {padding: 2rem 1.1rem 3rem;}
  [data-testid="stForm"] {padding: 1rem;}
  [data-testid="stTabs"] [role="tablist"] {gap: 0.8rem;}
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
}
</style>
"""


def inject_styles():
    """Apply restrained workspace styling without hiding native UI controls."""
    st.markdown(_STYLES, unsafe_allow_html=True)


def brand_wordmark(compact=False):
    """Render the ParkinSense wordmark and its original movement mark."""
    variant = " ps-brand-compact" if compact else ""
    st.markdown(
        f'<div class="ps-brand{variant}" aria-label="ParkinSense Pakistan">'
        '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
        '<rect x="1" y="1" width="38" height="38" rx="10" fill="#1d3935" stroke="#42645c"/>'
        '<path d="M10 27V13M10 20H19C24 20 28 16 29 11M19 20C24 20 28 24 30 29" '
        'fill="none" stroke="#b4e3ce" stroke-width="2.4" stroke-linecap="round"/>'
        '<circle cx="29" cy="11" r="2" fill="#d9b996"/>'
        '<circle cx="30" cy="29" r="2" fill="#d9b996"/>'
        '</svg><div><div class="ps-brand-name">ParkinSense<span class="ps-brand-region"> · PK</span></div>'
        '<div class="ps-brand-description">Movement &amp; everyday care</div></div></div>',
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
    """Label provenance or workflow state; color is never the only indicator."""
    safe_tone = tone if tone in {"care", "waiting"} else "neutral"
    st.markdown(
        f'<span class="ps-status ps-status-{safe_tone}">{escape(str(label))}</span>',
        unsafe_allow_html=True,
    )


def empty_state(title, detail):
    """Give a useful next step when there is no saved patient information."""
    st.markdown(
        f'<div class="ps-empty"><strong>{escape(str(title))}</strong>'
        f'<p>{escape(str(detail))}</p></div>',
        unsafe_allow_html=True,
    )
