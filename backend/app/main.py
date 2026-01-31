"""
DJMashAI Backend — FastAPI app.
Endpoints: /health, /analyze, /analyze-batch, /mix-plan.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.analysis import extract_track_features, TrackFeatureObject
from app.ai import plan_mix_order
from app.ai.song_identifier import identify_song
from app.planner import plan_transitions
from app.youtube import download_youtube_audio

load_dotenv()

MixStyle = Literal["club", "chill", "workout", "festival"]


class MixPlanRequest(BaseModel):
    tracks: list[TrackFeatureObject] = Field(..., min_length=2, description="Track Feature Objects (from /analyze)")
    style: MixStyle = Field(..., description="Mix style: club, chill, workout, festival")
    track_names: list[str] | None = Field(default=None, description="Optional names; same length as tracks")


class MixPlanResponse(BaseModel):
    order: list[int] = Field(..., description="Indices into tracks in play order")
    transitions: list[dict] = Field(..., description="Per-transition: start/end time, fade_curve, eq_strategy, reasoning_text")
    energy_curve: list[float] = Field(default_factory=list, description="Aggregated energy over mix (optional)")


class AnalyzeBatchOptions(BaseModel):
    lyrics: list[str | None] = Field(default_factory=list, description="Optional lyrics per track; same length as files")
    public: list[bool] = Field(default_factory=list, description="Per-track: allow AI to identify song; same length as files")


class AnalyzeBatchItem(BaseModel):
    features: TrackFeatureObject
    identified_song: dict[str, str] | None = Field(default=None, description="If public and identified: { title, artist }")
    is_public: bool = Field(default=False, description="Whether user allowed AI identification for this track")
    display_name: str | None = Field(default=None, description="Track name (filename or YouTube title)")

app = FastAPI(
    title="DJMashAI API",
    description="AI-powered DJ mix planning — analyze tracks, get mix order and transitions.",
    version="0.1.0",
)

# CORS for local frontend (Vite default 5173, Next 3000)
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").strip().split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Confirm API is running (local and deployed)."""
    return {"status": "ok", "service": "DJMashAI"}


