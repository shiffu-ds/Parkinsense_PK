"""Recent-visit summaries render without the browser's dataframe bundle."""

from html.parser import HTMLParser

import pytest
from streamlit.testing.v1 import AppTest

from app.components.visit_summary import visit_summary_html
from backend import services
from backend.db import configure_db, init_db
from ml.nlp.functional import analyze_text
from ml.tabular.adl import ADL_ITEMS, analyze_adl


class SummaryTable(HTMLParser):
    """Read native table semantics, ignoring visual CSS and wrapper elements."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.headers = []
        self.caption = ""
        self.rows = []
        self._active = None
        self._parts = []
        self._attrs = {}
        self._row = None
        self._hidden_depth = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if self._hidden_depth:
            self._hidden_depth += 1
        elif attrs.get("aria-hidden") == "true":
            self._hidden_depth = 1
        if tag == "tr":
            self._row = []
        if tag in {"caption", "th", "td"}:
            self._active, self._parts, self._attrs = tag, [], attrs

    def handle_data(self, data):
        if self._active and not self._hidden_depth:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if self._hidden_depth:
            self._hidden_depth -= 1
        if tag == self._active:
            value = "".join(self._parts).strip()
            if tag == "caption":
                self.caption = value
            elif tag == "th":
                self.headers.append((value, self._attrs))
            elif tag == "td" and self._row is not None:
                self._row.append(value)
            self._active = None
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def test_visit_summary_has_native_accessible_table_and_all_summary_fields():
    rendered = visit_summary_html([
        {"visit": "03 Oct 2026, 10:30 AM PKT", "status": "Completed", "tasks_saved": 2, "review": "Reviewed"},
    ])
    table = SummaryTable(rendered)
    assert any(tag == "table" for tag, _ in table.tags)
    assert any(tag == "thead" for tag, _ in table.tags)
    assert any(tag == "tbody" for tag, _ in table.tags)
    assert table.caption == "Recent visits"
    assert [label for label, _ in table.headers] == ["Visit", "Status", "Tasks saved", "Care team review"]
    assert all(attrs.get("scope") == "col" for _, attrs in table.headers)
    assert table.rows == [["03 Oct 2026, 10:30 AM PKT", "Completed", "2", "Reviewed"]]


def test_visit_summary_escapes_every_dynamic_string_as_text():
    malicious = '<script>alert("visit")</script><img src=x onerror="alert(1)"> & "quoted"'
    rendered = visit_summary_html([
        {"visit": malicious, "status": malicious, "tasks_saved": malicious, "review": malicious},
    ])
    table = SummaryTable(rendered)
    assert not any(tag in {"script", "img"} for tag, _ in table.tags)
    assert "&lt;script&gt;" in rendered and "&lt;img" in rendered
    assert table.rows == [[malicious] * 4]


def test_visit_summary_limits_display_to_five_real_rows():
    rows = [{"visit": f"Visit {index}", "status": "Draft", "tasks_saved": index, "review": "Awaiting review"} for index in range(8)]
    table = SummaryTable(visit_summary_html(rows))
    assert len(table.rows) == 5
    assert [row[0] for row in table.rows] == [f"Visit {index}" for index in range(5)]
    assert "Visit 5" not in visit_summary_html(rows)


def test_empty_visit_summary_does_not_invent_a_visit_or_zero_measurement():
    assert visit_summary_html([]) == ""


@pytest.mark.parametrize("language,caption,headers,status,review,direction,lang", [
    ("Urdu", "حالیہ جانچیں", ["جانچ", "حالت", "محفوظ کام", "نگہداشت کی ٹیم کا جائزہ"], "مکمل", "جائزہ ہو گیا", "rtl", "ur"),
    ("Roman Urdu", "Haliya jaize", ["Jaiza", "Haalat", "Save kiye gaye tasks", "Care team ka review"], "Mukammal", "Review ho gaya", "ltr", "en"),
])
def test_visit_summary_uses_profile_language_and_native_urdu_direction(language, caption, headers, status, review, direction, lang):
    table = SummaryTable(visit_summary_html([
        {"visit": "03 Oct 2026", "status": "Completed", "tasks_saved": 0, "review": "Reviewed"},
    ], language))
    assert table.caption == caption
    assert [label for label, _ in table.headers] == headers
    assert table.rows == [["03 Oct 2026", status, "0", review]]
    assert any(tag == "div" and attrs.get("dir") == direction and attrs.get("lang") == lang for tag, attrs in table.tags)


def test_unknown_language_retains_english_fallback():
    table = SummaryTable(visit_summary_html([
        {"visit": "03 Oct 2026", "status": "Draft", "tasks_saved": 0, "review": "Awaiting review"},
    ], "Pashto"))
    assert table.caption == "Recent visits"
    assert table.rows == [["03 Oct 2026", "Draft", "0", "Awaiting review"]]


@pytest.fixture
def saved_visits(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'visit-summary.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Summary Patient", "summary@example.test", "test-password-123", consent=True)
    admin = services.bootstrap_admin("Summary Admin", "summary-admin@example.test", "test-password-123")
    clinician = services.create_staff(admin["id"], "Summary Clinician", "summary-clinician@example.test", "test-password-123")
    services.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    completed = services.create_assessment(patient["id"])
    services.save_module(patient["id"], completed["id"], "adl", analyze_adl(dict.fromkeys(ADL_ITEMS, 1)))
    services.save_module(patient["id"], completed["id"], "nlp", analyze_text("Walking is difficult in the morning."))
    services.finish_assessment(patient["id"], completed["id"])
    services.review_assessment(clinician["id"], completed["id"], "reviewed", "Reviewed synthetic test visit.")
    services.create_assessment(patient["id"])
    other = services.register_patient("Other Summary Patient", "other-summary@example.test", "test-password-123", consent=True)
    services.create_assessment(other["id"])
    return patient


def test_real_patient_home_keeps_saved_counts_status_and_reviews_without_a_dataframe(saved_visits):
    from app.views import time_label

    app = AppTest.from_string("from app.views import patient_home\npatient_home()", default_timeout=20)
    app.session_state["user_id"] = saved_visits["id"]
    app.run()
    assert not app.exception
    assert not app.dataframe
    expected = services.list_assessments(saved_visits["id"])
    tables = [SummaryTable(element.value) for element in app.markdown if "<table" in element.value]
    assert len(tables) == 1
    assert tables[0].rows == [
        [time_label(visit["created_at"]), visit["status"].title(), str(len(visit["modules"])),
         "Reviewed" if visit["review_status"] == "reviewed" else "Awaiting review"]
        for visit in expected
    ]
    assert {row[2] for row in tables[0].rows} == {"0", "2"}
    assert len(tables[0].rows) == 2
