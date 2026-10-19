"""The review UI must find a compatible older visit, not stop at a mismatch."""
from copy import deepcopy

import pytest

from app import views


@pytest.mark.parametrize("changed,value", [("method", "old"), ("language", "Urdu"), ("task", "turning")])
def test_review_uses_first_compatible_prior_visit(monkeypatch, changed, value):
    result = {"status": "accepted", "quality": {"accepted": True},
              "method": "current", "task": "gait", "language": "English"}
    incompatible = {**result, changed: value}
    matching = deepcopy(result)
    visits = [
        {"id": "present", "created_at": "2026-03-01", "status": "draft", "modules": {"gait": result}},
        {"id": "matching", "created_at": "2026-02-01", "status": "submitted", "modules": {"gait": matching}},
        {"id": "old", "created_at": "2026-01-01", "status": "submitted", "modules": {"gait": incompatible}},
    ]
    monkeypatch.setattr(views, "history", lambda pid: visits)
    assert views.baseline_for("gait", excluding="present") is matching
    visits.pop(1)
    assert views.baseline_for("gait", excluding="present") is None
