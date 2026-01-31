"""
Transition sound effects — whoosh, filter sweep, echo tail, vinyl scratch.
Generated so the mix feels like a real DJ (sweeps, hits, scratches at handoffs).
"""

import io
from typing import Literal

import numpy as np
from scipy import signal
from scipy.io import wavfile

SFX_TYPE = Literal["whoosh", "filter_sweep", "echo_tail", "vinyl_scratch", "none"]
SR = 44100


def _envelope(n: int, attack: float = 0.1, release: float = 0.3) -> np.ndarray:
    """Smooth envelope: attack (sec), release (sec)."""
    a_frames = int(attack * SR)
    r_frames = int(release * SR)
    env = np.ones(n, dtype=np.float32)
    if a_frames > 0 and n >= a_frames:
        env[:a_frames] = np.linspace(0, 1, a_frames)
    if r_frames > 0 and n > r_frames:
        env[-r_frames:] = np.linspace(1, 0, r_frames)
    return env


def _whoosh(duration_sec: float = 0.5) -> np.ndarray:
    """Filtered noise sweep (low→high then fade) — classic transition whoosh."""
    n = int(duration_sec * SR)
    noise = np.random.randn(n).astype(np.float32) * 0.5
    nyq = SR / 2
    # Single bandpass 400–6k Hz for whoosh body
    b, a = signal.butter(2, [400 / nyq, 6000 / nyq], btype="band")
    out = signal.filtfilt(b, a, noise)
    # Envelope: quick attack, longer release (opens then closes)
    env = _envelope(n, attack=0.03, release=duration_sec * 0.7)
    return (out * env * 0.45).astype(np.float32)


def _filter_sweep(duration_sec: float = 0.4) -> np.ndarray:
    """Low-pass opening: muffled → bright (filter sweep up)."""
    n = int(duration_sec * SR)
    noise = np.random.randn(n).astype(np.float32) * 0.35
    t = np.arange(n, dtype=np.float32) / SR
    nyq = SR / 2
    # Cutoff sweeps from 400 Hz to 12 kHz
    cutoff = 400 + (12000 - 400) * (t / duration_sec)
    out = np.zeros(n, dtype=np.float32)
    chunk = 1024
    for i in range(0, n, chunk):
        end = min(i + chunk, n)
        fc = float(min(cutoff[i], nyq - 100))
        b, a = signal.butter(2, fc / nyq, btype="low")
        segment = noise[i:end]
        if len(segment) >= 3:
            segment = signal.filtfilt(b, a, segment)
        out[i:end] = segment
    env = _envelope(n, attack=0.01, release=duration_sec * 0.5)
    return (out * env * 0.45).astype(np.float32)


def _echo_tail(duration_sec: float = 0.6) -> np.ndarray:
    """Short reverb-like tail: noise burst with exponential decay."""
    n = int(duration_sec * SR)
    noise = np.random.randn(n).astype(np.float32) * 0.25
    t = np.arange(n, dtype=np.float32) / SR
    decay = np.exp(-t * 8)
    b, a = signal.butter(2, [200 / (SR / 2), 6000 / (SR / 2)], btype="band")
    out = signal.filtfilt(b, a, noise * decay)
    env = _envelope(n, attack=0.005, release=duration_sec * 0.3)
    return (out * env * 0.5).astype(np.float32)


def _vinyl_scratch(duration_sec: float = 0.15) -> np.ndarray:
    """Short scratch: burst of filtered noise with pitch character."""
    n = int(duration_sec * SR)
    noise = np.random.randn(n).astype(np.float32) * 0.6
    # Bandpass around 1–4 kHz for "scratch" feel
    nyq = SR / 2
    b, a = signal.butter(2, [800 / nyq, 5000 / nyq], btype="band")
    out = signal.filtfilt(b, a, noise)
    env = _envelope(n, attack=0.005, release=duration_sec * 0.7)
    return (out * env * 0.4).astype(np.float32)


def generate_sound_effect(
    effect: str,
    duration_sec: float = 0.5,
    sample_rate: int = SR,
) -> bytes:
    """
    Generate a transition sound effect as WAV bytes.
    effect: whoosh, filter_sweep, echo_tail, vinyl_scratch, or none (returns silence).
    """
    if effect == "none" or not effect:
        n = int(duration_sec * sample_rate)
        return _wav_bytes(np.zeros(n, dtype=np.float32), sample_rate)
    effect = effect.lower().strip()
    if effect == "whoosh":
        mono = _whoosh(duration_sec)
    elif effect == "filter_sweep":
        mono = _filter_sweep(duration_sec)
    elif effect == "echo_tail":
        mono = _echo_tail(duration_sec)
    elif effect == "vinyl_scratch":
        mono = _vinyl_scratch(min(duration_sec, 0.2))
    else:
        mono = _whoosh(duration_sec)
    if sample_rate != SR:
        from scipy.signal import resample
        n_out = int(len(mono) * sample_rate / SR)
        mono = resample(mono, n_out).astype(np.float32)
    return _wav_bytes(mono, sample_rate)


def _wav_bytes(samples: np.ndarray, sr: int) -> bytes:
    """Float32 mono [-1,1] to WAV bytes."""
    buf = io.BytesIO()
    # scipy wavfile expects int16 for 16-bit
    int16 = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    wavfile.write(buf, sr, int16)
    return buf.getvalue()
