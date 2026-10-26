"""Patient, clinician and administrator experiences over authorized services."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.components.design import (
    empty_state, inject_styles, next_step, plain_text, section_header, spiral_figure, status_pill, status_row,
    task_card, visit_progress,
)
from app.components.patient_language import (
    adl_choice, adl_label, camera_translations, configure_patient_language, hub_card, render_steps,
    resolved_language, task_label, text, voice_prompt, weekday_name, write_patient,
)
from backend import services
from app.components.private_access import begin_session, private_download, private_player

LANGUAGES = ["English", "Urdu", "Roman Urdu", "Pashto", "Mixed"]
LABELS = {
    "gait": "Walking / gait", "turning": "Turning",
    "finger_left": "Finger tapping — left", "finger_right": "Finger tapping — right",
    "hand_open_close": "Hand opening / closing", "sit_to_stand": "Sit-to-stand",
    "reach": "Functional reach", "grasp": "Grasp", "object_transfer": "Object transfer",
    "voice": "Voice", "nlp": "Daily-life description", "adl": "Daily activities",
    "voice_vowel": "Voice — sustained vowel", "voice_sentence": "Voice — fixed sentence",
    "voice_natural": "Voice — natural speech",
    "spiral_left": "Spiral drawing — left hand", "spiral_right": "Spiral drawing — right hand",
    "touch_tap_left": "Two-circle tapping — left hand", "touch_tap_right": "Two-circle tapping — right hand",
}
INSTRUCTIONS = {
    "gait": "Place the device on a stable stand with your full body visible. Walk along a clear, familiar route, turn safely, and return. Record 5–45 seconds. Use your usual mobility aid and assistance.",
    "turning": "Keep your full body in view. Make a comfortable turn with your usual support. Record 3–45 seconds. Stop if you feel unsteady.",
    "finger_left": "Show your left hand clearly. Tap your thumb and index finger together repeatedly at a comfortable pace for 5–45 seconds. Keep all fingers visible; avoid mirroring the recording.",
    "finger_right": "Show your right hand clearly. Tap your thumb and index finger together repeatedly at a comfortable pace for 5–45 seconds. Keep all fingers visible; avoid mirroring the recording.",
    "hand_open_close": "Keep one hand fully visible. Open and close it repeatedly at a comfortable pace for 5–45 seconds.",
    "sit_to_stand": "Use a stable chair and your usual assistance. Record from the side with your shoulders, hips, knees and ankles visible. Stand and sit only if safe for you. Record 3–45 seconds.",
    "reach": "Sit or stand comfortably. Keep your torso, hips, shoulders, elbows and wrists visible while you reach toward a nearby safe target and return. Record 3–45 seconds.",
    "grasp": "Place a safe everyday object within easy reach. Keep your hand visible while you grasp and release it. Record 3–45 seconds.",
    "object_transfer": "Move a light, safe object between nearby positions. Keep your hand visible throughout. Record 3–45 seconds.",
}


def style():
    inject_styles()


def clear_session():
    if st.session_state.get("user_id"):
        try:
            from backend.production import revoke_media_grants
            revoke_media_grants(st.session_state.user_id, session_key=st.session_state.get("media_session_key"))
            services.record_logout(st.session_state.user_id)
        except (ValueError, PermissionError):
            pass
    processor = st.session_state.get("live_processor")
    if processor is not None:
        try:
            processor.close()
        except Exception:
            pass
    for key in list(st.session_state):
        if key.startswith("capture_"):
            try:
                Path(st.session_state[key]).unlink(missing_ok=True)
            except OSError:
                pass
        del st.session_state[key]


def is_accepted(result):
    quality = result.get("quality", {})
    return (result.get("status") in {"accepted", "completed", "ACCEPT"}
            and isinstance(quality, dict)
            and quality.get("accepted") is not False
            and quality.get("decision") not in {"REPEAT", "REJECT"}
            and (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"))


def go(page):
    st.switch_page(st.Page(page))


def actor():
    user = services.get_user(st.session_state["user_id"])
    if "auth_revision" in st.session_state:
        from backend.production import verify_session_revision
        verify_session_revision(user["id"], st.session_state.auth_revision)
    if not user.get("active"):
        raise PermissionError("This account is inactive.")
    return user


def _ui_language(user=None):
    """Patient-facing copy follows the saved profile, while staff UI stays English."""
    user = user or actor()
    return resolved_language(user.get("language", "English")) if user["role"] == "patient" else "English"


def _patient_surface(user=None):
    user = user or actor()
    language = user.get("language", "English") if user["role"] == "patient" else "English"
    return configure_patient_language(language)


def time_label(value):
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo("UTC"))
        return moment.astimezone(ZoneInfo("Asia/Karachi")).strftime("%d %b %Y, %I:%M %p PKT")
    except ValueError:
        return str(value)


def auth_page():
    intro, art = st.columns([1.3, 1], gap="large")
    with art:
        spiral_figure("The spiral is one of the oldest bedside checks for tremor. ParkinSense keeps to that idea: "
                      "short, repeatable tasks you can record at home and review with your clinician.")
        with st.container(border=True):
            st.subheader("Pehli dafa istemal kar rahe hain?")
            st.write("Pehle public example par tareeqa dekhein: **recording chunein, Analyze karein, phir graphs aur report kholein**.")
            if st.button("Try a public demo — bina login", key="open_public_demo", type="primary"):
                from app.components.public_demo import public_demo_page
                st.switch_page(st.Page(public_demo_page, title="Try a public demo", url_path="public-demo"))
            st.caption("Apni recording ke liye login karein, phir Start Assessment mein movement task aur Upload ya Live Camera chunein.")
    with intro:
        st.title("Movement, with everyday life in view")
        st.markdown('<p class="ps-lede">Record a task, tell your care team how the day felt, and come back to your progress when you are ready.</p>',
                    unsafe_allow_html=True)
        _auth_forms()
    st.caption("A local workspace for patient recordings and clinician review. Measurement summaries support discussion; "
               "diagnosis and treatment decisions belong with your clinician.")
    _recovery_form()


def _auth_forms():
    login, register = st.tabs(["Log in", "Register"])
    with login, st.form("login"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.form_submit_button("Log in", type="primary"):
            try:
                user = services.authenticate(email, password)
                if not user:
                    raise ValueError("Email or password is incorrect.")
                begin_session(user)
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
    with register:
        st.write("Create a patient account. Care team and administrator accounts are managed by an administrator.")
        with st.form("register"):
            full_name = st.text_input("Full name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password (at least 10 characters)", type="password", key="register_password")
            confirm = st.text_input("Confirm password", type="password")
            language = st.selectbox("Preferred language", LANGUAGES)
            consent = st.checkbox("I consent to storing my assessment recordings and responses for functional monitoring and review by my assigned care team.")
            if st.form_submit_button("Create patient account", type="primary"):
                try:
                    if password != confirm:
                        raise ValueError("Passwords do not match.")
                    user = services.register_patient(full_name, email, password, language, consent)
                    begin_session(user)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def _recovery_form():
    with st.expander("Account recovery / Account wapas hasil karein / اکاؤنٹ کی بحالی"):
        st.write("Contact your workspace administrator through your usual trusted channel. After verifying your identity, they can give you a temporary recovery code. This app does not send recovery emails automatically.")
        with st.form("account_recovery"):
            token = st.text_input("Temporary recovery code", type="password", max_chars=200)
            new_password = st.text_input("New password (at least 10 characters)", type="password")
            confirm_recovery = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Reset password"):
                try:
                    if new_password != confirm_recovery:
                        raise ValueError("Passwords do not match.")
                    from backend.production import redeem_recovery_token
                    import secrets
                    if "recovery_request_key" not in st.session_state:
                        st.session_state.recovery_request_key = secrets.token_urlsafe(32)
                    redeem_recovery_token(token, new_password, request_key=st.session_state.recovery_request_key)
                    st.success("Password updated. Sign in with your new password; previous sessions are no longer valid.")
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))


def patient_id():
    user = actor()
    if user["role"] == "patient":
        return user["patient_id"]
    if user["role"] != "clinician":
        raise PermissionError("Patient information is restricted to the patient and assigned care team.")
    patients = services.list_patients(user["id"])
    if not patients:
        st.info("No patients are assigned to you yet. An administrator can link patient accounts to your care team.")
        st.stop()
    options = {p["id"]: p.get("full_name", p.get("name", p["id"])) for p in patients}
    selected = st.selectbox("Patient", list(options), format_func=options.get, key="care_patient")
    return selected


def history(pid=None):
    return services.list_assessments(actor()["id"], patient_id=pid or patient_id())


def active_assessment():
    aid = st.session_state.get("active_assessment_id")
    if aid:
        item = services.get_assessment(actor()["id"], aid)
        if item["status"] not in {"completed", "abandoned"}:
            return item
    language = _ui_language()
    st.info(text("need_assessment", language))
    if st.button(text("open_hub", language)):
        go(assessment_hub)
    st.stop()


TASK_GROUPS = {
    "gait": ["gait", "turning"], "hand": ["finger_left", "finger_right", "hand_open_close"],
    "transfer": ["sit_to_stand"], "reach": ["reach", "grasp", "object_transfer"],
    "voice": ["voice_vowel", "voice_sentence", "voice_natural", "nlp"], "adl": ["adl"],
    "touch": ["spiral_left", "spiral_right", "touch_tap_left", "touch_tap_right"],
}


def groups_saved(item):
    modules = item.get("modules", {})
    return sum(any(task in modules for task in tasks) for tasks in TASK_GROUPS.values())


def _date_only(value):
    # Directional isolates keep "21 Oct 2026" in order inside Urdu sentences.
    return "\u2066" + time_label(value).split(",")[0] + "\u2069" if value else "—"


# A finished review is pointed out on Home for this long; after that the next
# step goes back to starting a visit instead of repeating an old review forever.
REVIEW_NOTICE_DAYS = 14


def fresh_review(items, now=None):
    """The latest completed visit, if its clinician review is recent; otherwise None."""
    latest = next((i for i in items if i["status"] == "completed"), None)
    if not latest or latest.get("review_status") != "reviewed" or not latest.get("reviewed_at"):
        return None
    reviewed_at = datetime.fromisoformat(latest["reviewed_at"])
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
    return latest if (now or datetime.now(timezone.utc)) - reviewed_at <= timedelta(days=REVIEW_NOTICE_DAYS) else None


def planned_review_date(plans, today):
    """Review date from the newest follow-up note that sets one, if it is still ahead (ISO dates)."""
    planned = next((p["next_review_date"] for p in plans if p.get("next_review_date")), None)
    return planned if planned and planned >= today else None


def todays_plan(user_id, items):
    """(plan, groups planned for today, those not yet saved in a visit started today)."""
    from backend.services import task_plan
    try:
        plan = task_plan.get_task_plan(user_id)
    except (PermissionError, ValueError, LookupError):
        return None, [], []
    local = ZoneInfo("Asia/Karachi")
    today = datetime.now(local).date()
    planned = task_plan.planned_on(plan, today.weekday())
    done = set()
    for item in items:
        if item.get("created_at") and datetime.fromisoformat(item["created_at"]).astimezone(local).date() == today:
            done |= {group for group, tasks in TASK_GROUPS.items() if any(task in item.get("modules", {}) for task in tasks)}
    return plan, planned, [group for group in planned if group not in done]


def _medicine_prompt(user, language):
    """After a usual medicine time, ask once how it is working; one tap answers."""
    from backend.services import medication_diary
    from app.components.diary_panel import clock, quick_entry
    try:
        times = medication_diary.get_medicine_times(user["id"])
        due = medication_diary.due_medicine_time(times, medication_diary.list_diary(user["id"], days=1)) if times else None
    except (PermissionError, ValueError):
        due = None
    if due:
        next_step(text("next_diary", language, time=clock(due)), text("next_diary_detail", language), "waiting")
        quick_entry(user, language, key="home_diary")
    elif notice := st.session_state.pop("home_diary_notice", None):
        st.success(text("diary_saved", language, time=clock(datetime.fromisoformat(notice).astimezone(ZoneInfo("Asia/Karachi")).strftime("%H:%M"))))


def patient_home():
    from backend.services import care
    user = actor()
    language = _patient_surface(user)
    st.title(text("welcome", language, name=user['full_name']))
    write_patient(text("home_intro", language), language)
    items = history()
    unfinished = [i for i in items if i["status"] == "draft"]
    try:
        checkins = care.list_checkins(user["id"], limit=1)
        plans = care.list_care_plans(user["id"])
    except (PermissionError, ValueError):
        checkins, plans = [], []
    today = datetime.now(ZoneInfo("Asia/Karachi")).date().isoformat()
    checked_today = bool(checkins) and checkins[0]["date"] == today
    reviewed = fresh_review(items)
    _medicine_prompt(user, language)
    weekly, _planned_groups, pending = todays_plan(user["id"], items)
    target = assessment_hub
    if unfinished:
        visit = unfinished[0]
        next_step(text("next_resume", language, date=_date_only(visit["created_at"])),
                  text("next_resume_detail", language, done=groups_saved(visit), total=len(TASK_GROUPS)), "waiting")
    elif pending:
        next_step(text("plan_today", language, tasks=", ".join(hub_card(group, language)[0] for group in pending)),
                  text("plan_today_detail", language))
    elif not checked_today:
        next_step(text("next_checkin", language), text("next_checkin_detail", language))
        target = my_care_page
    elif reviewed:
        next_step(text("next_reviewed", language, date=_date_only(reviewed["created_at"])),
                  text("next_reviewed_detail", language))
        target = reports_page
    else:
        next_step(text("next_new", language), text("next_new_detail", language))
    first, second, _spacer = st.columns([1.2, 1.2, 1])
    if first.button(text("start_resume", language), type="primary" if target is assessment_hub else "secondary", width="stretch"):
        go(assessment_hub)
    if second.button(text("my_goals", language), type="primary" if target is my_care_page else "secondary", width="stretch"):
        go(my_care_page)
    if target is reports_page and st.button(text("open_reports", language)):
        go(reports_page)
    cols = st.columns(4)
    cols[0].metric(text("assessments", language), len(items))
    cols[1].metric(text("completed", language), sum(i["status"] == "completed" for i in items))
    cols[2].metric(text("latest_visit", language), _date_only(items[0]["created_at"]) if items else text("no_visits", language))
    cols[3].metric(text("last_checkin", language),
                   text("checkin_today", language) if checked_today else _date_only(checkins[0]["date"]) if checkins else text("no_checkin", language))
    planned = planned_review_date(plans, today)
    if planned:
        st.caption(text("next_review_date", language, date=datetime.fromisoformat(planned).strftime("%d %b %Y")))
    if weekly:
        summary = " · ".join(f"{hub_card(group, language)[0]} ({', '.join(weekday_name(day, language) for day in days)})"
                             for group, days in weekly["schedule"].items())
        st.caption(text("plan_week", language, plan=summary))
        if weekly.get("note"):
            st.caption(plain_text(weekly["note"]))
    if items:
        section_header(text("recent_visits", language), text("visits_detail", language))
        from app.components.visit_summary import render_visit_summary
        render_visit_summary([{"visit": time_label(i["created_at"]), "status": i["status"],
                               "tasks_saved": len(i.get("modules", {})),
                               "review": "Reviewed" if i.get("review_status") == "reviewed" else "Awaiting review"}
                              for i in items[:5]], language)
    else:
        empty_state(text("first_visit", language), text("first_visit_detail", language))


def my_care_page():
    from app.components.care_panels import patient_care_panel
    user = actor()
    if user["role"] != "patient":
        raise PermissionError("This page is for your own patient care notes.")
    language = _patient_surface(user)
    st.title({"Urdu": "روزانہ حال اور مقصد", "Roman Urdu": "Rozana haal aur maqsad"}.get(language, "Check-in & goals"))
    patient_care_panel(user)


def care_plan_page():
    from app.components.care_panels import clinician_care_panel
    user = actor()
    if user["role"] != "clinician":
        raise PermissionError("Care team follow-up is available to assigned clinicians.")
    st.title("Patient context & follow-up")
    clinician_care_panel(user, patient_id())


def assessment_hub():
    from app.components.visit_context_panel import assistance_form, medication_form
    user = actor()
    language = _patient_surface(user)
    st.title(text("hub_title", language))
    write_patient(text("hub_intro", language), language)
    if st.session_state.pop("hub_notice", None):
        st.success(text("assessment_completed", language))
    items = history()
    unfinished = [i for i in items if i["status"] not in {"completed", "abandoned"}]
    _plan, planned, _pending = todays_plan(user["id"], items)
    aid = st.session_state.get("active_assessment_id")
    item = services.get_assessment(user["id"], aid) if aid else None
    if item and item["status"] in {"completed", "abandoned"}:
        st.session_state.pop("active_assessment_id", None)
        item = None
    if item is None:
        if unfinished:
            next_step(text("next_resume", language, date=_date_only(unfinished[0]["created_at"])),
                      text("next_resume_detail", language, done=groups_saved(unfinished[0]), total=len(TASK_GROUPS)), "waiting")
            selected = st.selectbox(text("resume_assessment", language), unfinished, format_func=lambda i: time_label(i["created_at"]))
        resume_col, new_col, _ = st.columns([1.1, 1.1, 1])
        if unfinished and resume_col.button(text("resume_selected", language), type="primary", width="stretch"):
            st.session_state.active_assessment_id = selected["id"]
            st.rerun()
        if (new_col if unfinished else resume_col).button(text("new_assessment", language), type="secondary" if unfinished else "primary", width="stretch"):
            fresh = services.create_assessment(user["id"])
            st.session_state.active_assessment_id = fresh["id"]
            st.rerun()
        return
    done = groups_saved(item)
    status_pill(text("visit_label", language, date="\u2066" + time_label(item["created_at"]) + "\u2069"), "care" if done else "waiting")
    visit_progress(done, len(TASK_GROUPS), text("visit_progress", language, done=done, total=len(TASK_GROUPS)))
    st.caption(text("visit_progress", language, done=done, total=len(TASK_GROUPS)))
    medication_form(user, item, language, expanded=False)
    assistance_form(user, item, language)
    pages = {"gait": gait_page, "hand": hand_page, "transfer": transfer_page,
             "reach": reach_page, "touch": touch_page, "voice": voice_page, "adl": adl_page}
    keys = list(pages)
    for start in range(0, len(keys), 2):
        for col, card_key in zip(st.columns(2, gap="large"), keys[start:start + 2]):
            title, detail = hub_card(card_key, language)
            saved = sum(task in item.get("modules", {}) for task in TASK_GROUPS[card_key])
            with col, st.container(border=True, key=f"ps_task_{'done' if saved else 'open'}_{card_key}"):
                state = (text("saved_count", language, count=saved) if saved else
                         text("planned_today", language) if card_key in planned else text("ready", language))
                task_card(title, detail, state, done=bool(saved))
                if st.button(text("open_task", language, task=title), key=f"hub_open_{card_key}", width="stretch"):
                    go(pages[card_key])
    if any(is_accepted(r) for r in item.get("modules", {}).values()) and item["status"] not in {"completed", "abandoned"}:
        if st.button(text("complete_assessment", language), type="primary"):
            services.finish_assessment(user["id"], item["id"])
            st.session_state.pop("active_assessment_id", None)
            st.session_state.hub_notice = True
            st.rerun()
    with st.expander(text("restart_visit", language)):
        if st.checkbox(text("abandon_visit", language)) and st.button(text("restart_assessment", language)):
            fresh = services.restart_assessment(user["id"], item["id"])
            st.session_state.active_assessment_id = fresh["id"]
            st.rerun()
    # Leaving this visit open: go back to another unfinished one, or begin a fresh one.
    others = [i for i in unfinished if i["id"] != item["id"]]
    with st.expander(text("switch_visit", language)):
        if others:
            other = st.selectbox(text("resume_assessment", language), others,
                                 format_func=lambda i: time_label(i["created_at"]), key="hub_other_visit")
            if st.button(text("resume_selected", language), key="hub_switch_resume"):
                st.session_state.active_assessment_id = other["id"]
                st.rerun()
        if st.button(text("new_assessment", language), key="hub_switch_new"):
            fresh = services.create_assessment(user["id"])
            st.session_state.active_assessment_id = fresh["id"]
            st.rerun()


def gait_page():
    movement_page(["gait", "turning"])


def hand_page():
    movement_page(["finger_left", "finger_right", "hand_open_close"])


def transfer_page():
    movement_page(["sit_to_stand"])


def reach_page():
    movement_page(["reach", "grasp", "object_transfer"])


def practice_page():
    """Browser-only practice aids: a walking beat and louder-voice feedback."""
    from app.components.practice_tools import cadence_bpm, loudness_practice, metronome
    language = _patient_surface()
    st.title(text("practice_title", language))
    write_patient(text("practice_intro", language), language)
    walk, voice = st.tabs([text("practice_walk", language), text("practice_voice", language)])
    with walk:
        write_patient(text("metronome_intro", language), language)
        st.caption(text("metronome_safety", language))
        bpm = cadence_bpm(history())
        if bpm:
            st.caption(text("metronome_from_cadence", language))
        metronome(default_bpm=bpm or 90, key="practice_metronome",
                  labels={name: text(f"metronome_{name}", language, bpm="{bpm}") for name in ("start", "stop", "slower", "faster", "bpm")})
    with voice:
        write_patient(text("loudness_intro", language), language)
        st.caption(text("loudness_privacy", language))
        loudness_practice(key="practice_loudness", labels={
            name: text(f"loudness_{name}", language, seconds="{seconds}")
            for name in ("ready", "start", "stop", "calibrating", "go", "time", "denied")})


def _listen_to_steps(task, language, key):
    from app.components.patient_language import TASK_STEPS
    from app.components.read_aloud import listen_button
    listen_button(TASK_STEPS[task], language, key=key)


def touch_page():
    """Spiral drawing and two-circle tapping on the patient's own screen."""
    from ml.touch import analyze_touch
    from app.components.analysis_feedback import attempt_report_panel, failure_result, saved_report_panel
    from app.components.touch_test import touch_test
    from app.components.visit_context_panel import timing_reminder
    language = _patient_surface()
    item = active_assessment()
    st.title(text("touch_title", language))
    timing_reminder(actor(), item, language)
    write_patient(text("touch_intro", language), language)
    left, right = st.columns(2)
    test = left.selectbox(text("touch_test", language), ["spiral", "tapping"],
                          format_func=lambda value: text(f"touch_{value}", language), key=f"touch_test_{item['id']}")
    hand = right.radio(text("touch_hand", language), ["right", "left"], horizontal=True,
                       format_func=lambda value: text(f"hand_{value}", language), key=f"touch_hand_{item['id']}")
    task = f"{'spiral' if test == 'spiral' else 'touch_tap'}_{hand}"
    render_steps(task, language)
    _listen_to_steps(task, language, key=f"listen_{task}")
    st.caption(text("touch_same_device", language))
    draft_key = f"draft_{item['id']}_{task}"
    generation_key = f"touch_generation_{item['id']}_{task}"
    labels = {name: text(f"touch_{name}", language) for name in ("analysing", "measured", "clear", "done", "stop", "canvas")}
    labels["ready"] = text(f"touch_ready_{test}", language)
    labels["remaining"] = text("touch_remaining", language, seconds="{seconds}")
    # A saved result starts a fresh canvas; an analysed attempt stays beside its result.
    attempts_key = f"touch_attempts_{item['id']}_{task}"
    payload = touch_test(test, key=f"touch_canvas_{item['id']}_{task}_{st.session_state.get(generation_key, 0)}",
                         labels=labels, measured=st.session_state.get(attempts_key, 0) if draft_key in st.session_state else 0)
    if payload is not None:
        try:
            result = analyze_touch(task, payload)
        except ValueError as exc:
            result = failure_result(exc, task, language=actor()["language"])
        st.session_state[draft_key] = {"result": result, "media_key": None}
        st.session_state[attempts_key] = st.session_state.get(attempts_key, 0) + 1
        st.rerun()  # Redraw so the canvas learns this attempt was measured.
    if st.session_state.pop(f"touch_notice_{item['id']}", None):
        st.success(text("touch_saved", language))
    draft = st.session_state.get(draft_key)
    if draft:
        review_result(draft["result"], task, baseline=baseline_for(task, item["id"], current=draft["result"]),
                      identity=f"touch_draft_{item['id']}_{task}", assessment_id=item["id"])
        attempt_report_panel(actor(), item, task, draft["result"], identity=draft_key)
        if st.button(text("save_result", language), type="primary", disabled=not is_accepted(draft["result"]),
                     key=f"touch_save_{item['id']}_{task}"):
            services.save_module(actor()["id"], item["id"], task, draft["result"])
            del st.session_state[draft_key]
            st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
            st.session_state[f"touch_notice_{item['id']}"] = True
            st.rerun()
    saved = services.get_assessment(actor()["id"], item["id"])
    if not st.session_state.get(draft_key) and task in saved.get("modules", {}):
        section_header(text("saved_analysis", language), text("current_visit", language))
        review_result(saved["modules"][task], task, identity=f"touch_saved_{saved['id']}_{task}", assessment_id=saved["id"])
    if saved.get("reports"):
        saved_report_panel(actor(), saved, identity=f"touch_{item['id']}_{task}")


