"""Patient analysis summaries made from saved measurements and explicit sources.

The builder is pure and also supports a rejected-attempt preview. HTML output is
fully escaped, printable, and does not load a script, font, or remote asset.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape, unescape
import math
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ml.common.results import numeric_features
from ml.inference.reports import build_report
from ml.multimodal.fusion import modality_for
from ml.tabular.adl import ADL_ITEMS, ADL_SCALE

VERSION = "patient-analysis-report-1.0"
AUTO_SUMMARY = "patient-analysis-summary"
_TITLES = {
    "gait": "Walking", "walking": "Walking", "turning": "Turning",
    "finger_left": "Left finger tapping", "finger_right": "Right finger tapping",
    "hand_open_close": "Hand opening and closing", "sit_to_stand": "Sit to stand",
    "reach": "Reaching", "grasp": "Grasping", "object_transfer": "Object transfer",
    "voice_vowel": "Sustained vowel", "voice_sentence": "Read sentence",
    "voice_natural": "Natural speech", "voice": "Voice recording",
    "nlp": "Daily-life description", "adl": "Daily activities questionnaire",
}


def _text(value: Any, limit: int = 6000) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _method(result: dict) -> Any:
    return result.get("method") or result.get("analysis_version") or (result.get("pipeline"), result.get("version"))


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _compatible_history(assessment: dict, history: list[dict]) -> list[dict]:
    """Select genuinely earlier matching tasks; skip changed-method references."""
    current = assessment.get("modules", {})
    current_date = _date(assessment.get("created_at"))
    compatible = []
    for earlier in history:
        if (assessment.get("id") and earlier.get("id") == assessment.get("id")) or earlier.get("status") == "abandoned":
            continue
        earlier_date = _date(earlier.get("created_at", earlier.get("session_date")))
        if current_date is not None and (earlier_date is None or earlier_date >= current_date):
            continue
        modules = {}
        for task, result in earlier.get("modules", {}).items():
            now = current.get(task)
            if not isinstance(result, dict) or not isinstance(now, dict):
                continue
            if not isinstance(result.get("features", {}), dict):
                continue
            if (_method(result) == _method(now) and result.get("task") == now.get("task")
                    and result.get("language") == now.get("language") and numeric_features(result)):
                modules[task] = result
        if modules:
            compatible.append({**earlier, "modules": modules})
    return compatible


def _measurement(result: dict, name: str, value: float, task: str, change: dict | None) -> dict:
    # Shared definitions deliberately omit unknown units rather than guessing.
    from ml.common.statistics import measurement_definition
    definition = measurement_definition(result, name, task) or {}
    definition = {key: unescape(value) if isinstance(value, str) else value for key, value in definition.items()}
    feature_metadata = result.get("feature_metadata", {})
    metadata = feature_metadata.get(name, {}) if isinstance(feature_metadata, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    item = {
        "name": name, "label": definition.get("label") or metadata.get("label") or name.replace("_", " ").capitalize(),
        "value": value, "unit": definition.get("unit") or metadata.get("unit") or "Not specified by this method",
        "source": definition.get("source") or ("patient_self_report" if modality_for(task) in {"text", "adl"} else "automated_measurement"),
        "reference": None, "delta": None, "percent_change": None,
    }
    if change:
        item.update(reference=change.get("baseline"), delta=change.get("delta"), percent_change=change.get("percent_change"))
    return item


def _quality(result: dict) -> dict:
    quality = result.get("quality", {})
    quality = quality if isinstance(quality, dict) else {}
    messages = []
    for key in ("messages", "issues", "warnings"):
        values = quality.get(key, [])
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str):
                    messages.append(value[:1000])
                elif isinstance(value, dict) and isinstance(value.get("message"), str):
                    messages.append(value["message"][:1000])
    descriptive_checks = {"rules_version", "task_confirmation", "task_completion", "speech_presence", "language_source", "transcript_verified"}
    checks = {key: value[:1000] if isinstance(value, str) else value for key, value in quality.items()
              if key not in {"messages", "issues", "warnings", "accepted", "decision"}
              and isinstance(value, (str, int, float, bool))
              and (not isinstance(value, str) or key in descriptive_checks)
              and (not isinstance(value, float) or math.isfinite(value))}
    accepted = (quality.get("accepted") is not False and quality.get("decision") not in {"REPEAT", "REJECT"}
                and (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"))
    return {"accepted": accepted,
            "decision": _text(quality.get("decision")) or ("Accepted" if quality.get("accepted") is True else "Not accepted"),
            "messages": list(dict.fromkeys(messages)), "checks": checks}


def build_patient_report(assessment: dict[str, Any], history: list[dict] | None = None,
                         language: str = "English") -> dict[str, Any]:
    """Build an auditable summary; a rejected result never supplies measurements.

    Use report_type='attempt_preview' for an unsaved recording or form attempt.
    Fault steps come only from the fixed catalogue. Known quality.issue_codes
    preserve classified faults without retaining private decoder exception text.
    Identity is added only by the authorized caller when rendering the document.
    """
    if not isinstance(assessment, dict) or not isinstance(assessment.get("modules", {}), dict):
        raise ValueError("Provide an assessment with structured module results.")
    modules = {}
    for task, result in assessment.get("modules", {}).items():
        if isinstance(result, dict):
            modules[task] = {**result,
                             "features": result.get("features") if isinstance(result.get("features"), dict) else {},
                             "feature_metadata": result.get("feature_metadata") if isinstance(result.get("feature_metadata"), dict) else {},
                             "review_flags": result.get("review_flags") if isinstance(result.get("review_flags"), list) else []}
    compatible = _compatible_history(assessment, history or [])
    summary = build_report(modules, compatible, language)
    sections = []
    from ml.common.guidance import build_guidance
    for task, result in modules.items():
        quality = _quality(result)
        accepted = result.get("status") in {"accepted", "completed", "ACCEPT"} and quality["accepted"]
        comparison = summary["baseline"]["modules"].get(task, {})
        changes = {item["feature"]: item for item in comparison.get("changes", [])}
        rows = [_measurement(result, name, value, task, changes.get(name))
                for name, value in numeric_features(result).items()]
        guidance = build_guidance(result, task, language=language)
        # Decoder exception messages can contain private filesystem paths. The
        # catalogue's fixed reasons describe the failure without copying them.
        quality["messages"] = (["Local input quality checks passed; clinical interpretation still requires review."] if accepted else
                               list(dict.fromkeys(item["reason"] for item in guidance)))
        responses = []
        if accepted and task == "adl":
            values = result.get("responses", {})
            for name, value in (values.items() if isinstance(values, dict) else []):
                if name in ADL_ITEMS and type(value) is int and value in ADL_SCALE:
                    responses.append({"name": name, "label": ADL_ITEMS[name], "value": value, "description": ADL_SCALE[value]})
        entities = []
        if accepted and modality_for(task) == "text":
            for entity in result.get("entities", []):
                if isinstance(entity, dict):
                    entities.append({key: _text(entity.get(key), 240) for key in ("activity", "status", "side", "time", "source_excerpt")})
        values = result.get("limitations", [])
        limitations = [_text(value, 1500) for value in values if isinstance(value, str)] if isinstance(values, list) else []
        sections.append({
            "task": task, "title": _TITLES.get(task, task.replace("_", " ").capitalize()),
            "modality": modality_for(task), "status": _text(result.get("status")) or "unavailable", "accepted": accepted,
            "method": _text(result.get("method") or result.get("analysis_version") or result.get("pipeline")) or "Not specified",
            "source": "Patient self-report" if modality_for(task) in {"text", "adl"} else "Local automated measurements",
            "quality": quality, "measurements": rows, "reference": comparison,
            "responses": responses, "reported_entities": entities,
            "patient_note": _text(result.get("other_difficulty")) if accepted and task == "adl" else "",
            "guidance": [item for item in guidance if isinstance(item, dict)], "limitations": limitations,
        })
    now = datetime.now(timezone.utc)
    summary["baseline"]["method"] = "first-compatible-earlier-task-reference-1.0"
    review = {
        "status": _text(assessment.get("review_status")) or "pending",
        "author_id": assessment.get("reviewed_by"), "author_name": _text(assessment.get("review_author_name"), 160),
        "reviewed_at": assessment.get("reviewed_at"), "note": _text(assessment.get("review_note"), 4000),
        "source": "human_clinician" if assessment.get("reviewed_by") else "not_reviewed",
    }
    prior_revisions = {earlier.get("id"): earlier.get("module_revisions", {}) for earlier in compatible}
    reference_revisions = {section["task"]: {"assessment_id": section["reference"]["baseline_assessment_id"],
                                            "revision": prior_revisions.get(section["reference"]["baseline_assessment_id"], {}).get(section["task"])}
                           for section in sections if section["reference"].get("status") == "compared"}
    return {**summary, "method": VERSION, "version": VERSION, "auto_summary": AUTO_SUMMARY,
            "report_type": _text(assessment.get("report_type")) or "patient_analysis",
            "accepted": any(section["accepted"] for section in sections),
            "generated_at": now.isoformat(), "generated_at_local": now.astimezone(ZoneInfo("Asia/Karachi")).strftime("%d %b %Y, %I:%M %p PKT"),
            "source_assessment_id": assessment.get("id"), "assessment_status": assessment.get("status", "draft"),
            "source_assessment_updated_at": assessment.get("updated_at"),
            "source_module_revisions": dict(assessment.get("module_revisions", {})),
            "source_reference_revisions": reference_revisions,
            "sections": sections, "clinician_review": review,
            "clinical_measurements": assessment.get("clinical_measurements", []),
            "coverage_note": "Missing modules were not analysed and have no measurement or score.",
            "comparison_note": "Differences show measured changes only. They do not establish improvement, deterioration, severity, or a cause.",
            "privacy": "Generated locally. No patient recording or report was sent to an external AI provider."}


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _number(value: Any, *, signed: bool = False) -> str:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        return "—"
    return format(value, "+.4g" if signed else ".4g")


def _list(items: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>" if items else ""


def _safe_source(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    url = source.get("url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        return ""
    if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f'<p class="source">Source: <a href="{_e(url)}" rel="noopener noreferrer">{_e(source.get("title") or parsed.netloc)}</a></p>'


def render_patient_report_html(content: dict, patient_name: str = "", clinician_name: str = "") -> str:
    """Return a standalone HTML document suitable for a local download and print."""
    sections = []
    for section in content.get("sections", []):
        rows = []
        for item in section.get("measurements", []):
            rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in (
                _e(item.get("label")), _number(item.get("value")), _e(item.get("unit")),
                _number(item.get("reference")), _number(item.get("delta"), signed=True))) + "</tr>")
        table = ('<table><thead><tr><th>Measurement</th><th>Current</th><th>Unit</th><th>Earlier reference</th><th>Difference</th></tr></thead><tbody>'
                 + "".join(rows) + "</tbody></table>") if rows else '<p class="muted">No accepted measurements are available for this attempt.</p>'
        reference = section.get("reference", {})
        if reference.get("status") == "compared":
            table += f'<p class="muted">Reference: first compatible earlier task, {_e(reference.get("baseline_date"))}. Recording conditions may affect differences.</p>'
        elif rows:
            table += '<p class="muted">No compatible earlier reference is available. Earlier values are left blank.</p>'
        responses = section.get("responses", [])
        response_block = ""
        if responses:
            response_block = '<h3>Your questionnaire answers</h3><table><thead><tr><th>Daily activity</th><th>Your answer</th></tr></thead><tbody>' + "".join(
                f'<tr><td>{_e(item.get("label"))}</td><td>{_e(item.get("value"))}/4 — {_e(item.get("description"))}</td></tr>' for item in responses) + "</tbody></table>"
        entity_block = ""
        if section.get("reported_entities"):
            entity_block = '<h3>What your description mentioned</h3><table><thead><tr><th>Activity</th><th>Rule result</th><th>Your words</th></tr></thead><tbody>' + "".join(
                f'<tr><td>{_e(item.get("activity"))}</td><td>{_e(item.get("status"))}</td><td>{_e(item.get("source_excerpt"))}</td></tr>' for item in section["reported_entities"]) + '</tbody></table><p class="muted">These are dictionary-rule readings of self-report. Confirm the wording with your clinician.</p>'
        guidance = ""
        for item in section.get("guidance", []):
            steps = item.get("steps", [])
            steps = steps if isinstance(steps, list) else []
            translation = f'<p class="muted">{_e(item["translation_note"])}</p>' if item.get("translation_note") else ""
            guidance += f'<div class="guidance"><h3>{_e(item.get("title"))}</h3><p>{_e(item.get("reason"))}</p><ol>' + "".join(f'<li>{_e(step)}</li>' for step in steps) + '</ol>' + translation + _safe_source(item.get("source")) + '</div>'
        note = f'<blockquote><strong>Your note:</strong> {_e(section["patient_note"])}</blockquote>' if section.get("patient_note") else ""
        checks = section.get("quality", {}).get("checks", {})
        check_block = '<h3>Recording and response checks</h3><table><tbody>' + "".join(
            f'<tr><td>{_e(name.replace("_", " ").capitalize())}</td><td>{_e(value)}</td></tr>' for name, value in checks.items()) + '</tbody></table>' if checks else ""
        status = "Accepted recording or response" if section.get("accepted") else "Repeat or review needed"
        sections.append(f'<section><div class="section-heading"><h2>{_e(section.get("title"))}</h2><span>{_e(status)}</span></div>'
                        f'<p class="muted">{_e(section.get("source"))} · Method: {_e(section.get("method"))}</p>'
                        + _list(section.get("quality", {}).get("messages", [])) + table + response_block + entity_block + note + guidance + check_block
                        + '<div class="limits">' + _list(section.get("limitations", [])) + '</div></section>')
    review = content.get("clinician_review", {})
    review_html = '<p>Awaiting clinician review.</p>'
    if review.get("source") == "human_clinician":
        author = review.get("author_name") or clinician_name or "Linked clinician"
        review_html = f'<p><strong>{_e(author)}</strong> · {_e(review.get("status", "reviewed").replace("_", " "))} · {_e(review.get("reviewed_at"))}</p>'
        if review.get("note"):
            review_html += f'<blockquote>{_e(review["note"])}</blockquote>'
    if content.get("clinical_measurements"):
        review_html += '<h3>Clinician-entered context</h3><table><thead><tr><th>Context</th><th>Value</th><th>Unit</th></tr></thead><tbody>' + "".join(
            f'<tr><td>{_e(item.get("name", "").replace("_", " ").capitalize())}</td><td>{_number(item.get("value"))}</td><td>{_e(item.get("unit") or "Not specified")}</td></tr>'
            for item in content["clinical_measurements"] if isinstance(item, dict)) + '</tbody></table><p class="muted">Entered by a clinician; these values were not inferred from the recording.</p>'
    available = content.get("fusion", {}).get("available_modalities", [])
    missing = content.get("fusion", {}).get("missing_modalities", [])
    title = "Recording quality report" if content.get("report_type") == "attempt_preview" and not content.get("accepted") else "Patient analysis report"
    identity = f'<p class="patient">{_e(patient_name)}</p>' if patient_name else ""
    preview_note = '<p class="meta"><strong>Unsaved analysis attempt preview</strong> · This attempt has not entered the saved assessment.</p>' if content.get("report_type") == "attempt_preview" else ""
    assessment_id = _e(content.get("source_assessment_id"))
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + _e(title) + '''</title><style>
        :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#edf1f1;color:#193234;font:15px/1.6 Arial,Helvetica,sans-serif}
        main{max-width:1000px;margin:32px auto;background:white;padding:46px 52px;border-top:7px solid #246765}
        header{border-bottom:1px solid #dbe4e3;padding-bottom:23px}.brand{font-size:13px;font-weight:700;letter-spacing:2px;color:#246765}
        h1{font-size:28px;line-height:1.2;margin:10px 0}h2{font-size:19px;margin:0}h3{font-size:15px;margin:17px 0 5px}
        .patient{font-size:19px;margin:8px 0}.muted,.source,.limits{color:#536b6d;font-size:12px}.meta{font-size:12px;color:#536b6d;margin:5px 0}
        .summary{padding:20px 24px;background:#edf5f4;margin:24px 0}.summary p{margin:0 0 8px}section{margin-top:27px;padding-top:24px;border-top:1px solid #dbe4e3}
        .section-heading{display:flex;gap:20px;align-items:center;justify-content:space-between}.section-heading span{font-size:11px;background:#edf5f4;padding:4px 9px;border-radius:3px}
        table{width:100%;border-collapse:collapse;margin:14px 0;font-size:12px}th{text-align:left;color:#315a5b;background:#f2f6f5;font-weight:600}td,th{padding:8px 10px;border-bottom:1px solid #dde6e5;vertical-align:top;overflow-wrap:anywhere}
        td:not(:first-child){font-variant-numeric:tabular-nums}tr{break-inside:avoid}ul,ol{padding-left:24px}li{margin:5px 0}
        .guidance{background:#fff9ed;border-left:3px solid #a47b3d;padding:4px 19px;margin:17px 0;break-inside:avoid}blockquote{margin:12px 0;padding:13px 18px;border-left:3px solid #73a5a2;background:#f4f7f6;white-space:pre-wrap}
        a{color:#246765;overflow-wrap:anywhere}footer{margin-top:28px;border-top:1px solid #dbe4e3;padding-top:18px;font-size:11px;color:#536b6d}
        @page{size:A4;margin:17mm}@media print{body{background:white;font-size:10pt}main{margin:0;padding:0;max-width:none;border-top-width:4px}h1{font-size:22pt}h2{break-after:avoid}table{font-size:8pt}header,.summary,footer{break-inside:avoid}.guidance{background:#fff}}
        </style></head><body><main><header><div class="brand">PARKINSENSE PK</div><h1>''' + _e(title) + '</h1>' + identity + preview_note + f'<p class="meta">Generated {_e(content.get("generated_at_local"))} · Assessment {_e(content.get("assessment_status"))}</p><p class="meta">Record {assessment_id}</p></header>' \
        + f'<div class="summary"><p>{_e(content.get("patient_summary"))}</p><p class="muted">Available: {_e(", ".join(available) or "none")}. Missing: {_e(", ".join(missing) or "none")}.</p><p class="muted">{_e(content.get("coverage_note"))}</p></div>' \
        + "".join(sections) + '<section><h2>Clinician review</h2>' + review_html + '</section>' \
        + '<footer><p>' + _e(content.get("comparison_note")) + '</p>' + _list(content.get("limitations", [])) \
        + '<p>' + _e(content.get("privacy")) + '</p><p>Open this file in your browser and use Print to save a PDF or print a copy.</p></footer></main></body></html>'
