"""
DJMashAI Backend — FastAPI app.
Endpoints: /health, /analyze (Track Feature Object).
"""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.analysis import extract_track_features, TrackFeatureObject

load_dotenv()

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
