"""The touch-test page, its saved results and the shared guide geometry."""
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest
from streamlit.testing.v1 import AppTest

from backend import services
from backend.db import configure_db, init_db
from ml.common.statistics import measurements
from ml.inference.patient_report import build_patient_report
from ml.touch import SPIRAL_GEOMETRY, TAP_GEOMETRY, analyze_touch, spiral_template

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def patient(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'touch.sqlite'}", allow_sqlite=True)
    init_db()
    return services.register_patient("Touch Patient", "touch@example.test", "testing-password-123", consent=True)


def _spiral_payload():
    g = SPIRAL_GEOMETRY
    points = []
    for n in range(480):
        theta = n / 480 * 2 * math.pi * g["turns"]
        radius = g["r_max"] * theta / (2 * math.pi * g["turns"])
        points.append([g["cx"] + radius * math.cos(theta), g["cy"] + radius * math.sin(theta), n / 60, 0])
    return {"mode": "spiral", "canvas_px": [360, 360], "pointer": "touch", "dpr": 2, "points": points}


def test_touch_page_renders_for_an_open_visit(patient):
    visit = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import touch_page\ntouch_page()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    assert not app.exception
    assert app.title[0].value == "Spiral & tapping"
    app.radio(key=f"touch_hand_{visit['id']}").set_value("left").run()
    app.selectbox(key=f"touch_test_{visit['id']}").set_value("tapping").run()
    assert not app.exception
    assert any("20 seconds" in block.value for block in app.markdown)


def test_saved_touch_result_feeds_reports_statistics_and_lists(patient):
    visit = services.create_assessment(patient["id"])
    result = analyze_touch("spiral_right", _spiral_payload())
    assert result["quality"]["accepted"]
    services.save_module(patient["id"], visit["id"], "spiral_right", result)
    saved = services.list_assessments(patient["id"])[0]["modules"]["spiral_right"]
    assert saved["trace"] and services.FRAMES_OMITTED not in saved
    rows = measurements(saved, "spiral_right")
    assert {row.unit for row in rows} >= {"seconds", "% of drawing width"}
    report = build_patient_report(services.get_assessment(patient["id"], visit["id"]))
    section = next(section for section in report["sections"] if section["task"] == "spiral_right")
    assert section["title"] == "Spiral drawing — right hand" and section["accepted"]
    assert all(row["unit"] != "Not specified by this method" for row in section["measurements"])


def test_hub_lists_the_touch_group(patient):
    visit = services.create_assessment(patient["id"])
    app = AppTest.from_string("from app.views import assessment_hub\nassessment_hub()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.session_state["active_assessment_id"] = visit["id"]
    app.run()
    assert not app.exception
    assert any(button.label == "Open Spiral & tapping" for button in app.button)
    assert any("0 of 7 task groups saved" in caption.value for caption in app.caption)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for the canvas geometry check")
def test_canvas_guide_matches_the_scoring_guide(tmp_path):
    source = ROOT / "app/components/touch_test.js"
    script = tmp_path / "touch-geometry.mjs"
    script.write_text(r'''
import fs from 'node:fs';
const code = fs.readFileSync(process.argv[2], 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const spiral = JSON.parse(process.argv[3]);
const tapping = JSON.parse(process.argv[4]);
console.log(JSON.stringify({
  points: mod.spiralPoints(spiral, 600),
  hits: [mod.targetAt(0.25, 0.3, tapping), mod.targetAt(0.75, 0.31, tapping), mod.targetAt(0.5, 0.3, tapping)],
}));
''')
    completed = subprocess.run(["node", str(script), str(source), json.dumps(SPIRAL_GEOMETRY), json.dumps(TAP_GEOMETRY)],
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    expected = spiral_template(601)
    assert max(abs(a - b) for point, row in zip(output["points"], expected) for a, b in zip(point, row)) < 1e-9
    assert output["hits"] == [0, 1, -1]
