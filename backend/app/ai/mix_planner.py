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
    """Build a short summary of each track for the prompt."""
    names = track_names or [f"Track {i + 1}" for i in range(len(tracks))]
    lines = []
    for i, (t, name) in enumerate(zip(tracks, names)):
        lines.append(
            f"  [{i}] {name}: BPM={t.bpm:.0f}, key={t.key}, energy={t.energy_score:.2f}, "
            f"duration={t.duration_sec:.0f}s, loudness={t.loudness_profile}"
        )
    return "\n".join(lines)


def _build_prompt(tracks: list[TrackFeatureObject], style: str, track_names: list[str] | None) -> str:
    summary = _tracks_summary(tracks, track_names)
    return f"""You are a DJ mix planner. Given the following analyzed tracks and the requested mix style, output the optimal play order and a short reasoning for each transition.

Mix style: {style}

Tracks (index, name, BPM, key, energy 0-1, duration, loudness):
{summary}

Respond with ONLY a single JSON object, no markdown or code fences, with this exact structure:
{{
  "order": [list of track indices in play order, e.g. [2, 0, 1]],
  "transition_reasoning": [list of strings, one per transition: why the next track follows the previous. Same length as order minus 1. Be brief: BPM/key/energy reasons.]
}}

Example: if order is [1, 0, 2], then transition_reasoning has 2 items: why track 0 follows 1, then why track 2 follows 0.
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
    return order, reasoning[: len(order) - 1]
