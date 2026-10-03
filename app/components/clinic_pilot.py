"""Human-run clinic pilots and separately acknowledged patient participation."""

from datetime import date, timedelta
import json

import plotly.graph_objects as go
import streamlit as st

from app.components.design import empty_state, section_header, status_pill
from backend import services
from backend.services import pilot as api


def _error(exc):
    st.error(str(exc))


def _targets_fields(values, prefix):
    left, right = st.columns(2)
    result = {}
    with left:
        result["minimum_patients"] = st.number_input("Minimum participating patients", 1, 10000,
                                                    int(values["minimum_patients"]), key=prefix + "patients")
        result["minimum_review_pairs"] = st.number_input("Minimum comparable review pairs", 1, 10000,
                                                        int(values["minimum_review_pairs"]), key=prefix + "pairs")
        result["minimum_usability_responses"] = st.number_input("Minimum patient usability responses", 1, 10000,
                                                               int(values["minimum_usability_responses"]), key=prefix + "responses")
        result["minimum_usability_rating"] = st.number_input("Minimum median ease-of-use rating (1–5)", 1.0, 5.0,
                                                             float(values["minimum_usability_rating"]), step=0.5,
                                                             key=prefix + "rating")
    with right:
        for name, label in (("minimum_review_saving_fraction", "Target median review time saving (%)"),
                            ("minimum_completion_fraction", "Target completed / planned tasks (%)"),
                            ("minimum_usable_recording_fraction", "Target usable / all recordings (%)")):
            result[name] = st.number_input(label, 0.0, 100.0, float(values[name] * 100), step=5.0,
                                           key=prefix + name) / 100
    return result


def _pilot_form(actor_id, current=None):
    prefix = "pilot_create_" if current is None else "pilot_edit_" + current["id"]
    today = date.today()
    with st.form(prefix):
        name = st.text_input("Pilot name", value=current["name"] if current else "", max_chars=160)
        left, right = st.columns(2)
        with left:
            starts = st.date_input("Pilot start", value=date.fromisoformat(current["starts_on"]) if current else today)
        with right:
            ends = st.date_input("Pilot end", value=date.fromisoformat(current["ends_on"]) if current else today + timedelta(days=28))
        notes = st.text_area("Protocol notes", value=current["notes"] if current else "", max_chars=2000,
                             help="Define task list, support provided and comparable review procedure. Avoid patient identifiers.")
        st.caption("These feasibility targets are planning defaults, not validated clinical thresholds. Targets and dates freeze when the first outcome or review timer is recorded.")
        targets = _targets_fields(current["targets"] if current else api.DEFAULT_TARGETS, prefix)
        submit = st.form_submit_button("Save pilot plan" if current else "Create pilot", type="primary")
    if submit:
        try:
            if current:
                api.update_pilot_plan(actor_id, current["id"], name=name, starts_on=starts.isoformat(),
                                      ends_on=ends.isoformat(), targets=targets, notes=notes)
            else:
                created = api.create_pilot(actor_id, name, starts.isoformat(), ends.isoformat(), targets=targets, notes=notes)
                st.session_state["clinic_pilot_selected"] = created["id"]
            st.rerun()
        except (ValueError, PermissionError, LookupError) as exc:
            _error(exc)


def _actual_figure(rows, reviews=False):
    selected = [row for row in rows if row["baseline_review_seconds"] is not None and row["app_review_seconds"] is not None] if reviews else rows
    if not selected:
        return None
    if reviews:
        x = [row["baseline_review_seconds"] / 60 for row in selected]
        y = [row["app_review_seconds"] / 60 for row in selected]
        z = list(range(1, len(selected) + 1))
        labels = ("Baseline review (minutes)", "App review (minutes)", "Comparable pair order")
    else:
        x = [row["planned_tasks"] for row in selected]
        y = [row["attempted_tasks"] for row in selected]
        z = [row["completed_tasks"] for row in selected]
        labels = ("Planned tasks (count)", "Attempted tasks (count)", "Completed tasks (count)")
    figure = go.Figure(go.Scatter3d(x=x, y=y, z=z, mode="markers",
                                   marker={"size": 6, "color": "#85d4bf", "opacity": 0.9},
                                   text=[row["observed_on"] for row in selected],
                                   hovertemplate="Observed %{text}<br>" + labels[0] + ": %{x:.2f}<br>" +
                                   labels[1] + ": %{y:.2f}<br>" + labels[2] + ": %{z:.2f}<extra></extra>"))
    axes = {"backgroundcolor": "#172832", "gridcolor": "#38505b", "zerolinecolor": "#55717d",
            "showbackground": True}
    figure.update_layout(height=390, margin={"l": 0, "r": 0, "t": 5, "b": 0},
                         paper_bgcolor="#14212b", font={"color": "#dfece7"},
                         scene={"xaxis": dict(axes, title=labels[0]), "yaxis": dict(axes, title=labels[1]),
                                "zaxis": dict(axes, title=labels[2]), "aspectmode": "cube"},
                         uirevision="clinic-pilot-review" if reviews else "clinic-pilot-tasks")
    return figure


