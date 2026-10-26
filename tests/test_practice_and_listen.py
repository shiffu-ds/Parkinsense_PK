"""Browser-only practice aids and the read-aloud button."""
from pathlib import Path
import shutil
import subprocess

import pytest
from streamlit.testing.v1 import AppTest

from app.components.patient_language import TASK_STEPS, VOICE_PROMPTS
from app.components.practice_tools import cadence_bpm
from app.components.read_aloud import speech_for
from backend import services
from backend.db import configure_db, init_db

ROOT = Path(__file__).resolve().parents[1]


def gait(cadence, status="completed"):
    return {"status": status, "modules": {"gait": {"status": "completed", "quality": {"accepted": True, "decision": "ACCEPT"},
                                                   "features": {"cadence_steps_per_min_proxy": cadence}}}}


def test_walking_beat_starts_from_the_newest_accepted_cadence():
    assert cadence_bpm([gait(103.4), gait(80)]) == 105
    assert cadence_bpm([gait(150, status="abandoned"), gait(62)]) == 60
    assert cadence_bpm([gait(300)]) is None and cadence_bpm([]) is None


def test_urdu_and_roman_urdu_readers_hear_urdu_script():
    assert speech_for(TASK_STEPS["gait"], "Roman Urdu") == (TASK_STEPS["gait"][1], "ur-PK")
    assert speech_for(VOICE_PROMPTS["vowel"], "English") == (VOICE_PROMPTS["vowel"][0], "en-US")
    assert speech_for(VOICE_PROMPTS["vowel"], "Pashto")[1] == "en-US"  # No translation is claimed.


def test_practice_page_renders_both_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'practice.sqlite'}", allow_sqlite=True)
    init_db()
    patient = services.register_patient("Practice Patient", "practice@example.test", "testing-password-123", consent=True)
    app = AppTest.from_string("from app.views import practice_page\npractice_page()", default_timeout=30)
    app.session_state["user_id"] = patient["id"]
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Walking beat", "Louder voice"]
    assert any("nothing is recorded" in caption.value for caption in app.caption)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for the browser helper checks")
def test_browser_helpers(tmp_path):
    script = tmp_path / "practice-check.mjs"
    script.write_text(r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const load = async (path) => import('data:text/javascript;base64,' + Buffer.from(fs.readFileSync(path, 'utf8')).toString('base64'));
const practice = await load(process.argv[2]);
const listen = await load(process.argv[3]);
assert.equal(practice.clampBpm(103), 105);
assert.equal(practice.clampBpm(10), 40);
assert.equal(practice.clampBpm(400), 140);
assert.ok(Math.abs(practice.levelDb(new Float32Array(100).fill(0.5)) - 20 * Math.log10(0.5)) < 1e-6);
assert.equal(practice.levelDb(new Float32Array(10)), -100);
assert.equal(practice.meterFraction(-60), 0);
assert.equal(practice.meterFraction(0), 1);
assert.equal(practice.median([3, 1, 2]), 2);
assert.equal(practice.median([4, 1, 2, 3]), 2.5);
const voices = [{lang: 'en-US', name: 'a'}, {lang: 'ur_PK', name: 'b'}, {lang: 'hi-IN', name: 'c'}];
assert.equal(listen.pickVoice(voices, 'ur-PK').name, 'b');
assert.equal(listen.pickVoice(voices, 'en-US').name, 'a');
assert.equal(listen.pickVoice([{lang: 'en-GB', name: 'g'}], 'ur-PK'), null);
console.log('ok');
''')
    completed = subprocess.run(["node", str(script), str(ROOT / "app/components/practice.js"),
                                str(ROOT / "app/components/read_aloud.js")], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
