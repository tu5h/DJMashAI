"""
DJMashAI Backend — FastAPI app.
Endpoints: /health, /analyze, /analyze-batch, /mix-plan, /commentary, /stem-transition-preview, /sound-effect.
"""

import base64
import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.analysis import extract_track_features, TrackFeatureObject
from app.analysis.vocal_phrases import get_vocal_phrase_boundaries, get_vocal_segments
from app.analysis.external import enrich_track_from_external
from app.ai import plan_mix_order
from app.ai.song_identifier import identify_song
from app.planner import plan_transitions
from app.stems import plan_stem_transition, render_stem_transition, separate_into_stems
from app.audio import generate_sound_effect
from app.voice import generate_commentary_audio
from app.youtube import download_youtube_audio

# Thread pool for stem separation (CPU-heavy, don't block event loop)
_stem_executor = ThreadPoolExecutor(max_workers=2)

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


class CommentaryRequest(BaseModel):
    ordered_track_names: list[str] = Field(..., min_length=2, description="Track names in mix order")
    transition_reasoning: list[str] = Field(..., description="Per-transition reasoning (same length as ordered_track_names - 1)")
    style: MixStyle = Field(..., description="Mix style: club, chill, workout, festival")


class CommentaryLineResponse(BaseModel):
    label: str = Field(..., description="e.g. intro, transition_1, outro")
    text: str = Field(..., description="Commentary line to speak")
    audio_base64: str | None = Field(default=None, description="MP3 audio as base64 if ElevenLabs API key set")


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
            try:
                segments = get_vocal_segments(p)
                if segments:
                    phrase_starts = sorted({s["start"] for s in segments})
                    phrase_ends = sorted({s["end"] for s in segments})
                    features = features.model_copy(
                        update={
                            "vocal_phrase_starts": phrase_starts,
                            "vocal_phrase_ends": phrase_ends,
                            "vocal_segments": segments,
                        }
                    )
            except Exception:
                pass
            # Optional: enrich with external beat/chord analysis (AutoMasher-style or ChordMini API)
            try:
                enriched = enrich_track_from_external(p, features)
                if enriched is not None:
                    features = enriched
            except Exception:
                pass
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
        order, transition_reasoning, transition_sounds = plan_mix_order(req.tracks, req.style, req.track_names)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except ImportError as e:
        raise HTTPException(
            503,
            "Gemini SDK not installed. From the backend folder with venv active run: pip install google-genai",
        ) from e
    ordered_tracks = [req.tracks[i] for i in order]
    transitions = plan_transitions(ordered_tracks, transition_reasoning)
    for i, t in enumerate(transitions):
        t["transition_sound"] = transition_sounds[i] if i < len(transition_sounds) else "whoosh"
    # Optional: aggregate energy curve over mix (simple concat of ordered energy curves)
    energy_curve: list[float] = []
    for t in ordered_tracks:
        energy_curve.extend(t.energy_curve)
    return MixPlanResponse(order=order, transitions=transitions, energy_curve=energy_curve)


@app.post("/commentary", response_model=list[CommentaryLineResponse])
def commentary(req: CommentaryRequest) -> list[CommentaryLineResponse]:
    """
    Generate AI DJ MC commentary: Gemini writes short lines, ElevenLabs TTS (if API key set).
    Input: ordered track names, per-transition reasoning, mix style.
    """
    reasoning = list(req.transition_reasoning)
    n_trans = max(0, len(req.ordered_track_names) - 1)
    if len(reasoning) < n_trans:
        reasoning = reasoning + [""] * (n_trans - len(reasoning))
    reasoning = reasoning[:n_trans]
    try:
        lines = generate_commentary_audio(
            ordered_track_names=req.ordered_track_names,
            transition_reasoning=reasoning,
            style=req.style,
        )
        return [CommentaryLineResponse(label=l["label"], text=l["text"], audio_base64=l.get("audio_base64")) for l in lines]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except ImportError as e:
        raise HTTPException(
            503,
            "Gemini SDK not installed. From the backend folder with venv active run: pip install google-genai",
        ) from e


