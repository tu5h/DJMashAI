"""
Vocal phrase boundaries via speech-to-text (Whisper).
Used to pick transition points so phrases link: outgoing ends at phrase end, incoming reaches full at phrase start.
Full segments with text enable word-matching across tracks (any phrase in A with matching word in B).
"""

from pathlib import Path


def get_vocal_segments(audio_path: str | Path) -> list[dict]:
    """
    Transcribe audio with Whisper and return segments with text and timings.
    Each segment: {"start": float, "end": float, "text": str}.
    Returns [] if Whisper is not installed or transcription fails.
    """
    try:
        import whisper
    except ImportError:
        return []

    path = Path(audio_path)
    if not path.is_file():
        return []

    try:
        model = whisper.load_model("base")
        result = model.transcribe(str(path), word_timestamps=False, language=None, fp16=False)
    except Exception:
        return []

    segments: list[dict] = []
    for seg in result.get("segments", []):
        s, e = seg.get("start"), seg.get("end")
        text = (seg.get("text") or "").strip()
        if s is not None and isinstance(s, (int, float)) and e is not None and isinstance(e, (int, float)):
            segments.append({"start": float(s), "end": float(e), "text": text})
    return segments


def get_vocal_phrase_boundaries(audio_path: str | Path) -> tuple[list[float], list[float]]:
    """
    Transcribe audio with Whisper and return (phrase_starts, phrase_ends) in seconds.
    - phrase_ends: times where a vocal phrase ends (snap outgoing track end here).
    - phrase_starts: times where a vocal phrase starts (snap crossfade end so incoming track is at phrase start).
    Returns ([], []) if Whisper is not installed or transcription fails.
    """
    segments = get_vocal_segments(audio_path)
    if not segments:
        return ([], [])
    starts = sorted({seg["start"] for seg in segments})
    ends = sorted({seg["end"] for seg in segments})
    return (starts, ends)


def get_vocal_phrase_ends(audio_path: str | Path) -> list[float]:
    """Backward-compat: return only phrase end times."""
    _, ends = get_vocal_phrase_boundaries(audio_path)
    return ends
