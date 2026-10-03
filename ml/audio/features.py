"""Local WAV quality checks and reproducible acoustic measurements.

These are engineered signal features, not validated Parkinson biomarkers. ASR,
jitter/shimmer and syllable-rate claims are deliberately absent without a
configured, validated provider. Original recordings are never rewritten.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal
from scipy.fft import dct

from ml.common.results import normalize_language

VERSION = "acoustic-features-1.0"
TASKS = {"natural", "vowel", "sentence"}


def _rejected(message: str, status: str = "repeat", **quality: Any) -> dict[str, Any]:
    return {"status": status, "quality": {"accepted": False, "messages": [message], **quality},
            "features": {}, "method": VERSION, "transcript": None,
            "asr": {"status": "unavailable", "reason": "No local ASR model configured. Enter a reviewed transcript."}}


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf
    with sf.SoundFile(path) as recording:
        if recording.format not in {"WAV", "WAVEX"}:
            raise ValueError("The audio container must be WAV.")
        if not 8000 <= recording.samplerate <= 192000:
            raise ValueError("Unsupported sample rate; use 8–192 kHz WAV audio.")
        if recording.frames / recording.samplerate > 180:
            raise ValueError("Recordings must be at most 180 seconds.")
        if recording.channels not in {1, 2}:
            raise ValueError("Use mono or stereo WAV audio.")
        return recording.read(dtype="float32", always_2d=True).mean(axis=1), recording.samplerate


def _mel_filterbank(sample_rate: int, n_fft: int, bands: int = 26) -> np.ndarray:
    mel_max = 2595 * np.log10(1 + sample_rate / 2 / 700)
    hz = 700 * (10 ** (np.linspace(0, mel_max, bands + 2) / 2595) - 1)
    bins = np.minimum(np.floor((n_fft + 1) * hz / sample_rate).astype(int), n_fft // 2)
    filters = np.zeros((bands, n_fft // 2 + 1))
    for index in range(bands):
        left, mid, right = bins[index:index + 3]
        if mid > left:
            filters[index, left:mid] = np.arange(mid - left) / (mid - left)
        if right > mid:
            filters[index, mid:right] = np.arange(right - mid, 0, -1) / (right - mid)
    return filters


def analyze_audio(path: str | Path, language: str = "english", task: str = "natural") -> dict[str, Any]:
    language = normalize_language(language)
    if task not in TASKS:
        raise ValueError("Audio task must be natural, vowel, or sentence.")
    path = Path(path)
    if path.suffix.lower() != ".wav":
        return _rejected("Use a WAV recording.")
    if not path.is_file() or path.stat().st_size == 0:
        return _rejected("Audio file is missing or empty.")
    if path.stat().st_size > 72 * 1024 * 1024:
        return _rejected("Audio file exceeds the 72 MB processing limit.")
    try:
        raw, source_rate = _read_wav(path)
    except ImportError:
        return _rejected("Install the soundfile audio dependency.", status="unavailable")
    except (ValueError, RuntimeError, OSError) as exc:
        return _rejected(f"Cannot decode WAV recording: {exc}")
    duration = len(raw) / source_rate
    if not np.all(np.isfinite(raw)):
        return _rejected("Recording contains invalid audio samples.")
    minimum = 2.0 if task == "vowel" else 3.0
    if duration < minimum:
        return _rejected(f"Record at least {minimum:g} seconds.", duration_seconds=duration)
    centered = raw - float(np.mean(raw))
    rms_original = float(np.sqrt(np.mean(centered ** 2)))
    clipping = float(np.mean(np.abs(raw) >= 0.999))
    if rms_original < 10 ** (-55 / 20):
        return _rejected("Recording is silent or too quiet. Move closer and record again.", duration_seconds=duration)
    if clipping > 0.01:
        return _rejected("Recording is clipping. Reduce microphone gain and record again.", clipping_fraction=clipping)

    rate = 16000
    common = int(np.gcd(source_rate, rate))
    wave = signal.resample_poly(centered, rate // common, source_rate // common).astype(np.float32)
    peak = float(np.max(np.abs(wave)))
    # A working copy only: DC removal, anti-aliased resampling, peak normalization.
    normalized = wave / max(peak, 1e-12) * 0.95
    window, hop, n_fft = 400, 160, 512
    frames = np.lib.stride_tricks.sliding_window_view(wave, window)[::hop]
    frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
    energy_threshold = max(10 ** (-50 / 20), float(np.percentile(frame_rms, 90)) * 0.15)
    active = frame_rms > energy_threshold
    active_fraction = float(np.mean(active))
    if active.sum() * hop / rate < 1.0:
        return _rejected("Less than one second of usable signal. Please repeat the task.", active_fraction=active_fraction)
    active_indices = np.flatnonzero(active)
    interior_silence = ~active[active_indices[0]:active_indices[-1] + 1]
    boundaries = np.diff(np.r_[False, interior_silence, False].astype(int))
    silence_lengths = np.flatnonzero(boundaries == -1) - np.flatnonzero(boundaries == 1)
    pauses = silence_lengths * hop / rate
    pauses = pauses[pauses >= 0.2]

    _, _, stft = signal.stft(normalized, fs=rate, nperseg=window, noverlap=window-hop,
                            nfft=n_fft, boundary=None, padded=False)
    power = np.abs(stft) ** 2
    spectrum = np.abs(stft)
    frequencies = np.fft.rfftfreq(n_fft, 1 / rate)
    energies = np.sum(spectrum, axis=0) + 1e-12
    centroid = np.sum(spectrum * frequencies[:, None], axis=0) / energies
    mel_energy = _mel_filterbank(rate, n_fft) @ power
    mfcc = dct(np.log(np.maximum(mel_energy, 1e-12)), type=2, axis=0, norm="ortho")[:13]
    # Autocorrelation estimate: reject weak periodicity rather than invent pitch.
    pitch_values = []
    pitch_strengths = []
    pitch_window = 640
    for start in range(0, len(wave) - pitch_window, hop * 3):
        segment = wave[start:start+pitch_window]
        if np.sqrt(np.mean(segment ** 2)) <= energy_threshold:
            continue
        segment = (segment - segment.mean()) * np.hanning(pitch_window)
        correlation = signal.correlate(segment, segment, mode="full", method="fft")[pitch_window - 1:]
        lo, hi = rate // 400, rate // 65
        # First strongest local peak avoids the zero-lag shoulder.
        peaks, _ = signal.find_peaks(correlation[lo:hi])
        if not len(peaks) or correlation[0] <= 0:
            continue
        candidates = peaks + lo
        lag = int(candidates[np.argmax(correlation[candidates])])
        strength = float(correlation[lag] / correlation[0])
        if strength >= 0.6:
            pitch_values.append(rate / lag)
            pitch_strengths.append(strength)

    features = {
        "duration_seconds": float(duration),
        "signal_rms_dbfs": float(20 * np.log10(max(rms_original, 1e-12))),
        "signal_active_fraction": active_fraction,
        "internal_pause_count": int(len(pauses)),
        "internal_pause_seconds": float(pauses.sum()),
        "spectral_centroid_mean_hz": float(centroid.mean()),
        "spectral_centroid_std_hz": float(centroid.std()),
        "clipping_fraction": clipping,
        **{f"mfcc_{i+1:02d}_mean": float(row.mean()) for i, row in enumerate(mfcc)},
    }
    if len(pitch_values) >= 5:
        features.update({"f0_autocorrelation_median_hz": float(np.median(pitch_values)),
                         "f0_autocorrelation_std_hz": float(np.std(pitch_values)),
                         "f0_periodicity_mean": float(np.mean(pitch_strengths))})
    return {
        "status": "accepted", "task": f"audio_{task}", "language": language,
        "quality": {"accepted": True, "messages": ["Usable audio signal; confirm the selected speech task was completed."],
                    "duration_seconds": duration, "active_fraction": active_fraction,
                    "clipping_fraction": clipping, "source_sample_rate": source_rate,
                    "task_completion": "requires_human_confirmation", "speech_presence": "signal_activity_proxy"},
        "features": features, "method": VERSION, "transcript": None,
        "asr": {"status": "unavailable", "reason": "No local ASR model configured. Enter a reviewed transcript."},
        "provenance": {"source": "local_wav_measurement", "processed_sample_rate": rate,
                       "preprocessing": ["DC removal", "polyphase resampling", "working-copy peak normalization"],
                       "feature_units": {"mfcc": "log-mel DCT units", "pitch": "Hz, autocorrelation estimate"}},
        "limitations": ["Acoustic measurements are not clinical scores.",
                        "Energy segmentation is not validated voice activity detection.",
                        "No speech rate, jitter, shimmer, transcription, or diagnosis is inferred.",
                        "Microphone, gain, room, task and distance affect comparison."],
    }
