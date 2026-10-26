"""A public-video demonstration with no patient, database, or account access.

Only clips explicitly listed in the operator's local catalogue are available.
The catalogue and video hashes are verified before showing or analysing media;
the browser cannot supply a filesystem path or upload a personal recording here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

import streamlit as st

from ml.vision.pipeline import CVError, MAX_VIDEO_BYTES, SUPPORTED_EXTENSIONS, analysis_version, analyze_video
from ml.vision.tasks import TASKS
from ml.audio import analyze_audio
from ml.audio.features import VERSION as AUDIO_VERSION

DEMO_TASKS = {**TASKS, "voice_natural": {"label": "Voice · natural speech"}}

DEMO_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "clinical-video-check-2026-10-16"
MANIFEST_NAME = "demo_manifest.json"
RESULT_KEY = "public_demo_analysis"


class DemoCatalogError(ValueError):
    """A fixed, public-safe message about an unavailable demo catalogue."""


def _url(value):
    try:
        parsed = urlsplit(value) if isinstance(value, str) else None
        return value if parsed and parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username and not parsed.password else ""
    except ValueError:
        return ""


def _text(row, field, *, required=False):
    value = row.get(field, "")
    if not isinstance(value, str) or len(value) > 3000 or (required and not value.strip()):
        raise DemoCatalogError("A demonstration source entry is incomplete. Ask the app operator to check its catalogue.")
    return value.strip()


def load_demo_clips(root: Path | None = None) -> list[dict]:
    """Load only bounded, hash-matched videos inside the dedicated demo folder."""
    root = Path(root or DEMO_ROOT).resolve()
    manifest = root / MANIFEST_NAME
    try:
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 128 * 1024:
            raise DemoCatalogError("Public demonstration videos are not installed yet. Ask the app operator to prepare the public video examples.")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        rows = data.get("clips") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
            raise DemoCatalogError("The public demonstration catalogue needs at least one valid video example.")
        clips, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise DemoCatalogError("A demonstration source entry is incomplete. Ask the app operator to check its catalogue.")
            clip = {field: _text(row, field, required=field in {"id", "title", "task", "path", "sha256", "source_url", "context", "license"})
                    for field in ("id", "title", "task", "path", "sha256", "source_url", "source_title", "context", "license", "license_url", "creator", "changes")}
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", clip["id"]) or clip["id"] in seen or clip["task"] not in DEMO_TASKS:
                raise DemoCatalogError("A demonstration source entry has an invalid identifier or movement task.")
            seen.add(clip["id"])
            if not _url(clip["source_url"]) or (clip["license_url"] and not _url(clip["license_url"])):
                raise DemoCatalogError("A demonstration source has an invalid attribution link.")
            candidate = Path(clip["path"])
            path = (candidate if candidate.is_absolute() else root / candidate).resolve()
            audio = clip["task"] == "voice_natural"
            extensions = {".wav"} if audio else SUPPORTED_EXTENSIONS
            size_limit = 72 * 1024 * 1024 if audio else MAX_VIDEO_BYTES
            if not path.is_relative_to(root) or path.suffix.lower() not in extensions or not path.is_file():
                raise DemoCatalogError("A public demonstration video is unavailable in the designated demo folder.")
            if not 128 <= path.stat().st_size <= size_limit or not re.fullmatch(r"[a-fA-F0-9]{64}", clip["sha256"]):
                raise DemoCatalogError("A public demonstration video does not meet the size or integrity requirements.")
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != clip["sha256"].lower():
                raise DemoCatalogError("A public demonstration video has changed. Ask the app operator to verify its source before trying again.")
            clip["path"], clip["sha256"] = path, digest
            start, end = row.get("start_seconds"), row.get("end_seconds")
            if start is not None or end is not None:
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
                    raise DemoCatalogError("A demonstration video has an invalid source excerpt range.")
                clip.update(start_seconds=start, end_seconds=end)
            clips.append(clip)
        return clips
    except DemoCatalogError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise DemoCatalogError("The public demonstration catalogue could not be read. Ask the app operator to check its files.") from exc


def attribute_demo_html(document: str, clip: dict) -> str:
    """Keep source attribution attached when a public report or replay is saved."""
    source_url = _url(clip.get("source_url"))
    source = f'<a href="{escape(source_url, quote=True)}" rel="noopener noreferrer">{escape(clip.get("source_title") or clip["title"])}</a>' if source_url else escape(clip["title"])
    license_url = _url(clip.get("license_url"))
    license_text = escape(clip.get("license", ""))
    license_note = f'<a href="{escape(license_url, quote=True)}" rel="noopener noreferrer">{license_text}</a>' if license_url else license_text
    excerpt = (f"Source excerpt: {clip['start_seconds']:g}–{clip['end_seconds']:g} seconds. " if "start_seconds" in clip else "")
    banner = ("<aside style=\"border:2px solid #1D6B52;padding:20px;margin:20px\">"
              "<h1>Public recording demonstration</h1><p>This is a software demonstration using a published recording. "
              "It is not a patient record, a diagnosis, or an independent validation of measurement accuracy.</p>"
              f"<p><strong>Source:</strong> {source}</p><p>{escape(clip.get('context', ''))}</p>"
              f"<p><strong>Creator:</strong> {escape(clip.get('creator', ''))} · <strong>Licence:</strong> {license_note}</p>"
              f"<p>{escape(excerpt + clip.get('changes', ''))}</p>"
              f"<p>Recording SHA-256: <code>{escape(clip.get('sha256', ''))}</code></p></aside>")
    return re.sub(r"(<body\b[^>]*>)", lambda match: match.group(1) + banner, document, count=1)


def demo_report_html(clip: dict, result: dict, *, language="English") -> str:
    """Reuse the clinical report formatter, with unmistakable demo attribution."""
    from ml.inference.patient_report import build_patient_report, render_patient_report_html

    report = build_patient_report({"id": "public-demo", "status": "draft", "report_type": "attempt_preview",
                                   "modules": {clip["task"]: result}, "module_revisions": {},
                                   "review_status": "pending"}, language=language)
    document = render_patient_report_html(report, patient_name="Public recording · demonstration")
    return attribute_demo_html(document, clip)


def public_demo_page():
    """Three explicit steps; results live only in this browser session."""
    st.title("Try a public recording demo")
    st.write("**1. Recording chunain → 2. Analyze karein → 3. Graphs aur report dekhein**")
    st.caption("Published recordings help you learn the app. No patient account or saved visit is created here.")
    language = st.selectbox("Guidance language / Rehnumai ki zaban", ["Roman Urdu", "English", "Urdu"], key="public_demo_language")
    try:
        clips = load_demo_clips()
    except DemoCatalogError as exc:
        st.session_state.pop(RESULT_KEY, None)
        st.info(str(exc))
        return
    by_id = {clip["id"]: clip for clip in clips}
    st.subheader("1. Choose a recording / Recording chunain")
    selected = st.selectbox("Public example", list(by_id), format_func=lambda value: by_id[value]["title"], key="public_demo_clip")
    clip = by_id[selected]
    # The task is chosen by the reviewed example catalogue, not guessed from a
    # publisher's disease label. This avoids inadvertently changing the test.
    task = clip["task"]
    audio = task == "voice_natural"
    stamp = f"{clip['id']}:{clip['sha256']}:{task}:{AUDIO_VERSION if audio else analysis_version(task)}"
    attempt = st.session_state.get(RESULT_KEY)
    if attempt and attempt.get("stamp") != stamp:
        st.session_state.pop(RESULT_KEY, None)
        st.session_state.pop("public_demo_replay", None)
        attempt = None
    st.write(f"**Assessment task:** {DEMO_TASKS[task]['label']}")
    if audio:
        st.audio(str(clip["path"]), format="audio/wav")
    else:
        st.video(str(clip["path"]))
    st.write(clip["context"])
    st.link_button("Open the published source", clip["source_url"])
    st.caption(f"Creator: {clip['creator'] or 'See published source'} · Licence: {clip['license']}")
    if clip["license_url"]:
        st.link_button("Read the source licence", clip["license_url"])
    if "start_seconds" in clip:
        st.caption(f"Source excerpt: {clip['start_seconds']:g}–{clip['end_seconds']:g} seconds. Playback starts at this excerpt's beginning.")
    if clip["changes"]:
        st.caption("Excerpt preparation: " + clip["changes"])
    st.subheader("2. Run the analysis / Analysis shuru karein")
    st.write("Press the button once and wait for the results below. App is recording ko locally process karegi.")
    if st.button("Analyze this recording", type="primary", key="public_demo_analyze"):
        from .analysis_feedback import failure_result
        with st.spinner("Processing recording… / Recording check ho rahi hai…"):
            try:
                result = analyze_audio(clip["path"], "English", "natural") if audio else analyze_video(clip["path"], task)
            except CVError as exc:
                result = failure_result(exc, task, language=language)
        attempt = {"stamp": stamp, "result": result, "analyzed_at": datetime.now(timezone.utc).isoformat()}
        st.session_state[RESULT_KEY] = attempt
    if not attempt:
        st.session_state.pop("public_demo_report_document", None)
        st.info("Ab 'Analyze this recording' dabayein. Result, graphs aur report yahin neeche nazar aayenge.")
        return
    result = attempt["result"]
    st.subheader("3. Review the result / Nateeja dekhein")
    quality = result.get("quality", {})
    if quality.get("accepted") is True:
        st.success("Recording quality passed · Recording measurement ke liye qabool hui.")
    else:
        st.warning("Recording needs attention · Neeche wajah aur agla qadam dekhein.")
    st.caption("Acceptance means the local recording checks passed. It does not establish a diagnosis or clinical accuracy.")
    from .patient_language import text
    st.info(text("task_review_required", language))
    cols = st.columns(3)
    if audio:
        features = result.get("features", {})
        duration = features.get("duration_seconds", quality.get("duration_seconds"))
        fraction = features.get("signal_active_fraction", quality.get("active_fraction"))
        cols[0].metric("Duration", f"{duration:.2f} s" if isinstance(duration, (int, float)) else "—")
        cols[1].metric("Signal active", f"{fraction:.0%}" if isinstance(fraction, (int, float)) else "—")
        cols[2].metric("Internal pauses", features.get("internal_pause_count", "—"))
        st.caption("Audio shows measured acoustic statistics. It does not produce body joints, automatic transcription or a diagnosis.")
    else:
        cols[0].metric("Tracked frames", quality.get("valid_frames", "—"))
        cols[1].metric("Frames checked", quality.get("sampled_frames", "—"))
        fraction = quality.get("valid_fraction")
        cols[2].metric("Tracking coverage", f"{fraction:.0%}" if isinstance(fraction, (int, float)) else "—")
    from .guidance_panel import render_guidance
    render_guidance(result, task, language=language, identity="public_demo_guidance")
    limitations = result.get("limitations", [])
    if limitations:
        st.markdown("#### Measurement notes / Pemaish ki wazahat")
        for limitation in limitations:
            st.info(str(limitation))
    from .pose_3d_viewer import CAMERAS, STYLES, build_motion_figure, build_motion_html, motion_frame_summary
    summary = motion_frame_summary(result)
    if summary["available"]:
        st.markdown("#### 3D movement replay")
        st.caption("Play se movement chalegi. Model ko drag karke ghumayein; time bar se kisi lamhe ko dekhein.")
        left, right = st.columns(2)
        camera = left.selectbox("Camera view", list(CAMERAS), index=list(CAMERAS).index("Isometric"), key="public_demo_camera")
        style = right.selectbox("Model style", STYLES, key="public_demo_style")
        speed = st.selectbox("Playback speed", [0.25, 0.5, 1.0, 2.0], index=2,
                             format_func=lambda value: f"{value:g}×", key="public_demo_speed")
        options = {"camera": camera, "style": style, "playback_speed": speed, "show_trails": True, "show_grid": True}
        st.plotly_chart(build_motion_figure(result, **options), width="stretch", theme=None, key="public_demo_3d", config={"displaylogo": False, "scrollZoom": True})
        st.caption(summary["note"])
        st.caption("Depth and scale are single-camera model estimates. This view shows tracked joints; it is not a body scan.")
        with st.expander("Download the public 3D replay"):
            if st.button("Prepare demo 3D replay", key="public_demo_prepare_replay"):
                st.session_state["public_demo_replay"] = {"stamp": (stamp, camera, style, speed), "html": attribute_demo_html(build_motion_html(result, **options), clip)}
            replay = st.session_state.get("public_demo_replay")
            if replay and replay.get("stamp") == (stamp, camera, style, speed):
                st.download_button("Download demo 3D replay", replay["html"], file_name="parkinsense-public-demo-3d.html", mime="text/html", key="public_demo_download_replay", on_click="ignore")
    elif not audio:
        st.info("Usable 3D joints were not found in this clip. Follow the recording guidance above.")
    from .statistical_3d import module_statistics_panel
    module_statistics_panel(result, task, identity="public-demo:" + stamp)
    st.markdown("#### Demo analysis report")
    from .report_document import session_report_html
    document = session_report_html("public_demo_report_document", {"clip": clip, "attempt": attempt, "language": language},
                                   lambda: demo_report_html(clip, result, language=language))
    st.write("Report yahin khol kar parhein, ya HTML file download karein. Download ki hui file browser mein khol kar Print → Save as PDF use karein.")
    st.download_button("Download demo report", document.encode("utf-8"),
                       file_name="parkinsense-public-demo-report.html", mime="text/html", key="public_demo_download_report", on_click="ignore")
    if st.button("Open report here / Report yahin kholein", key="public_demo_open_report"):
        st.session_state["public_demo_report_open"] = True
    if st.session_state.get("public_demo_report_open"):
        import streamlit.components.v1 as components
        components.html(document, height=720, scrolling=True)
    st.caption("Agar browser download block kare, Open report here use karein. HTML download ko PDF file samajh kar na kholein.")
    st.caption("Public demonstration only. To record your own task privately, return to the welcome page and sign in.")
