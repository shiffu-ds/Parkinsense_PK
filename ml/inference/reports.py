"""Deterministic auditable quality-to-report coordination; no external LLM."""
from __future__ import annotations

from typing import Any
import re

from ml.common.results import normalize_language, numeric_features
from ml.inference.evidence import ApprovedKnowledgeBase
from ml.multimodal import fuse_results
from ml.temporal import compare_to_baseline
from ml.xai import explain_measurements

VERSION = "deterministic-safe-report-1.0"


def _patient_summary(count: int, comparison_count: int, language: str) -> str:
    if language == "urdu":
        return (f"آپ کے {count} کاموں کے قابل استعمال نتائج محفوظ ہیں۔ {comparison_count} پیمائشوں کا آپ کے پہلے نتائج سے موازنہ کیا گیا ہے۔ "
                "یہ پیمائشیں تشخیص نہیں ہیں۔ نتائج اپنے معالج کے ساتھ دیکھیں۔")
    if language in {"roman urdu", "mixed"}:
        return (f"Aap ke {count} kaamon ke qabil-e-istemal nataij maujood hain. {comparison_count} paimaishon ka pehle nataij se muqabla hua. "
                "Yeh paimaishain tashkhees nahi hain. Nataij apne muaalij ke saath dekhein.")
    if language == "pashto":
        return (f"ستاسو د {count} کارونو د کارولو وړ پایلې شته. {comparison_count} اندازه ګانې له پخوانیو پایلو سره پرتله شوې دي. "
                "دا اندازه ګانې تشخیص نه دي. پایلې له خپل ډاکټر سره وګورئ.")
    return (f"Usable results are available for {count} tasks. {comparison_count} measurements were compared with your earlier results. "
            "These measurements are not a diagnosis. Review your results with your clinician.")


def build_report(task_results: dict[str, dict[str, Any]], history: list[dict[str, Any]] | None = None,
                 language: str = "english", knowledge_base: ApprovedKnowledgeBase | None = None) -> dict[str, Any]:
    language = normalize_language(language)
    history = history or []
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", task) for task in task_results):
        raise ValueError("Report task names must be safe module identifiers.")
    stages = []
    accepted = [task for task, result in task_results.items() if numeric_features(result)]
    rejected = [task for task in task_results if task not in accepted]
    stages.append({"stage": "quality", "status": "passed" if accepted else "no_usable_results", "accepted_tasks": accepted, "excluded_tasks": rejected})
    fusion = fuse_results(task_results)
    stages.append({"stage": "analysis", "status": fusion["status"], "method": "measured_feature_coverage", "clinical_prediction": False})
    baseline = compare_to_baseline(task_results, history)
    explanation = explain_measurements(baseline)
    stages.append({"stage": "history", "status": "completed", "method": baseline["method"], "history_assessments": len(history)})
    evidence = (knowledge_base or ApprovedKnowledgeBase()).retrieve(" ".join(accepted)) if accepted else []
    stages.append({"stage": "evidence", "status": "retrieved" if evidence else "no_approved_evidence", "document_ids": [item["id"] for item in evidence]})
    approved_flags = {"Self-reported falls needs clinician review.", "Self-reported freezing needs clinician review."}
    review_items = [flag for result in task_results.values() for flag in result.get("review_flags", []) if flag in approved_flags]
    if rejected:
        review_items.append("Repeat or review tasks excluded by quality checks: " + ", ".join(rejected) + ".")
    review_items.append("Clinical interpretation requires a qualified clinician; no validated prediction model is configured.")
    clinician = (f"Usable measurements: {len(accepted)} task(s). Available modalities: {', '.join(fusion['available_modalities']) or 'none'}. "
                 f"Missing modalities: {', '.join(fusion['missing_modalities']) or 'none'}. "
                 "No validated clinical score or probability is available. Measurement uncertainty has not been calibrated.")
    if explanation["changes"]:
        clinician += "\n" + "\n".join(item["description"] for item in explanation["changes"][:12])
    else:
        clinician += "\nNo comparable earlier accepted task measurements are available."
    patient = _patient_summary(len(accepted), len(explanation["changes"]), language)
    # Generated wording uses fixed templates and structured measurements only.
    # Raw transcripts/evidence excerpts are never interpolated as instructions.
    safety = {"status": "passed", "diagnosis_claims": False, "medication_instructions": False,
              "unsupported_clinical_scores": False, "unvalidated_prediction_disclosed": True,
              "raw_patient_media_to_external_provider": False, "method": "fixed_templates_structured_measurements"}
    stages.append({"stage": "safety", **safety})
    stages.append({"stage": "report", "status": "completed", "method": VERSION, "external_llm": False})
    return {"status": "generated", "method": VERSION, "version": VERSION, "language": language,
            "patient_summary": patient, "clinician_summary": clinician, "review_items": review_items,
            "fusion": fusion, "baseline": baseline, "explanation": explanation, "evidence": evidence,
            "uncertainty": fusion["uncertainty"], "safety": safety, "stages": stages,
            "limitations": ["This deterministic report is not a validated medical report or autonomous diagnosis.",
                            "Urdu, Roman Urdu and Pashto templates require clinician language review before clinical deployment.",
                            "No LLM, deep model, retrieval evidence or clinical prediction is invented when unavailable."]}
