"""Synthetic statistical and isolated consent/source fixtures, not clinical evidence."""

import json
import math
from pathlib import Path
import subprocess
import sys
import csv

import pytest
from streamlit.testing.v1 import AppTest

from backend import services as svc
from backend.db import configure_db, init_db
from backend.services import privacy
from backend.services import validation as api
from ml.validation.evaluation import evaluate


def row(person="p1", recording="r1", **changes):
    return {"participant_id": person, "recording_id": recording, "task": "gait", "metric": "duration_seconds",
            "unit": "seconds", "method_version": "fixture-v1", "split": "evaluation", "status": "accepted",
            "measured": 5.0, "reference": 4.0, "reference_method": "Independent frame timing",
            "reference_blinded": True, "device_family": "phone", "lighting": "even indoor", "site": "s1",
            "age_band": "60–79", "repeat_group": "", **changes}


def test_accuracy_balances_people_and_preserves_zero_and_negative_error():
    rows = [row("a", f"a{i}", measured=2, reference=0) for i in range(10)]
    rows.append(row("b", "b", measured=0, reference=10))
    summary = evaluate(rows)["metrics"][0]["accuracy"]
    assert summary["paired_recordings"] == 11 and summary["paired_participants"] == 2
    assert summary["mae"] == 6 and summary["bias"] == -4
    assert summary["rmse"] == pytest.approx(math.sqrt(52))
    assert summary["mae_ci95"] is None


def test_rejected_and_missing_references_remain_in_denominators():
    rows = [row(), row("p2", "r2", status="rejected", measured=None, reference=None),
            row("p3", "r3", status="unavailable", measured=None, reference=None),
            row("p4", "r4", reference=None, lighting="")]
    s = evaluate(rows)["metrics"][0]
    assert s["accuracy"]["attempts"] == 4 and s["accuracy"]["paired_recordings"] == 1
    assert s["accuracy"]["reference_missing"] == 1 and s["accuracy"]["rejected_attempts"] == 1
    assert any(g["group"] == "unknown" for g in s["strata"]["lighting"])


def test_matched_repeats_do_not_cross_camera_lighting_or_people():
    rows = [row("a", "a1", measured=2, repeat_group="session1"),
            row("a", "a2", measured=4, repeat_group="session1"),
            row("b", "b1", measured=100, repeat_group="session1"),
            row("a", "a3", measured=100, repeat_group="session1", lighting="low light")]
    repeat = evaluate(rows)["metrics"][0]["repeatability"]
    assert repeat["participants"] == 1 and repeat["matched_groups"] == 1
    assert repeat["within_participant_sd"] == pytest.approx(math.sqrt(2))
    assert repeat["repeatability_coefficient"] == pytest.approx(3.92)


def test_participant_bootstrap_is_deterministic_and_training_is_excluded():
    rows = [row(f"p{i}", f"r{i}", measured=i) for i in range(5)]
    rows.append(row("train", "t1", split="training", measured=999))
    first = evaluate(rows, tolerance=3, minimum_participants=10)
    assert first == evaluate(list(reversed(rows)), tolerance=3, minimum_participants=10)
    s = first["metrics"][0]
    assert s["accuracy"]["paired_participants"] == 5
    assert s["accuracy"]["mae_ci95"] is not None
    assert s["target"]["planned_sample_reached"] is False


@pytest.mark.parametrize("change", [{"measured": float("nan")}, {"measured": float("inf")}, {"measured": 1e308},
                                   {"measured": True}, {"status": "rejected"}, {"reference_method": ""},
                                   {"unit": "Unit not specified · duration"}, {"split": "test-ish"}])
def test_invalid_or_fabricated_measurement_rows_fail(change):
    with pytest.raises(ValueError):
        evaluate([row(**change)])


def test_duplicate_sources_and_participant_split_leakage_fail():
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate([row(), row()])
    with pytest.raises(ValueError, match="leakage"):
        evaluate([row(), row(recording="training", split="training")])


