"""
Optional external analysis (AutoMasher-style / ChordMini API).
When enabled, enriches tracks with beat grid and chord segments from an external source
so transitions can use pop-trained chord/beat extraction for better mix quality.
"""

import os
from pathlib import Path
from typing import Any

from app.analysis.extractor import TrackFeatureObject


def enrich_track_from_external(audio_path: str | Path, features: TrackFeatureObject) -> TrackFeatureObject | None:
    """
    Optionally enrich track with beat_times_sec and chord_segments from external analysis.
    Set CHORDMINI_API_URL (e.g. https://api.chordmini.me/analyze) to POST audio and get
    { "beats": [sec,...], "chords": [{ "start", "end", "chord" },...] }.
    Or set EXTERNAL_BEAT_CHORD_SCRIPT to a script path that accepts audio path and prints JSON.
    Returns updated TrackFeatureObject or None if not configured or request fails.
    """
    api_url = os.getenv("CHORDMINI_API_URL", "").strip()
    script_path = os.getenv("EXTERNAL_BEAT_CHORD_SCRIPT", "").strip()
    if not api_url and not script_path:
        return None

    beats: list[float] = []
    chords: list[dict] = []

    if script_path:
        # Run local script (e.g. AutoMasher extraction wrapper): script <audio_path> -> JSON on stdout
        import json
        import subprocess
        path = Path(audio_path)
        if not path.is_file():
            return None
        try:
            out = subprocess.run(
                [script_path, str(path)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=path.parent,
            )
            if out.returncode != 0 or not out.stdout.strip():
                return None
            data = json.loads(out.stdout.strip())
            beats = data.get("beats") or data.get("beat_times_sec") or []
            chords = data.get("chords") or data.get("chord_segments") or []
        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

    elif api_url:
        # POST audio to ChordMini-style API (rate-limited; use sparingly)
        import httpx
        path = Path(audio_path)
        if not path.is_file():
            return None
        try:
            with open(path, "rb") as f:
                files = {"audio": (path.name, f, "audio/mpeg")}
                with httpx.Client(timeout=60) as client:
                    r = client.post(api_url, files=files)
            if r.status_code != 200:
                return None
            data = r.json()
            beats = data.get("beats") or data.get("beat_times_sec") or []
            chords = data.get("chords") or data.get("chord_segments") or []
        except (httpx.HTTPError, ValueError):
            return None

    # Normalize chord items to {start, end, chord}
    chord_segments_out: list[dict] = []
    for c in chords:
        if isinstance(c, dict) and "chord" in c:
            chord_segments_out.append({
                "start": float(c.get("start", 0)),
                "end": float(c.get("end", 0)),
                "chord": str(c.get("chord", "N")),
            })
    beat_times_sec = [float(b) for b in beats if isinstance(b, (int, float))]

    if not beat_times_sec and not chord_segments_out:
        return None

    update: dict[str, Any] = {}
    if beat_times_sec:
        update["beat_times_sec"] = beat_times_sec
    if chord_segments_out:
        update["chord_segments"] = chord_segments_out
    return features.model_copy(update=update)
