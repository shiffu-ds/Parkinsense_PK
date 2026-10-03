"""Actual measurement studies, reference values and a native-unit 3D view."""

import plotly.graph_objects as go
import streamlit as st

from app.components.design import empty_state, section_header
from backend import services
from backend.services import validation as api


def validation_page():
    user = services.get_user(st.session_state.user_id)
    if user["role"] != "clinician":
        raise PermissionError("A clinician account is required.")
    section_header("Measurement validation", "Plan independent reference comparisons before collecting evidence. Camera and lighting coverage remain visible.")
    studies = api.list_studies(user["id"])
    patients = services.list_patients(user["id"])
    with st.expander("Create a validation protocol", expanded=not studies):
        if not patients:
            empty_state("No assigned patients", "An administrator can link patients to your care team. A saved, accepted task provides exact metric definitions for the protocol.")
        else:
            patient = st.selectbox("Protocol source patient", patients, format_func=lambda p: p["full_name"], key="validation_source_patient")
            visits = services.list_assessments(user["id"], patient_id=patient["id"])
            if visits:
                visit = st.selectbox("Source visit", visits, format_func=lambda v: v["created_at"], key="validation_source_visit")
                options = api.source_options(user["id"], visit["id"])
                if options:
                    source = st.selectbox("Defined measurement", options,
                                          format_func=lambda m: f"{m['task']} · {m['metric']} · {m['unit']}")
                    st.caption(f"Extractor: {source['method_version']}. Reference must measure this exact quantity and unit; a clinical score is not a substitute.")
                    with st.form("validation_protocol"):
                        name = st.text_input("Study name", max_chars=160)
                        reference_method = st.text_input("Independent reference method", max_chars=120)
                        n = st.number_input("Planned independent participants", 3, 10000, 30)
                        tolerance = st.number_input("Prespecified maximum MAE (native units)", min_value=0.0, value=0.0,
                                                    help="Set with an independent domain expert; zero is not a recommended clinical threshold.")
                        notes = st.text_area("Protocol: sampling, reference procedure, camera/lighting coverage and matched repeat procedure", max_chars=4000)
                        agreed = st.checkbox("I have independently defined the reference procedure and tolerance before adding study cases.")
                        submit = st.form_submit_button("Create protocol")
                    if submit:
                        if not agreed:
                            st.error("Prespecify the protocol before creating the study.")
                        else:
                            api.create_study(user["id"], name, **{k: source[k] for k in ("task", "metric", "unit", "method_version")},
                                             reference_method=reference_method, minimum_participants=n,
                                             tolerance_mae=tolerance, protocol_notes=notes)
                            st.rerun()
                else:
                    st.info("Save a movement or audio measurement with a defined unit to create a study.")
            else:
                st.info("No saved visits yet.")
    if not studies:
        st.info("No validation evidence yet. Real recordings and independently obtained reference measurements are required.")
        return
    study = st.selectbox("Validation study", studies, format_func=lambda s: s["name"])
    current = api.study_evidence(user["id"], study["id"])
    protocol = study["protocol"]
    st.caption(f"{protocol['task']} · {protocol['metric']} · {protocol['unit']} · {protocol['method_version']}")
    with st.expander("Prespecified protocol"):
        st.write(protocol["notes"])
        st.write(f"Reference: {protocol['reference_method']} · Planned N: {protocol['minimum_participants']} · MAE tolerance: {protocol['tolerance_mae']} {protocol['unit']}")
        st.caption("Protocols are immutable. A different extractor, threshold or reference procedure requires a new study.")
    if patients:
        patient = st.selectbox("Study patient", patients, format_func=lambda p: p["full_name"])
        if st.button("Invite patient to validation"):
            api.invite_patient(user["id"], study["id"], patient["id"])
            st.success("Invitation saved. The patient must choose participation in Data & privacy.")
        visits = services.list_assessments(user["id"], patient_id=patient["id"])
        with st.expander("Add an actual saved recording comparison"):
            if visits:
                visit = st.selectbox("Comparison visit", visits, format_func=lambda v: v["created_at"])
                with st.form("validation_case"):
                    has_reference = st.checkbox("Independent reference is available")
                    reference = st.number_input(f"Reference value ({protocol['unit']})", value=0.0)
                    blinded = st.selectbox("Reference evaluator blinded to app result?", ["Unknown", "Yes", "No"])
                    device = st.text_input("Camera/device family", value="unknown", max_chars=120)
                    lighting = st.selectbox("Lighting condition", ["unknown", "even indoor", "low light", "backlit", "daylight"])
                    site = st.text_input("Site code (no personal identifiers)", value="unknown", max_chars=120)
                    age = st.selectbox("Age band", ["unknown", "under 40", "40–59", "60–79", "80+"])
                    repeat = st.text_input("Matched repeat group (empty if not a controlled repeat)", max_chars=120)
                    st.caption("The measured value comes from the saved task. Use a new visit per recording. Reference entries are immutable: check them before saving.")
                    submit = st.form_submit_button("Save comparison")
                if submit:
                    api.record_case(user["id"], study["id"], visit["id"], reference=reference if has_reference else None,
                                    reference_blinded={"Unknown": None, "Yes": True, "No": False}[blinded],
                                    device_family=device, lighting=lighting, site=site, age_band=age, repeat_group=repeat)
                    st.rerun()
            else:
                st.info("This patient has no saved visits.")
    evidence = current["evidence"]
    st.caption(evidence["coverage_scope"])
    st.caption(evidence["split_scope"])
    if not evidence["metrics"]:
        empty_state("Awaiting real study evidence", "No active, consented comparison recordings are available. Missing accuracy is not zero error.")
        return
    summary = evidence["metrics"][0]
    accuracy = summary["accuracy"]
    cards = st.columns(3)
    cards[0].metric("Independent paired participants", accuracy["paired_participants"])
    cards[1].metric("Mean absolute error", "Unknown" if accuracy["mae"] is None else f"{accuracy['mae']:.3g} {summary['unit']}")
    repeatability = summary["repeatability"]
    cards[2].metric("Matched repeat participants", repeatability["participants"])
    st.write({"bias": accuracy["bias"], "rmse": accuracy["rmse"], "participant MAE 95% interval": accuracy["mae_ci95"],
              "within-participant SD": repeatability["within_participant_sd"], "planned targets": summary["target"]})
    st.caption(repeatability["assumption"])
    paired = [c for c in current["cases"] if c["reference"] is not None]
    if paired:
        unit = summary["unit"]
        fig = go.Figure(go.Scatter3d(x=[c["reference"] for c in paired], y=[c["measured"] for c in paired],
            z=[c["measured"] - c["reference"] for c in paired], mode="markers",
            marker={"size": 6, "color": "#79d6c1"}, hovertemplate="Reference %{x:.3g}<br>Measured %{y:.3g}<br>Error %{z:.3g}<extra></extra>"))
        fig.update_layout(height=410, margin={"l": 0, "r": 0, "b": 0, "t": 10},
                          scene={"xaxis_title": f"Reference ({unit})", "yaxis_title": f"Measured ({unit})",
                                 "zaxis_title": f"Error ({unit})"}, uirevision=study["id"])
        st.plotly_chart(fig, width="stretch", key="validation_actual_3d")
    for field, rows in summary["strata"].items():
        with st.expander(f"Coverage by {field.replace('_', ' ')}"):
            st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("App comparisons support measurement research. They do not establish a medical diagnosis, regulatory approval, representative coverage or clinical readiness.")


