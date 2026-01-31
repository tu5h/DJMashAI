"""
Audio feature extraction for DJMashAI.
Produces Track Feature Object (BPM, key, energy curve, intro/outro, drop regions).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import librosa
import numpy as np
from pydantic import BaseModel, Field

# Formats that often fail with librosa on Windows (need ffmpeg for audioread or conversion)
_FFMPEG_FALLBACK_EXTS = (".m4a", ".aac", ".webm", ".opus", ".mp4")


# Key names for chroma-based key detection (C, C#, ... B)
KEY_NAMES = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
]
# Major/minor profile templates (simplified Krumhansl-Schmuckler style)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Camelot wheel for harmonic mixing: key name -> code (e.g. "8A" = compatible with 7A, 9A, 8B)
KEY_TO_CAMELOT: dict[str, str] = {
    "C major": "8B", "C minor": "5A", "C# major": "3B", "C# minor": "12A",
    "D major": "10B", "D minor": "7A", "D# major": "5B", "D# minor": "2A",
    "E major": "12B", "E minor": "9A", "F major": "7B", "F minor": "4A",
    "F# major": "2B", "F# minor": "11A", "G major": "9B", "G minor": "6A",
    "G# major": "4B", "G# minor": "1A", "A major": "11B", "A minor": "8A",
    "A# major": "6B", "A# minor": "3A", "B major": "1B", "B minor": "10A",
}


class TrackFeatureObject(BaseModel):
    """Track Feature Object — per-track analysis output (Features.md)."""
    bpm: float = Field(..., description="Detected tempo (BPM)")
    key: str = Field(..., description="Estimated musical key (e.g. C major)")
    camelot_code: str = Field(..., description="Camelot code for harmonic mixing (e.g. 8A)")
    energy_score: float = Field(..., ge=0, le=1, description="Overall energy 0–1")
    energy_curve: list[float] = Field(..., description="Energy over time (normalized)")
    energy_segments: tuple[float, float, float] = Field(
        ..., description="Energy in first/mid/last third (0–1) for energy arc"
    )
    intro_window: tuple[float, float] = Field(..., description="(start_sec, end_sec) intro region")
    outro_window: tuple[float, float] = Field(..., description="(start_sec, end_sec) outro region")
    first_beat_sec: float = Field(..., description="Time of first strong beat (sec) for phrase alignment")
    drop_regions: list[tuple[float, float]] = Field(default_factory=list, description="(start_sec, end_sec) drop zones")
    duration_sec: float = Field(..., description="Track length in seconds")
    loudness_profile: str = Field(default="normal", description="Loudness character: quiet | normal | loud")
    vocal_phrase_ends: list[float] = Field(
        default_factory=list,
        description="Times (sec) where a vocal phrase ends, for clean transitions (no mid-word cut)",
    )
    vocal_phrase_starts: list[float] = Field(
        default_factory=list,
        description="Times (sec) where a vocal phrase starts, so incoming track links at phrase start",
    )
    vocal_segments: list[dict] = Field(
        default_factory=list,
        description="Full transcript segments: [{start, end, text}]; used for word-matching across tracks",
    )
    beat_times_sec: list[float] = Field(
        default_factory=list,
        description="All beat positions (sec) for beat-aligned transitions (AutoMasher-style extraction)",
    )
    chord_segments: list[dict] = Field(
        default_factory=list,
        description="Chord over time: [{start, end, chord}]; transition at chord change for cleaner handoffs",
    )


def _key_to_camelot(key: str) -> str:
    """Convert key string (e.g. 'C major') to Camelot code for harmonic mixing."""
    return KEY_TO_CAMELOT.get(key.strip(), "8A")


def _energy_segments(energy_curve: list[float]) -> tuple[float, float, float]:
    """Energy in first third, middle third, last third (0–1) for energy arc."""
    n = len(energy_curve)
    if n < 3:
        v = float(np.mean(energy_curve)) if energy_curve else 0.5
        return (v, v, v)
    curve = np.array(energy_curve, dtype=float)
    third = n // 3
    start = float(np.mean(curve[:third]))
    mid = float(np.mean(curve[third : 2 * third]))
    end = float(np.mean(curve[2 * third :]))
    return (round(min(1.0, max(0.0, start)), 4), round(min(1.0, max(0.0, mid)), 4), round(min(1.0, max(0.0, end)), 4))


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


def _chord_segments(y: np.ndarray, sr: int, hop_length: int, frame_dur: float, duration_sec: float) -> list[dict]:
    """
    Chroma-based chord segments over time (AutoMasher-style: chord labels for transition-at-chord-change).
    Returns [{start, end, chord}] with chord as root name (e.g. C, Am). Simple template matching per window.
    """
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    n_frames = chroma.shape[1]
    if n_frames < 4:
        return []
    # Segment by ~2 sec windows, get dominant chord per window
    window_frames = max(4, int(2.0 / frame_dur))
    segments: list[dict] = []
    prev_chord: str | None = None
    seg_start_sec = 0.0
    for i in range(0, n_frames, window_frames):
        end_i = min(i + window_frames, n_frames)
        chunk = chroma[:, i:end_i]
        mean_chroma = np.mean(chunk, axis=1)
        mean_chroma = mean_chroma / (np.linalg.norm(mean_chroma) + 1e-8)
        best_key = "C"
        best_corr = -2.0
        for k in range(12):
            major_rot = np.roll(MAJOR_PROFILE, k)
            minor_rot = np.roll(MINOR_PROFILE, k)
            major_rot = major_rot / (np.linalg.norm(major_rot) + 1e-8)
            minor_rot = minor_rot / (np.linalg.norm(minor_rot) + 1e-8)
            c_maj = np.corrcoef(mean_chroma, major_rot)[0, 1]
            c_min = np.corrcoef(mean_chroma, minor_rot)[0, 1]
            if c_maj > best_corr:
                best_corr = c_maj
                best_key = f"{KEY_NAMES[k]}"
            if c_min > best_corr:
                best_corr = c_min
                best_key = f"{KEY_NAMES[k]}m"
        start_sec = round(i * frame_dur, 1)
        end_sec = round(min((end_i) * frame_dur, duration_sec), 1)
        if prev_chord is None or best_key != prev_chord:
            if prev_chord is not None:
                segments[-1]["end"] = start_sec
            segments.append({"start": start_sec, "end": end_sec, "chord": best_key})
            prev_chord = best_key
        else:
            segments[-1]["end"] = end_sec
    return segments


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


def _load_audio(path: Path, sr: int = 22050) -> tuple[np.ndarray, int]:
    """
    Load audio file as (y, sr). For m4a/webm/opus on Windows, tries ffmpeg conversion
    if librosa fails (PySoundFile/audioread often need ffmpeg in PATH).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    try:
        y, loaded_sr = librosa.load(str(path), sr=sr, mono=True)
        return y, loaded_sr
    except Exception as load_err:
        ext = path.suffix.lower()
        if ext not in _FFMPEG_FALLBACK_EXTS:
            raise load_err

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError(
                "m4a/YouTube audio on Windows needs ffmpeg. Install ffmpeg and add its bin folder to PATH. "
                "See https://ffmpeg.org/download.html"
            ) from load_err

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    str(path),
                    "-ac",
                    "1",
                    "-ar",
                    str(sr),
                    "-f",
                    "wav",
                    wav_path,
                ],
                capture_output=True,
                check=True,
                timeout=120,
            )
            y, loaded_sr = librosa.load(wav_path, sr=sr, mono=True)
            return y, loaded_sr
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode("utf-8", errors="replace").strip() or "unknown"
            raise RuntimeError(
                f"ffmpeg failed to convert {path.suffix} to wav: {stderr}"
            ) from e
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg not found in PATH. Install ffmpeg and add its bin folder to PATH."
            ) from load_err
        finally:
            Path(wav_path).unlink(missing_ok=True)