def _analyze_media(item, task, filename, data, capture_metadata=None):
    from ml.vision.pipeline import analyze_video, CVError
    from app.components.analysis_feedback import failure_result
    user = actor()
    draft_key = f"draft_{item['id']}_{task}"
    st.session_state.pop(draft_key, None)
    key = None
    try:
        key = services.store_upload(user["id"], item["id"], task, filename, data)
        path = services.get_media_path(user["id"], item["id"], key)
        with st.spinner(text("movement_spinner", _ui_language(user))):
            result = analyze_video(path, task, capture_metadata=capture_metadata)
    except (CVError, ValueError, OSError, LookupError) as exc:
        result = failure_result(exc, task, language=user["language"])
    st.session_state[draft_key] = {"result": result, "media_key": key}


def _finish_live_recording(processor, item, task):
    """Keep the current camera attempt, including an honest failed preview."""
    from app.components.analysis_feedback import failure_result
    draft_key = f"draft_{item['id']}_{task}"
    try:
        captured = processor.stop_recording()
        metadata = processor.snapshot()
        if metadata.get("timing_valid") is False:
            result = failure_result("Camera connection gaps during recording", task, language=actor()["language"])
        elif captured and Path(captured).is_file() and Path(captured).stat().st_size:
            _analyze_media(item, task, "recording.avi", Path(captured).read_bytes(), capture_metadata=metadata)
            return
        else:
            result = failure_result("Recording is missing or empty", task, language=actor()["language"])
    except (ValueError, OSError) as exc:
        result = failure_result(exc, task, language=actor()["language"])
    finally:
        processor.mark_recording_reviewed()
    st.session_state[draft_key] = {"result": result, "media_key": None}


