"""
AI mix intelligence — Gemini decides optimal track order and transition reasoning.
"""

import json
import os
import re
from typing import Any

from app.analysis.extractor import TrackFeatureObject


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _tracks_summary(tracks: list[TrackFeatureObject], track_names: list[str] | None) -> str:
    """Build a full summary of each track so the AI has all information for transition reasoning."""
    names = track_names or [f"Track {i + 1}" for i in range(len(tracks))]
    lines = []
    for i, (t, name) in enumerate(zip(tracks, names)):
        seg = getattr(t, "energy_segments", (t.energy_score, t.energy_score, t.energy_score))
        if isinstance(seg, (list, tuple)) and len(seg) >= 3:
            arc = f"arc start/mid/end={seg[0]:.2f}/{seg[1]:.2f}/{seg[2]:.2f}"
        else:
            arc = f"energy={t.energy_score:.2f}"
        intro_s, intro_e = t.intro_window[0], t.intro_window[1]
        outro_s, outro_e = t.outro_window[0], t.outro_window[1]
        intro = f"intro {intro_s:.0f}-{intro_e:.0f}s"
        outro = f"outro {outro_s:.0f}-{outro_e:.0f}s"
        first_beat = getattr(t, "first_beat_sec", 0)
        camelot = getattr(t, "camelot_code", "")
        drop_str = ""
        if t.drop_regions:
            drop_str = f", drops at {', '.join(f'{s:.0f}s' for s, _ in t.drop_regions[:3])}"
        # Vocal phrase boundaries: best cut points (we use these for quick, sharp handoffs)
        phrase_str = ""
        ends = getattr(t, "vocal_phrase_ends", None) or []
        starts = getattr(t, "vocal_phrase_starts", None) or []
        if ends or starts:
            in_outro_ends = [x for x in ends if outro_s <= x <= outro_e][:5]
            in_intro_starts = [x for x in starts if intro_s <= x <= intro_e][:5]
            if in_outro_ends:
                phrase_str = f", phrase_ends_in_outro={[round(x, 1) for x in in_outro_ends]}"
            if in_intro_starts:
                phrase_str += f", phrase_starts_in_intro={[round(x, 1) for x in in_intro_starts]}"
        # Beat grid and chord segments (AutoMasher-style: use for beat-aligned and chord-aware transitions)
        beat_str = ""
        beats = getattr(t, "beat_times_sec", None) or []
        if beats:
            in_outro_beats = [x for x in beats if outro_s <= x <= outro_e][:8]
            in_intro_beats = [x for x in beats if intro_s <= x <= intro_e][:8]
            if in_outro_beats or in_intro_beats:
                beat_str = f", beats_in_outro={[round(x, 1) for x in in_outro_beats][:5]}, beats_in_intro={[round(x, 1) for x in in_intro_beats][:5]}"
        chord_str = ""
        chords = getattr(t, "chord_segments", None) or []
        if chords:
            in_outro_chords = [c for c in chords if outro_s <= c.get("end", 0) <= outro_e][:3]
            in_intro_chords = [c for c in chords if intro_s <= c.get("start", 0) <= intro_e][:3]
            if in_outro_chords or in_intro_chords:
                chord_str = f", chords_outro={[c.get('chord') for c in in_outro_chords]}, chords_intro={[c.get('chord') for c in in_intro_chords]}"
        lines.append(
            f"  [{i}] {name}: BPM={t.bpm:.0f}, key={t.key} (Camelot {camelot}), {arc}, duration={t.duration_sec:.0f}s, "
            f"loudness={t.loudness_profile}, {intro}, {outro}, first_beat={first_beat:.1f}s{drop_str}{phrase_str}{beat_str}{chord_str}"
        )
    return "\n".join(lines)