def extract_track_features(audio_path: str | Path) -> TrackFeatureObject:
    """
    Load audio and extract Track Feature Object.
    Raises on invalid file or analysis failure.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    y, sr = _load_audio(path, sr=22050)
    duration_sec = float(librosa.get_duration(y=y, sr=sr))
    hop_length = 512

    # BPM and full beat grid (AutoMasher-style: beat_times_sec for beat-aligned transitions)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    bpm = float(tempo)
    frame_dur = hop_length / sr
    first_beat_sec = float(beat_frames[0] * frame_dur) if beat_frames is not None and len(beat_frames) > 0 else 0.0
    beat_times_sec = [round(float(f) * frame_dur, 2) for f in (beat_frames if beat_frames is not None else [])]

    # Key and Camelot
    key = _estimate_key(y, sr)
    camelot_code = _key_to_camelot(key)

    # Energy curve, score, and segments (first/mid/last third)
    energy_curve, energy_score = _energy_curve(y, sr, hop_length=hop_length)
    energy_segments = _energy_segments(energy_curve)

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

    # Chord segments (chroma-based, for transition-at-chord-change)
    chord_segments = _chord_segments(y, sr, hop_length, frame_dur, duration_sec)

    return TrackFeatureObject(
        bpm=bpm,
        key=key,
        camelot_code=camelot_code,
        energy_score=round(energy_score, 4),
        energy_curve=[round(x, 4) for x in energy_curve],
        energy_segments=energy_segments,
        intro_window=intro_window,
        outro_window=outro_window,
        first_beat_sec=round(first_beat_sec, 2),
        drop_regions=drop_regions,
        duration_sec=round(duration_sec, 2),
        loudness_profile=loudness_profile,
        beat_times_sec=beat_times_sec,
        chord_segments=chord_segments,
    )