def movement_page(tasks):
    from ml.vision.pipeline import make_video_processor
    from streamlit_webrtc import WebRtcMode, webrtc_streamer
    language = _patient_surface()
    item = active_assessment()
    heading = st.empty()
    task = st.selectbox(text("movement_task", language), tasks, format_func=lambda value: task_label(value, language))
    heading.title(task_label(task, language))
    st.session_state.current_step = 1
    from app.components.visit_context_panel import timing_reminder
    timing_reminder(actor(), item, language)
    render_steps(task, language)
    _listen_to_steps(task, language, key=f"listen_{task}")
    with st.expander(text("setup", language)):
        write_patient(text("setup_camera", language), language)
        write_patient(text("setup_stop", language), language)
        st.caption(text("quality_check", language))
    from app.components.setup_check import setup_guide
    setup_guide(task, baseline_for(task, item["id"]), language, key=f"setup_guide_{item['id']}_{task}")
    # The values remain stable IDs; translated labels never reach analysis APIs.
    mode = st.radio(text("recording_source", language), ["Upload Recorded Video", "Live Camera"],
        format_func=lambda value: text("upload_video" if value == "Upload Recorded Video" else "live_camera", language), horizontal=True)
    draft_key = f"draft_{item['id']}_{task}"
    draft = st.session_state.get(draft_key)
    st.progress(1.0 if draft else 2 / 7, text=text("review_save" if draft else "choose_recording", language))
    if mode == "Upload Recorded Video":
        uploaded = st.file_uploader(text("upload_assessment", language), type=["mp4", "mov", "avi", "mkv"], key=f"upload_{item['id']}_{task}")
        st.caption(text("video_limits", language))
        write_patient(text("mobile_recording", language), language)
        if uploaded:
            st.caption(text("choose_recording", language))
            if st.button(text("analyze_video", language), type="primary"):
                _analyze_media(item, task, uploaded.name, uploaded.getvalue())
                st.rerun()
    else:
        from app.components.live_camera import live_camera_panel
        from app.components.pose_3d_viewer import CAMERAS
        write_patient(text("live_steps", language), language)
        st.caption(text("mobile_live", language))
        section_header(text("live_tracking", language), text("focused_joints", language))
        options_left, options_middle, options_right = st.columns([1.3, 1.1, 1])
        lines = options_left.checkbox(text("joint_lines", language), value=True, key=f"live_lines_{item['id']}_{task}", help=text("joint_lines_help", language))
        trails = options_middle.checkbox(text("movement_trails", language), value=True, key=f"live_trails_{item['id']}_{task}")
        camera = options_right.selectbox(text("viewpoint", language), list(CAMERAS), index=3, key=f"live_camera_view_{item['id']}_{task}")
        lens = st.selectbox(text("camera_lens", language), ["auto", "rear", "front"],
            format_func=lambda value: text(f"lens_{value}", language), key=f"live_lens_{item['id']}_{task}",
            help=text("lens_help", language))
        video_constraints = {"width": {"ideal": 1280}, "height": {"ideal": 720}, "frameRate": {"ideal": 30, "max": 30}}
        if lens != "auto":
            video_constraints["facingMode"] = {"ideal": "environment" if lens == "rear" else "user"}
        capture_key = f"capture_{item['id']}_{task}"
        if capture_key not in st.session_state:
            from backend.storage import capture_root, sweep_stale_captures
            try:
                sweep_stale_captures()  # Clips left behind by sessions that never logged out.
            except OSError:
                pass
            fd, path = tempfile.mkstemp(suffix=".avi", dir=capture_root())
            os.close(fd)
            st.session_state[capture_key] = path
        path = st.session_state[capture_key]
        processor_class = make_video_processor(task, path, overlay=lines, show_trails=trails)
        try:
            ice_servers = json.loads(os.getenv("PARKINSENSE_ICE_SERVERS", "[]"))
        except json.JSONDecodeError:
            ice_servers = []
        video_column, tracking_column = st.columns([1.05, 1], gap="large")
        with video_column:
            st.subheader(text("camera_lines", language))
            ctx = webrtc_streamer(key=f"live_{item['id']}_{task}", mode=WebRtcMode.SENDRECV,
                video_processor_factory=processor_class,
                media_stream_constraints={"video": video_constraints, "audio": False},
                video_html_attrs={"autoPlay": True, "playsInline": True, "muted": True, "style": {"width": "100%", "transform": "none"}},
                rtc_configuration={"iceServers": ice_servers}, translations=camera_translations(language), async_processing=True)
            st.caption(text("anatomical_side", language))
        with tracking_column:
            live_camera_panel(ctx, task, identity=f"{item['id']}_{task}", overlay=lines, show_trails=trails,
                camera=camera, language=actor()["language"], on_finish=lambda processor: _finish_live_recording(processor, item, task))
    draft = st.session_state.get(draft_key)
    if draft:
        from app.components.analysis_feedback import attempt_report_panel
        media_path = services.get_media_path(actor()["id"], item["id"], draft["media_key"]) if draft.get("media_key") else None
        review_result(draft["result"], task, baseline=baseline_for(task, item["id"], current=draft["result"]), media_path=media_path, assessment_id=item["id"])
        attempt_report_panel(actor(), item, task, draft["result"], identity=draft_key)
        accepted = is_accepted(draft["result"])
        if st.button(text("save_result", language), type="primary", disabled=not accepted):
            services.save_module(actor()["id"], item["id"], task, draft["result"], media_path=draft["media_key"])
            del st.session_state[draft_key]
            st.rerun()
    saved = services.get_assessment(actor()["id"], item["id"])
    if not st.session_state.get(draft_key) and task in saved.get("modules", {}):
        section_header(text("saved_analysis", language), text("current_visit", language))
        review_result(saved["modules"][task], task, media_path=module_media_path(saved, task), assessment_id=saved["id"])
    if saved.get("reports"):
        from app.components.analysis_feedback import saved_report_panel
        saved_report_panel(actor(), saved, identity=f"movement_{item['id']}_{task}")


