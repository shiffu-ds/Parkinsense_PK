"""Small read-only visit summaries without Streamlit's lazy DataFrame grid.

The landing page needs four fields and at most five rows. Native HTML keeps
these visible when the browser has a failed grid import cached. All values
are escaped; this component never embeds patient data in executable code.
"""

from html import escape

import streamlit as st

from .patient_language import resolved_language, text

_HEADERS = {
    "English": ("Visit", "Status", "Tasks saved", "Care team review"),
    "Urdu": ("جانچ", "حالت", "محفوظ کام", "نگہداشت کی ٹیم کا جائزہ"),
    "Roman Urdu": ("Jaiza", "Haalat", "Save kiye gaye tasks", "Care team ka review"),
}
_VALUES = {
    "draft": ("Draft", "جاری جانچ", "Jaiza jaari hai"),
    "completed": ("Completed", "مکمل", "Mukammal"),
    "abandoned": ("Abandoned", "چھوڑی گئی جانچ", "Chhora hua jaiza"),
    "reviewed": ("Reviewed", "جائزہ ہو گیا", "Review ho gaya"),
    "awaiting review": ("Awaiting review", "جائزے کا انتظار", "Review ka intezar"),
}
_CSS = """
<style>
.ps-visit-summary {border:1px solid #2d404a;border-radius:9px;background:#14212b;color:#edf1ec;overflow:hidden;width:100%;}
.ps-visit-summary table {border-collapse:collapse;width:100%;margin:0;font-size:.95rem;}
.ps-visit-summary th,.ps-visit-summary td {padding:.9rem 1rem;text-align:start;border-bottom:1px solid #2d404a;overflow-wrap:anywhere;}
.ps-visit-summary th {background:#1b2d37;color:#bdcbd8;font-weight:600;}
.ps-visit-summary tbody tr:last-child td {border-bottom:none;}
.ps-visit-summary .ps-status {display:inline-block;border:1px solid #42616a;border-radius:6px;padding:.2rem .55rem;line-height:1.5;}
.ps-visit-summary .ps-review {color:#bdcbd8;}
.ps-visit-summary .ps-mobile-label {display:none;}
.ps-visit-summary caption {position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;}
@media(max-width:720px) {
  .ps-visit-summary table,.ps-visit-summary tbody {display:block;}
  .ps-visit-summary thead {position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);}
  .ps-visit-summary tbody tr {display:block;padding:.65rem .9rem;border-bottom:1px solid #2d404a;}
  .ps-visit-summary tbody tr:last-child {border-bottom:none;}
  .ps-visit-summary td {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:.8rem;align-items:center;border:0;padding:.5rem 0;}
  .ps-visit-summary .ps-mobile-label {display:block;color:#aab7bc;font-size:.88rem;}
}
</style>
"""


def _value(value, language):
    label = str(value)
    options = _VALUES.get(label.strip().lower())
    return options[{"English": 0, "Urdu": 1, "Roman Urdu": 2}[language]] if options else label


def visit_summary_html(rows, language="English"):
    """Render server-formatted rows; preserve real zero counts and text safely."""
    if not rows:
        return ""
    language = resolved_language(language)
    headers = _HEADERS[language]
    caption = escape(text("recent_visits", language), quote=True)
    direction, lang = ("rtl", "ur") if language == "Urdu" else ("ltr", "en")
    heading = "".join(f'<th id="ps-visit-col-{i}" scope="col">{escape(label)}</th>' for i, label in enumerate(headers))
    body = []
    for row in rows[:5]:
        values = (row["visit"], _value(row["status"], language), row["tasks_saved"], _value(row["review"], language))
        cells = []
        for i, (label, value) in enumerate(zip(headers, values)):
            css_class = "ps-status" if i == 1 else "ps-review" if i == 3 else "ps-value"
            cells.append(f'<td headers="ps-visit-col-{i}"><span class="ps-mobile-label" aria-hidden="true">{escape(label)}</span>'
                         f'<span class="{css_class}">{escape(str(value), quote=True)}</span></td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (_CSS + f'<div class="ps-visit-summary" lang="{lang}" dir="{direction}">'
            f'<table aria-label="{caption}"><caption>{caption}</caption><thead><tr>{heading}</tr></thead>'
            '<tbody>' + "".join(body) + "</tbody></table></div>")


def render_visit_summary(rows, language="English"):
    html = visit_summary_html(rows, language)
    if html:
        # Markdown is already loaded for the home copy. No DataFrame lazy
        # module, new iframe, remote font or script is needed for this table.
        st.markdown(html, unsafe_allow_html=True)
