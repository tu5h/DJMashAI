"""
AI DJ MC commentary: Gemini generates short lines, ElevenLabs TTS.
"""

import base64
import json
import os
import re
from typing import Any

import httpx

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL_ID", "eleven_monolingual_v1")


def _build_commentary_prompt(ordered_track_names: list[str], transition_reasoning: list[str], style: str) -> str:
    lines = [f"  Track {i + 1}: {name}" for i, name in enumerate(ordered_track_names)]
    track_list = "\n".join(lines)
    trans_list = "\n".join([f"  After track {i + 1} → {i + 2}: {r}" for i, r in enumerate(transition_reasoning)])
    return f"""You are a DJ MC. Generate SHORT spoken commentary lines for this mix. Mix style: {style}.

Tracks in order:
{track_list}

Transition reasons (why each next track follows):
{trans_list}

Output a JSON array of commentary lines. Each item: {{ "label": "intro" | "transition_1" | "transition_2" | ... | "outro", "text": "short line to speak (one sentence, under 15 words)" }}.
Include exactly: 1 intro (hype the set), {len(transition_reasoning)} transition callouts (briefly mention the next track or vibe), 1 outro (wrap up). Keep every "text" under 15 words and punchy.
Output ONLY the JSON array, no markdown."""


def _parse_commentary_json(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def generate_commentary_text(
    ordered_track_names: list[str],
    transition_reasoning: list[str],
    style: str,
) -> list[dict[str, str]]:
    """Use Gemini to generate DJ commentary lines. Returns list of { label, text }."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    try:
        from google import genai
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai") from None

    client = genai.Client(api_key=api_key)
    prompt = _build_commentary_prompt(ordered_track_names, transition_reasoning, style)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    raw = response.text if hasattr(response, "text") else (response.candidates[0].content.parts[0].text if response.candidates else "")
    if not raw:
        raise ValueError("Gemini returned empty commentary response")
    items = _parse_commentary_json(raw)
    if not isinstance(items, list):
        items = [items]
    result = []
    for i, item in enumerate(items[: 2 + len(transition_reasoning)]):
        label = item.get("label") or f"line_{i}"
        text = (item.get("text") or "").strip() or "Next track."
        result.append({"label": str(label), "text": text})
    return result


def synthesize_speech(text: str, api_key: str, voice_id: str | None = None) -> bytes:
    """Call ElevenLabs TTS; returns MP3 bytes."""
    voice_id = voice_id or ELEVENLABS_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {"text": text, "model_id": ELEVENLABS_MODEL}
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content


def generate_commentary_audio(
    ordered_track_names: list[str],
    transition_reasoning: list[str],
    style: str,
) -> list[dict[str, Any]]:
    """
    Generate commentary lines (Gemini) and optionally TTS (ElevenLabs).
    Returns list of { label, text, audio_base64? }. audio_base64 only if ELEVENLABS_API_KEY is set.
    """
    lines = generate_commentary_text(ordered_track_names, transition_reasoning, style)
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID") or ELEVENLABS_VOICE_ID
    out = []
    for line in lines:
        label = line["label"]
        text = line["text"]
        audio_base64 = None
        if api_key and text:
            try:
                raw = synthesize_speech(text, api_key, voice_id)
                audio_base64 = base64.b64encode(raw).decode("ascii")
            except Exception:
                pass
        out.append({"label": label, "text": text, "audio_base64": audio_base64})
    return out
