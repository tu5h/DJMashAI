"""
Stem-aware transition plan — AI decides per-stem fade schedule so vocals don't overlap and beats align.
"""

import json
import os
import re
from typing import Any

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _build_stem_prompt(crossfade_duration_sec: float, bpm_a: float, bpm_b: float, style: str = "club") -> str:
    return f"""You are a DJ transition planner. We have two tracks (A and B), each split into 4 stems: vocals, drums, bass, other.

Transition window: {crossfade_duration_sec:.0f} seconds total. During this time we mix from track A (outgoing) to track B (incoming).
Track A BPM: {bpm_a:.0f}. Track B BPM: {bpm_b:.0f}. Mix style: {style}.

Rules:
1. **Vocals must NOT overlap**: Fade out A's vocals completely BEFORE bringing B's vocals in. E.g. A vocals fade 0-4s, B vocals start at 4s and fade in 4-8s.
2. **Drums**: Can crossfade at beat (e.g. swap around midpoint) or short overlap; avoid two kick patterns at once for long.
3. **Bass**: Swap at phrase or midpoint; avoid long overlap of two bass lines.
4. **Other**: Can crossfade over the window.

Output a JSON object with exactly these keys (all times in seconds, 0 = start of transition):
- vocals_a_fade_start, vocals_a_fade_duration (when to start fading A vocals out, over how many sec)
- vocals_b_fade_start, vocals_b_fade_duration (when to start fading B vocals in, over how many sec)
- drums_a_fade_start, drums_a_fade_duration
- drums_b_fade_start, drums_b_fade_duration
- bass_a_fade_start, bass_a_fade_duration
- bass_b_fade_start, bass_b_fade_duration
- other_a_fade_start, other_a_fade_duration
- other_b_fade_start, other_b_fade_duration

Ensure: vocals_a is silent by the time vocals_b starts (vocals_a_fade_start + vocals_a_fade_duration <= vocals_b_fade_start).
All values must be >= 0 and within [0, {crossfade_duration_sec:.0f}].
Output ONLY the JSON object, no markdown."""


def _parse_stem_json(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def plan_stem_transition(
    crossfade_duration_sec: float,
    bpm_a: float,
    bpm_b: float,
    style: str = "club",
) -> dict[str, Any]:
    """
    Call Gemini to get per-stem fade schedule (no vocal overlap, drums/bass aligned).
    Returns dict with keys like vocals_a_fade_start, vocals_a_fade_duration, vocals_b_fade_start, ...
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    try:
        from google import genai
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai") from None

    client = genai.Client(api_key=api_key)
    prompt = _build_stem_prompt(crossfade_duration_sec, bpm_a, bpm_b, style)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    raw = response.text if hasattr(response, "text") else (response.candidates[0].content.parts[0].text if response.candidates else "")
    if not raw:
        raise ValueError("Gemini returned empty stem transition response")
    data = _parse_stem_json(raw)
    # Clamp to transition window
    t_max = crossfade_duration_sec
    for k, v in data.items():
        if isinstance(v, (int, float)):
            data[k] = max(0.0, min(t_max, float(v)))
    return data
