import { useState, useRef, useEffect } from "react";

const API_BASE = "/api";
const MIX_STYLES = [
  { id: "club", label: "Club" },
  { id: "chill", label: "Chill" },
  { id: "workout", label: "Workout" },
  { id: "festival", label: "Festival" },
];

const TRACK_COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4",
  "#84cc16", "#ef4444",
];

function nextId() {
  return Math.random().toString(36).slice(2);
}

export default function App() {
  const [slots, setSlots] = useState([
    { id: nextId(), file: null, youtubeUrl: "", isPublic: false },
  ]);
  const [analyzedTracks, setAnalyzedTracks] = useState([]);
  const [mixStyle, setMixStyle] = useState("club");
  const [mixPlan, setMixPlan] = useState(null);
  const [selectedTransitionIndex, setSelectedTransitionIndex] = useState(null);
  const [loadingAnalyze, setLoadingAnalyze] = useState(false);
  const [loadingMixPlan, setLoadingMixPlan] = useState(false);
  const [analyzingTotal, setAnalyzingTotal] = useState(0);
  const [analyzingStep, setAnalyzingStep] = useState(0);
  const [error, setError] = useState(null);
  const [isPreviewPlaying, setIsPreviewPlaying] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const resultRef = useRef(null);
  const mixPlanRef = useRef(null);
  const audioContextRef = useRef(null);
  const scheduledSourcesRef = useRef([]);

  useEffect(() => {
    if (!loadingAnalyze || analyzingTotal <= 0) return;
    const id = setInterval(() => {
      setAnalyzingStep((s) => Math.min(s + 1, analyzingTotal - 1));
    }, 2000);
    return () => clearInterval(id);
  }, [loadingAnalyze, analyzingTotal]);

  useEffect(() => {
    if (analyzedTracks.length > 0 && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [analyzedTracks.length]);

  useEffect(() => {
    if (mixPlan && mixPlanRef.current) {
      mixPlanRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [mixPlan]);

  useEffect(() => {
    return () => stopPreview();
  }, []);

  function addSlot() {
    setSlots((s) => [...s, { id: nextId(), file: null, youtubeUrl: "", isPublic: false }]);
    setError(null);
  }

  function removeSlot(id) {
    setSlots((s) => (s.length > 1 ? s.filter((x) => x.id !== id) : s));
    setAnalyzedTracks([]);
    setMixPlan(null);
    setError(null);
  }

  function updateSlot(id, upd) {
    setSlots((s) =>
      s.map((x) => (x.id === id ? { ...x, ...upd } : x))
    );
    setError(null);
  }

  async function handleAnalyze(e) {
    e.preventDefault();
    const slotsWithContent = slots.filter((s) => s.file || (s.youtubeUrl && s.youtubeUrl.trim()));
    if (!slotsWithContent.length) {
      setError("Add at least one track: upload an audio file or paste a YouTube link.");
      return;
    }
    setError(null);
    setAnalyzedTracks([]);
    setMixPlan(null);
    setAnalyzingTotal(slotsWithContent.length);
    setAnalyzingStep(0);
    setLoadingAnalyze(true);
    try {
      const formData = new FormData();
      const hasYoutube = slotsWithContent.some((s) => s.youtubeUrl?.trim());
      if (hasYoutube) {
        const layout = slotsWithContent.map((s) => (s.file ? "file" : "youtube"));
        const urls = slotsWithContent.filter((s) => s.youtubeUrl?.trim()).map((s) => s.youtubeUrl.trim());
        formData.append("layout", JSON.stringify(layout));
        formData.append("urls", JSON.stringify(urls));
        slotsWithContent.filter((s) => s.file).forEach((s) => formData.append("files", s.file));
      } else {
        slotsWithContent.forEach((s) => formData.append("files", s.file));
      }
      formData.append(
        "options",
        JSON.stringify({
          lyrics: slotsWithContent.map(() => null),
          public: slotsWithContent.map((s) => s.isPublic),
        })
      );
      const res = await fetch(`${API_BASE}/analyze-batch`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setAnalyzedTracks(
        data.map((item, i) => ({
          name: item.display_name || slotsWithContent[i]?.file?.name || "Track",
          features: item.features,
          identified_song: item.identified_song ?? null,
          is_public: item.is_public ?? false,
          sourceFile: slotsWithContent[i]?.file ?? null,
        }))
      );
    } catch (err) {
      setError(err.message || "Analysis failed.");
    } finally {
      setLoadingAnalyze(false);
      setAnalyzingStep(0);
    }
  }

  async function handleGenerateMixPlan(e) {
    e.preventDefault();
    if (analyzedTracks.length < 2) {
      setError("Analyze at least 2 tracks to generate a mix plan.");
      return;
    }
    setError(null);
    setMixPlan(null);
    setSelectedTransitionIndex(null);
    setLoadingMixPlan(true);
    try {
      const res = await fetch(`${API_BASE}/mix-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tracks: analyzedTracks.map((t) => t.features),
          style: mixStyle,
          track_names: analyzedTracks.map((t) => t.name),
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setMixPlan(data);
    } catch (err) {
      setError(err.message || "Mix plan failed.");
    } finally {
      setLoadingMixPlan(false);
    }
  }

  function stopPreview() {
    scheduledSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch (_) {}
    });
    scheduledSourcesRef.current = [];
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setIsPreviewPlaying(false);
    setPreviewError(null);
  }

  async function playPreview() {
    if (!mixPlan || !orderedTracks.length) return;
    const missing = orderedTracks.find((t) => !t.sourceFile);
    if (missing) {
      setPreviewError("Mix preview only works when all tracks were uploaded as files (no YouTube-only tracks).");
      return;
    }
    setPreviewError(null);
    stopPreview();
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    audioContextRef.current = ctx;
    const buffers = [];
    try {
      for (const track of orderedTracks) {
        const arrayBuffer = await track.sourceFile.arrayBuffer();
        const buf = await ctx.decodeAudioData(arrayBuffer.slice(0));
        buffers.push(buf);
      }
    } catch (e) {
      setPreviewError("Could not decode audio: " + (e.message || "Unknown error"));
      ctx.close();
      return;
    }
    const transitions = mixPlan.transitions ?? [];
    const mixStartTime = [0];
    for (let i = 0; i < transitions.length; i++) {
      mixStartTime.push(mixStartTime[i] + (transitions[i].transition_start_time ?? 0));
    }
    const sources = [];
    const now = ctx.currentTime;
    for (let i = 0; i < buffers.length; i++) {
      const gainNode = ctx.createGain();
      gainNode.connect(ctx.destination);
      const src = ctx.createBufferSource();
      src.buffer = buffers[i];
      src.connect(gainNode);
      const startMix = mixStartTime[i];
      const dur = buffers[i].duration;
      gainNode.gain.setValueAtTime(i === 0 ? 1 : 0, now + startMix);
      if (i > 0) {
        const crossfade = transitions[i - 1].crossfade_duration_sec ?? 16;
        gainNode.gain.linearRampToValueAtTime(1, now + startMix + Math.min(crossfade, dur));
      }
      if (i < buffers.length - 1 && transitions[i]) {
        const crossfadeOut = transitions[i].crossfade_duration_sec ?? 16;
        const rampStart = startMix + (transitions[i].transition_start_time ?? 0);
        gainNode.gain.setValueAtTime(1, now + rampStart);
        gainNode.gain.linearRampToValueAtTime(0, now + rampStart + Math.min(crossfadeOut, dur - (transitions[i].transition_start_time ?? 0)));
      }
      src.start(now + startMix);
      src.stop(now + startMix + dur);
      src.onended = () => {
        if (i === buffers.length - 1) setIsPreviewPlaying(false);
      };
      sources.push(src);
    }
    scheduledSourcesRef.current = sources;
    setIsPreviewPlaying(true);
  }

  const orderedTracks = mixPlan
    ? mixPlan.order.map((i) => analyzedTracks[i])
    : [];
  const transitions = mixPlan?.transitions ?? [];
  const energyCurve = mixPlan?.energy_curve ?? [];

  const curveBoundaries = orderedTracks.length
    ? (() => {
        const b = [0];
        let acc = 0;
        orderedTracks.forEach((t) => {
          acc += (t.features.energy_curve?.length ?? 0);
          b.push(acc);
        });
        return b;
      })()
    : [];

  const totalCurveLen = curveBoundaries[curveBoundaries.length - 1] ?? 0;
  const curveSampleStep = Math.max(1, Math.floor((totalCurveLen || 1) / 120));
  const curveSamples = [];
  if (totalCurveLen > 0) {
    for (let i = 0; i < totalCurveLen; i += curveSampleStep) {
      const segIdx = curveBoundaries.findIndex((b) => b > i) - 1;
      const trackIdx = segIdx >= 0 ? segIdx : 0;
      const v = energyCurve[i] ?? 0;
      curveSamples.push({ i, v, trackIdx });
    }
  }

  const isTransitionHighlight = (trackIndex) => {
    if (selectedTransitionIndex === null) return false;
    return (
      trackIndex === selectedTransitionIndex ||
      trackIndex === selectedTransitionIndex + 1
    );
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>DJMashAI</h1>
        <p style={styles.subtitle}>
          Add tracks (upload or YouTube link). Tick Public to identify the song from its title.
        </p>
      </header>

      <main style={styles.main}>
        <form onSubmit={handleAnalyze} style={styles.form}>
          <h3 style={styles.sectionTitle}>Tracks</h3>
          {slots.map((slot) => (
            <div key={slot.id} style={styles.slot}>
              <div style={styles.slotHeader}>
                <span style={styles.slotLabel}>Track {slots.findIndex((s) => s.id === slot.id) + 1}</span>
                {slots.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeSlot(slot.id)}
                    style={styles.removeSlot}
                    title="Remove track"
                    aria-label="Remove track"
                  >
                    ×
                  </button>
                )}
              </div>
              <input
                type="file"
                accept=".mp3,.wav,.m4a,.flac,.ogg"
                onChange={(e) => updateSlot(slot.id, { file: e.target.files?.[0] ?? null })}
                style={styles.input}
              />
              <span style={styles.orLabel}>— or paste a YouTube link —</span>
              <input
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                value={slot.youtubeUrl || ""}
                onChange={(e) => updateSlot(slot.id, { youtubeUrl: e.target.value })}
                style={styles.input}
              />
              <label style={styles.toggleRow}>
                <input
                  type="checkbox"
                  checked={slot.isPublic}
                  onChange={(e) => updateSlot(slot.id, { isPublic: e.target.checked })}
                />
                <span style={styles.toggleLabel}>Public (AI identifies song from title)</span>
              </label>
            </div>
          ))}
          <button type="button" onClick={addSlot} style={styles.addSlotBtn} title="Add track">
            + Add track
          </button>
          <button
            type="submit"
            disabled={loadingAnalyze || !slots.some((s) => s.file || (s.youtubeUrl && s.youtubeUrl.trim()))}
            style={styles.button}
          >
            {loadingAnalyze ? "Analyzing…" : "Analyze tracks"}
          </button>
        </form>

        {loadingAnalyze && (
          <div style={styles.loadingWrap}>
            <div style={styles.loadingBar}>
              <div className="loading-fill" style={styles.loadingFill} />
            </div>
            <p style={styles.loadingText}>
              {analyzingTotal > 0
                ? `Analyzing track ${Math.min(analyzingStep + 1, analyzingTotal)} of ${analyzingTotal}…`
                : "Analyzing tracks…"}
            </p>
          </div>
        )}

        {error && <div style={styles.error}>{error}</div>}

        {analyzedTracks.length > 0 && (
          <section ref={resultRef} style={styles.result}>
            <h2 style={styles.resultTitle}>Analyzed tracks ({analyzedTracks.length})</h2>
            <ul style={styles.trackList}>
              {analyzedTracks.map((t, i) => (
                <li key={i} style={styles.trackItem}>
                  <strong style={styles.trackName}>{t.name}</strong>
                  {t.identified_song?.title && (
                    <span style={styles.identified}>
                      Identified: {t.identified_song.title}
                      {t.identified_song.artist ? ` — ${t.identified_song.artist}` : ""}
                    </span>
                  )}
                  {t.is_public && !t.identified_song?.title && (
                    <span style={styles.publicBadge}>Public (not identified)</span>
                  )}
                  <span style={styles.trackMeta}>
                    {t.features.bpm.toFixed(0)} BPM · {t.features.key} · {(t.features.energy_score * 100).toFixed(0)}% energy
                  </span>
                </li>
              ))}
            </ul>

            {analyzedTracks.length >= 2 && (
              <>
                <h3 style={styles.styleTitle}>Mix style</h3>
                <div style={styles.styleRow}>
                  {MIX_STYLES.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setMixStyle(s.id)}
                      style={{
                        ...styles.styleButton,
                        ...(mixStyle === s.id ? styles.styleButtonActive : {}),
                      }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={handleGenerateMixPlan}
                  disabled={loadingMixPlan}
                  style={styles.mixButton}
                >
                  {loadingMixPlan ? "Generating mix plan…" : "Generate mix plan"}
                </button>
                {loadingMixPlan && (
                  <div style={styles.loadingWrap}>
                    <div style={styles.loadingBar}>
                      <div className="loading-fill" style={styles.loadingFill} />
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {mixPlan && (
          <section ref={mixPlanRef} style={styles.mixSection}>
            <h2 style={styles.resultTitle}>Mix timeline</h2>
            <div style={styles.timeline}>
              {orderedTracks.map((t, i) => (
                <div
                  key={i}
                  style={{
                    ...styles.timelineTrack,
                    borderLeftColor: TRACK_COLORS[i % TRACK_COLORS.length],
                    borderLeftWidth: 4,
                    borderLeftStyle: "solid",
                    ...(isTransitionHighlight(i)
                      ? { background: "rgba(99, 102, 241, 0.12)", borderRadius: 8 }
                      : {}),
                  }}
                >
                  <span
                    style={{
                      ...styles.timelineNum,
                      background: TRACK_COLORS[i % TRACK_COLORS.length],
                    }}
                  >
                    {i + 1}
                  </span>
                  <span style={styles.timelineName}>{t.name}</span>
                  <span style={styles.timelineMeta}>
                    {t.features.bpm.toFixed(0)} BPM · {(t.features.energy_score * 100).toFixed(0)}%
                  </span>
                  {i < orderedTracks.length - 1 && (
                    <button
                      type="button"
                      style={{
                        ...styles.transitionBtn,
                        ...(selectedTransitionIndex === i ? styles.transitionBtnActive : {}),
                      }}
                      onClick={() =>
                        setSelectedTransitionIndex(selectedTransitionIndex === i ? null : i)
                      }
                      title="Why this transition?"
                    >
                      → transition
                    </button>
                  )}
                </div>
              ))}
            </div>

            {transitions.length > 0 &&
              selectedTransitionIndex !== null &&
              transitions[selectedTransitionIndex] && (
                <div style={styles.reasoningBox}>
                  <h3 style={styles.reasoningTitle}>
                    Why {orderedTracks[selectedTransitionIndex]?.name} →{" "}
                    {orderedTracks[selectedTransitionIndex + 1]?.name}?
                  </h3>
                  <p style={styles.reasoningText}>
                    {transitions[selectedTransitionIndex].reasoning_text ||
                      "No reasoning provided."}
                  </p>
                  <p style={styles.reasoningMeta}>
                    Transition:{" "}
                    {transitions[selectedTransitionIndex].transition_start_time}s –{" "}
                    {transitions[selectedTransitionIndex].transition_end_time}s ·{" "}
                    {transitions[selectedTransitionIndex].crossfade_duration_sec}s crossfade ·{" "}
                    {transitions[selectedTransitionIndex].eq_strategy}
                  </p>
                </div>
              )}

            {curveSamples.length > 0 && (
              <div style={styles.curveSection}>
                <h3 style={styles.curveTitle}>Energy curve (mix) — each track in its own colour</h3>
                <div style={styles.curveContainer}>
                  {curveSamples.map(({ i, v, trackIdx }, idx) => (
                    <div
                      key={idx}
                      style={{
                        ...styles.curveBar,
                        height: `${Math.max(4, (v ?? 0) * 100)}%`,
                        background:
                          selectedTransitionIndex !== null
                            ? isTransitionHighlight(trackIdx)
                              ? TRACK_COLORS[trackIdx % TRACK_COLORS.length]
                              : "rgba(63, 63, 70, 0.5)"
                            : TRACK_COLORS[trackIdx % TRACK_COLORS.length],
                      }}
                      title={`Track ${trackIdx + 1}: ${((v ?? 0) * 100).toFixed(0)}%`}
                    />
                  ))}
                </div>
              </div>
            )}

            {(() => {
              const canPreview = orderedTracks.length > 0 && orderedTracks.every((t) => t.sourceFile);
              return (
                <div style={styles.previewSection}>
                  <h3 style={styles.curveTitle}>Mix preview</h3>
                  <p style={styles.previewHint}>
                    {canPreview
                      ? "Play the mix in planned order with crossfades at each transition (uploaded files only)."
                      : "Upload all tracks as files (no YouTube links) to enable mix preview."}
                  </p>
                  {previewError && <p style={styles.previewError}>{previewError}</p>}
                  <div style={styles.previewButtons}>
                    {!isPreviewPlaying ? (
                      <button
                        type="button"
                        style={{ ...styles.button, ...(!canPreview ? styles.buttonDisabled : {}) }}
                        onClick={playPreview}
                        disabled={!canPreview}
                      >
                        Play mix preview
                      </button>
                    ) : (
                      <button type="button" style={{ ...styles.button, background: "#b91c1c" }} onClick={stopPreview}>
                        Stop preview
                      </button>
                    )}
                  </div>
                </div>
              );
            })()}
          </section>
        )}
      </main>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: 640,
    margin: "0 auto",
    padding: "2rem 1rem",
    minHeight: "100vh",
  },
  header: { marginBottom: "2rem", textAlign: "center" },
  title: {
    fontSize: "1.75rem",
    fontWeight: 700,
    margin: 0,
    color: "#fafafa",
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: "0.5rem 0 0", color: "#a1a1aa", fontSize: "0.95rem" },
  main: {},
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    marginBottom: "1.5rem",
  },
  sectionTitle: {
    margin: "0 0 0.5rem",
    fontSize: "1rem",
    fontWeight: 600,
    color: "#fafafa",
  },
  slot: {
    padding: "1rem",
    borderRadius: 12,
    border: "1px solid #27272a",
    background: "#18181b",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
  },
  slotHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  slotLabel: { fontSize: "0.875rem", fontWeight: 600, color: "#a1a1aa" },
  removeSlot: {
    width: 28,
    height: 28,
    borderRadius: 6,
    border: "1px solid #3f3f46",
    background: "transparent",
    color: "#a1a1aa",
    fontSize: "1.25rem",
    lineHeight: 1,
    cursor: "pointer",
    padding: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  orLabel: {
    fontSize: "0.8rem",
    color: "#71717a",
    textAlign: "center",
  },
  addSlotBtn: {
    padding: "0.75rem 1rem",
    borderRadius: 8,
    border: "2px dashed #3f3f46",
    background: "transparent",
    color: "#818cf8",
    fontWeight: 600,
    fontSize: "0.9rem",
    cursor: "pointer",
  },
  input: {
    padding: "0.5rem 0.75rem",
    borderRadius: 8,
    border: "1px solid #27272a",
    background: "#27272a",
    color: "#e4e4e7",
    fontSize: "0.9rem",
    cursor: "pointer",
  },
  toggleRow: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    cursor: "pointer",
    fontSize: "0.875rem",
    color: "#a1a1aa",
  },
  toggleLabel: { userSelect: "none" },
  button: {
    padding: "0.75rem 1.25rem",
    borderRadius: 8,
    border: "none",
    background: "#6366f1",
    color: "#fff",
    fontWeight: 600,
    fontSize: "0.95rem",
    cursor: "pointer",
  },
  loadingWrap: { marginBottom: "1.5rem" },
  loadingBar: {
    height: 6,
    borderRadius: 3,
    background: "#27272a",
    overflow: "hidden",
    marginBottom: "0.5rem",
  },
  loadingFill: {
    height: "100%",
    width: "40%",
    background: "linear-gradient(90deg, #6366f1, #818cf8)",
    borderRadius: 3,
  },
  loadingText: { margin: 0, fontSize: "0.875rem", color: "#a1a1aa" },
  error: {
    padding: "0.75rem 1rem",
    borderRadius: 8,
    background: "rgba(239, 68, 68, 0.15)",
    color: "#fca5a5",
    marginBottom: "1rem",
    fontSize: "0.9rem",
  },
  result: {
    padding: "1.25rem",
    borderRadius: 12,
    background: "#18181b",
    border: "1px solid #27272a",
    marginBottom: "1.5rem",
  },
  resultTitle: {
    margin: "0 0 1rem",
    fontSize: "1.1rem",
    fontWeight: 600,
    color: "#fafafa",
  },
  trackList: {
    margin: "0 0 1rem",
    paddingLeft: "1.25rem",
    color: "#e4e4e7",
    fontSize: "0.9rem",
  },
  trackItem: { marginBottom: "0.5rem" },
  trackName: { color: "#fafafa", display: "block" },
  identified: {
    display: "block",
    fontSize: "0.85rem",
    color: "#22c55e",
    marginTop: "0.25rem",
  },
  publicBadge: {
    display: "inline-block",
    fontSize: "0.8rem",
    color: "#a1a1aa",
    marginTop: "0.25rem",
  },
  trackMeta: { color: "#a1a1aa", marginLeft: 0, display: "block", marginTop: "0.2rem" },
  styleTitle: { margin: "1rem 0 0.5rem", fontSize: "0.95rem", color: "#a1a1aa", fontWeight: 500 },
  styleRow: { display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" },
  styleButton: {
    padding: "0.5rem 0.75rem",
    borderRadius: 8,
    border: "1px solid #27272a",
    background: "#27272a",
    color: "#e4e4e7",
    fontSize: "0.875rem",
    cursor: "pointer",
  },
  styleButtonActive: {
    background: "#6366f1",
    borderColor: "#6366f1",
    color: "#fff",
  },
  mixButton: {
    padding: "0.75rem 1.25rem",
    borderRadius: 8,
    border: "none",
    background: "#22c55e",
    color: "#fff",
    fontWeight: 600,
    fontSize: "0.95rem",
    cursor: "pointer",
  },
  mixSection: {
    padding: "1.25rem",
    borderRadius: 12,
    background: "#18181b",
    border: "1px solid #27272a",
  },
  timeline: { display: "flex", flexDirection: "column", gap: "0.25rem" },
  timelineTrack: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    flexWrap: "wrap",
    padding: "0.5rem 0.75rem",
  },
  timelineNum: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    color: "#fff",
    fontSize: "0.75rem",
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  timelineName: { color: "#fafafa", fontWeight: 500, flex: "1 1 180px" },
  timelineMeta: { color: "#a1a1aa", fontSize: "0.85rem" },
  transitionBtn: {
    padding: "0.25rem 0.5rem",
    borderRadius: 6,
    border: "1px solid #3f3f46",
    background: "transparent",
    color: "#818cf8",
    fontSize: "0.8rem",
    cursor: "pointer",
  },
  transitionBtnActive: {
    background: "#6366f1",
    borderColor: "#6366f1",
    color: "#fff",
  },
  reasoningBox: {
    marginTop: "1rem",
    padding: "1rem",
    borderRadius: 8,
    background: "#27272a",
    border: "1px solid #3f3f46",
  },
  reasoningTitle: { margin: "0 0 0.5rem", fontSize: "0.95rem", color: "#fafafa", fontWeight: 600 },
  reasoningText: { margin: 0, color: "#e4e4e7", fontSize: "0.9rem", lineHeight: 1.5 },
  reasoningMeta: { margin: "0.5rem 0 0", color: "#a1a1aa", fontSize: "0.8rem" },
  curveSection: {
    marginTop: "1.25rem",
    paddingTop: "1.25rem",
    borderTop: "1px solid #27272a",
  },
  curveTitle: {
    margin: "0 0 0.5rem",
    fontSize: "0.9rem",
    color: "#a1a1aa",
    fontWeight: 500,
  },
  curveContainer: {
    display: "flex",
    alignItems: "flex-end",
    gap: 2,
    height: 56,
  },
  curveBar: {
    flex: 1,
    minWidth: 2,
    borderRadius: 2,
  },
  previewSection: {
    marginTop: "1.25rem",
    paddingTop: "1.25rem",
    borderTop: "1px solid #27272a",
  },
  previewHint: { margin: "0 0 0.5rem", fontSize: "0.875rem", color: "#a1a1aa" },
  previewError: { margin: "0 0 0.5rem", fontSize: "0.875rem", color: "#fca5a5" },
  previewButtons: { display: "flex", gap: "0.5rem", alignItems: "center" },
  buttonDisabled: { opacity: 0.6, cursor: "not-allowed" },
};
