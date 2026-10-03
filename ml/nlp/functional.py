"""Transparent multilingual self-report extraction; no unconfigured ASR/LLM."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from ml.common.results import normalize_language

VERSION = "functional-dictionary-1.0"
DOMAINS = {
    "dressing": ["dress", "dressing", "button", "buttons", "kapray", "kapre", "kapde", "buttoning", "کپڑے", "بٹن", "جامې", "کالي"],
    "feeding": ["eat", "eating", "feeding", "spoon", "khana", "کھانا", "چمچ", "خوړل", "خواړه"],
    "grooming": ["grooming", "comb", "shave", "brush", "kanghi", "کنگھی", "داڑھی", "غاښ", "ږیره"],
    "writing": ["write", "writing", "likhna", "likhne", "لکھ", "لکھنا", "لیکھ", "لیکلو"],
    "walking": ["walk", "walking", "chalna", "chalne", "چلنا", "چلنے", "چل", "ګرځېدل", "تګ"],
    "transfers": ["stand", "standing", "sit", "sitting", "chair", "uthna", "uthne", "اٹھنا", "اٹھنے", "کرسی", "کښیناستل", "پاڅېدل"],
    "freezing": ["freeze", "freezing", "stuck", "jamna", "قدم رک", "پاؤں جم", "پښې بند"],
    "falls": ["fall", "falls", "fell", "falling", "girna", "gir gaya", "gir gai", "گرنا", "گر گیا", "گر گئی", "لوېد", "لوید"],
    "fatigue": ["tired", "fatigue", "thakawat", "thakan", "تھکاوٹ", "تھکن", "ستړیا", "ستړی"],
    "hand_use": ["hand", "hands", "grip", "grasp", "haath", "hath", "ہاتھ", "گرفت", "لاس", "لاسونه"],
    "daily_life": ["daily", "household", "phone", "bath", "bathing", "rozmarra", "روزمرہ", "فون", "نہانا", "ورځني", "لمبل"],
}
DIFFICULTY = ["difficulty", "difficult", "trouble", "cannot", "can't", "unable", "problem", "hard", "mushkil", "dikkat", "مسئلہ", "مشکل", "نہیں کر", "ستونزه", "سخت"]
NEGATION = ["no", "never", "not", "without", "nahi", "nahin", "نہیں", "نشته", "نه لرم"]
SIDE = {"left": ["left", "baen", "bayen", "بائیں", "کیڼ"], "right": ["right", "daen", "dayen", "دائیں", "ښي"], "both": ["both", "dono", "دونوں", "دواړه"]}
SEVERITY = {"mild": ["mild", "slight", "halki", "ہلکی", "لږ"], "moderate": ["moderate", "darmiyani", "درمیانی", "منځنۍ"], "severe": ["severe", "very difficult", "bohat", "بہت", "شدید", "ډېر"]}
TIMES = {"morning": ["morning", "subah", "صبح", "سهار"], "evening": ["evening", "shaam", "شام", "ماښام"], "night": ["night", "raat", "رات", "شپه"], "today": ["today", "aaj", "آج", "نن"]}


def _contains(text: str, term: str) -> bool:
    if term.isascii():
        return bool(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text))
    return term in text


def _label(text: str, mapping: dict[str, list[str]]) -> str | None:
    matches = [key for key, terms in mapping.items() if any(_contains(text, word) for word in terms)]
    return matches[0] if len(matches) == 1 else None


def analyze_text(text: str, language: str = "english") -> dict[str, Any]:
    language = normalize_language(language)
    if not isinstance(text, str) or not 3 <= len(text.strip()) <= 5000:
        raise ValueError("Enter a reviewed transcript or self-report between 3 and 5,000 characters.")
    normalized = unicodedata.normalize("NFKC", text).lower().strip()
    # Contrast clauses limit the common 'no falls, but walking is difficult' error.
    clauses = [clause.strip() for clause in re.split(r"[.!?۔؛\n]|\b(?:but|however|lekin)\b|لیکن", normalized) if clause.strip()]
    entities: list[dict[str, Any]] = []
    for domain, words in DOMAINS.items():
        for clause in clauses:
            terms = [word for word in words if _contains(clause, word)]
            if not terms:
                continue
            # Negation remains lexical and can be ambiguous. Preserve that uncertainty.
            negated = any(_contains(clause, word) for word in NEGATION)
            inability = any(_contains(clause, word) for word in ["cannot", "can't", "unable", "نہیں کر"])
            difficulty = any(_contains(clause, word) for word in DIFFICULTY)
            if negated and not inability:
                status = "denied_or_negated"
            elif difficulty or domain in {"falls", "freezing", "fatigue"}:
                status = "reported_difficulty"
            else:
                status = "mentioned_only"
            entities.append({
                "activity": domain, "problem": terms[0], "status": status,
                "side": _label(clause, SIDE), "severity": _label(clause, SEVERITY),
                "time": _label(clause, TIMES), "source_excerpt": clause[:240],
                "confidence": 0.65 if status == "reported_difficulty" else 0.5,
                "confidence_type": "heuristic_rule_strength_not_calibrated_probability",
                "provenance": "patient_self_report_reviewed_transcript",
            })
            break
    difficulties = [entity["activity"] for entity in entities if entity["status"] == "reported_difficulty"]
    return {
        "status": "accepted", "task": "text", "language": language,
        "quality": {"accepted": True, "messages": ["Reviewed text analyzed with multilingual keyword rules."],
                    "language_source": "user_selected", "transcript_verified": "user_responsibility"},
        "features": {"reported_difficulty_domain_count": len(difficulties),
                     **{f"self_report_{domain}_difficulty": int(domain in difficulties) for domain in DOMAINS}},
        "entities": entities, "method": VERSION,
        "provenance": {"source": "manual_transcript_or_self_report", "language_detection": "not_performed", "extractor": "versioned_dictionary_rules"},
        "review_flags": [f"Self-reported {domain} needs clinician review." for domain in difficulties if domain in {"falls", "freezing"}],
        "limitations": ["Keyword rules can miss phrasing and misunderstand negation or mixed speech.",
                        "Findings are self-reports, not observed signs or validated clinical scores.",
                        "No reported keyword does not establish absence of difficulty."],
    }
