"""
Optional AI song identification — try to match track title (filename or YouTube title) to a known song.
Only called when user marks track as public; we use the title only (no lyrics).
"""

import json
import os
import re
from typing import Any


def _parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def identify_song(lyrics: str | None, filename: str | None) -> dict[str, str] | None:
    """
    If GEMINI_API_KEY is set and we have a title (filename), ask Gemini to identify the song.
    lyrics is ignored (kept for API compatibility). Returns { "title": "...", "artist": "..." } or None.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    if not filename and not lyrics:
        return None

    try:
        from google import genai
    except ImportError:
        return None

    hint = f"Track title or filename: {filename}" if filename else (f"Lyrics (excerpt):\n{(lyrics or '')[:2000]}" if lyrics else "")
    if not hint.strip():
        return None

    prompt = f"""Given the following information about an audio file, identify the song if it is a known release.
{hint}

Respond with ONLY a JSON object: {{ "title": "Song title", "artist": "Artist name" }}
If you cannot identify the song with confidence, respond: {{ "title": null, "artist": null }}
No other text, no markdown."""

    try:
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(model=model, contents=prompt)
        text = response.text if hasattr(response, "text") else (
            response.candidates[0].content.parts[0].text if response.candidates else ""
        )
        if not text:
            return None
        data = _parse_json(text)
        if not data or data.get("title") is None or data.get("artist") is None:
            return None
        return {"title": str(data.get("title", "")), "artist": str(data.get("artist", ""))}
    except Exception:
        return None
