"""Patient, clinician and administrator experiences over authorized services."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.components.design import brand_wordmark, empty_state, inject_styles, section_header, status_pill
from app.components.patient_language import (
    adl_choice, adl_label, camera_translations, configure_patient_language, hub_card, render_steps,
    resolved_language, task_label, text, voice_prompt, write_patient,
)
from backend import services
from backend.config import get_settings
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
    brand_wordmark()
    st.title("Movement, with everyday life in view")
    st.write("Record a task, tell your care team how the day felt, and return to your progress when you're ready.")
    st.caption("A local workspace for patient recordings and clinician review. Measurement summaries support discussion; diagnosis and treatment decisions belong with your clinician.")
    with st.container(border=True):
        st.subheader("Pehli dafa istemal kar rahe hain?")
        st.write("Pehle public example par tareeqa dekhein: **recording chunein → Analyze karein → graphs aur report kholein**.")
        if st.button("Try a public demo — bina login", key="open_public_demo", type="primary"):
            from app.components.public_demo import public_demo_page
            st.switch_page(st.Page(public_demo_page, title="Try a public demo", url_path="public-demo"))
        st.caption("Apni recording ke liye neeche login karein, phir Start Assessment → movement task → Upload ya Live Camera chunein.")
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


def patient_home():
    user = actor()
    language = _patient_surface(user)
    status_pill(text("home_status", language), "care")
    st.title(text("welcome", language, name=user['full_name']))
    write_patient(text("home_intro", language), language)
    items = history()
    cols = st.columns(3)
    cols[0].metric(text("assessments", language), len(items))
    cols[1].metric(text("completed", language), sum(i["status"] == "completed" for i in items))
    cols[2].metric(text("latest_visit", language), time_label(items[0]["created_at"]).split(",")[0] if items else text("no_visits", language))
    if st.button(text("start_resume", language), type="primary"):
        go(assessment_hub)
    if st.button(text("my_goals", language)):
        go(my_care_page)
    if items:
        section_header(text("recent_visits", language), text("visits_detail", language))
        from app.components.visit_summary import render_visit_summary
        render_visit_summary([{"visit": time_label(i["created_at"]), "status": i["status"],
                               "tasks_saved": len(i.get("modules", {})),
                               "review": "Reviewed" if i.get("review_status") == "reviewed" else "Awaiting review"}
                              for i in items[:5]], language)
    else:
        empty_state(text("first_visit", language), text("first_visit_detail", language))
    st.divider()
    section_header(text("day_note", language), text("day_note_detail", language))


def my_care_page():
    from app.components.care_panels import patient_care_panel
    user = actor()
    if user["role"] != "patient":
        raise PermissionError("This page is for your own patient care notes.")
    st.title("My Care")
    patient_care_panel(user)


def care_plan_page():
    from app.components.care_panels import clinician_care_panel
    user = actor()
    if user["role"] != "clinician":
        raise PermissionError("Care team follow-up is available to assigned clinicians.")
    st.title("Patient context & follow-up")
    clinician_care_panel(user, patient_id())


def assessment_hub():
    user = actor()
    language = _patient_surface(user)
    st.title(text("hub_title", language))
    write_patient(text("hub_intro", language), language)
    items = history()
    unfinished = [i for i in items if i["status"] not in {"completed", "abandoned"}]
    if st.button(text("new_assessment", language), type="primary"):
        item = services.create_assessment(user["id"])
        st.session_state.active_assessment_id = item["id"]
        st.rerun()
    if unfinished:
        selected = st.selectbox(text("resume_assessment", language), unfinished, format_func=lambda i: time_label(i["created_at"]))
        if st.button(text("resume_selected", language)):
            st.session_state.active_assessment_id = selected["id"]
            st.rerun()
    aid = st.session_state.get("active_assessment_id")
    if aid:
        item = services.get_assessment(user["id"], aid)
        status_pill(f"Visit · {time_label(item['created_at'])}")
        st.caption(text("tasks_saved", language, count=len(item.get('modules', {}))) + f" · {item['status'].title()}")
        cards = [
            ("gait", gait_page), ("hand", hand_page), ("transfer", transfer_page),
            ("reach", reach_page), ("voice", voice_page), ("adl", adl_page),
        ]
        for start in range(0, len(cards), 2):
            for col, (card_key, page) in zip(st.columns(2), cards[start:start+2]):
                title, detail = hub_card(card_key, language)
                with col, st.container(border=True):
                    st.subheader(title)
                    st.write(detail)
                    tasks = {gait_page: ["gait", "turning"], hand_page: ["finger_left", "finger_right", "hand_open_close"], transfer_page: ["sit_to_stand"], reach_page: ["reach", "grasp", "object_transfer"], voice_page: ["voice_vowel", "voice_sentence", "voice_natural", "nlp"], adl_page: ["adl"]}[page]
                    saved = sum(task in item.get("modules", {}) for task in tasks)
                    st.caption(text("saved_count", language, count=saved) if saved else text("ready", language))
                    if st.button(text("open_task", language, task=title), key=f"hub_open_{card_key}", width="stretch"):
                        go(page)
        if any(is_accepted(r) for r in item.get("modules", {}).values()) and item["status"] not in {"completed", "abandoned"}:
            if st.button(text("complete_assessment", language)):
                services.finish_assessment(user["id"], aid)
                st.session_state.pop("active_assessment_id", None)
                st.success(text("assessment_completed", language))
        with st.expander(text("restart_visit", language)):
            if st.checkbox(text("abandon_visit", language)) and st.button(text("restart_assessment", language)):
                fresh = services.restart_assessment(user["id"], aid)
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
    task = st.selectbox(text("movement_task", language), tasks, format_func=lambda value: task_label(value, language))
    st.title(task_label(task, language))
    st.session_state.current_step = 1
    render_steps(task, language)
    with st.expander(text("setup", language)):
        write_patient(text("setup_camera", language), language)
        write_patient(text("setup_stop", language), language)
        st.caption(text("quality_check", language))
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
        root = get_settings().storage_root / "capture"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        capture_key = f"capture_{item['id']}_{task}"
        if capture_key not in st.session_state:
            fd, path = tempfile.mkstemp(suffix=".avi", dir=root)
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
    identity = identity or (str(media_path) if media_path else hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()) + task
    render_guidance(result, task, language=actor()["language"], identity=f"{identity}_guidance")
    if accepted and result.get("landmark_frames"):
        from app.components.motion_studio import movement_studio
        movement_studio({**result, "task": task}, baseline={**baseline, "task": task} if baseline else None, identity=identity,
                        export_context={"user": actor(), "assessment_id": assessment_id} if assessment_id else None)
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
    write_patient(text("voice_setup", ui_language), ui_language)
    language = st.selectbox(text("speech_language", ui_language), LANGUAGES, index=LANGUAGES.index(actor()["language"]) if actor()["language"] in LANGUAGES else 0)
    task = st.selectbox(text("voice_task", ui_language), ["vowel", "sentence", "natural"], format_func=lambda value: text(value, ui_language))
    # A fixed sentence follows the recording language, even when interface
    # labels use a different saved profile language.
    write_patient(voice_prompt(task, language), resolved_language(language))
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
    selected = st.selectbox("Assessment", list(by_id), format_func=lambda visit_id: f"{time_label(by_id[visit_id]['created_at'])} · {by_id[visit_id]['status']} · {visit_id[:8]}")
    return services.get_assessment(actor()["id"], selected)


def results_page():
    st.title("My Results")
    visits = history()
    item = select_visit(visits)
    st.caption(f"Review status: {item.get('review_status', 'Awaiting clinician review')}")
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
    st.title("Progress over time")
    visits = history(patient_id())
    rows = []
    for visit in reversed(visits):
        if visit["status"] == "abandoned":
            continue
        for task, result in visit.get("modules", {}).items():
            if not is_accepted(result):
                continue
            for feature, value in result.get("features", {}).items():
                if isinstance(value, (float, int)):
                    rows.append({"Date": visit["created_at"], "Task": task, "Measure": feature, "Value": value, "Method": result.get("method", result.get("analysis_version", "Unspecified")), "Language": result.get("language", "Not applicable")})
    if not rows:
        st.info("Your accepted task measurements will appear here after you save a result.")
        return
    df = pd.DataFrame(rows)
    task = st.selectbox("Task", sorted(df.Task.unique()), format_func=lambda k: LABELS.get(k, k.replace("_", " ")))
    subset = df[df.Task == task]
    feature = st.selectbox("Measure", sorted(subset.Measure.unique()), format_func=lambda k: k.replace("_", " "))
    subset = subset[subset.Measure == feature].copy()
    if subset.Language.nunique() > 1:
        language = st.selectbox("Recording language", sorted(subset.Language.unique()))
        subset = subset[subset.Language == language]
    if subset.Method.nunique() > 1:
        st.caption("These results used different measurement methods. Choose one method for a consistent comparison.")
        method = st.selectbox("Measurement method", sorted(subset.Method.unique()))
        subset = subset[subset.Method == method]
    subset["Date"] = pd.to_datetime(subset["Date"], utc=True).dt.tz_convert("Asia/Karachi")
    from app.components.statistical_3d import module_statistics_panel
    current = next((visit["modules"][task] for visit in visits if visit.get("status") != "abandoned" and is_accepted(visit.get("modules", {}).get(task, {}))
                    and visit["modules"][task].get("method", visit["modules"][task].get("analysis_version", "Unspecified")) == subset.iloc[-1]["Method"]
                    and visit["modules"][task].get("language", "Not applicable") == subset.iloc[-1]["Language"]), None)
    if current:
        module_statistics_panel(current, task, identity=f"progress_{patient_id()}_{task}", history=visits, default_view="history")
    st.caption("Only accepted recordings from the same task are compared. Differences in camera position, language, task instructions or assistance can affect these measurements.")
    st.dataframe(subset[["Date", "Value"]], hide_index=True)


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


def clinician_page():
    st.title("Clinician Dashboard")
    pid = patient_id()
    if st.button("Patient check-ins & care team follow-up"):
        go(care_plan_page)
    items = history(pid)
    if not items:
        st.info("This patient has no assessments yet.")
        return
    item = select_visit(items)
    overview, movement, speech, adl, clinical, explanation = st.tabs(["Overview", "Movement & 3D", "Voice / Speech", "ADL", "Clinical context", "Explanation"])
    with overview:
        st.write(f"Assessment: {time_label(item['created_at'])}")
        st.write(f"Status: {item['status']} · Review: {item.get('review_status', 'pending')}")
        st.write("Available tasks: " + ", ".join(LABELS.get(t, t) for t in item.get("modules", {})))
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
        st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")
        with st.form("staff"):
            st.subheader("Create care-team account")
            name = st.text_input("Staff full name")
            email = st.text_input("Staff email")
            password = st.text_input("Initial password", type="password")
            role = st.selectbox("Role", ["clinician", "admin"])
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
