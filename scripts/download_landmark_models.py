"""Explicitly download the small official MediaPipe landmark model bundles.

Run `uv run python scripts/download_landmark_models.py`. No model or raw
patient recording is downloaded automatically while using the application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
import zipfile

MODEL_URLS = {
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
}


def download_models(directory: Path, force: bool = False) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"source": "Official Google MediaPipe models", "models": {}}
    for name, url in MODEL_URLS.items():
        target = directory / name
        if force or not target.exists():
            temporary = None
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "ParkinSense-PK-model-setup/1.0"})
                with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as handle:
                    temporary = Path(handle.name)
                    with urllib.request.urlopen(request, timeout=60) as response:
                        total = 0
                        while chunk := response.read(1024 * 1024):
                            total += len(chunk)
                            if total > 50 * 1024 * 1024:
                                raise ValueError("Unexpectedly large model bundle.")
                            handle.write(chunk)
                if not zipfile.is_zipfile(temporary):
                    raise ValueError("The downloaded file is not a MediaPipe task bundle.")
                with zipfile.ZipFile(temporary) as archive:
                    if not any(item.endswith(".tflite") for item in archive.namelist()) or archive.testzip():
                        raise ValueError("The model bundle is incomplete or corrupt.")
                os.replace(temporary, target)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
        if not zipfile.is_zipfile(target):
            raise ValueError(f"{name} is corrupt; rerun with --force.")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest["models"][name] = {"url": url, "sha256": digest, "bytes": target.stat().st_size}
        print(f"Ready: {name} ({target.stat().st_size / 1024 / 1024:.1f} MB), SHA-256 {digest}")
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "models" / "landmarks")
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    try:
        download_models(arguments.directory, arguments.force)
    except Exception as error:
        raise SystemExit(f"Model download failed: {error}. Check network access and rerun.")

