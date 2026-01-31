# DJMashAI — Feature Specification
AI-Powered DJ Mixing & Transition Intelligence

This document defines the full feature set for DJMashAI, including MVP hackathon scope and stretch capabilities. It is intended as a build reference for development.

---

# 🎯 Core Product Goal

Turn ordinary playlists into AI-planned DJ-style mixes using:

- audio feature extraction
- music theory heuristics
- LLM reasoning
- explainable transition decisions
- AI-generated DJ commentary

AI is the decision engine — not a decorative add-on.

---

# ✅ MVP Features (Hackathon Scope)

These are the required features for the 24-hour hackathon build.

---

## 🎵 Track Upload & Processing

Users can:

- upload multiple audio tracks
- view track list
- trigger analysis pipeline

System performs:

- audio loading
- waveform scan
- feature extraction

---

## 🔍 Audio Feature Extraction Engine

Per-track automatic detection:

- BPM (tempo)
- beat grid estimation
- musical key detection
- energy curve
- intro/outro likelihood
- drop probability zones
- loudness profile

Output:

Track Feature Object (JSON):

- bpm
- key
- energy_score
- energy_curve
- intro_window
- outro_window
- drop_regions

---

## 🧠 AI Mix Intelligence (Gemini + OpenRouter)

AI receives:

- extracted audio features
- metadata
- genre labels (if available)

AI generates:

- optimal track order
- energy flow design
- transition strategy
- compatibility scoring
- harmonic reasoning
- mix style adaptation

Mix styles supported:

- club
- chill
- workout
- festival
- smooth blend

---

## 🔄 AI Transition Planner

For each track pair:

System determines:

- best transition window
- phrase alignment suggestion
- BPM adjustment suggestion
- crossfade duration
- EQ swap timing
- filter sweep timing

Outputs:

Transition Plan Object:

- transition_start_time
- transition_end_time
- fade_curve
- eq_strategy
- reasoning_text

All transitions must be explainable.

---

## 📈 Energy Timeline Visualization

UI displays:

- ordered mix timeline
- energy curve across set
- track energy levels
- drop markers
- transition points

Purpose:

- visual proof of AI reasoning
- judge-friendly explainability

---

## 🗣️ Explainable AI Decisions

Clicking any transition shows:

- why this track follows the previous
- BPM compatibility reasoning
- key compatibility reasoning
- energy progression reasoning
- style-based decision logic

Example:

> Track B follows Track A because energy rises + harmonic compatibility is high.

---

## 🎤 AI DJ MC Voice Layer (ElevenLabs)

AI generates performance commentary:

Types:

- intro hype line
- transition callout
- drop countdown
- energy warning
- set-style announcement

Generated from:

- mix plan
- energy curve
- drop timing

Pipeline:

LLM text → ElevenLabs voice → audio output

---

## 🔊 Mix Preview Simulation (Basic)

Web preview system:

- simulated crossfades
- fade curves applied
- preview transitions
- not full DJ beatmatching
- hackathon-level approximation

---

## 🎛️ Mix Style Selector

User selects:

- club
- chill
- workout
- festival

Affects AI decisions:

- ordering
- transition aggression
- energy curve shape
- commentary style
- transition duration

---

# 🤖 AI Feature Usage Map

AI is used for:

- track vibe classification
- energy labeling
- set ordering
- transition reasoning
- compatibility scoring
- commentary generation
- crowd energy prediction
- mix style adaptation
- explainable decisions

No AI feature is cosmetic.

---

# ⭐ Stretch Features (If Time Allows)

Not required for McVP but valuable if implemented.

---

## 🎼 AI Mashup Compatibility Scoring

AI scores track pairs:

- harmonic match
- rhythmic compatibility
- vocal overlap risk
- drop alignment
- groove similarity

Outputs score + explanation.

---

## 🧬 Stem Separation (AI Audio Models)

Split tracks into:

- vocals
- drums
- bass
- melody

Enables:

- vocal-only transitions
- instrumental blends
- vocal swaps

---

## 🧠 Multi-Model Ensemble Reasoning

Use multiple LLMs via OpenRouter:

- compare ordering decisions
- consensus scoring
- reasoning agreement check

Improves reliability.

---

## 🎚️ Prompt-Based Mix Control

User can type:

“Make it more hype”
“Make smoother transitions”
“More dramatic drops”

AI adjusts:

- energy curve
- transition length
- ordering logic

---

## 🔮 Crowd Reaction Prediction

AI predicts:

- danceability
- drop impact
- crowd energy response

Displayed as score.

---

## 🎧 Genre Blend Mode

AI designs hybrid sets:

- genre A + genre B
- rhythm anchoring decisions
- energy balancing

---

# 🖥️ Frontend Feature Set

UI Panels:

- track upload panel
- analysis status panel
- mix timeline
- energy curve chart
- transition inspector
- AI reasoning viewer
- voice preview player

---

# ⚙️ Backend Feature Set

Services:

- audio analysis engine
- feature extractor
- mix planner
- AI reasoning orchestrator
- transition planner
- commentary generator
- voice synthesis connector

---

# 📊 Demo Features for Judges

Demo must show:

- upload → analysis → mix plan
- energy curve visualization
- explainable transitions
- AI reasoning text
- AI DJ voice output
- style switching changes plan

---

# 🚫 Explicit Non-Goals (Hackathon Version)

Not included:

- real-time DJ mixing
- live beatmatching engine
- streaming service integration
- pro DJ interface
- social sharing platform
- mobile app build

Focus = AI mix intelligence.

---

# 🚀 Post-Hackathon Expansion

Future roadmap:

- real-time mixing
- auto mashups
- live DJ copilot mode
- creator set builder
- Spotify integration
- AI remix engine
- auto festival set design

---

End of Feature Specification
