"""Abandoned live-camera clips are removed; anything else in private storage is left alone."""
import os
import time

from backend.storage import CAPTURE_MAX_AGE_SECONDS, capture_root, sweep_stale_captures


def _aged(path, seconds):
    moment = time.time() - seconds
    os.utime(path, (moment, moment))
    return path


def test_only_old_app_clips_are_swept(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    root = capture_root()
    assert oct(root.stat().st_mode & 0o777) == "0o700"
    stale = root / "tmpold.avi"
    stale.write_bytes(b"clip")
    _aged(stale, CAPTURE_MAX_AGE_SECONDS + 60)
    empty = root / "tmpempty.avi"
    empty.touch()
    _aged(empty, CAPTURE_MAX_AGE_SECONDS * 3)
    fresh = root / "tmpfresh.avi"
    fresh.write_bytes(b"recording now")
    foreign = root / "notes.txt"
    foreign.write_text("not a capture")
    _aged(foreign, CAPTURE_MAX_AGE_SECONDS * 3)
    outside = tmp_path / "outside.avi"
    outside.write_bytes(b"elsewhere")
    _aged(outside, CAPTURE_MAX_AGE_SECONDS * 3)
    link = root / "tmplink.avi"
    link.symlink_to(outside)

    assert sweep_stale_captures() == 2
    assert not stale.exists() and not empty.exists()
    assert fresh.exists() and foreign.exists() and link.is_symlink() and outside.exists()


def test_sweep_threshold_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("PARKINSENSE_STORAGE_ROOT", str(tmp_path / "private"))
    clip = capture_root() / "tmpclip.avi"
    clip.write_bytes(b"clip")
    assert sweep_stale_captures(max_age_seconds=3600) == 0
    assert sweep_stale_captures(max_age_seconds=3600, now=time.time() + 7200) == 1
    assert not clip.exists()
