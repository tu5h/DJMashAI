# Getting started — DJMashAI

Run backend and frontend locally for the first milestone: **upload a track → see BPM, key, energy**.

## Backend (Python)

Use the project’s **virtual environment** so packages install into `backend/.venv` instead of system Python (avoids “Permission denied” when installing demucs/antlr4).

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env if you need CORS_ORIGINS
```

**If you see “Permission denied” (e.g. on `C:\Python312\Scripts\pygrun`):** you’re not using the venv. Create and activate it as above, then run `pip install -r requirements.txt` again in the same terminal where the venv is active.

**Run the server:**

- **Option A — activate venv, then:**  
  `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Option B — no activation (Windows):**  
  `.\run.ps1`  
  or:  
  `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Option B — macOS/Linux:**  
  `.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

- Health: [http://localhost:8000/health](http://localhost:8000/health)
- Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Frontend (Vite + React)

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

- App: [http://localhost:5173](http://localhost:5173)

The frontend proxies `/api` to `http://localhost:8000`, so uploads go to the backend.

## First test

1. Start backend, then frontend.
2. Open [http://localhost:5173](http://localhost:5173).
3. Choose an audio file (.mp3, .wav, .m4a, .flac).
4. Click **Analyze track**.
5. You should see BPM, key, energy, duration, intro/outro, drop regions, and an energy curve.

**Mix plan:**

1. Set `GEMINI_API_KEY` in `.env` (get one at [Google AI Studio](https://aistudio.google.com/apikey)).
2. Add tracks: **upload files** and/or **paste YouTube links** (e.g. `https://www.youtube.com/watch?v=...`). Use "— or paste a YouTube link —" per slot; you can mix file + YouTube in the same run.
3. Optionally turn **Public** on so AI can try to identify the song from its title (filename or YouTube title).
4. Click **Analyze tracks**, then pick a **mix style** and **Generate mix plan**.
5. View the **mix timeline** (coloured per track), **energy curve**, and click **→ transition** to see AI reasoning.
6. **DJ commentary:** Click **Generate DJ commentary** to get short MC lines (intro, transition callouts, outro). Set **ELEVENLABS_API_KEY** in `.env` to hear them as voice (TTS); otherwise you’ll see the text only.
7. **Stem-aware transitions:** To avoid vocals overlapping and messy beats, use **Preview (stems)** on a transition (only when both tracks were uploaded as files). The backend splits each track into stems (vocals, drums, bass, other), asks the AI for a per-stem fade schedule (no vocal overlap, drums aligned), then renders and returns the mixed clip. Requires **demucs**: `pip install demucs` (optional; works on Python 3.12+).
8. **Vocal phrase boundaries:** Transitions are tuned so the first track **ends** when the crossfade ends (replace, not overlap). If **openai-whisper** is installed, the backend transcribes each track and: snaps the transition start to the nearest **end** of a vocal phrase in the outgoing outro (no mid-word cut), and snaps the crossfade length so the incoming track reaches full volume at a **start** of a vocal phrase in its intro — so each phrase links nicely to the next.
9. **Beat grid & chord segments (AutoMasher-style):** Each track gets a full **beat grid** (`beat_times_sec`) and **chord segments** (chroma-based) so transitions can be **beat-aligned** and cut at **chord boundaries** for a tighter mix. The **track AI** (Gemini mix planner) sees beats and chords in intro/outro and uses them when reasoning about order and handoffs.
10. **Optional external analysis:** For pop-trained chord/beat extraction (e.g. [AutoMasher](https://github.com/darinchau/AutoMasher) or [ChordMini API](https://www.chordmini.me/docs)), set **EXTERNAL_BEAT_CHORD_SCRIPT** to a script that accepts an audio path and prints JSON `{ "beats": [sec,...], "chords": [{ "start", "end", "chord" },...] }`, or set **CHORDMINI_API_URL** to POST audio and receive the same JSON. The backend will merge beat/chord data into each track for better transition snapping.

**YouTube:** Audio is extracted with **yt-dlp** (installed via `pip install -r requirements.txt`). On **Windows**, analyzing YouTube (m4a) tracks requires **ffmpeg** in your PATH—otherwise you may see "Analysis failed" with no details. Install ffmpeg (see below) and add its `bin` folder to PATH.

---

## Installing FFmpeg (required on Windows for YouTube analysis; optional elsewhere)

**Windows**

- **Winget (built-in):**  
  `winget install ffmpeg`  
  (If prompted, choose “FFmpeg (Essentials)” or the Gyan.dev package.)
- **Chocolatey:**  
  `choco install ffmpeg`
- **Scoop:**  
  `scoop install ffmpeg`
- **Manual:**  
  1. Download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (e.g. `ffmpeg-release-essentials.7z`).  
  2. Extract the archive (e.g. to `C:\FFmpeg`).  
  3. Add the **bin** folder (e.g. `C:\FFmpeg\bin`) to your system **PATH** (Settings → System → About → Advanced system settings → Environment Variables → Path → Edit → New).

**macOS**

- **Homebrew:**  
  `brew install ffmpeg`

**Linux**

- **Ubuntu/Debian:**  
  `sudo apt update && sudo apt install ffmpeg`
- **Fedora:**  
  `sudo dnf install ffmpeg`
- **Arch:**  
  `sudo pacman -S ffmpeg`

After installing, open a **new** terminal and run `ffmpeg -version` to confirm it’s on your PATH.
