from uuid import uuid4

import pandas as pd
import pytest

from ml.common.tables import feature_table


def test_export_keeps_alignment_missing_modality_and_excludes_raw_prose(tmp_path):
    pid = str(uuid4())
    records = [
        {"id": str(uuid4()), "patient_id": pid, "created_at": "2026-10-02T10:00:00+00:00", "status": "completed", "modules": {
            "gait": {"status": "completed", "quality": {"decision": "ACCEPT"}, "analysis_version": "cv1", "features": {"cadence_proxy": 100.0}, "landmark_frames": ["private frames"]},
            "nlp": {"status": "accepted", "quality": {"accepted": True}, "method": "nlp1", "features": {"reported_count": 2}, "entities": [{"source_excerpt": "private patient text"}]}}},
        {"id": str(uuid4()), "patient_id": pid, "created_at": "2026-10-03T10:00:00+00:00", "status": "completed", "modules": {
            "gait": {"status": "repeat", "quality": {"decision": "REPEAT"}, "features": {"cadence_proxy": 0}},
            "adl": {"status": "accepted", "quality": {"accepted": True}, "method": "adl1", "features": {"mean": 1}}}},
        {"id": str(uuid4()), "patient_id": pid, "created_at": "2026-10-04T10:00:00+00:00", "status": "abandoned", "modules": {
            "gait": {"status": "accepted", "quality": {"accepted": True}, "features": {"cadence_proxy": 60}}}},
    ]
    table = feature_table(pid, records)
    assert len(table) == 2
    assert table.iloc[0]["gait__cadence_proxy"] == 100
    assert pd.isna(table.iloc[1]["gait__cadence_proxy"])
    assert "private" not in table.to_json()
    target = tmp_path / "features.parquet"
    table.to_parquet(target, index=False)
    restored = pd.read_parquet(target)
    assert restored.patient_id.tolist() == [pid, pid]
    assert str(restored.session_date.dt.tz) == "UTC"
    assert restored.assessment_id.tolist() == [records[0]["id"], records[1]["id"]]


def test_export_cannot_mix_patient_rows_or_include_quality_unknown():
    pid = str(uuid4())
    with pytest.raises(ValueError, match="authorized"):
        feature_table(pid, [{"patient_id": str(uuid4())}])
    unknown = {"patient_id": pid, "id": str(uuid4()), "created_at": "2026-10-03T10:00:00Z", "status": "completed", "modules": {
        "gait": {"status": "repeat", "features": {"x": 1}}}}
    assert feature_table(pid, [unknown]).empty
