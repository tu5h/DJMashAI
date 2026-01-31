"""
Audio feature extraction for DJMashAI.
Produces Track Feature Object (BPM, key, energy curve, intro/outro, drop regions).
"""

from pathlib import Path
from typing import Any

import librosa
import numpy as np
from pydantic import BaseModel, Field


# Key names for chroma-based key detection (C, C#, ... B)
KEY_NAMES = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
]
# Major/minor profile templates (simplified Krumhansl-Schmuckler style)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class TrackFeatureObject(BaseModel):
    """Track Feature Object — per-track analysis output (Features.md)."""
    bpm: float = Field(..., description="Detected tempo (BPM)")
    key: str = Field(..., description="Estimated musical key (e.g. C major)")
    energy_score: float = Field(..., ge=0, le=1, description="Overall energy 0–1")
    energy_curve: list[float] = Field(..., description="Energy over time (normalized)")
    intro_window: tuple[float, float] = Field(..., description="(start_sec, end_sec) intro region")
    outro_window: tuple[float, float] = Field(..., description="(start_sec, end_sec) outro region")
    drop_regions: list[tuple[float, float]] = Field(default_factory=list, description="(start_sec, end_sec) drop zones")
    duration_sec: float = Field(..., description="Track length in seconds")
    loudness_profile: str = Field(default="normal", description="Loudness character: quiet | normal | loud")


def _estimate_key(y: np.ndarray, sr: int) -> str:
    """Estimate key from chroma (simplified pitch-class profile)."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    chroma_mean = np.mean(chroma, axis=1)
    chroma_mean = chroma_mean / (np.linalg.norm(chroma_mean) + 1e-8)
    best_key = "C major"
    best_corr = -2.0
    for i in range(12):
        major_rot = np.roll(MAJOR_PROFILE, i)
        minor_rot = np.roll(MINOR_PROFILE, i)
        major_rot = major_rot / (np.linalg.norm(major_rot) + 1e-8)
        minor_rot = minor_rot / (np.linalg.norm(minor_rot) + 1e-8)
        c_maj = np.corrcoef(chroma_mean, major_rot)[0, 1]
        c_min = np.corrcoef(chroma_mean, minor_rot)[0, 1]
        if c_maj > best_corr:
            best_corr = c_maj
            best_key = f"{KEY_NAMES[i]} major"
        if c_min > best_corr:
            best_corr = c_min
            best_key = f"{KEY_NAMES[i]} minor"
    return best_key


def _energy_curve(y: np.ndarray, sr: int, hop_length: int = 512, n_bands: int = 20) -> tuple[list[float], float]:
    """Compute normalized energy curve and overall energy score (0–1)."""
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    # Smooth
    from scipy.ndimage import uniform_filter1d
    rms_smooth = uniform_filter1d(rms.astype(float), size=max(1, len(rms) // n_bands), mode="nearest")
    rms_min, rms_max = float(np.min(rms_smooth)), float(np.max(rms_smooth))
    if rms_max - rms_min < 1e-8:
        curve = [0.5] * len(rms_smooth)
        score = 0.5
    else:
        curve = ((rms_smooth - rms_min) / (rms_max - rms_min)).tolist()
        score = float(np.mean(rms_smooth))
        score = (score - rms_min) / (rms_max - rms_min + 1e-8)
    return curve, min(1.0, max(0.0, score))


def _intro_outro_windows(duration_sec: float, energy_curve: list[float], hop_length: int, sr: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """Estimate intro (low energy start) and outro (low energy end) windows."""
    n = len(energy_curve)
    if n < 4:
        return (0.0, min(15.0, duration_sec * 0.2)), (max(0, duration_sec - 15), duration_sec)
    frame_dur = hop_length / sr
    # Intro: first ~15–30 sec or until energy rises
    intro_frames = min(int(30 / frame_dur), n // 3)
    intro_energy = np.mean(energy_curve[:intro_frames]) if intro_frames else 0.5
    intro_end = min(30.0, duration_sec * 0.25)
    # Outro: last ~15–30 sec
    outro_start = max(0, duration_sec - 30)
    return (0.0, intro_end), (outro_start, duration_sec)


def _drop_regions(energy_curve: list[float], duration_sec: float, hop_length: int, sr: int) -> list[tuple[float, float]]:
    """Estimate drop-like regions (local energy peaks)."""
    from scipy.ndimage import uniform_filter1d
    from scipy.signal import find_peaks
    n = len(energy_curve)
    if n < 10:
        return []
    curve = np.array(energy_curve, dtype=float)
    smooth = uniform_filter1d(curve, size=max(3, n // 30), mode="nearest")
    peaks, _ = find_peaks(smooth, height=0.6, distance=max(5, n // 15))
    frame_dur = hop_length / sr
    regions: list[tuple[float, float]] = []
    for p in peaks[:10]:  # cap at 10 drops
        start_sec = max(0, (p - 8) * frame_dur)
        end_sec = min(duration_sec, (p + 8) * frame_dur)
        regions.append((float(start_sec), float(end_sec)))
    return regions


def extract_track_features(audio_path: str | Path) -> TrackFeatureObject:
    """
    Load audio and extract Track Feature Object.
    Raises on invalid file or analysis failure.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    y, sr = librosa.load(path, sr=22050, mono=True)
    duration_sec = float(librosa.get_duration(y=y, sr=sr))
    hop_length = 512

    # BPM
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    bpm = float(tempo)

    # Key
    key = _estimate_key(y, sr)

    # Energy curve and score
    energy_curve, energy_score = _energy_curve(y, sr, hop_length=hop_length)

    # Intro / outro
    intro_window, outro_window = _intro_outro_windows(duration_sec, energy_curve, hop_length, sr)

    # Drop regions
    drop_regions = _drop_regions(energy_curve, duration_sec, hop_length, sr)

    # Loudness (simple RMS-based)
    rms_mean = float(np.mean(librosa.feature.rms(y=y, hop_length=hop_length)))
    if rms_mean < 0.02:
        loudness_profile = "quiet"
    elif rms_mean > 0.15:
        loudness_profile = "loud"
    else:
        loudness_profile = "normal"

    return TrackFeatureObject(
        bpm=bpm,
        key=key,
        energy_score=round(energy_score, 4),
        energy_curve=[round(x, 4) for x in energy_curve],
        intro_window=intro_window,
        outro_window=outro_window,
        drop_regions=drop_regions,
        duration_sec=round(duration_sec, 2),
        loudness_profile=loudness_profile,
    )