def _summary(current, actor_id):
    metrics = current["metrics"]
    cards = st.columns(4)
    cards[0].metric("Participating patients observed", metrics["observed_patients"])
    cards[1].metric("Completed / planned tasks", f"{metrics['completed_tasks']} / {metrics['planned_tasks']}",
                    help="Planned tasks include tasks never attempted. Attempted but incomplete tasks remain in the denominator.")
    cards[2].metric("Comparable review pairs", metrics["paired_reviews"])
    saving = metrics["median_minutes_saved"]
    cards[3].metric("Median review minutes saved", "Unknown" if saving is None else f"{saving:.2f}")
    st.caption(f"Coverage: {metrics['paired_review_patients']} patients with paired reviews; "
               f"{metrics['usability_responses']} usability responses from {metrics['usability_patients']} patients. "
               f"Recordings: {metrics['usable_recordings']} usable of {metrics['recording_attempts']} attempts. "
               "Unknown responses remain unknown; counts and manual durations are clinician reported, usability is patient reported.")
    st.dataframe([{"Feasibility target": key.replace("_", " ").title(), "Current result": value.replace("_", " ")}
                  for key, value in metrics["target_checks"].items()], hide_index=True, width="stretch")
    st.caption("A target stays unknown until its minimum patient and observation coverage is reached. Feasibility results do not establish medical accuracy or a willingness to pay across clinics.")
    if current["observations"]:
        left, right = st.columns(2)
        with left:
            st.markdown("**Observed task counts · 3D**")
            st.plotly_chart(_actual_figure(current["observations"]), theme=None, width="stretch",
                            key="pilot_task_plot_" + current["id"])
        with right:
            st.markdown("**Comparable review durations · 3D**")
            figure = _actual_figure(current["observations"], reviews=True)
            if figure is not None:
                st.plotly_chart(figure, theme=None, width="stretch", key="pilot_review_plot_" + current["id"])
            else:
                empty_state("No comparable review pair yet", "Record baseline and app review durations for the same authorized assessment.")
    else:
        empty_state("No pilot observations yet", "Invite assigned patients, wait for their separate acknowledgement, then record visits and unsuccessful attempts.")
    st.download_button("Download deidentified aggregate", json.dumps(api.export_pilot_aggregate(actor_id, current["id"]),
                                                                    indent=2, allow_nan=False),
                       file_name="clinic-pilot-aggregate.json", mime="application/json", key="pilot_export_" + current["id"])


def _review_input(current, patient_id, assessment_id, mode):
    label = "Baseline" if mode == "baseline" else "App"
    scope = current["id"] + "_" + patient_id + "_" + str(assessment_id) + "_" + mode
    timers = [row for row in current["timers"] if row["patient_id"] == patient_id and
              row["assessment_id"] == assessment_id and row["mode"] == mode and row["elapsed_seconds"] is not None]
    used = {row[f"{mode}_timer_id"] for row in current["observations"]}
    timers = [row for row in timers if row["id"] not in used]
    choices = ["Unknown", "Manually reported"] + (["Collected timer"] if timers else [])
    source = st.selectbox(label + " review duration source", choices, key="pilot_source_" + scope)
    if source == "Manually reported":
        seconds = st.number_input(label + " review duration (seconds)", 0.0, 14400.0, value=0.0,
                                  key="pilot_seconds_" + scope)
        return {f"{mode}_review_seconds": seconds}
    if source == "Collected timer":
        timer = st.selectbox(label + " collected timer", timers,
                             format_func=lambda row: f"{row['elapsed_seconds']:.1f} seconds · {row['started_at'][:19]}",
                             key="pilot_timer_choice_" + scope)
        return {f"{mode}_timer_id": timer["id"]}
    return {}