def validation_participation_panel(user):
    language = user.get("language", "English")
    urdu, roman = language == "Urdu", language == "Roman Urdu"
    title = "پیمائش کی جانچ میں شرکت" if urdu else "Measurement validation mein shirkat" if roman else "Measurement validation participation"
    with st.expander(title):
        st.write("یہ اختیاری شرکت ہے۔ آپ کی محفوظ پیمائشوں کا آزاد حوالہ سے موازنہ کیا جائے گا۔ آپ کسی وقت شرکت ختم کر سکتے ہیں؛ عام نگہداشت کی رضامندی الگ ہے۔" if urdu else
                 "Ye ikhtiari shirkat hai. Aap ki saved measurements ka independent reference se muqabla hoga. Aap kisi waqt shirkat khatam kar sakte hain; aam care ki razamandi alag hai." if roman else
                 "Participation is optional. Saved measurements will be compared with independent references. You may withdraw at any time; monitoring consent is separate.")
        for item in api.patient_invitations(user["id"]):
            st.write(item["name"])
            st.caption(item["protocol"]["reference_method"])
            label = ("شرکت ختم کریں" if urdu else "Shirkat khatam karein" if roman else "Withdraw participation") if item["active"] else (
                "اس مطالعے میں شرکت قبول کریں" if urdu else "Is study mein shirkat qabool karein" if roman else "Agree to this study")
            if item["withdrawn"]:
                st.caption("اس مطالعے میں شرکت ختم ہو چکی ہے۔" if urdu else "Is study mein shirkat khatam ho chuki hai." if roman else "Participation was withdrawn for this study.")
            if st.button(label, key="validation_consent_" + item["id"], disabled=item["withdrawn"] or (not item["active"] and not item["eligible"])):
                api.choose_participation(user["id"], item["id"], agree=not item["active"])
                st.rerun()