def baseline_for(task, excluding=None, pid=None, current=None):
    visits = history(pid)
    current_visit = next((v for v in visits if v["id"] == excluding), None)
    cutoff = current_visit["created_at"] if current_visit else None
    current = current or (current_visit.get("modules", {}).get(task) if current_visit else None)
    for visit in reversed(visits):
        if visit["id"] == excluding or visit["status"] == "abandoned":
            continue
        if cutoff and visit["created_at"] >= cutoff:
            continue
        result = visit.get("modules", {}).get(task)
        if result and is_accepted(result):
            if current and ((result.get("method") or result.get("analysis_version")) != (current.get("method") or current.get("analysis_version"))
                            or result.get("language") != current.get("language") or result.get("task") != current.get("task")):
                continue
            if result.get(services.FRAMES_OMITTED):
                # Visit lists leave out landmarks; the replay overlay needs this one visit in full.
                result = services.get_assessment(actor()["id"], visit["id"])["modules"].get(task, result)
            return result
    return None


def review_result(result, task, baseline=None, media_path=None, history_items=None, identity=None, assessment_id=None):
    from app.components.guidance_panel import render_guidance
    from app.components.statistical_3d import module_statistics_panel
    from ml.common.statistics import measurements
    quality = result.get("quality", {})
    language = _ui_language()
    accepted = is_accepted(result)
    self_report = task in {"adl", "nlp"}
    (st.success if accepted else st.warning)(text("accepted_responses" if accepted and self_report else "accepted_recording" if accepted else "retry", language))
    if accepted and not self_report:
        st.info(text("task_review_required", language))
    if accepted and baseline and not self_report:
        from app.components.setup_check import setup_notice
        setup_notice(result, baseline, task, language)
    identity = identity or (str(media_path) if media_path else hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()) + task
    render_guidance(result, task, language=actor()["language"], identity=f"{identity}_guidance")
    if accepted and result.get("landmark_frames"):
        from app.components.motion_studio import movement_studio
        movement_studio({**result, "task": task}, baseline={**baseline, "task": task} if baseline else None, identity=identity,
                        export_context={"user": actor(), "assessment_id": assessment_id} if assessment_id else None)
    if task in TASK_GROUPS["touch"]:
        from app.components.touch_review import render_touch_result
        render_touch_result(result, key=f"touch_{hashlib.sha256(identity.encode()).hexdigest()[:16]}")
    module_statistics_panel(result, task, identity=f"stats_{identity}", history=history_items)
    metadata = result.get("feature_metadata", {})
    rows = measurements(result, task)
    if rows:
        with st.expander(text("measurement_details", language), expanded=not bool(result.get("landmark_frames"))):
            st.dataframe(pd.DataFrame([{"Measure": row.label, "Value": round(row.value, 4), "Unit": row.unit} for row in rows]), hide_index=True, width="stretch")
    for caveat in result.get("caveats", result.get("limitations", [])):
        st.caption(caveat)
    if actor()["role"] == "clinician":
        with st.expander("Measurement methods and recording quality"):
            st.json({"quality": quality, "methods": metadata, "coordinate_system": result.get("coordinate_system")})