def _observations(current, actor_id):
    closed = current["status"] == "closed"
    st.caption("Task counts are observed visit counts: planned is agreed before the visit, attempted includes failures, completed means the patient finished the instructions. A usable recording passes the recording quality check; it does not establish measurement accuracy.")
    available = [row for row in services.list_patients(actor_id) if row["active"]]
    if available and not closed:
        with st.form("pilot_invitation_" + current["id"]):
            patient = st.selectbox("Assigned patient to invite", available, format_func=lambda row: row["full_name"])
            invite = st.form_submit_button("Invite to clinic pilot")
        if invite:
            try:
                api.invite_patient(actor_id, current["id"], patient["patient_id"])
                st.rerun()
            except (ValueError, PermissionError, LookupError) as exc:
                _error(exc)
    if current["enrollments"]:
        st.dataframe([{"Patient": row["patient_name"], "Separate participation": "Acknowledged" if row["acknowledged"] else "Awaiting patient"}
                      for row in current["enrollments"]], hide_index=True, width="stretch")
    participating = [row for row in current["enrollments"] if row["acknowledged"]]
    if not participating or closed:
        st.info("This pilot is closed." if closed else "Patients acknowledge pilot participation in My Care before observations can be recorded.")
        return
    person = st.selectbox("Participating patient", participating, format_func=lambda row: row["patient_name"],
                          key="pilot_patient_" + current["id"])
    visits = services.list_assessments(actor_id, person["patient_id"])
    visit = st.selectbox("Assessment for this observation", [None] + visits,
                         format_func=lambda row: "No assessment linked — task counts only" if row is None else
                         f"{row['created_at'][:16]} · {row['status']} · {row['id'][:8]}",
                         key="pilot_visit_" + current["id"])
    visit_id = visit["id"] if visit else None
    with st.expander("Collect review duration"):
        st.caption("Start immediately before reviewing this assessment and stop immediately afterward. The timer measures elapsed server time, including idle time; it cannot verify attention or review quality. Use a consistent baseline procedure and counterbalance review order.")
        mode = st.selectbox("Review mode", ("baseline", "app"), key="pilot_timer_mode_" + current["id"])
        running = next((row for row in current["timers"] if row["stopped_at"] is None), None)
        if running:
            st.caption("Review timer running since " + running["started_at"][:19])
            if st.button("Stop review timer", key="pilot_timer_stop_" + current["id"]):
                try:
                    timer = api.stop_review_timer(actor_id, current["id"], running["id"])
                    if timer["elapsed_seconds"] is None:
                        st.warning("This timer exceeded four hours or the server clock changed. Its duration is unusable.")
                    else:
                        st.rerun()
                except (ValueError, PermissionError, LookupError) as exc:
                    _error(exc)
        elif st.button("Start review timer", key="pilot_timer_start_" + current["id"], disabled=visit is None):
            try:
                api.start_review_timer(actor_id, current["id"], person["patient_id"], visit_id, mode=mode)
                st.rerun()
            except (ValueError, PermissionError, LookupError) as exc:
                _error(exc)
    # Source choices stay outside the form so their dependent controls update.
    left, right = st.columns(2)
    with left:
        baseline = _review_input(current, person["patient_id"], visit_id, "baseline")
    with right:
        app = _review_input(current, person["patient_id"], visit_id, "app")
    with st.form("pilot_observation_" + current["id"] + "_" + person["patient_id"] + "_" + str(visit_id)):
        observed_on = st.date_input("Observation date", value=date.today())
        left, right = st.columns(2)
        with left:
            planned = st.number_input("Tasks planned before visit", 1, 100, value=1)
            attempted = st.number_input("Tasks attempted (including failures)", 0, 100, value=0)
            completed = st.number_input("Tasks completed", 0, 100, value=0)
        with right:
            attempts = st.number_input("All recording attempts (including rejected recordings)", 0, 100, value=0)
            usable = st.number_input("Recordings accepted by quality check", 0, 100, value=0)
            device = st.selectbox("Recording device category", api.DEVICE_CATEGORIES, index=3)
        usability = st.selectbox("Patient-reported ease of use", [None, 1, 2, 3, 4, 5],
                                 format_func=lambda value: "Unknown / not asked" if value is None else
                                 {1: "1 · Very difficult", 2: "2 · Difficult", 3: "3 · Neutral", 4: "4 · Easy", 5: "5 · Very easy"}[value])
        help_needed = st.selectbox("Did the patient need help?", [None, True, False],
                                   format_func=lambda value: "Unknown / not observed" if value is None else ("Yes" if value else "No"))
        notes = st.text_area("Visit notes", max_chars=2000)
        submit = st.form_submit_button("Save pilot observation", type="primary")
    if submit:
        try:
            api.save_observation(actor_id, current["id"], person["patient_id"],
                                 {"assessment_id": visit_id, "observed_on": observed_on.isoformat(),
                                  "planned_tasks": planned, "attempted_tasks": attempted, "completed_tasks": completed,
                                  "recording_attempts": attempts, "usable_recordings": usable, "usability_rating": usability,
                                  "needed_help": help_needed, "device_category": device, "notes": notes} | baseline | app)
            st.rerun()
        except (ValueError, PermissionError, LookupError) as exc:
            _error(exc)