@app.post("/analyze", response_model=TrackFeatureObject)
async def analyze_track(file: UploadFile = File(...)) -> TrackFeatureObject:
    """
    Upload one audio file; returns Track Feature Object (BPM, key, energy, intro/outro, drop regions).
    """
    if not file.filename or not file.filename.lower().endswith((".mp3", ".wav", ".m4a", ".flac", ".ogg")):
        raise HTTPException(400, "Expected audio file: .mp3, .wav, .m4a, .flac, .ogg")

    suffix = Path(file.filename).suffix or ".mp3"
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}") from e

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        result = extract_track_features(tmp_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}") from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/analyze-batch")
async def analyze_batch(
    files: list[UploadFile] = File(default=[]),
    layout: str | None = Form(default=None, description='JSON array: ["file"|"youtube", ...]'),
    urls: str | None = Form(default=None, description='JSON array of YouTube URLs for youtube slots'),
    options: str | None = Form(default=None, description='JSON: { "lyrics": [str|null], "public": [bool] }'),
) -> list[AnalyzeBatchItem]:
    """
    Upload audio files and/or YouTube URLs. Use layout to mix: e.g. ["youtube","file"] with urls and files.
    Optional per-track lyrics and public flag. Returns list of { features, identified_song?, is_public }.
    """
    layout_list: list[str] = []
    urls_list: list[str] = []
    if layout:
        try:
            layout_list = json.loads(layout)
            if not isinstance(layout_list, list) or not all(s in ("file", "youtube") for s in layout_list):
                raise ValueError("layout must be array of 'file' or 'youtube'")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(400, f"Invalid layout: {e}") from e
    if urls:
        try:
            urls_list = json.loads(urls)
            if not isinstance(urls_list, list):
                urls_list = []
        except json.JSONDecodeError:
            urls_list = []

    if layout_list:
        if layout_list.count("youtube") != len(urls_list):
            raise HTTPException(400, "Number of YouTube URLs must match youtube slots in layout.")
        if layout_list.count("file") != len(files):
            raise HTTPException(400, "Number of uploaded files must match file slots in layout.")
        if len(layout_list) > 20:
            raise HTTPException(400, "At most 20 tracks.")
    else:
        if not files or len(files) > 20:
            raise HTTPException(400, "Send 1–20 audio files, or use layout + urls for YouTube.")

    opts = AnalyzeBatchOptions(lyrics=[], public=[])
    if options:
        try:
            data = json.loads(options)
            opts = AnalyzeBatchOptions(
                lyrics=data.get("lyrics", []) or [],
                public=data.get("public", []) or [],
            )
        except (json.JSONDecodeError, Exception):
            pass

    slot_count = len(layout_list) if layout_list else len(files)
    if len(opts.lyrics) < slot_count:
        opts.lyrics = opts.lyrics + [None] * (slot_count - len(opts.lyrics))
    if len(opts.public) < slot_count:
        opts.public = opts.public + [False] * (slot_count - len(opts.public))
    opts.lyrics = opts.lyrics[:slot_count]
    opts.public = opts.public[:slot_count]

    paths_to_clean: list[str] = []
    tmp_dirs_to_clean: list[str] = []
    paths_and_names: list[tuple[str, str]] = []
    file_iter = iter(files) if files else iter([])
    url_iter = iter(urls_list) if urls_list else iter([])

    total = slot_count
    try:
        if layout_list:
            for i, kind in enumerate(layout_list):
                if kind == "youtube":
                    url = next(url_iter, "")
                    print(f"[DJMashAI] Downloading YouTube slot {i + 1}/{total}...", flush=True)
                    try:
                        path, display_name, tmpdir = download_youtube_audio(url)
                        paths_to_clean.append(path)
                        tmp_dirs_to_clean.append(tmpdir)
                        paths_and_names.append((path, display_name))
                        print(f"[DJMashAI] Downloaded slot {i + 1}/{total}.", flush=True)
                    except Exception as e:
                        raise HTTPException(400, f"YouTube download failed for slot {i + 1}: {e}") from e
                else:
                    print(f"[DJMashAI] Reading file slot {i + 1}/{total}...", flush=True)
                    f = next(file_iter, None)
                    if not f or not f.filename or not f.filename.lower().endswith((".mp3", ".wav", ".m4a", ".flac", ".ogg")):
                        raise HTTPException(400, f"Slot {i + 1}: expected audio file.")
                    suffix = Path(f.filename).suffix or ".mp3"
                    contents = await f.read()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(contents)
                        paths_to_clean.append(tmp.name)
                        paths_and_names.append((tmp.name, f.filename or "Track"))
        else:
            for i, f in enumerate(files):
                print(f"[DJMashAI] Reading file {i + 1}/{total}...", flush=True)
                if not f.filename or not f.filename.lower().endswith((".mp3", ".wav", ".m4a", ".flac", ".ogg")):
                    raise HTTPException(400, "Each file must be .mp3, .wav, .m4a, .flac, or .ogg")
                suffix = Path(f.filename).suffix or ".mp3"
                contents = await f.read()
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(contents)
                    paths_to_clean.append(tmp.name)
                    paths_and_names.append((tmp.name, f.filename or "Track"))

        results = []
        for i, (p, name) in enumerate(paths_and_names):
            print(f"[DJMashAI] Analyzing track {i + 1}/{total}...", flush=True)
            try:
                features = extract_track_features(p)
            except Exception as e:
                msg = str(e).strip() or getattr(e, "message", "") or type(e).__name__
                if not msg or msg == type(e).__name__:
                    msg = "m4a/YouTube on Windows often needs ffmpeg. Install ffmpeg and add its bin folder to PATH."
                raise HTTPException(500, f"Analysis failed for {name}: {msg}") from e
            is_public = opts.public[i] if i < len(opts.public) else False
            lyrics = (opts.lyrics[i] or "").strip() if i < len(opts.lyrics) else ""
            identified_song = None
            if is_public and (lyrics or name):
                print(f"[DJMashAI] Identifying song {i + 1}/{total}...", flush=True)
                identified_song = identify_song(lyrics if lyrics else None, name if name else None)
            results.append(
                AnalyzeBatchItem(
                    features=features,
                    identified_song=identified_song,
                    is_public=is_public,
                    display_name=name,
                )
            )
        print(f"[DJMashAI] Done. Analyzed {total} track(s).", flush=True)
        return results
    finally:
        for p in paths_to_clean:
            Path(p).unlink(missing_ok=True)
        for d in tmp_dirs_to_clean:
            try:
                Path(d).rmdir()
            except Exception:
                pass


@app.post("/mix-plan", response_model=MixPlanResponse)
async def mix_plan(req: MixPlanRequest) -> MixPlanResponse:
    """
    Given a list of Track Feature Objects and a mix style, returns optimal order and transition plan (Gemini + planner).
    """
    if req.track_names and len(req.track_names) != len(req.tracks):
        raise HTTPException(400, "track_names must have same length as tracks")
    try:
        order, transition_reasoning = plan_mix_order(req.tracks, req.style, req.track_names)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except ImportError as e:
        raise HTTPException(
            503,
            "Gemini SDK not installed. From the backend folder with venv active run: pip install google-genai",
        ) from e
    ordered_tracks = [req.tracks[i] for i in order]
    transitions = plan_transitions(ordered_tracks, transition_reasoning)
    # Optional: aggregate energy curve over mix (simple concat of ordered energy curves)
    energy_curve: list[float] = []
    for t in ordered_tracks:
        energy_curve.extend(t.energy_curve)
    return MixPlanResponse(order=order, transitions=transitions, energy_curve=energy_curve)