@app.post("/stem-transition-preview")
async def stem_transition_preview(
    file_a: UploadFile = File(..., description="Outgoing track (A) audio file"),
    file_b: UploadFile = File(..., description="Incoming track (B) audio file"),
    transition_start_a: float = Form(..., description="Time in track A (sec) when transition starts"),
    crossfade_duration_sec: float = Form(..., description="Crossfade duration (sec)"),
    bpm_a: float = Form(..., description="BPM of track A"),
    bpm_b: float = Form(..., description="BPM of track B"),
    style: str = Form("club", description="Mix style: club, chill, workout, festival"),
) -> dict:
    """
    Build a stem-aware transition: separate both tracks into stems, AI plans per-stem fades
    (no vocal overlap, drums/bass aligned), render mixed audio. Returns { audio_base64, schedule }.
    """
    if not file_a.filename or not file_b.filename:
        raise HTTPException(400, "Both file_a and file_b required.")
    for f in (file_a, file_b):
        if not (f.filename and f.filename.lower().endswith((".mp3", ".wav", ".m4a", ".flac", ".ogg"))):
            raise HTTPException(400, "Both files must be audio: .mp3, .wav, .m4a, .flac, .ogg")
    tmp_a = tmp_b = None
    tmpdir_a = tmpdir_b = ""
    try:
        suffix_a = Path(file_a.filename).suffix or ".mp3"
        suffix_b = Path(file_b.filename).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix_a) as t_a:
            t_a.write(await file_a.read())
            tmp_a = t_a.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix_b) as t_b:
            t_b.write(await file_b.read())
            tmp_b = t_b.name
        def separate(path: str):
            return separate_into_stems(path, timeout=600)
        future_a = _stem_executor.submit(separate, tmp_a)
        future_b = _stem_executor.submit(separate, tmp_b)
        stems_a, tmpdir_a = future_a.result(timeout=620)
        stems_b, tmpdir_b = future_b.result(timeout=620)
        if not stems_a or not stems_b:
            raise HTTPException(500, "Stem separation failed. Install demucs: pip install demucs")
        schedule = plan_stem_transition(
            crossfade_duration_sec=crossfade_duration_sec,
            bpm_a=bpm_a,
            bpm_b=bpm_b,
            style=style,
        )
        wav_bytes, _ = render_stem_transition(
            stems_a=stems_a,
            stems_b=stems_b,
            schedule=schedule,
            transition_start_a_sec=transition_start_a,
            crossfade_duration_sec=crossfade_duration_sec,
        )
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        return {"audio_base64": audio_b64, "schedule": schedule}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except ImportError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Stem transition failed: {e}") from e
    finally:
        if tmp_a:
            Path(tmp_a).unlink(missing_ok=True)
        if tmp_b:
            Path(tmp_b).unlink(missing_ok=True)
        for d in (tmpdir_a, tmpdir_b):
            if d and Path(d).exists():
                shutil.rmtree(d, ignore_errors=True)


@app.get("/sound-effect", response_class=Response)
def sound_effect(
    type: str = "whoosh",
    duration: float = 0.5,
) -> Response:
    """
    Generate a transition sound effect (whoosh, filter_sweep, echo_tail, vinyl_scratch).
    Returns WAV bytes. Used at transition points so the mix feels like a real DJ.
    """
    valid = {"whoosh", "filter_sweep", "echo_tail", "vinyl_scratch", "none"}
    effect = type.lower().strip() if type else "whoosh"
    if effect not in valid:
        effect = "whoosh"
    duration_sec = max(0.1, min(2.0, float(duration)))
    try:
        wav_bytes = generate_sound_effect(effect, duration_sec=duration_sec)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(500, f"Sound effect failed: {e}") from e
