"""
Render a stem-aware transition: load stems, apply per-stem gain schedule, mix to one wav.
"""

from pathlib import Path
from typing import Any

import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None

STEM_NAMES = ("vocals", "drums", "bass", "other")


def _load_stem_segment(path: Path, start_sec: float, duration_sec: float, sr: int) -> tuple[np.ndarray, int]:
    """Load a segment of a stem wav; return (samples mono, actual_sr)."""
    if sf is None:
        raise ImportError("soundfile is required for stem rendering: pip install soundfile")
    data, file_sr = sf.read(str(path))
    if data.ndim == 2:
        data = data.mean(axis=1)
    start_samp = int(start_sec * file_sr)
    n_samp = int(duration_sec * file_sr)
    segment = data[start_samp : start_samp + n_samp]
    if file_sr != sr:
        from scipy import signal as scipy_signal
        num = int(len(segment) * sr / file_sr)
        segment = scipy_signal.resample(segment, min(num, int(duration_sec * sr) + 1))
    n_out = int(duration_sec * sr)
    segment = segment[:n_out]
    if len(segment) < n_out:
        segment = np.pad(segment.astype(np.float32), (0, n_out - len(segment)), mode="constant", constant_values=0)
    return segment.astype(np.float32), sr


def _gain_curve(n_samples: int, sr: int, fade_start_sec: float, fade_duration_sec: float, out: bool) -> np.ndarray:
    """out=True: 1 -> 0 over fade. out=False: 0 -> 1 over fade."""
    t = np.arange(n_samples, dtype=float) / sr
    gain = np.ones(n_samples)
    start = fade_start_sec
    end = fade_start_sec + fade_duration_sec
    if out:
        mask = t >= start
        gain[mask] = 1.0 - np.clip((t[mask] - start) / fade_duration_sec, 0, 1)
        gain[t >= end] = 0
    else:
        mask = t >= start
        gain[mask] = np.clip((t[mask] - start) / fade_duration_sec, 0, 1)
        gain[t >= end] = 1.0
    return gain


def render_stem_transition(
    stems_a: dict[str, Path],
    stems_b: dict[str, Path],
    schedule: dict[str, Any],
    transition_start_a_sec: float,
    crossfade_duration_sec: float,
    sr: int = 44100,
) -> tuple[bytes, int]:
    """
    Load stems for A (from transition_start_a_sec) and B (from 0), apply schedule gains, mix.
    Returns (wav_bytes, sample_rate). Schedule keys: vocals_a_fade_start, vocals_a_fade_duration, ...
    """
    if sf is None:
        raise ImportError("soundfile is required: pip install soundfile")
    n_samp = int(crossfade_duration_sec * sr)
    out = np.zeros(n_samp, dtype=np.float32)
    stem_srs: dict[str, int] = {}

    for name in STEM_NAMES:
        # Track A stem
        if name in stems_a:
            seg, seg_sr = _load_stem_segment(
                stems_a[name], transition_start_a_sec, crossfade_duration_sec, sr
            )
            stem_srs[name] = seg_sr
            key_start = f"{name}_a_fade_start"
            key_dur = f"{name}_a_fade_duration"
            start = float(schedule.get(key_start, 0))
            dur = float(schedule.get(key_dur, crossfade_duration_sec))
            gain = _gain_curve(n_samp, sr, start, max(0.01, dur), out=True)
            if len(seg) < n_samp:
                seg = np.pad(seg, (0, n_samp - len(seg)), mode="constant", constant_values=0)
            out += (seg[:n_samp].astype(np.float32) * gain).astype(np.float32)
        # Track B stem
        if name in stems_b:
            seg, seg_sr = _load_stem_segment(stems_b[name], 0.0, crossfade_duration_sec, sr)
            stem_srs[name] = seg_sr
            key_start = f"{name}_b_fade_start"
            key_dur = f"{name}_b_fade_duration"
            start = float(schedule.get(key_start, 0))
            dur = float(schedule.get(key_dur, crossfade_duration_sec))
            gain = _gain_curve(n_samp, sr, start, max(0.01, dur), out=False)
            if len(seg) < n_samp:
                seg = np.pad(seg, (0, n_samp - len(seg)), mode="constant", constant_values=0)
            out += (seg[:n_samp].astype(np.float32) * gain).astype(np.float32)

    # Normalize to avoid clipping
    peak = np.abs(out).max()
    if peak > 1e-6:
        out = out / peak * 0.95
    import io
    buf = io.BytesIO()
    sf.write(buf, out, sr, format="WAV")
    return buf.getvalue(), sr