def _payments(current, actor_id):
    st.caption("Record the clinic's reported intention and respondent role. An intention is not a purchase, collected payment or confirmed market demand. Keep respondent names out of these records.")
    if current["payment_intents"]:
        st.dataframe([{key: row[key] for key in ("reported_on", "respondent_role", "intent", "amount", "currency", "period")}
                      for row in current["payment_intents"]], hide_index=True, width="stretch")
    if current["status"] == "closed":
        return
    with st.form("pilot_payment_" + current["id"]):
        role = st.selectbox("Payment discussion respondent role", api.RESPONDENT_ROLES)
        intent = st.selectbox("Reported payment intention", ("undecided", "yes", "no"))
        has_amount = st.checkbox("An amount was explicitly proposed")
        amount = st.number_input("Proposed amount", 0.0, 1e9, value=0.0)
        currency = st.selectbox("Currency", api.CURRENCIES)
        period = st.selectbox("Proposed payment period", api.PAYMENT_PERIODS)
        reported_on = st.date_input("Payment discussion date", value=date.today())
        notes = st.text_area("Payment discussion notes", max_chars=2000)
        submit = st.form_submit_button("Save reported payment intention")
    if submit:
        try:
            api.save_payment_intent(actor_id, current["id"], respondent_role=role, intent=intent,
                                    amount=amount if has_amount else None, currency=currency, period=period,
                                    reported_on=reported_on.isoformat(), notes=notes)
            st.rerun()
        except (ValueError, PermissionError, LookupError) as exc:
            _error(exc)


def clinic_pilot_page(actor=None):
    """Home supplies its authenticated actor; services recheck every operation."""
    actor = services.get_user((actor or {}).get("id") or st.session_state.get("user_id"))
    if actor["role"] != "clinician":
        st.error("Clinic pilots are available to clinicians.")
        return
    section_header("Clinic pilots", "Measure how the workflow performs in a real clinic: completed tasks, recording usability, comparable review time and reported payment intentions.", eyebrow="Feasibility evidence")
    with st.expander("Create a clinic pilot"):
        _pilot_form(actor["id"])
    records = api.list_pilots(actor["id"])
    if not records:
        empty_state("Plan your first pilot", "Define dates and success targets before gathering observations. No clinic outcomes have been collected by creating this page.")
        return
    options = {row["id"]: row for row in records}
    if st.session_state.get("clinic_pilot_selected") not in options:
        st.session_state["clinic_pilot_selected"] = records[0]["id"]
    pilot_id = st.selectbox("Clinic pilot", list(options), format_func=lambda value: options[value]["name"],
                            key="clinic_pilot_selected")
    current = api.get_pilot(actor["id"], pilot_id)
    status_pill(current["status"].title(), "care" if current["status"] == "active" else "waiting")
    st.caption(current["starts_on"] + " to " + current["ends_on"] + " · " +
               ("Plan frozen" if current["plan_locked_at"] else "Plan editable until the first outcome or timer"))
    overview, observations, payments, protocol = st.tabs(("Overview", "Patients & visits", "Payment intentions", "Protocol"))
    with overview:
        _summary(current, actor["id"])
    with observations:
        _observations(current, actor["id"])
    with payments:
        _payments(current, actor["id"])
    with protocol:
        st.json(current["targets"])
        if current["notes"]:
            st.write(current["notes"])
        if current["status"] == "draft" and current["plan_locked_at"] is None:
            with st.expander("Edit the pilot plan"):
                _pilot_form(actor["id"], current)
        st.markdown("1. Agree the tasks, support offered and baseline review procedure.\n2. Invite assigned patients and obtain their separate acknowledgement.\n3. Log every planned task and recording attempt, including unsuccessful ones.\n4. Collect comparable review durations and the patient's own usability response.\n5. Discuss payment intention with a clinic decision maker and record their role.\n6. Check coverage and missing data before deciding whether to extend the pilot.")
        if current["status"] != "closed":
            confirmed = st.checkbox("All available observations are recorded; finalize this pilot", key="pilot_finalize_" + pilot_id)
            if st.button("Close clinic pilot", disabled=not confirmed, key="pilot_close_" + pilot_id):
                try:
                    api.close_pilot(actor["id"], pilot_id)
                    st.rerun()
                except (ValueError, PermissionError, LookupError) as exc:
                    _error(exc)