def module_media_path(item, task):
    file_id = item.get("module_file_ids", {}).get(task)
    record = next((f for f in item.get("files", []) if f["id"] == file_id), None)
    return services.get_media_path(actor()["id"], item["id"], record["storage_key"]) if record else None


def _show_current_analysis(item, task):
    from app.components.analysis_feedback import attempt_report_panel
    attempt = st.session_state.get(f"attempt_{item['id']}_{task}")
    result = attempt.get("result") if attempt else item.get("modules", {}).get(task)
    if result is None:
        return
    language = _ui_language()
    section_header(text("analysis_title", language, task=task_label(task, language)), text("latest_analysis", language))
    identity = f"current_{item['id']}_{task}"
    review_result(result, task, identity=identity, assessment_id=item["id"])
    if attempt and not is_accepted(result):
        attempt_report_panel(actor(), item, task, result, identity=identity)


def voice_page():
    from ml.audio import analyze_audio
    from ml.nlp import analyze_text
    from app.components.analysis_feedback import failure_result, saved_report_panel
    ui_language = _patient_surface()
    item = active_assessment()
    st.title(text("voice_title", ui_language))
    from app.components.visit_context_panel import timing_reminder
    timing_reminder(actor(), item, ui_language)
    write_patient(text("voice_setup", ui_language), ui_language)
    language = st.selectbox(text("speech_language", ui_language), LANGUAGES, index=LANGUAGES.index(actor()["language"]) if actor()["language"] in LANGUAGES else 0)
    task = st.selectbox(text("voice_task", ui_language), ["vowel", "sentence", "natural"], format_func=lambda value: text(value, ui_language))
    # A fixed sentence follows the recording language, even when interface
    # labels use a different saved profile language.
    write_patient(voice_prompt(task, language), resolved_language(language))
    from app.components.patient_language import VOICE_PROMPTS
    from app.components.read_aloud import listen_button
    listen_button(VOICE_PROMPTS[task], language, key=f"listen_voice_{task}")
    if language not in {"English", "Urdu", "Roman Urdu"}:
        st.caption("The task prompt is shown in English for this speech language. Agree a consistent sentence with your clinician before comparing visits.")
    mode = st.radio(text("audio_source", ui_language), ["Microphone", "Upload WAV"],
        format_func=lambda value: text("microphone" if value == "Microphone" else "upload_wav", ui_language), horizontal=True)
    audio = st.audio_input(text("record_voice", ui_language), key=f"audio_{item['id']}_{task}") if mode == "Microphone" else st.file_uploader(text("upload_audio", ui_language), type=["wav"], key=f"audio_upload_{item['id']}_{task}")
    write_patient(text("audio_stop", ui_language), ui_language)
    if audio:
        # audio_input already previews the locally captured voice. Uploaded
        # recordings are played only through the authenticated media gateway.
        if st.button(text("save_voice", ui_language), type="primary"):
            module = f"voice_{task}"
            key = None
            try:
                key = services.store_upload(actor()["id"], item["id"], module, "voice.wav", audio.getvalue())
                with st.spinner(text("audio_spinner", ui_language)):
                    result = analyze_audio(services.get_media_path(actor()["id"], item["id"], key), language, task)
                result["voice_task"] = task
                if is_accepted(result):
                    services.save_module(actor()["id"], item["id"], module, result, media_path=key)
                    st.success(text("voice_saved", ui_language))
            except (ValueError, OSError, LookupError) as exc:
                result = failure_result(exc, module, language=actor()["language"])
            st.session_state[f"attempt_{item['id']}_{module}"] = {"result": result, "media_key": key}
    current = services.get_assessment(actor()["id"], item["id"])
    _show_current_analysis(current, f"voice_{task}")
    st.caption(text("asr_unavailable", ui_language))
    saved_text_result = current.get("modules", {}).get("nlp", {})
    saved_text = saved_text_result.get("reviewed_text", "") if is_accepted(saved_text_result) else ""
    saved_text = saved_text if isinstance(saved_text, str) and len(saved_text) <= 5000 else ""
    transcript_key = f"transcript_{item['id']}"
    if transcript_key not in st.session_state:
        st.session_state[transcript_key] = saved_text
    with st.form(f"transcript_form_{item['id']}"):
        transcript = st.text_area(text("transcript", ui_language), max_chars=5000, key=transcript_key)
        if st.form_submit_button(text("save_description", ui_language)):
            try:
                result = analyze_text(transcript, language)
                services.save_module(actor()["id"], item["id"], "nlp", result)
                st.success(text("description_saved", ui_language))
            except ValueError as exc:
                result = failure_result(exc, "nlp", language=actor()["language"])
            st.session_state[f"attempt_{item['id']}_nlp"] = {"result": result}
    current = services.get_assessment(actor()["id"], item["id"])
    _show_current_analysis(current, "nlp")
    saved_report_panel(actor(), current, identity=f"voice_page_{item['id']}")


