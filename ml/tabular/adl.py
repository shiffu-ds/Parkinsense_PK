from __future__ import annotations

from typing import Any

ADL_ITEMS = {
    "dressing": "Dressing", "feeding": "Feeding", "grooming": "Grooming",
    "bathing": "Bathing", "writing": "Writing", "phone_use": "Phone use",
    "walking": "Walking", "transfers": "Transfers", "household_activities": "Household activities",
}
ADL_SCALE = {0: "No difficulty", 1: "Slight difficulty", 2: "Moderate difficulty",
             3: "A lot of difficulty", 4: "Unable without help"}


def analyze_adl(responses: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(responses, dict):
        raise ValueError("ADL responses must be an object.")
    if set(responses) - set(ADL_ITEMS) - {"other_difficulty"}:
        raise ValueError("Unknown ADL item supplied.")
    if set(ADL_ITEMS) - set(responses):
        raise ValueError("Complete all nine ADL items before submitting.")
    for name in ADL_ITEMS:
        value = responses[name]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
            raise ValueError(f"{ADL_ITEMS[name]} must be a whole number from 0 to 4.")
    other = responses.get("other_difficulty", "")
    if not isinstance(other, str) or len(other) > 2000:
        raise ValueError("Other daily-life difficulty must be text of at most 2,000 characters.")
    return {
        "status": "accepted", "task": "adl", "quality": {"accepted": True, "messages": ["All ADL items completed."]},
        "features": {**{f"adl_{name}_self_report": responses[name] for name in ADL_ITEMS},
                     "adl_self_report_mean": sum(responses[name] for name in ADL_ITEMS) / len(ADL_ITEMS)},
        "responses": {name: responses[name] for name in ADL_ITEMS},
        "other_difficulty": other.strip(), "method": "custom-adl-self-report-1.0",
        "scale": ADL_SCALE, "provenance": {"source": "patient_self_report", "instrument": "custom_unvalidated_0_to_4_questionnaire"},
        "limitations": ["This custom questionnaire is not a validated clinical scale.",
                        "The mean summarizes patient responses and does not estimate Parkinson severity."],
    }