def test_distinct_units_methods_stay_separate_and_one_tolerance_cannot_span_them():
    rows = [row(), row("p2", "r2", unit="milliseconds", method_version="fixture-v2")]
    assert len(evaluate(rows)["metrics"]) == 2
    with pytest.raises(ValueError, match="one exact"):
        evaluate(rows, tolerance=2)
    assert evaluate([])["metrics"] == []


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    configure_db(f"sqlite:///{tmp_path / 'validation.sqlite'}", allow_sqlite=True)
    init_db()
    password = "fixture-password-only-123"
    admin = svc.bootstrap_admin("Fixture Admin", "admin@example.test", password)
    patient = svc.register_patient("Fixture Patient", "patient@example.test", password, consent=True)
    other = svc.register_patient("Other Fixture", "other@example.test", password, consent=True)
    clinician = svc.create_staff(admin["id"], "Fixture Clinician", "clinician@example.test", password)
    svc.link_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    return admin, patient, other, clinician


def study(clinician):
    return api.create_study(clinician["id"], "Fixture comparison", task="gait", metric="duration_seconds",
                            unit="seconds", method_version="fixture-v1", reference_method="Independent frame timing",
                            minimum_participants=3, tolerance_mae=1, protocol_notes="Synthetic fixture; not a real pilot.")


def source(patient, *, data=b"synthetic fixture recording", value=5, method="fixture-v1", media=True, analysis_version=False):
    visit = svc.create_assessment(patient["id"])
    key = svc.store_upload(patient["id"], visit["id"], "gait", "fixture.mp4", data) if media else None
    result = {"task": "gait", "method": method, "status": "accepted", "quality": {"accepted": True},
              "features": {"duration_seconds": value}, "feature_metadata": {"duration_seconds": {"unit": "seconds", "label": "Duration"}}}
    if analysis_version:
        result["analysis_version"] = result.pop("method")
    svc.save_module(patient["id"], visit["id"], "gait", result, media_path=key)
    svc.finish_assessment(patient["id"], visit["id"])
    return visit


def test_study_requires_patient_optin_and_actual_unique_recording(accounts):
    _, patient, other, clinician = accounts
    plan = study(clinician)
    visit = source(patient)
    with pytest.raises(PermissionError):
        api.record_case(clinician["id"], plan["id"], visit["id"], reference=4)
    invitation = api.invite_patient(clinician["id"], plan["id"], patient["patient_id"])
    with pytest.raises(PermissionError):
        api.choose_participation(clinician["id"], invitation, agree=True)
    with pytest.raises(PermissionError):
        api.choose_participation(other["id"], invitation, agree=True)
    api.choose_participation(patient["id"], invitation, agree=True)
    api.record_case(clinician["id"], plan["id"], visit["id"], reference=4, reference_blinded=True)
    current = api.study_evidence(clinician["id"], plan["id"])
    assert current["study"]["locked"]
    assert current["evidence"]["metrics"][0]["accuracy"]["mae"] == 1
    repeated = source(patient)
    with pytest.raises(ValueError, match="already included"):
        api.record_case(clinician["id"], plan["id"], repeated["id"], reference=4)
    no_media = source(patient, media=False)
    assert api.source_options(clinician["id"], no_media["id"]) == []
    with pytest.raises(ValueError, match="source recording"):
        api.record_case(clinician["id"], plan["id"], no_media["id"], reference=4)


def test_withdrawal_excludes_evidence_permanently_and_unlinked_read_fails(accounts):
    admin, patient, _, clinician = accounts
    plan = study(clinician)
    invitation = api.invite_patient(clinician["id"], plan["id"], patient["patient_id"])
    api.choose_participation(patient["id"], invitation, agree=True)
    visit = source(patient)
    api.record_case(clinician["id"], plan["id"], visit["id"], reference=None)
    api.choose_participation(patient["id"], invitation, agree=False)
    assert api.study_evidence(clinician["id"], plan["id"])["evidence"]["metrics"] == []
    with pytest.raises(PermissionError, match="final"):
        api.choose_participation(patient["id"], invitation, agree=True)
    svc.unlink_patient(admin["id"], patient["patient_id"], clinician["clinician_id"])
    assert api.patient_invitations(patient["id"])[0]["eligible"] is False


