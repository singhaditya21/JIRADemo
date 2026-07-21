import React, { useEffect, useState, useCallback, useRef } from "react";
import { Scoreboard, PairingPanel, Analysts, KBGap, Towers, Intake, Ageing,
  SlaOutcomes, BacklogFlow, ChannelQuality, AgeingByStatus } from "./panels.jsx";
import { Drawer } from "./drill.jsx";

const PROJECTS = ["OPS", "ITSM"];
const WINDOWS = [30, 90, 180];

// Where the data comes from:
//   - "static" (GitHub Pages): fetch the JSON baked at deploy time by app.export_pages.
//   - "api" (local dev):       fetch the live app.server backend that holds the token.
// Production defaults to static (Pages has no backend); dev defaults to api. Override with
// VITE_DATA_MODE. In static mode the page also re-polls so it picks up each CI redeploy.
const DATA_MODE = import.meta.env.VITE_DATA_MODE || (import.meta.env.PROD ? "static" : "api");
const BASE = import.meta.env.BASE_URL || "/";
const REFRESH_MS = 5 * 60 * 1000; // re-check for a fresher deploy every 5 min (static mode)

function dataUrl(project, days) {
  return DATA_MODE === "static"
    ? `${BASE}data/${project}-${days}.json?_=${Date.now()}` // cache-bust so a redeploy shows
    : `/api/tower?project=${project}&days=${days}`;
}

function useTheme() {
  const [t, setT] = useState(() => localStorage.getItem("ct-theme") || "auto");
  useEffect(() => {
    const root = document.documentElement;
    if (t === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", t);
    localStorage.setItem("ct-theme", t);
  }, [t]);
  return [t, setT];
}

// "3 min ago" from an ISO timestamp, re-rendered on a tick.
function Freshness({ iso }) {
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 30000);
    return () => clearInterval(id);
  }, []);
  if (!iso) return null;
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const rel =
    secs < 90 ? "just now" :
    secs < 3600 ? `${Math.round(secs / 60)} min ago` :
    secs < 86400 ? `${Math.round(secs / 3600)} h ago` :
    `${Math.round(secs / 86400)} d ago`;
  const abs = new Date(iso).toLocaleString();
  return <span className="fresh" title={`data generated ${abs}`}>updated {rel}</span>;
}

export default function App() {
  const [project, setProject] = useState("OPS");
  const [days, setDays] = useState(90);
  const [model, setModel] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useTheme();
  const [drill, setDrill] = useState(null);   // the clicked-into detail, or null
  const reqId = useRef(0);

  const load = useCallback((quiet = false) => {
    const id = ++reqId.current;
    if (!quiet) { setLoading(true); setErr(null); }
    fetch(dataUrl(project, days))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => {
        if (id !== reqId.current) return;            // a newer request superseded this one
        if (j.error) throw new Error(j.error);
        setModel(j); setErr(null);
      })
      .catch((e) => { if (id === reqId.current && !quiet) setErr(String(e.message || e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
  }, [project, days]);

  useEffect(() => { load(); }, [load]);

  // Static mode: quietly re-poll so a left-open tab reflects the latest deploy.
  useEffect(() => {
    if (DATA_MODE !== "static") return;
    const t = setInterval(() => load(true), REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const backendHint = DATA_MODE === "static"
    ? <>the data file may not be published yet — the GitHub Action bakes <span className="mono">webapp/public/data</span> on deploy.</>
    : <>is the API running? <span className="mono">python3 -m app.server</span></>;

  return (
    <>
      <header className="mast">
        <div>
          <h1>L1/L2 Control Tower</h1>
          <div className="sub">
            {model
              ? <>{model.project} · {model.window_label} · {model.volume} in window · <Freshness iso={model.generated_at} /></>
              : DATA_MODE === "static" ? "aligned with Jira, refreshed on schedule" : "live from Jira"}
          </div>
        </div>
        <div className="controls">
          <div className="seg">
            {PROJECTS.map((p) => (
              <button key={p} className={p === project ? "on" : ""} onClick={() => setProject(p)}>{p}</button>
            ))}
          </div>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {WINDOWS.map((w) => <option key={w} value={w}>{w} days</option>)}
          </select>
          <button onClick={() => load()} title="refresh">↻</button>
          <button onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "auto" : "dark")} title="theme">
            {theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐"}
          </button>
        </div>
      </header>

      <main>
        {loading && !model && <div className="state">loading {project} …</div>}
        {/* A user-initiated load (switch/refresh) that fails shows the error rather than
            stale, wrong-labelled data. Quiet auto-poll failures stay silent (last good data
            remains on screen), so `err` is only ever set by a non-quiet load. */}
        {err && <div className="state err">could not load: {err}<br /><br />{backendHint}</div>}
        {model && !err && (
          <>
            <div className="grid">
              <Scoreboard model={model} open={setDrill} />
              <PairingPanel model={model} open={setDrill} />
              <Analysts model={model} open={setDrill} />
              <SlaOutcomes model={model} open={setDrill} />
              <BacklogFlow model={model} open={setDrill} />
              <KBGap model={model} open={setDrill} />
              <Towers model={model} open={setDrill} />
              <ChannelQuality model={model} open={setDrill} />
              <Intake model={model} open={setDrill} />
              <Ageing model={model} open={setDrill} />
              <AgeingByStatus model={model} open={setDrill} />
            </div>
            <p className="note">
              Every figure is computed by <span className="mono">app/analytics.py</span> — the same code the static
              control tower and the metrics CLI use, so they cannot disagree.
              {DATA_MODE === "static"
                ? " Baked to static JSON by a scheduled GitHub Action (the Jira token stays in CI, never in the browser)."
                : " Read-only against Jira."}
              {model.warnings?.length ? ` ${model.warnings.length} data warning(s).` : ""}
            </p>
            <Drawer drill={drill} model={model} onClose={() => setDrill(null)} />
          </>
        )}
      </main>
    </>
  );
}
