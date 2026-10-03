from __future__ import annotations

import math
from numbers import Real
from typing import Any


def numeric_features(result: dict[str, Any]) -> dict[str, float]:
    """Only accepted finite measurements may contribute to history or fusion."""
    quality = result.get("quality", {})
    if not isinstance(quality, dict):
        return {}
    if quality.get("accepted") is False or quality.get("decision") in {"REPEAT", "REJECT"}:
        return {}
    if result.get("status") not in {"accepted", "completed", "ACCEPT"}:
        return {}
    if not (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"):
        return {}
    return {
        str(key): float(value)
        for key, value in result.get("features", {}).items()
        if isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    }


def normalize_language(language: str) -> str:
    value = str(language).strip().lower().replace("_", " ")
    aliases = {"en": "english", "ur": "urdu", "ps": "pashto", "roman": "roman urdu"}
    value = aliases.get(value, value)
    if value not in {"english", "urdu", "pashto", "roman urdu", "mixed"}:
        raise ValueError("Choose English, Urdu, Roman Urdu, Pashto, or Mixed speech.")
    return value