def test_real_movement_analysis_version_field_is_supported(accounts):
    _, patient, _, clinician = accounts
    plan = study(clinician)
    invite = api.invite_patient(clinician["id"], plan["id"], patient["patient_id"])
    api.choose_participation(patient["id"], invite, agree=True)
    visit = source(patient, analysis_version=True)
    assert api.source_options(clinician["id"], visit["id"])[0]["method_version"] == "fixture-v1"
    api.record_case(clinician["id"], plan["id"], visit["id"], reference=4)
    assert api.study_evidence(clinician["id"], plan["id"])["evidence"]["metrics"][0]["accuracy"]["mae"] == 1


def test_method_mismatch_inactive_and_unconsented_sources_fail(accounts):
    admin, patient, _, clinician = accounts
    plan = study(clinician)
    invitation = api.invite_patient(clinician["id"], plan["id"], patient["patient_id"])
    api.choose_participation(patient["id"], invitation, agree=True)
    visit = source(patient, method="changed-extractor")
    with pytest.raises(ValueError, match="method differs"):
        api.record_case(clinician["id"], plan["id"], visit["id"])
    privacy.set_monitoring_consent(patient["id"], acknowledged=False)
    with pytest.raises(PermissionError):
        api.record_case(clinician["id"], plan["id"], visit["id"])
    svc.set_user_active(admin["id"], patient["id"], False)
    with pytest.raises(PermissionError):
        api.invite_patient(clinician["id"], plan["id"], patient["patient_id"])


def test_empty_validation_dashboard_is_honest_and_has_no_fabricated_chart(accounts):
    _, _, _, clinician = accounts
    app = AppTest.from_string("from app.components.validation_review import validation_page\nvalidation_page()")
    app.session_state["user_id"] = clinician["id"]
    app.run()
    assert not app.exception
    assert not app.get("plotly_chart")
    assert any("No validation evidence" in e.value for e in app.info)


def test_json_output_contains_no_nan_or_patient_identifiers():
    result = evaluate([row()])
    encoded = json.dumps(result, allow_nan=False)
    assert "participant_id" not in encoded and "recording_id" not in encoded


def test_offline_cli_templates_and_exact_protocol_evaluation(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_recordings.py"
    manifest, protocol, output = (tmp_path / name for name in ("recordings.csv", "protocol.json", "evaluation.json"))
    created = subprocess.run([sys.executable, str(script), "--template", str(manifest), "--protocol-template", str(protocol)], capture_output=True, text=True)
    assert created.returncode == 0 and len(manifest.read_text().splitlines()) == 1
    plan = json.loads(protocol.read_text())
    plan.update(prespecified_at="2026-01-01T00:00:00+00:00", reference_procedure="Independent fixture timing",
                measurement={k: row()[k] for k in ("task", "metric", "unit", "method_version")},
                tolerance=2, minimum_participants=3)
    protocol.write_text(json.dumps(plan))
    with manifest.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row()))
        writer.writeheader()
        writer.writerow(row())
    command = [sys.executable, str(script), "--manifest", str(manifest), "--protocol", str(protocol), "--output", str(output), "--deidentified-consented"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(output.read_text())
    assert evidence["metrics"][0]["accuracy"]["mae"] == 1
    assert len(evidence["provenance"]["manifest_sha256"]) == 64
    assert output.stat().st_mode & 0o077 == 0
    # A saved evaluation is never silently overwritten.
    assert subprocess.run(command, capture_output=True).returncode != 0
    output.unlink()
    plan["measurement"]["unit"] = "milliseconds"
    protocol.write_text(json.dumps(plan))
    mismatch = subprocess.run(command, capture_output=True, text=True)
    assert mismatch.returncode != 0 and "differ" in mismatch.stderr
    assert not output.exists()