def adl_page():
    from ml.tabular import analyze_adl
    from ml.tabular.adl import ADL_ITEMS
    from app.components.analysis_feedback import failure_result, saved_report_panel
    language = _patient_surface()
    item = active_assessment()
    st.title(text("adl_title", language))
    write_patient(text("adl_intro", language), language)
    st.caption(text("adl_caveat", language))
    saved = item.get("modules", {}).get("adl", {})
    saved_responses = saved.get("responses", {}) if is_accepted(saved) else {}
    saved_responses = saved_responses if isinstance(saved_responses, dict) else {}
    for key in ADL_ITEMS:
        answer_key = f"adl_answer_{item['id']}_{key}"
        if answer_key not in st.session_state:
            answer = saved_responses.get(key)
            st.session_state[answer_key] = answer if type(answer) is int and answer in range(5) else None
    note_key = f"adl_note_{item['id']}"
    if note_key not in st.session_state:
        note = saved.get("other_difficulty", "") if is_accepted(saved) else ""
        st.session_state[note_key] = note if isinstance(note, str) and len(note) <= 2000 else ""
    with st.form(f"adl_{item['id']}"):
        values = {key: st.selectbox(adl_label(key, language), options=list(range(5)), index=None,
            placeholder=text("choose_experience", language), format_func=lambda value: adl_choice(value, language), key=f"adl_answer_{item['id']}_{key}") for key in ADL_ITEMS}
        values["other_difficulty"] = st.text_area(text("other_difficulty", language), max_chars=2000, key=note_key)
        if st.form_submit_button(text("save_adl", language), type="primary"):
            try:
                result = analyze_adl(values)
                services.save_module(actor()["id"], item["id"], "adl", result)
                st.success(text("adl_saved", language))
            except ValueError as exc:
                result = failure_result(exc, "adl", language=actor()["language"])
            st.session_state[f"attempt_{item['id']}_adl"] = {"result": result}
    current = services.get_assessment(actor()["id"], item["id"])
    _show_current_analysis(current, "adl")
    saved_report_panel(actor(), current, identity=f"adl_page_{item['id']}")


def select_visit(items=None):
    items = items if items is not None else history()
    if not items:
        st.info("No assessments have been saved yet.")
        st.stop()
    by_id = {item["id"]: item for item in items}

    def visit_name(visit_id):
        visit = by_id[visit_id]
        status = STATUS_WORDS.get(visit["status"], visit["status"])
        review = ", reviewed" if visit.get("review_status") == "reviewed" else ""
        return f"{time_label(visit['created_at'])} — {status.lower()}{review} (ref {visit_id[:6]})"
    selected = st.selectbox("Assessment", list(by_id), format_func=visit_name)
    return services.get_assessment(actor()["id"], selected)


def results_page():
    st.title("My Results")
    visits = history()
    item = select_visit(visits)
    reviewed = item.get("review_status") == "reviewed"
    status_pill(REVIEW_WORDS.get(item.get("review_status"), "Awaiting review"), "care" if reviewed else "waiting")
    if not item.get("modules"):
        st.info("This assessment does not have saved results yet.")
    for task, result in item.get("modules", {}).items():
        with st.expander(LABELS.get(task, task.replace("_", " ").title())):
            path = module_media_path(item, task)
            review_result(result, task, baseline_for(task, item["id"]), media_path=path, history_items=visits, identity=f"results_{item['id']}_{task}", assessment_id=item["id"])
    from app.components.analysis_feedback import saved_report_panel
    saved_report_panel(actor(), item, identity=f"results_{item['id']}")


def motion_page():
    st.title("3D Movement Studio")
    st.write("Inspect body or hand movement from different angles, replay a moment and compare a previous recording.")
    pid = patient_id()
    visits = history(pid)
    item = select_visit(visits)
    modules = {k: v for k, v in item.get("modules", {}).items() if v.get("landmark_frames")}
    if not modules:
        st.info("Save an accepted movement recording to see its 3D replay.")
        return
    task = st.selectbox("Movement module", list(modules), format_func=lambda k: LABELS.get(k, k))
    baseline = baseline_for(task, item["id"], pid, current=modules[task])
    path = module_media_path(item, task)
    review_result(modules[task], task, baseline, media_path=path, history_items=visits, identity=f"studio_{item['id']}_{task}", assessment_id=item["id"])


def progress_page():
    from ml.common.statistics import measurement_definition
    from app.components.trend_chart import render_trend
    from backend.services.visit_context import list_visit_contexts
    st.title("Progress over time")
    pid = patient_id()
    visits = history(pid)
    rows = []
    for visit in reversed(visits):
        if visit["status"] == "abandoned":
            continue
        for task, result in visit.get("modules", {}).items():
            if not is_accepted(result):
                continue
            for feature, value in result.get("features", {}).items():
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    definition = measurement_definition(result, feature, task) or {}
                    rows.append({"Date": visit["created_at"], "Visit": visit["id"], "Task": task, "Measure": feature,
                                 "Label": definition.get("label", feature.replace("_", " ").capitalize()),
                                 "Unit": definition.get("unit", "value"), "Value": value,
                                 "Method": result.get("method", result.get("analysis_version", "Unspecified")),
                                 "Language": result.get("language", "Not applicable")})
    if not rows:
        empty_state("Nothing to compare yet", "Accepted task measurements appear here after you save a result. "
                    "Two visits with the same task are enough to draw a line.")
        return
    df = pd.DataFrame(rows)
    left, right = st.columns(2)
    task = left.selectbox("Task", sorted(df.Task.unique()), format_func=lambda k: LABELS.get(k, k.replace("_", " ")))
    subset = df[df.Task == task]
    labels = subset.drop_duplicates("Measure").set_index("Measure")["Label"].to_dict()
    feature = right.selectbox("Measure", sorted(subset.Measure.unique(), key=lambda k: labels.get(k, k)),
                              format_func=lambda k: labels.get(k, k))
    subset = subset[subset.Measure == feature].copy()
    if subset.Language.nunique() > 1:
        language = st.selectbox("Recording language", sorted(subset.Language.unique()))
        subset = subset[subset.Language == language]
    if subset.Method.nunique() > 1:
        st.caption("These results used different measurement methods. Choose one method for a consistent comparison.")
        method = st.selectbox("Measurement method", sorted(subset.Method.unique()))
        subset = subset[subset.Method == method]
    subset["Date"] = pd.to_datetime(subset["Date"], utc=True).dt.tz_convert("Asia/Karachi")
    try:
        contexts = list_visit_contexts(actor()["id"], subset["Visit"].tolist())
    except (PermissionError, LookupError):
        contexts = {}
    states = [contexts.get(v, {}).get("medication_state") if contexts.get(v) else None for v in subset["Visit"]]
    from app.components.visit_context_panel import describe_assistance
    from backend.services.visit_context import list_visit_assistance
    try:
        assistance = list_visit_assistance(actor()["id"], subset["Visit"].tolist())
    except (PermissionError, LookupError):
        assistance = {}
    label, unit = labels.get(feature, feature), subset.iloc[-1]["Unit"]
    first, latest = float(subset.iloc[0]["Value"]), float(subset.iloc[-1]["Value"])
    cols = st.columns(3)
    cols[0].metric("First accepted visit", f"{first:.4g}")
    cols[1].metric("Latest", f"{latest:.4g}")
    change = latest - first
    percent = f" ({change / abs(first) * 100:+.0f}%)" if first else ""
    cols[2].metric("Change since first", f"{change:+.3g}{percent}" if len(subset) > 1 else "—")
    st.caption(f"{label}, in {unit}. {len(subset)} accepted visit{'s' if len(subset) != 1 else ''}.")
    render_trend(subset["Date"].tolist(), subset["Value"].astype(float).tolist(), label, unit, states, key=f"trend_{pid}_{task}_{feature}")
    st.caption("Only accepted recordings from the same task are compared. A change is a measured difference, not a judgement "
               "of better or worse. Camera position, language, task instructions, assistance and medicine timing can all affect it.")
    from app.components.statistical_3d import module_statistics_panel
    current = next((visit["modules"][task] for visit in visits if visit.get("status") != "abandoned" and is_accepted(visit.get("modules", {}).get(task, {}))
                    and visit["modules"][task].get("method", visit["modules"][task].get("analysis_version", "Unspecified")) == subset.iloc[-1]["Method"]
                    and visit["modules"][task].get("language", "Not applicable") == subset.iloc[-1]["Language"]), None)
    if current:
        with st.expander("3D statistical review"):
            module_statistics_panel(current, task, identity=f"progress_{pid}_{task}", history=visits, default_view="history")
    table = pd.DataFrame({"Date": subset["Date"].dt.strftime("%d %b %Y, %I:%M %p"), f"Value ({unit})": subset["Value"].round(4),
                          "Medicine timing": [{"on": "ON", "off": "OFF", "wearing_off": "Wearing off", "unsure": "Not sure",
                                               "none": "No PD medicine"}.get(s, "Not recorded") for s in states],
                          "Help / walking aid": [describe_assistance(assistance.get(v)) or "Not recorded" for v in subset["Visit"]]})
    st.dataframe(table, hide_index=True, width="stretch")


