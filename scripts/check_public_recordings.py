"""Re-run installed, attributed demos without touching patient records.

Usage: .venv/bin/python scripts/check_public_recordings.py
Outputs go to a new timestamped folder under artifacts/public-recording-checks.
Media installation and source/license details: docs/clinical-video-demo.md.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.components.public_demo import load_demo_clips, demo_report_html, attribute_demo_html
from app.components.pose_3d_viewer import build_motion_html, motion_frame_summary
from ml.audio import analyze_audio
from ml.vision.pipeline import analyze_video


def main():
    output = ROOT / "artifacts" / "public-recording-checks" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    summaries = []
    for clip in load_demo_clips():
        started = time.perf_counter()
        result = (analyze_audio(clip["path"], "English", "natural") if clip["task"] == "voice_natural"
                  else analyze_video(clip["path"], clip["task"]))
        folder = output / clip["id"]
        folder.mkdir()
        (folder / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        provenance = {**clip, "path": str(clip["path"].relative_to(ROOT))}
        (folder / "source.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / "report.html").write_text(demo_report_html(clip, result, language="Roman Urdu"), encoding="utf-8")
        if motion_frame_summary(result)["available"]:
            (folder / "replay.html").write_text(attribute_demo_html(build_motion_html(result), clip), encoding="utf-8")
        summary = {"id": clip["id"], "task": clip["task"], "sha256": clip["sha256"],
                   "method": result.get("analysis_version", result.get("method")),
                   "quality": result.get("quality"), "features": result.get("features"),
                   "limitations": result.get("limitations", []), "elapsed_s": round(time.perf_counter()-started, 2)}
        summaries.append(summary)
        (output / "results.json").write_text(json.dumps(summaries, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"id": clip["id"], "accepted": result["quality"]["accepted"], "output": str(folder)}), flush=True)
    print("Saved evidence: " + str(output), flush=True)


if __name__ == "__main__":
    main()
