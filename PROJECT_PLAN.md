# DJMashAI — Hackathon Project Plan

Quick-reference plan: tech choices, Docker strategy, and where to start.

---

## 1. Should you use Docker for the backend?

**Short answer: Yes, but keep it minimal.**

| Use Docker? | When it makes sense |
|-------------|---------------------|
| **Yes** | You want to deploy to DigitalOcean and avoid "works on my machine" (Python + librosa + system libs can be fussy). One `Dockerfile` → run locally and deploy the same image to DO App Platform. |
| **No (for now)** | You're solo, never used Docker, and every minute counts. Use `requirements.txt` + a clear README; add Docker only when you're ready to deploy. |

**Recommendation for this hackathon:**

- **Start without Docker** — get the backend running locally with a venv and `requirements.txt`. Move fast.
- **Add Docker when you deploy** — once `/analyze` and `/mix-plan` work, add a simple `Dockerfile` so DigitalOcean App Platform can run the same environment. That way you're not blocked on Docker on day one.

**DigitalOcean options:**

- **App Platform** — Connect GitHub repo, use a Dockerfile or Python buildpack, auto-deploy. Best for "backend API for judges."
- **Droplet** — More control; you SSH in and run the app or a container. Use if you need more than App Platform allows.

---

## 2. What should you use?

Stick to what README/Features specify; only a few choices to make:

| Layer | Use this |
|-------|----------|
| **Backend** | Python 3.10+, FastAPI |
| **Audio** | librosa, numpy, scipy |
| **AI** | Google Gemini API, OpenRouter (for fallback/ensemble later) |
| **Voice** | ElevenLabs API |
| **Frontend** | React or Next.js (Next if you want API routes; React + Vite is lighter) |
| **Deploy** | DigitalOcean App Platform (backend) + static frontend or same app |

**API keys you’ll need:**

- Gemini (Google AI Studio)
- ElevenLabs
- OpenRouter (optional for MVP)

---

## 3. Where do you start? (Order of work)

### Phase 1 — Backend foundation (start here)

1. **Repo structure**
   - Create `backend/` and `frontend/` (or `web/`) in the repo.
   - Backend: FastAPI app, `requirements.txt`, `.env.example` for API keys.

2. **First backend endpoints**
   - `GET /health` — so you can confirm the API runs locally and on DO.
   - `POST /analyze` — accepts one audio file (or multipart), runs librosa for BPM + key + simple energy, returns a **Track Feature Object** (JSON).  
   - This is your first demo: "upload a track → get back BPM, key, energy."

3. **Expand analysis**
   - Add beat grid, intro/outro windows, drop regions, loudness so the Track Feature Object matches Features.md.  
   - Add `POST /analyze-batch` (or multiple files in one request) if you want to analyze a full playlist in one go.

### Phase 2 — AI mix intelligence

4. **Mix plan endpoint**
   - `POST /mix-plan` — input: list of Track Feature Objects + mix style (club/chill/workout/festival).  
   - Call Gemini with a structured prompt: features + style → optimal order, energy flow, short transition strategy per pair.  
   - Output: **ordered track list + per-transition reasoning** (and optionally transition windows).

5. **Transition planner**
   - In backend, a small module that takes the mix plan and computes for each pair: transition window, phrase alignment, crossfade length, EQ/filter suggestion.  
   - Attach this to the mix plan response so the frontend can show "transition from 1:23 to 1:45" and reasoning.

### Phase 3 — Frontend

6. **Minimal UI**
   - Track upload (one or many files) → call `/analyze` (or batch).  
   - Show track list + per-track features (BPM, key, energy).  
   - Button: "Generate mix plan" → call `/mix-plan` with style selector.  
   - Show **mix timeline** (ordered tracks) + **energy curve** (simple chart) + **transition points**.

7. **Explainability**
   - Click a transition → show AI reasoning (why this track follows, BPM/key/energy).  
   - Use the `reasoning_text` (or equivalent) from the mix plan and transition planner.

### Phase 4 — Voice + preview

8. **AI MC voice**
   - Backend: endpoint that takes mix plan + transition/drop events, calls Gemini for short commentary lines, then ElevenLabs for TTS.  
   - Frontend: voice preview player (play generated lines at the right moments in the timeline or on click).

9. **Mix preview**
   - Simple Web Audio crossfade between two tracks at suggested transition window.  
   - Hackathon-level is fine: no need for full beatmatching.

### Phase 5 — Deploy (DigitalOcean)

10. **Backend**
    - Add a minimal `Dockerfile` in `backend/` (Python base, install deps, run FastAPI).  
    - Push to GitHub, connect repo to DO App Platform, deploy.  
    - Set env vars (Gemini, ElevenLabs, etc.) in App Platform.

11. **Frontend**
    - Build static (e.g. `npm run build`), deploy as static site on DO or same App Platform app.  
    - Point frontend to the backend URL (env var for API base).

---

## 4. Suggested folder structure

```
DJMashAI/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, routes
│   │   ├── analysis/         # audio feature extraction
│   │   ├── ai/               # Gemini, OpenRouter, prompts
│   │   ├── planner/          # transition planner
│   │   └── voice/            # ElevenLabs integration
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile            # add when deploying
├── frontend/                 # or "web/"
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── api/              # if you need a small BFF
│   ├── package.json
│   └── ...
├── README.md
├── Features.md
└── PROJECT_PLAN.md           # this file
```

---

## 5. First 3 concrete steps

1. **Create `backend/`** — FastAPI app, `requirements.txt` (fastapi, uvicorn, librosa, numpy, scipy, python-dotenv, httpx, pydantic), and `GET /health`. Run with `uvicorn app.main:app --reload`. Confirm it works locally.

2. **Implement `POST /analyze`** — One audio file in, call librosa for BPM and key, compute a simple energy curve, return JSON matching the Track Feature Object. Test with a single MP3/WAV.

3. **Create `frontend/`** — Vite + React or Next.js, one page: file input → upload to `/analyze` → display BPM, key, energy.  
   This gives you "upload → see analysis" as the first milestone before any AI.

After that, add `/mix-plan` and the timeline UI; then transitions, voice, and Docker + DigitalOcean when you’re ready to show a live demo.

---

## 6. Summary

| Question | Answer |
|----------|--------|
| **Use Docker?** | Start without it; add a Dockerfile when you deploy to DigitalOcean. |
| **Use DigitalOcean?** | Yes — App Platform for backend (and optionally frontend) is enough for the demo. |
| **Where to start?** | Backend first: project structure → `/health` → `/analyze` (Track Feature Object) → then `/mix-plan` and AI; frontend in parallel once analyze works. |
| **First milestone** | "Upload one track → see BPM, key, energy in the UI." |

If you tell me your comfort level (Python/FastAPI, Docker, React), I can turn "First 3 steps" into exact commands and file contents (e.g. `backend/app/main.py` and `backend/requirements.txt`) so you can paste and run.