def reports_page():
    from ml.inference import build_report
    from backend.services.reporting import get_patient_report
    from app.components.analysis_feedback import saved_report_panel
    st.title("Reports")
    pid = patient_id()
    visits = history(pid)
    item = select_visit(visits)
    if not item.get("modules"):
        st.info("Save at least one task before preparing a report.")
        return
    automatic = get_patient_report(actor()["id"], item["id"])
    if automatic is None or automatic.get("outdated"):
        st.info("Generate the patient report for this earlier assessment." if automatic is None else "Update this report before sharing it.")
        if st.button("Generate patient report" if automatic is None else "Update patient report", type="primary", disabled=item["status"] == "abandoned"):
            generated = get_patient_report(actor()["id"], item["id"], refresh=True)
            if generated:
                st.rerun()
            else:
                st.warning("A patient report needs at least one accepted recording or response.")
    if automatic:
        report = automatic["content"]
        saved_report_panel(actor(), item, identity=f"reports_{item['id']}", expanded=True)
        st.caption(f"Prepared {report.get('generated_at_local', '')} · Assessment: {item['status']}")
        review = report.get("clinician_review", {})
        if review.get("source") == "human_clinician":
            st.subheader("Care team's review")
            st.write(review.get("author_name") or "Your linked clinician")
            st.write(review.get("note") or "Review completed without an additional note.")
        else:
            st.info("Awaiting your care team's review. Automated measurements and questionnaire answers are shown separately below.")
        for section in report.get("sections", []):
            with st.expander(section["title"], expanded=len(report.get("sections", [])) == 1):
                st.caption(f"{section['source']} · {section['method']}")
                st.write("Accepted for review" if section["accepted"] else "Repeat or review needed")
                rows = [{"Measurement": row["label"], "Current": row["value"], "Unit": row["unit"], "Earlier reference": row.get("reference"), "Difference": row.get("delta")} for row in section.get("measurements", [])]
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                else:
                    st.caption("This attempt has no accepted measurements.")
                if section.get("responses"):
                    st.dataframe(pd.DataFrame([{"Activity": row["label"], "Your answer": row["description"]} for row in section["responses"]]), hide_index=True, width="stretch")
                if section.get("reported_entities"):
                    st.dataframe(pd.DataFrame([{"Activity": row["activity"], "Rule result": row["status"], "Your words": row["source_excerpt"]} for row in section["reported_entities"]]), hide_index=True, width="stretch")
                if section.get("patient_note"):
                    st.write("Your note:", section["patient_note"])
                for message in section.get("quality", {}).get("messages", []):
                    st.write(message)
                from app.components.guidance_panel import render_guidance
                render_guidance(item["modules"].get(section["task"], {}), section["task"], language=actor()["language"], identity=f"report_{item['id']}_{section['task']}")
                for limitation in section.get("limitations", []):
                    st.caption(limitation)
        st.caption(report.get("coverage_note", ""))
        st.caption(report.get("comparison_note", ""))
        private_download("Download report data (JSON)", json.dumps(report, ensure_ascii=False, indent=2), user=actor(), assessment_id=item["id"], file_name="parkinsense-patient-report.json", mime="application/json", key=f"auto_json_{item['id']}")
    with st.expander("Additional measurement summaries"):
        st.caption("Save a separate summary when you want to retain a snapshot alongside the automatic report.")
        if st.button("Prepare and save measurement summary", disabled=item["status"] == "abandoned"):
            prior = [v for v in visits if v["created_at"] < item["created_at"] and v["status"] != "abandoned"]
            report = build_report(item["modules"], prior, actor()["language"])
            services.save_report(actor()["id"], item["id"], report)
            st.rerun()
    reports = [record for record in item.get("reports", []) if record.get("content", {}).get("auto_summary") != "patient-analysis-summary"]
    for index, record in enumerate(reversed(reports)):
        report = record.get("content", record.get("report", record))
        source = report.get("source_module_revisions")
        if record.get("outdated") is True or (source is not None and source != item.get("module_revisions", {})):
            st.warning("This report was saved before the current task results changed. Prepare a new summary for the current visit.")
        st.write(report.get("patient_summary", ""))
        if actor()["role"] == "clinician":
            st.subheader("Clinician summary")
            st.write(report.get("clinician_summary", ""))
            with st.expander("Evidence, uncertainty and workflow"):
                st.json({k: report.get(k) for k in ["explanation", "fusion", "baseline", "evidence", "stages", "safety"]})
        private_download("Download report (JSON)", json.dumps(report, ensure_ascii=False, indent=2), user=actor(), assessment_id=item["id"], file_name=f"assessment-{item['id']}-report.json", mime="application/json", key=f"report_{item['id']}_{index}")


STATUS_WORDS = {"draft": "In progress", "completed": "Completed", "abandoned": "Abandoned"}
REVIEW_WORDS = {"reviewed": "Reviewed", "pending": "Awaiting review"}
MED_WORDS = {"on": "ON", "wearing_off": "Wearing off", "off": "OFF", "unsure": "Not sure", "none": "No PD medicine"}


def _caseload(user):
    from backend.services.caseload import caseload_summary
    rows = caseload_summary(user["id"])
    if not rows:
        return
    waiting = sum(r["awaiting_review"] for r in rows)
    falls = sum(1 for r in rows if r["falls_14d"])
    cols = st.columns(3)
    cols[0].metric("Patients", len(rows))
    cols[1].metric("Visits awaiting review", waiting)
    cols[2].metric("Patients reporting falls (14 days)", falls)
    table = pd.DataFrame([{
        "Patient": r["full_name"] + ("" if r["active"] else " (inactive)"),
        "Last visit": _date_only(r["last_visit_at"]) if r["last_visit_at"] else "No visits",
        "Awaiting review": r["awaiting_review"],
        "Open visits": r["open_drafts"],
        "Last check-in": datetime.fromisoformat(r["last_checkin"]).strftime("%d %b %Y") if r["last_checkin"] else "None",
        "Falls (14 days)": r["falls_14d"],
        "Medicine at last visit": MED_WORDS.get(r["latest_medication_state"], "Not recorded"),
        "OFF / wearing off (7 days)": r.get("off_reports_7d", 0),
        "Next planned review": datetime.fromisoformat(r["next_review"]).strftime("%d %b %Y") if r["next_review"] else "—",
    } for r in sorted(rows, key=lambda r: (-r["awaiting_review"], -r["falls_14d"], r["full_name"]))])
    with st.expander("Caseload", expanded=True):
        st.caption("Sorted by visits awaiting review, then reported falls. Falls are the patient's own check-in answers.")
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Awaiting review": st.column_config.NumberColumn(format="%d"),
                                    "Falls (14 days)": st.column_config.NumberColumn(format="%d")})


