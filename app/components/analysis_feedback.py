"""Reusable analysis attempt feedback and printable patient report downloads."""

import hashlib

import streamlit as st

from .design import section_header, status_pill
from .private_access import private_download


def failure_result(error, task, *, language="English"):
    """Retain canonical fault codes, never a raw exception or private path."""
    from ml.common.guidance import build_guidance
    guidance = build_guidance(task=task, error=error, language=language)
    return {
        "task": task,
        "status": "unavailable" if any(item["kind"] == "processing" for item in guidance) else "repeat",
        "quality": {"accepted": False,
                    "messages": [item["reason"] for item in guidance],
                    "issue_codes": [item["code"] for item in guidance]},
        "features": {}, "method": "recording-attempt-feedback-1.0",
    }


def _patient_name(user, assessment):
    if user["role"] == "patient":
        return user["full_name"]
    from backend import services
    patients = services.list_patients(user["id"])
    return next((patient.get("full_name", "") for patient in patients if patient["id"] == assessment["patient_id"]), "")


def attempt_report_panel(user, assessment, task, result, *, identity):
    """An unsaved/rejected recording can still receive an honest fault report."""
    from ml.inference.patient_report import build_patient_report, render_patient_report_html
    preview = {**assessment, "modules": {task: result}, "module_revisions": {},
               "report_type": "attempt_preview", "review_status": "pending",
               "review_note": None, "reviewed_by": None, "reviewed_at": None,
               "clinical_measurements": []}
    token = hashlib.sha256(str(identity).encode()).hexdigest()[:16]
    from .report_document import session_report_html
    patient_name = _patient_name(user, assessment)
    document = session_report_html(f"attempt_report_document_{token}",
        {"actor_id": user["id"], "preview": preview, "language": user["language"], "patient_name": patient_name},
        lambda: render_patient_report_html(build_patient_report(preview, language=user["language"]), patient_name=patient_name))
    with st.expander("Download this analysis report"):
        st.caption("This report describes this analysis attempt. An accepted result enters your saved visit report after you save it. Rejected recordings have quality feedback and steps to try again.")
        private_download("Download analysis report", document,
                         user=user, assessment_id=assessment["id"], file_name=f"parkinsense-{task}-analysis.html", mime="text/html", key=f"attempt_report_{token}")
        st.caption("Open the downloaded HTML report in a browser to read or print it, including Save as PDF. It contains private health information.")


def saved_report_panel(user, assessment, *, identity, expanded=False):
    """Read the authoritative current auto-report; reads never create reports."""
    from backend.services.reporting import get_patient_report
    from ml.inference.patient_report import render_patient_report_html
    row = get_patient_report(user["id"], assessment["id"])
    if row is None:
        return
    report = row["content"]
    token = hashlib.sha256(str(identity).encode()).hexdigest()[:16]
    with st.expander("Your automatic analysis report", expanded=expanded):
        section_header("Visit report", "Updated when a task is saved. Measurements, your responses and the care team's review keep their own sources.")
        status_pill("Generated from your saved analysis", "care")
        st.write(report.get("patient_summary", ""))
        if row.get("outdated"):
            st.warning("This report refers to an earlier version of the visit. Open Reports to update it before sharing.")
        private_download("Download patient report", render_patient_report_html(report, patient_name=_patient_name(user, assessment)),
                         user=user, assessment_id=assessment["id"], file_name="parkinsense-patient-report.html", mime="text/html", key=f"patient_report_{token}")
        st.caption("Open the HTML report in a browser to read or print it, including Save as PDF. Review the findings with your clinician.")
