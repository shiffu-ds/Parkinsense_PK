"""The public demo can analyse only vetted, attributed clips, without a visit."""
from __future__ import annotations

import hashlib
import json

import pytest
from streamlit.testing.v1 import AppTest

from app.components import public_demo


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "public-demo"
    root.mkdir()
    video = root / "teaching.mp4"
    video.write_bytes(b"public teaching video fixture" * 12)
    entry = {"id": "teaching", "title": "Public walking example", "task": "gait", "path": video.name,
             "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
             "source_url": "https://example.org/published-video", "source_title": "Teaching source",
             "context": "The publisher describes this as a walking example.", "creator": "Teaching author",
             "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "start_seconds": 2, "end_seconds": 12}
    manifest = root / public_demo.MANIFEST_NAME
    manifest.write_text(json.dumps({"clips": [entry]}))
    return root, entry


def rewrite(root, entries):
    (root / public_demo.MANIFEST_NAME).write_text(json.dumps({"clips": entries}))


def test_only_hash_matched_public_clip_is_loaded(catalog):
    root, entry = catalog
    clips = public_demo.load_demo_clips(root)
    assert clips[0]["path"] == root / "teaching.mp4"
    assert clips[0]["source_url"] == entry["source_url"]
    assert clips[0]["start_seconds"] == 2
    (root / "teaching.mp4").write_bytes(b"changed video" * 20)
    with pytest.raises(public_demo.DemoCatalogError, match="has changed"):
        public_demo.load_demo_clips(root)


@pytest.mark.parametrize("use_symlink", [False, True])
def test_catalog_cannot_read_files_outside_public_demo_folder(catalog, use_symlink):
    root, entry = catalog
    outside = root.parent / "private.mp4"
    outside.write_bytes(b"private recording" * 20)
    entry["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    if use_symlink:
        link = root / "escape.mp4"
        link.symlink_to(outside)
        entry["path"] = link.name
    else:
        entry["path"] = "../private.mp4"
    rewrite(root, [entry])
    with pytest.raises(public_demo.DemoCatalogError, match="designated demo folder"):
        public_demo.load_demo_clips(root)


@pytest.mark.parametrize("change", [
    {"task": "diagnose_parkinson"}, {"source_url": "javascript:alert(1)"},
    {"license_url": "file:///secret"}, {"end_seconds": 1}, {"context": ""},
])
def test_catalog_rejects_invalid_task_attribution_or_excerpt(catalog, change):
    root, entry = catalog
    rewrite(root, [{**entry, **change}])
    with pytest.raises(public_demo.DemoCatalogError):
        public_demo.load_demo_clips(root)


def test_demo_report_has_source_demo_identity_and_escaped_attribution(catalog):
    _, entry = catalog
    entry["title"] = "<script>alert('source')</script>"
    entry["context"] = '<img src=x onerror="alert(1)">'
    result = {"task": "gait", "status": "repeat", "quality": {"accepted": False, "issues": ["Too few usable landmark frames were detected."]}, "features": {}}
    html = public_demo.demo_report_html(entry, result)
    assert "Public recording demonstration" in html
    assert "not a patient record" in html
    assert entry["source_url"] in html and entry["sha256"] in html
    assert "&lt;img" in html and '<img src=x' not in html
    assert "alert('source')" not in html
    assert "Public recording" in html


def test_demo_page_runs_same_pipeline_without_an_account_and_clears_stale_result(catalog, monkeypatch):
    root, entry = catalog
    monkeypatch.setattr(public_demo, "DEMO_ROOT", root)
    from backend import services

    def forbidden(*args, **kwargs):
        pytest.fail("The public demo must not access patient assessments")

    monkeypatch.setattr(services, "create_assessment", forbidden)
    monkeypatch.setattr(services, "get_assessment", forbidden)
    calls = []

    def analyze(path, task):
        calls.append((path, task))
        return {"task": task, "status": "repeat", "quality": {"accepted": False, "valid_frames": 0, "sampled_frames": 50,
                "valid_fraction": 0, "issues": ["Too few usable landmark frames were detected."]}, "features": {}, "landmark_frames": []}

    monkeypatch.setattr(public_demo, "analyze_video", analyze)
    app = AppTest.from_string("from app.components.public_demo import public_demo_page\npublic_demo_page()", default_timeout=20).run()
    assert not app.exception
    assert not calls
    assert not app.get("file_uploader")
    app.button(key="public_demo_analyze").click().run()
    assert not app.exception
    assert calls == [(root / "teaching.mp4", "gait")]
    assert app.session_state[public_demo.RESULT_KEY]["result"]["quality"]["valid_frames"] == 0
    assert "user_id" not in app.session_state
    assert "active_assessment_id" not in app.session_state
    assert any(item.label == "Download demo report" for item in app.get("download_button"))
    second = {**entry, "id": "second", "title": "Second example", "task": "turning"}
    rewrite(root, [entry, second])
    app.run()
    app.selectbox(key="public_demo_clip").select("second").run()
    assert not app.exception
    assert public_demo.RESULT_KEY not in app.session_state
    assert len(calls) == 1


def test_missing_catalog_is_actionable_and_does_not_leak_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(public_demo, "DEMO_ROOT", tmp_path / "secret-directory")
    app = AppTest.from_string("from app.components.public_demo import public_demo_page\npublic_demo_page()", default_timeout=20).run()
    assert not app.exception
    assert "not installed yet" in app.info[0].value
    assert "secret-directory" not in app.info[0].value
    assert not app.button


def test_real_audio_demo_has_statistics_and_report_without_body_tracking(catalog, monkeypatch):
    import numpy as np
    import soundfile as sf
    root, entry = catalog
    path = root / "speech.wav"
    rate = 16000
    # A synthetic tone tests processing, not speech recognition or diagnosis.
    sf.write(path, 0.2 * np.sin(2 * np.pi * 180 * np.arange(rate * 4) / rate), rate)
    entry.update(task="voice_natural", path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    rewrite(root, [entry])
    monkeypatch.setattr(public_demo, "DEMO_ROOT", root)
    def forbidden(*args, **kwargs):
        pytest.fail("Voice must not run the vision pipeline or save a patient visit")
    monkeypatch.setattr(public_demo, "analyze_video", forbidden)
    from backend import services
    monkeypatch.setattr(services, "save_module", forbidden)
    app = AppTest.from_string("from app.components.public_demo import public_demo_page\npublic_demo_page()", default_timeout=20).run()
    assert not app.exception
    assert app.get("audio") and not app.get("video")
    app.button(key="public_demo_analyze").click().run()
    assert not app.exception
    result = app.session_state[public_demo.RESULT_KEY]["result"]
    assert result["quality"]["accepted"]
    assert result["features"]["f0_autocorrelation_median_hz"] == pytest.approx(180, abs=10)
    assert app.get("plotly_chart")
    assert not any("3D joints were not found" in item.value for item in app.info)
    html = public_demo.demo_report_html(entry, result)
    assert "voice_natural" not in html  # human-readable module label
    assert "Natural speech" in html or "Natural Speech" in html
    assert entry["sha256"] in html


def test_voice_catalog_cannot_mislabel_video_as_wav(catalog):
    root, entry = catalog
    rewrite(root, [{**entry, "task": "voice_natural"}])
    with pytest.raises(public_demo.DemoCatalogError, match="designated demo folder"):
        public_demo.load_demo_clips(root)


def test_report_download_stays_stable_and_inline_preview_matches_it(catalog, monkeypatch):
    """Unrelated reruns must not replace a user's download with a new timestamp."""
    from datetime import datetime, timedelta, timezone
    from ml.inference import patient_report
    root, entry = catalog
    monkeypatch.setattr(public_demo, "DEMO_ROOT", root)
    class MovingClock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return datetime(2026, 10, 19, tzinfo=timezone.utc) + timedelta(minutes=cls.calls)

    monkeypatch.setattr(patient_report, "datetime", MovingClock)
    monkeypatch.setattr(public_demo, "analyze_video", lambda *_: {
        "task": "gait", "status": "repeat", "quality": {"accepted": False}, "features": {}})
    app = AppTest.from_string("from app.components.public_demo import public_demo_page\npublic_demo_page()").run()
    app.button(key="public_demo_analyze").click().run()
    assert not app.exception
    first_url = app.get("download_button")[0].proto.url
    document = app.session_state["public_demo_report_document"]["html"]
    assert first_url and entry["source_url"] in document
    app.run()
    assert app.get("download_button")[0].proto.url == first_url
    assert MovingClock.calls == 1
    app.button(key="public_demo_open_report").click().run()
    assert not app.exception
    assert app.get("iframe")[0].proto.srcdoc == document
    assert app.get("download_button")[0].proto.url == first_url
    app.selectbox(key="public_demo_language").set_value("Urdu").run()
    assert not app.exception
    assert MovingClock.calls == 2
    assert app.get("download_button")[0].proto.url != first_url
    assert app.get("iframe")[0].proto.srcdoc == app.session_state["public_demo_report_document"]["html"]


def test_3d_playback_changes_do_not_repeat_inference_and_invalidate_export(catalog, monkeypatch):
    """Synthetic joints exercise UI state; they do not validate model accuracy."""
    root, entry = catalog
    monkeypatch.setattr(public_demo, "DEMO_ROOT", root)
    limitation = "Arm-swing measurement is unavailable because both arms could not be tracked reliably."
    frames = []
    for frame_index in range(3):
        joints = [[(index % 5) * 0.05, (index // 5) * 0.07,
                   (index % 3) * 0.025 + frame_index * 0.01, 0.95] for index in range(33)]
        frames.append({"timestamp_s": frame_index * 0.1, "landmarks": joints, "world_landmarks": joints})
    calls = []

    def analyze(path, task):
        calls.append((path, task))
        return {"task": task, "status": "completed", "quality": {"accepted": True, "valid_frames": 3,
                "sampled_frames": 3, "valid_fraction": 1}, "features": {},
                "landmark_frames": frames, "limitations": [limitation]}

    monkeypatch.setattr(public_demo, "analyze_video", analyze)
    app = AppTest.from_string("from app.components.public_demo import public_demo_page\npublic_demo_page()", default_timeout=20).run()
    app.button(key="public_demo_analyze").click().run()
    assert not app.exception
    assert calls == [(root / "teaching.mp4", "gait")]
    assert limitation in [item.value for item in app.info]
    assert app.selectbox(key="public_demo_camera").value == "Isometric"
    assert app.selectbox(key="public_demo_speed").value == 1.0
    original = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert original["layout"]["meta"]["coordinate_source"] == "world_landmarks"
    assert original["layout"]["meta"]["playback_speed"] == 1.0
    app.button(key="public_demo_prepare_replay").click().run()
    assert not app.exception
    assert any(item.label == "Download demo 3D replay" for item in app.get("download_button"))
    old_export = app.session_state["public_demo_replay"]
    assert entry["source_url"] in old_export["html"]
    assert entry["license_url"] in old_export["html"]
    assert "Public recording demonstration" in old_export["html"]

    app.selectbox(key="public_demo_speed").set_value(0.5).run()
    assert not app.exception
    changed = json.loads(app.get("plotly_chart")[0].proto.spec)
    playback = changed["layout"]["updatemenus"][0]["buttons"][0]
    assert changed["layout"]["meta"]["playback_speed"] == 0.5
    assert [frame["duration"] for frame in playback["args"][1]["frame"]] == [200, 200, 0]
    assert not any(item.label == "Download demo 3D replay" for item in app.get("download_button"))
    assert any(item.label == "Download demo report" for item in app.get("download_button"))
    assert app.session_state["public_demo_replay"]["stamp"] == old_export["stamp"]
    assert len(calls) == 1

    app.button(key="public_demo_prepare_replay").click().run()
    assert not app.exception
    assert any(item.label == "Download demo 3D replay" for item in app.get("download_button"))
    assert app.session_state["public_demo_replay"]["stamp"] != old_export["stamp"]
    assert len(calls) == 1