def clinician_page():
    from app.components.visit_context_panel import describe
    from backend.services.visit_context import get_visit_context
    st.title("Clinician Dashboard")
    user = actor()
    _caseload(user)
    section_header("Patient review", "Choose a patient and visit to review recordings, answers and context.")
    pid = patient_id()
    if st.button("Patient check-ins & care team follow-up"):
        go(care_plan_page)
    items = history(pid)
    if not items:
        empty_state("No visits yet", "This patient has not recorded an assessment. Their check-ins and goals are on the follow-up page.")
        return
    item = select_visit(items)
    context = get_visit_context(user["id"], item["id"])
    overview, movement, speech, adl, clinical, explanation = st.tabs(["Overview", "Movement & 3D", "Voice / Speech", "Daily activities", "Clinical context", "Explanation"])
    with overview:
        reviewed = item.get("review_status") == "reviewed"
        status_row([(STATUS_WORDS.get(item["status"], item["status"].title()), "care" if item["status"] == "completed" else "waiting"),
                    (REVIEW_WORDS.get(item.get("review_status"), "Awaiting review"), "care" if reviewed else "waiting")])
        st.write(f"Visit started {time_label(item['created_at'])}.")
        tasks = [LABELS.get(t, t) for t in item.get("modules", {})]
        st.write("Saved tasks: " + (", ".join(tasks) if tasks else "none yet") + ".")
        st.write("Medicine timing (patient-reported): " + (describe(context) or "not recorded") + ".")
        from app.components.visit_context_panel import describe_assistance
        from backend.services.visit_context import get_visit_assistance
        st.write("Help and walking aid (patient-reported): " + (describe_assistance(get_visit_assistance(user["id"], item["id"])) or "not recorded") + ".")
        if context and context.get("note"):
            st.caption("Patient's medicine note: " + plain_text(context["note"]))
        st.caption("Unrecorded modalities contribute no measurement or model output.")
        with st.form("clinical_review"):
            note = st.text_area("Review note", max_chars=3000)
            if st.form_submit_button("Mark reviewed", disabled=item["status"] == "abandoned"):
                services.review_assessment(actor()["id"], item["id"], note=note)
                st.success("Clinician review saved.")
    with movement:
        for task, result in item.get("modules", {}).items():
            if task in INSTRUCTIONS:
                with st.expander(LABELS[task]):
                    path = module_media_path(item, task)
                    review_result(result, task, baseline_for(task, item["id"], pid), media_path=path, history_items=items, identity=f"clinician_{item['id']}_{task}", assessment_id=item["id"])
                    if path:
                        with st.expander("Original recording"):
                            media = next((f for f in item.get("files", []) if f["storage_key"] == result.get("media_path")), None)
                            if media is None:
                                media = next((f for f in item.get("files", []) if f["id"] == item.get("module_file_ids", {}).get(task)), None)
                            if media:
                                private_player(actor(), item, media)
    with speech:
        for task, result in item.get("modules", {}).items():
            if task.startswith("voice") or task == "nlp":
                st.subheader(task.replace("_", " ").title())
                review_result(result, task, history_items=items, identity=f"clinician_{item['id']}_{task}")
                if task == "nlp":
                    st.json(result.get("extractions", result))
    with adl:
        if "adl" in item.get("modules", {}):
            review_result(item["modules"]["adl"], "adl", history_items=items, identity=f"clinician_{item['id']}_adl")
    with clinical:
        st.caption("Clinician-entered context is stored separately from automated measurements.")
        if item.get("clinical_measurements"):
            st.dataframe(pd.DataFrame(item["clinical_measurements"])[["name", "value", "unit"]], hide_index=True)
        with st.form("clinical_context"):
            age = st.number_input("Age (years)", min_value=0, max_value=120, value=None)
            duration = st.number_input("Disease duration (years)", min_value=0.0, max_value=120.0, value=None)
            if st.form_submit_button("Save clinical context", disabled=item["status"] == "abandoned"):
                values = {name: {"value": value, "unit": "years"} for name, value in [("age_years", age), ("disease_duration_years", duration)] if value is not None}
                try:
                    services.save_clinical_measurements(actor()["id"], item["id"], values)
                    st.success("Clinical context saved.")
                except ValueError as exc:
                    st.error(str(exc))
    with explanation:
        from ml.inference import build_report
        prior = [v for v in items if v["created_at"] < item["created_at"] and v["status"] != "abandoned"]
        report = build_report(item.get("modules", {}), prior, "English")
        st.write(report.get("clinician_summary", ""))
        st.json(report.get("explanation", {}))
        st.caption("Clinical prediction and calibrated model uncertainty require a validated model artifact. Current summaries use measured changes only.")


def profile_page():
    user = actor()
    ui_language = _patient_surface(user)
    st.title(text("profile", ui_language))
    st.write(user["email"])
    with st.form("profile"):
        name = st.text_input(text("full_name", ui_language), value=user["full_name"])
        language = st.selectbox(text("preferred_language", ui_language), LANGUAGES, index=LANGUAGES.index(user["language"]) if user["language"] in LANGUAGES else 0)
        if st.form_submit_button(text("save_profile", ui_language)):
            services.update_profile(user["id"], full_name=name, language=language)
            st.success(text("profile_saved", ui_language))
            if language != user["language"]:
                st.rerun()


def admin_page():
    st.title("Administration")
    user = actor()
    users, permissions, status, audit = st.tabs(["Users", "Permissions", "System Status", "Audit Logs"])
    records = services.list_users(user["id"])
    with users:
        cols = st.columns(3)
        cols[0].metric("Patients", sum(r["role"] == "patient" for r in records))
        cols[1].metric("Clinicians", sum(r["role"] == "clinician" for r in records))
        cols[2].metric("Inactive accounts", sum(not r["active"] for r in records))
        st.dataframe(pd.DataFrame([{
            "Name": r["full_name"], "Email": r["email"], "Role": r["role"].title(), "Language": r["language"],
            "Status": "Active" if r["active"] else "Inactive", "Joined": _date_only(r.get("created_at")).strip("\u2066\u2069"),
        } for r in records]), hide_index=True, width="stretch")
        with st.form("staff"):
            st.subheader("Create care-team account")
            name = st.text_input("Staff full name")
            email = st.text_input("Staff email")
            password = st.text_input("Initial password", type="password")
            role = st.selectbox("Role", ["clinician", "admin"], format_func={"clinician": "Clinician", "admin": "Administrator"}.get)
            if st.form_submit_button("Create staff account"):
                try:
                    services.create_staff(user["id"], name, email, password, role=role)
                    st.success("Staff account created.")
                except ValueError as exc:
                    st.error(str(exc))
    with permissions:
        patients = [r for r in records if r["role"] == "patient"]
        clinicians = [r for r in records if r["role"] == "clinician"]
        if patients and clinicians:
            with st.form("links"):
                patient = st.selectbox("Patient account", patients, format_func=lambda r: r["full_name"])
                clinician = st.selectbox("Clinician account", clinicians, format_func=lambda r: r["full_name"])
                if st.form_submit_button("Assign care team"):
                    services.link_patient(user["id"], patient["patient_id"], clinician["clinician_id"])
                    st.success("Care-team assignment saved.")
        if records:
            target = st.selectbox("Manage account access", records, format_func=lambda r: f"{r['full_name']} ({r['role']})")
            if st.button("Deactivate" if target["active"] else "Activate", disabled=target["id"] == user["id"]):
                services.set_user_active(user["id"], target["id"], not target["active"])
                st.rerun()
    with status:
        info = services.system_status(user["id"])
        st.success(f"Database connected ({info['engine']})")
        st.write("Private media storage configured")
        model_dir = Path(__file__).resolve().parents[1] / "models" / "landmarks"
        st.write("Pose model: " + ("Installed" if (model_dir / "pose_landmarker_lite.task").exists() else "Not installed"))
        st.write("Hand model: " + ("Installed" if (model_dir / "hand_landmarker.task").exists() else "Not installed"))
        st.caption("No clinical prediction model, speech-recognition provider or approved evidence library is configured by default.")
    with audit:
        st.dataframe(pd.DataFrame(services.list_audit_logs(user["id"])), hide_index=True, width="stretch")
