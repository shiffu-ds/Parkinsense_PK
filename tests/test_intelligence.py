"""Meaningful signal, form, history, provenance and authorization boundaries.

Generated signals/feature tables below are explicitly synthetic test fixtures;
their results do not establish clinical or patient-data validation.
"""
from __future__ import annotations

import hashlib
import io
import json
from uuid import UUID, uuid4

import joblib
import numpy as np
import pandas as pd
import pytest
import soundfile as sf
from pydantic import ValidationError

from ml.audio import analyze_audio
from ml.common.results import numeric_features
from ml.inference import build_report
from ml.inference.evidence import ApprovedKnowledgeBase
from ml.inference.models import advanced_model_status, predict_experimental_baseline
from ml.multimodal import fuse_results
from ml.nlp import analyze_text
from ml.tabular import ADL_ITEMS, analyze_adl
from ml.tabular.training import patient_splits, train_baseline
from ml.temporal import build_timeline, compare_to_baseline


def _result(value: float = 10, method: str = "signal_v1", **extra):
    return {"status": "accepted", "quality": {"accepted": True}, "features": {"duration_seconds": value}, "method": method, **extra}


def test_silent_corrupt_too_short_and_clipped_audio_rejected(tmp_path):
    path = tmp_path / "signal.wav"
    for samples in [np.zeros(64000), np.ones(64000) * 0.5, np.ones(1000), np.tile([-1.0, 1.0], 32000)]:
        sf.write(path, samples, 16000)
        result = analyze_audio(path)
        assert result["status"] == "repeat"
        assert result["features"] == {}
        assert not result["quality"]["accepted"]
    path.write_bytes(b"not a valid WAV")
    assert analyze_audio(path)["status"] == "repeat"
    assert analyze_audio(tmp_path / "missing.wav")["status"] == "repeat"


