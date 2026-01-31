import { useState } from "react";

const API_BASE = "/api";

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleAnalyze(e) {
    e.preventDefault();
    if (!file) {
      setError("Select an audio file first.");
      return;
    }
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>DJMashAI</h1>
        <p style={styles.subtitle}>AI-powered DJ mix planning — upload a track to analyze</p>
      </header>

      <main style={styles.main}>
        <form onSubmit={handleAnalyze} style={styles.form}>
          <label style={styles.label}>
            <span style={styles.labelText}>Audio file (.mp3, .wav, .m4a, .flac)</span>
            <input
              type="file"
              accept=".mp3,.wav,.m4a,.flac,.ogg"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
              style={styles.input}
            />
          </label>
          <button type="submit" disabled={loading || !file} style={styles.button}>
            {loading ? "Analyzing…" : "Analyze track"}
          </button>
        </form>

        {error && (
          <div style={styles.error}>
            {error}
          </div>
        )}

        {result && (
          <section style={styles.result}>
            <h2 style={styles.resultTitle}>Track features</h2>
            <dl style={styles.dl}>
              <div style={styles.row}>
                <dt style={styles.dt}>BPM</dt>
                <dd style={styles.dd}>{result.bpm.toFixed(1)}</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Key</dt>
                <dd style={styles.dd}>{result.key}</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Energy</dt>
                <dd style={styles.dd}>{(result.energy_score * 100).toFixed(0)}%</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Duration</dt>
                <dd style={styles.dd}>{result.duration_sec.toFixed(1)} s</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Loudness</dt>
                <dd style={styles.dd}>{result.loudness_profile}</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Intro</dt>
                <dd style={styles.dd}>{result.intro_window[0].toFixed(1)}s – {result.intro_window[1].toFixed(1)}s</dd>
              </div>
              <div style={styles.row}>
                <dt style={styles.dt}>Outro</dt>
                <dd style={styles.dd}>{result.outro_window[0].toFixed(1)}s – {result.outro_window[1].toFixed(1)}s</dd>
              </div>
              {result.drop_regions?.length > 0 && (
                <div style={styles.row}>
                  <dt style={styles.dt}>Drop regions</dt>
                  <dd style={styles.dd}>
                    {result.drop_regions.length} region(s):{" "}
                    {result.drop_regions
                      .slice(0, 3)
                      .map(([a, b]) => `${a.toFixed(0)}–${b.toFixed(0)}s`)
                      .join(", ")}
                    {result.drop_regions.length > 3 && " …"}
                  </dd>
                </div>
              )}
            </dl>
            {result.energy_curve?.length > 0 && (
              <div style={styles.curveSection}>
                <h3 style={styles.curveTitle}>Energy curve (preview)</h3>
                <div style={styles.curveContainer}>
                  {result.energy_curve
                    .filter((_, i) => i % Math.max(1, Math.floor(result.energy_curve.length / 80)) === 0)
                    .map((v, i) => (
                      <div
                        key={i}
                        style={{
                          ...styles.curveBar,
                          height: `${Math.max(4, v * 100)}%`,
                        }}
                        title={`${(v * 100).toFixed(0)}%`}
                      />
                    ))}
                </div>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: 560,
    margin: "0 auto",
    padding: "2rem 1rem",
    minHeight: "100vh",
  },
  header: {
    marginBottom: "2rem",
    textAlign: "center",
  },
  title: {
    fontSize: "1.75rem",
    fontWeight: 700,
    margin: 0,
    color: "#fafafa",
    letterSpacing: "-0.02em",
  },
  subtitle: {
    margin: "0.5rem 0 0",
    color: "#a1a1aa",
    fontSize: "0.95rem",
  },
  main: {},
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    marginBottom: "1.5rem",
  },
  label: {
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
  },
  labelText: {
    fontSize: "0.875rem",
    color: "#a1a1aa",
    fontWeight: 500,
  },
  input: {
    padding: "0.5rem 0.75rem",
    borderRadius: 8,
    border: "1px solid #27272a",
    background: "#18181b",
    color: "#e4e4e7",
    fontSize: "0.9rem",
    cursor: "pointer",
  },
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
  },
  resultTitle: {
    margin: "0 0 1rem",
    fontSize: "1.1rem",
    fontWeight: 600,
    color: "#fafafa",
  },
  dl: {
    margin: 0,
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: "1rem",
  },
  dt: {
    margin: 0,
    color: "#a1a1aa",
    fontSize: "0.875rem",
  },
  dd: {
    margin: 0,
    color: "#e4e4e7",
    fontSize: "0.9rem",
    fontWeight: 500,
  },
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
    height: 48,
  },
  curveBar: {
    flex: 1,
    minWidth: 2,
    background: "linear-gradient(to top, #6366f1, #818cf8)",
    borderRadius: 2,
  },
};