def pilot_participation_panel(actor):
    """A patient's decision is separate from monitoring consent and task results."""
    if actor.get("role") != "patient":
        return
    invitations = api.list_patient_invitations(actor["id"])
    if not invitations:
        return
    roman = actor.get("language") in ("Roman Urdu", "Mixed")
    urdu = actor.get("language") == "Urdu"
    title = "Clinic pilot participation" if not (roman or urdu) else ("Clinic pilot mein shirkat" if roman else "کلینک پائلٹ میں شرکت")
    section_header(title, "The pilot records task completion, recording difficulties, ease of use and clinician review time. Participation is optional and separate from monitoring consent." if not (roman or urdu) else
                   ("Is pilot mein task completion, recording ki mushkil, istemal ki asani aur doctor ka review waqt record hota hai. Shirkat aap ki marzi se hai aur monitoring consent se alag hai." if roman else
                    "اس پائلٹ میں کام کی تکمیل، ریکارڈنگ کی مشکلات، استعمال میں آسانی اور ڈاکٹر کے جائزے کا وقت ریکارڈ ہوتا ہے۔ شرکت اختیاری ہے اور مانیٹرنگ کی رضامندی سے الگ ہے۔"))
    for row in invitations:
        with st.container(border=True):
            st.write(row["name"])
            st.caption(f"{row['starts_on']} — {row['ends_on']} · {row['consent_version']}")
            if row["withdrawn"]:
                st.info("Participation withdrawn." if not (roman or urdu) else ("Aap ki shirkat wapas le li gayi hai." if roman else "آپ کی شرکت واپس لے لی گئی ہے۔"))
                continue
            if row["acknowledged"]:
                st.caption("You have acknowledged this optional pilot. Withdrawing stops new observations and excludes your data from pilot dashboards; retained records follow the clinic's data handling policy." if not (roman or urdu) else
                           ("Aap ne is ikhtiyari pilot ke liye razamandi di hai. Wapas lene par naye observations band aur aap ka data pilot dashboard se hata diya jata hai; pehle records clinic ki data policy ke mutabiq rehte hain." if roman else
                            "آپ نے اس اختیاری پائلٹ کے لیے رضامندی دی ہے۔ واپس لینے پر نئے مشاہدات بند اور آپ کا ڈیٹا پائلٹ ڈیش بورڈ سے ہٹا دیا جاتا ہے؛ سابقہ ریکارڈ کلینک کی ڈیٹا پالیسی کے مطابق رہتے ہیں۔"))
                label = "Withdraw pilot participation" if not (roman or urdu) else ("Pilot se shirkat wapas lein" if roman else "پائلٹ سے شرکت واپس لیں")
                if st.button(label, key="pilot_withdraw_" + row["id"]):
                    api.withdraw_pilot_participation(actor["id"], row["id"])
                    st.rerun()
            elif not row["closed"]:
                label = "I choose to participate in this optional clinic pilot" if not (roman or urdu) else ("Main apni marzi se is clinic pilot mein shirkat chahta/chahti hun" if roman else "میں اپنی مرضی سے اس کلینک پائلٹ میں شرکت چاہتا/چاہتی ہوں")
                acknowledge = st.checkbox(label, key="pilot_ack_" + row["id"])
                label = "Acknowledge pilot participation" if not (roman or urdu) else ("Pilot ki shirkat ki razamandi dein" if roman else "پائلٹ کی شرکت کی رضامندی دیں")
                if st.button(label, key="pilot_join_" + row["id"], disabled=not acknowledge):
                    api.acknowledge_pilot_participation(actor["id"], row["id"], acknowledged=True)
                    st.rerun()