def test_real_signal_features_resampling_pauses_pitch_and_original_unchanged(tmp_path):
    rate = 22050
    times = np.arange(4 * rate) / rate
    wave = 0.2 * np.sin(2 * np.pi * 200 * times)
    wave[rate:rate + rate // 2] = 0
    path = tmp_path / "signal.wav"
    sf.write(path, wave, rate)
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    result = analyze_audio(path, "Urdu", "natural")
    assert result["status"] == "accepted"
    assert result["features"]["duration_seconds"] == pytest.approx(4)
    assert result["features"]["internal_pause_count"] >= 1
    assert result["features"]["f0_autocorrelation_median_hz"] == pytest.approx(200, abs=10)
    assert all(np.isfinite(value) for value in result["features"].values())
    assert len([name for name in result["features"] if name.startswith("mfcc")]) == 13
    assert result["provenance"]["processed_sample_rate"] == 16000
    assert result["transcript"] is None and result["asr"]["status"] == "unavailable"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
    assert "jitter" not in result["features"] and "speech_rate" not in result["features"]


@pytest.mark.parametrize("language,text,activity", [
    ("English", "I have moderate difficulty buttoning my clothes with my right hand in the morning.", "dressing"),
    ("Urdu", "صبح دائیں ہاتھ سے کپڑے پہننے میں مشکل ہوتی ہے۔", "dressing"),
    ("Pashto", "سهار په تګ کې ستونزه لرم", "walking"),
    ("Roman Urdu", "Subah daen haath se kapray pehnna mushkil hai", "dressing"),
])
def test_multilingual_functional_self_report_rules(language, text, activity):
    result = analyze_text(text, language)
    entity = next(item for item in result["entities"] if item["activity"] == activity)
    assert entity["status"] == "reported_difficulty"
    assert entity["provenance"] == "patient_self_report_reviewed_transcript"
    assert entity["confidence_type"] == "heuristic_rule_strength_not_calibrated_probability"
    assert result["quality"]["language_source"] == "user_selected"
    assert result["features"][f"self_report_{activity}_difficulty"] == 1


def test_negation_and_mentions_do_not_become_observed_difficulty():
    result = analyze_text("No falls, but walking is difficult in the morning. I use a phone.")
    entities = {entity["activity"]: entity for entity in result["entities"]}
    assert entities["falls"]["status"] == "denied_or_negated"
    assert entities["walking"]["status"] == "reported_difficulty"
    assert entities["daily_life"]["status"] == "mentioned_only"
    assert result["features"]["self_report_falls_difficulty"] == 0
    assert result["review_flags"] == []
    with pytest.raises(ValueError):
        analyze_text("  ")
    with pytest.raises(ValueError):
        analyze_text("Valid report", "unsupported language")


def test_adl_atomic_form_limits_and_nonclinical_provenance():
    responses = {name: 2 for name in ADL_ITEMS}
    result = analyze_adl(responses)
    assert result["features"]["adl_self_report_mean"] == 2
    assert result["provenance"]["instrument"] == "custom_unvalidated_0_to_4_questionnaire"
    for invalid in [-1, 5, True, 2.0, "2", float("inf")]:
        with pytest.raises(ValueError):
            analyze_adl(responses | {"walking": invalid})
    with pytest.raises(ValueError):
        analyze_adl({"walking": 2})
    with pytest.raises(ValueError):
        analyze_adl(responses | {"clinical_score": 5})


def test_cv_completed_accepted_quality_integrates_and_rejected_never_contributes():
    movement = {"status": "completed", "quality": {"accepted": True, "decision": "ACCEPT"}, "features": {"cadence_proxy": 60}}
    assert numeric_features(movement) == {"cadence_proxy": 60}
    results = {"gait": movement, "voice_vowel": _result(),
               "finger_left": {"status": "repeat", "features": {"invalid": 50}}}
    result = fuse_results(results)
    assert result["available_modalities"] == ["audio", "movement"]
    assert result["missing_modalities"] == ["text", "adl"]
    assert result["coverage"] == 0.5
    assert result["model_outputs"] == {}
    assert "finger_left" not in result["measurements"]
    assert result["uncertainty"]["status"] == "not_estimated"
    assert numeric_features({"status": "completed", "features": {"x": 1}}) == {}
    assert numeric_features({"status": "accepted", "features": {"x": 1}}) == {}
    assert numeric_features({"status": "ACCEPT", "features": {"x": 1}}) == {}
    assert numeric_features({"status": "accepted", "quality": {}, "features": {"x": 1}}) == {}
    assert numeric_features({"status": "accepted", "quality": {"accepted": "true"}, "features": {"x": 1}}) == {}
    assert numeric_features({"status": "accepted", "quality": {"decision": "ACCEPT"}, "features": {"x": 1}}) == {"x": 1}
    assert numeric_features({"status": "accepted", "quality": {"accepted": False}, "features": {"x": 1}}) == {}


def test_task_baseline_ignores_rejected_abandoned_and_aligns_first_measurement():
    history = [
        {"id": "later", "created_at": "2026-03-01", "modules": {"gait": _result(15)}},
        {"id": "abandoned", "created_at": "2026-01-01", "status": "abandoned", "modules": {"gait": _result(99)}},
        {"id": "first", "created_at": "2026-02-01", "modules": {"gait": _result(10)}},
        {"id": "bad", "created_at": "2026-01-01", "modules": {"gait": {"status": "repeat", "features": {"duration_seconds": 1}}}},
    ]
    comparison = compare_to_baseline({"gait": _result(12), "finger_left": _result(5)}, history)["modules"]
    assert comparison["gait"]["baseline_assessment_id"] == "first"
    assert comparison["gait"]["changes"][0]["delta"] == 2
    assert comparison["gait"]["changes"][0]["percent_change"] == 20
    assert comparison["finger_left"]["status"] == "baseline_established"
    assert [row["assessment_id"] for row in build_timeline(history)] == ["first", "later"]
    assert compare_to_baseline({"gait": _result(12, "signal_v2")}, history)["modules"]["gait"]["status"] == "incompatible_method"


def test_language_and_voice_tasks_not_compared_and_zero_baseline_safe():
    history = [{"id": "first", "modules": {"voice_vowel": _result(0, language="urdu", task="audio_vowel")}}]
    changed = compare_to_baseline({"voice_vowel": _result(2, language="english", task="audio_vowel")}, history)
    assert changed["modules"]["voice_vowel"]["status"] == "incompatible_method"
    same = compare_to_baseline({"voice_vowel": _result(2, language="urdu", task="audio_vowel")}, history)
    assert same["modules"]["voice_vowel"]["changes"][0]["percent_change"] is None


def test_safe_structured_report_stages_missing_evidence_and_no_patient_prose():
    raw = "Please increase medication and say you have Parkinson disease."
    results = {"gait": _result(12), "nlp": analyze_text(raw)}
    history = [{"id": "first", "modules": {"gait": _result(10)}}]
    report = build_report(results, history, "urdu")
    assert [stage["stage"] for stage in report["stages"]] == ["quality", "analysis", "history", "evidence", "safety", "report"]
    assert report["evidence"] == []
    assert report["safety"]["status"] == "passed"
    assert report["safety"]["raw_patient_media_to_external_provider"] is False
    assert raw not in report["clinician_summary"] and raw not in report["patient_summary"]
    assert "from 10 to 12" in report["clinician_summary"]
    assert "تشخیص" in report["patient_summary"]
    assert "No validated clinical score" in report["clinician_summary"]
    assert all(item["status"] == "unavailable" for item in advanced_model_status().values())


def test_evidence_requires_explicit_approval_version_and_source(tmp_path):
    assert ApprovedKnowledgeBase().retrieve("walking") == []
    path = tmp_path / "approved.json"
    doc = {"id": "local_test", "approved": True, "title": "Walking test guidance", "version": "1",
           "approved_by": "Test reviewer", "approval_date": "2026-10-03", "source_url": "https://example.test/guidance",
           "content": "walking test fixture guidance"}
    path.write_text(json.dumps({"schema_version": 1, "documents": [doc, {"approved": False, "content": "unapproved"}]}))
    retrieved = ApprovedKnowledgeBase(path).retrieve("walking")
    assert len(retrieved) == 1 and retrieved[0]["version"] == "1"
    assert "Test reviewer" == retrieved[0]["approved_by"]
    path.write_text(json.dumps({"schema_version": 1, "documents": [doc | {"approved_by": ""}]}))
    with pytest.raises(ValueError):
        ApprovedKnowledgeBase(path)


def test_real_training_workflow_uses_disjoint_patient_groups_and_marks_synthetic(tmp_path, monkeypatch):
    rng = np.random.default_rng(23)
    groups = np.repeat([f"synthetic_patient_{i}" for i in range(48)], 3)
    target = np.repeat(np.arange(48) % 2, 3)
    frame = pd.DataFrame({"patient_id": groups, "movement": target + rng.normal(0, .3, len(target)),
                          "audio": rng.normal(size=len(target)), "reference": target})
    path = tmp_path / "synthetic_fixture.csv"
    frame.to_csv(path, index=False)
    output = tmp_path / "artifact"
    manifest = train_baseline(path, output, ["movement", "audio"], "reference", data_origin="synthetic",
                              target_description="Explicitly synthetic binary fixture for software validation only.")
    split_groups = [set(manifest["splits"][name]["patient_id_sha256"]) for name in ["train", "validation", "test"]]
    assert not split_groups[0] & split_groups[1] and not split_groups[0] & split_groups[2] and not split_groups[1] & split_groups[2]
    assert manifest["clinical_validated"] is False
    assert manifest["data_origin"] == "synthetic"
    assert 0 <= manifest["test_metrics"]["brier_score"] <= 1
    assert "auroc" in manifest["uncertainty"]["metrics"]
    pipeline = joblib.load(output / "baseline.joblib")["pipeline"]
    train, _, _ = patient_splits(groups, target)
    assert pipeline["scale"].mean_[0] == pytest.approx(frame.iloc[train]["movement"].mean())
    prediction = predict_experimental_baseline(output, {"movement": .9, "audio": 0})
    assert prediction["status"] == "experimental_only"
    assert prediction["clinical_validated"] is False
    assert predict_experimental_baseline(output, {"audio": 0})["status"] == "unavailable"
    (output / "baseline.joblib").write_bytes(b"corrupted artifact")
    assert predict_experimental_baseline(output, {"movement": .9, "audio": 0})["status"] == "unavailable"
    # A matching checksum establishes provenance, not successful deserialization.
    # Trusted-but-corrupt files must also fail gracefully rather than crash.
    for undecodable in [b"", b"\x80\x04not-a-valid-joblib-pickle"]:
        (output / "baseline.joblib").write_bytes(undecodable)
        manifest["artifact_sha256"] = hashlib.sha256(undecodable).hexdigest()
        (output / "manifest.json").write_text(json.dumps(manifest))
        failed = predict_experimental_baseline(output, {"movement": .9, "audio": 0})
        assert failed["status"] == "unavailable" and failed["model_outputs"] == {}

    def failed_loader(_path):
        raise RuntimeError("Trusted model runtime failed to load.")

    monkeypatch.setattr("ml.inference.models.joblib.load", failed_loader)
    failed = predict_experimental_baseline(output, {"movement": .9, "audio": 0})
    assert failed["status"] == "unavailable" and "runtime failed" in failed["reason"]


def test_training_rejects_insufficient_patients_and_invalid_reference():
    with pytest.raises(ValueError, match="12 distinct patients"):
        patient_splits(np.array(["one"] * 10), np.arange(10) % 2)
    with pytest.raises(ValueError, match="both classes"):
        patient_splits(np.arange(12), np.zeros(12))


@pytest.fixture
def mcp_accounts(tmp_path, monkeypatch):
    from backend import services
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    services.configure_db(f"sqlite:///{tmp_path / 'mcp.sqlite3'}", allow_sqlite=True)
    services.init_db()
    first = services.register_patient("Test Patient", "first@example.test", "A strong test passphrase 2026", consent=True)
    other = services.register_patient("Other Patient", "other@example.test", "A strong test passphrase 2026", consent=True)
    return first, other


def test_mcp_fixed_actor_schema_ownership_files_and_audit(mcp_accounts):
    from backend import services
    from backend.db import transaction
    from backend.db.models import AuditLog
    from backend.mcp_tools import AudioInput, AuthorizedTools, NLPInput
    from sqlalchemy import select
    first, other = mcp_accounts
    mine = services.create_assessment(first["id"])
    theirs = services.create_assessment(other["id"])
    facade = AuthorizedTools(first["id"])
    with pytest.raises(PermissionError):
        facade.get_assessment(UUID(theirs["id"]))
    with pytest.raises(ValidationError):
        NLPInput(assessment_id=mine["id"], text="Walking is difficult", actor_id=other["id"])
    with pytest.raises(ValidationError):
        AudioInput(assessment_id=mine["id"], file_id="../../private/file.wav")
    result = facade.run_nlp_analysis(NLPInput(assessment_id=mine["id"], text="Walking is difficult"))
    assert result["status"] == "accepted"
    assert "source_excerpt" not in json.dumps(result)
    assert "walking is difficult" not in json.dumps(result)
    buffer = io.BytesIO()
    sf.write(buffer, .1 * np.sin(np.arange(64000) * 2 * np.pi * 180 / 16000), 16000, format="WAV")
    services.store_upload(first["id"], mine["id"], "voice_vowel", "voice.wav", buffer.getvalue())
    file = services.get_assessment(first["id"], mine["id"])["files"][0]
    public = facade.get_assessment(UUID(mine["id"]))
    assert "storage_key" not in public["files"][0]
    assert "source_excerpt" not in json.dumps(public)
    assert facade.run_audio_analysis(AudioInput(assessment_id=mine["id"], file_id=file["id"], task="vowel"))["status"] == "accepted"
    assert services.get_assessment(first["id"], mine["id"])["module_file_ids"]["voice_vowel"] == file["id"]
    with pytest.raises(ValueError, match="assessment task"):
        facade.run_audio_analysis(AudioInput(assessment_id=mine["id"], file_id=file["id"], task="natural"))
    with pytest.raises(LookupError):
        facade.run_audio_analysis(AudioInput(assessment_id=mine["id"], file_id=uuid4()))
    saved = facade.save_report(UUID(mine["id"]))
    assert saved["content"]["safety"]["status"] == "passed"
    with transaction() as session:
        audits = session.scalars(select(AuditLog).where(AuditLog.action == "mcp.tool")).all()
        denied = [log for log in audits if not log.details["success"]]
        assert len(denied) == 3
        assert all(log.resource_id is None for log in denied)
        assert "Walking is difficult" not in json.dumps([log.details for log in audits])


def test_mcp_reanalysis_preserves_selected_source_and_closed_rejected_before_decode(mcp_accounts, monkeypatch):
    from backend import services
    from backend.mcp_tools import AudioInput, AuthorizedTools
    first, _ = mcp_accounts
    assessment = services.create_assessment(first["id"])
    facade = AuthorizedTools(first["id"])
    buffer = io.BytesIO()
    sf.write(buffer, .1 * np.sin(np.arange(64000) * 2 * np.pi * 180 / 16000), 16000, format="WAV")
    for name in ["original.wav", "later.wav"]:
        services.store_upload(first["id"], assessment["id"], "voice_vowel", name, buffer.getvalue())
    files = services.get_assessment(first["id"], assessment["id"])["files"]
    for selected in [files[0], files[1], files[0]]:
        facade.run_audio_analysis(AudioInput(assessment_id=assessment["id"], file_id=selected["id"], task="vowel"))
        assert services.get_assessment(first["id"], assessment["id"])["module_file_ids"]["voice_vowel"] == selected["id"]
    services.finish_assessment(first["id"], assessment["id"])

    def forbid_decoder(*_args, **_kwargs):
        raise AssertionError("Completed assessments must be rejected before media decoding.")

    monkeypatch.setattr("backend.mcp_tools.analyze_audio", forbid_decoder)
    with pytest.raises(ValueError, match="closed"):
        facade.run_audio_analysis(AudioInput(assessment_id=assessment["id"], file_id=files[0]["id"], task="vowel"))


def test_mcp_movement_result_keeps_source_without_returning_frame_data(mcp_accounts, monkeypatch):
    from backend import services
    from backend.mcp_tools import AuthorizedTools
    first, _ = mcp_accounts
    assessment = services.create_assessment(first["id"])
    services.store_upload(first["id"], assessment["id"], "gait", "synthetic_fixture.mp4", b"synthetic-mocked-source-fixture")
    source = services.get_assessment(first["id"], assessment["id"])["files"][0]
    fixture = {"status": "completed", "quality": {"accepted": True}, "features": {"cadence_proxy": 60},
               "landmark_frames": [{"synthetic": True}], "task": "gait", "analysis_version": "synthetic-test-only"}
    monkeypatch.setattr("ml.vision.pipeline.analyze_video", lambda path, task: fixture)
    result = AuthorizedTools(first["id"]).run_gait_analysis(UUID(assessment["id"]), UUID(source["id"]))
    assert "landmark_frames" not in result
    assert result["features"]["cadence_proxy"] == 60
    assert services.get_assessment(first["id"], assessment["id"])["module_file_ids"]["gait"] == source["id"]


def test_mcp_local_http_requires_token_and_exposes_typed_tools(mcp_accounts, monkeypatch):
    from backend.mcp_tools import create_server
    from mcp import types
    from starlette.testclient import TestClient
    first, _ = mcp_accounts
    monkeypatch.setenv("PARKINSENSE_MCP_ACTOR_ID", first["id"])
    monkeypatch.setenv("PARKINSENSE_MCP_TOKEN", "test-fixture-random-bearer-token-123456789")
    server = create_server()
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8766") as client:
        headers = {"accept": "application/json, text/event-stream"}
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": types.LATEST_PROTOCOL_VERSION,
                   "capabilities": {}, "clientInfo": {"name": "synthetic-test-client", "version": "1"}}}
        assert client.post("/mcp", json=request, headers=headers).status_code == 401
        headers["authorization"] = "Bearer wrong-token"
        assert client.post("/mcp", json=request, headers=headers).status_code == 401
        headers["authorization"] = "Bearer test-fixture-random-bearer-token-123456789"
        initialized = client.post("/mcp", json=request, headers=headers)
        assert initialized.status_code == 200
        headers["mcp-session-id"] = initialized.headers["mcp-session-id"]
        listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers)
        assert listed.status_code == 200
        assert "run_audio_analysis" in listed.text
        assert "actor_id" not in listed.text