def _build_prompt(tracks: list[TrackFeatureObject], style: str, track_names: list[str] | None) -> str:
    summary = _tracks_summary(tracks, track_names)
    return f"""You are a DJ mix planner. You have FULL information for each track below. Use ALL of it to decide optimal order and to write transition reasoning.

**Important: we use QUICK, SHARP transitions** — short crossfade (4–14 sec), decisive handoff. Tracks replace each other; we do NOT want long overlapping blends. Your reasoning should reflect: why this order gives a clean, punchy handoff (Camelot, energy flow, phrase boundaries), not long smooth blends.

Use this data when reasoning (use ALL of it — beat grid and chords improve transition quality):
- **Camelot code**: harmonic mixing — same code = same key; ±1 step or A↔B at same number = compatible. Prefer compatible keys for clean handoffs.
- **Energy arc (start/mid/end)**: flow energy across the set (e.g. build then release, or keep high for workout).
- **Intro/outro windows**: we cut out during current track's outro and bring next in during its intro. Transition is SHORT and sharp.
- **phrase_ends_in_outro / phrase_starts_in_intro**: exact times (sec) where vocals end/start — we snap transitions to these so we never cut mid-word. Prefer order that lets phrase boundaries line up.
- **beats_in_outro / beats_in_intro**: beat grid (sec) — we snap transitions to beats so handoffs are beat-aligned. Prefer order where beats line up across tracks.
- **chords_outro / chords_intro**: chord labels in outro/intro — we prefer cutting at chord changes; compatible chords across handoff sound better.
- **First beat (sec)**: phrase alignment — starting the next track on a phrase sounds cleaner.
- **Drops**: high-energy moments; avoid cutting through them; consider building to or from them.
- **BPM**: similar BPM or ±2–4% for pitch shift; large jumps need a quick cut, not a long blend.
- **Loudness**: match levels at handoff.

Mix style: {style}

Tracks (index, name, BPM, key, Camelot, energy arc, duration, loudness, intro/outro, first_beat, drops, phrase_ends_in_outro, phrase_starts_in_intro, beats_in_outro/intro, chords_outro/intro):
{summary}

For each transition you must also pick ONE short transition sound effect that a real DJ might use. Choose exactly one per transition from: whoosh, filter_sweep, echo_tail, vinyl_scratch, none. Use whoosh for smooth handoffs, filter_sweep for energy builds, echo_tail for dreamy transitions, vinyl_scratch for punchy cuts, none for no effect.

Respond with ONLY a single JSON object, no markdown or code fences, with this exact structure:
{{
  "order": [list of track indices in play order, e.g. [2, 0, 1]],
  "transition_reasoning": [list of strings, one per transition. For EACH transition use the data above: why this order gives a good QUICK handoff (Camelot, energy flow, intro/outro and phrase timing, BPM, style). Be specific: mention keys/Camelot, energy arc, phrase boundaries or timing. Same length as order minus 1.],
  "transition_sounds": [list of exactly one per transition from: whoosh, filter_sweep, echo_tail, vinyl_scratch, none. Same length as order minus 1.]
}}

Example: if order is [1, 0, 2], then transition_reasoning and transition_sounds each have 2 items.
Output only the JSON object."""


def _parse_gemini_json(text: str) -> dict[str, Any]:
    """Extract JSON from model response (may be wrapped in markdown)."""
    text = text.strip()
    # Remove markdown code block if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def plan_mix_order(
    tracks: list[TrackFeatureObject],
    style: str,
    track_names: list[str] | None = None,
) -> tuple[list[int], list[str]]:
    """
    Call Gemini to get optimal track order and per-transition reasoning.
    Returns (order, transition_reasoning).
    Raises if API key missing or response invalid.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    try:
        from google import genai
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai") from None

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(tracks, style, track_names)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    text = response.text if hasattr(response, "text") else (response.candidates[0].content.parts[0].text if response.candidates else "")
    if not text:
        raise ValueError("Gemini returned empty response")
    data = _parse_gemini_json(text)
    order = data.get("order")
    reasoning = data.get("transition_reasoning") or []
    if not isinstance(order, list) or len(order) != len(tracks):
        raise ValueError("Gemini returned invalid order: must be a permutation of track indices")
    order = [int(x) for x in order]
    if set(order) != set(range(len(tracks))):
        raise ValueError("Gemini returned invalid order: must be a permutation of track indices")
    if len(reasoning) != max(0, len(order) - 1):
        reasoning = list(reasoning) + [""] * max(0, len(order) - 1 - len(reasoning))
    n_trans = max(0, len(order) - 1)
    sounds = data.get("transition_sounds") or []
    if not isinstance(sounds, list) or len(sounds) != n_trans:
        sounds = ["whoosh"] * n_trans
    valid = {"whoosh", "filter_sweep", "echo_tail", "vinyl_scratch", "none"}
    sounds = [s if s in valid else "whoosh" for s in sounds[:n_trans]]
    return order, reasoning[:n_trans], sounds
