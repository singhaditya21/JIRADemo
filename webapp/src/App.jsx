import React, { useEffect, useState, useCallback } from "react";
import { Scoreboard, PairingPanel, Analysts, KBGap, Towers, Intake, Ageing } from "./panels.jsx";

const PROJECTS = ["OPS", "ITSM"];
const WINDOWS = [30, 90, 180];

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

export default function App() {
  const [project, setProject] = useState("OPS");
  const [days, setDays] = useState(90);
  const [model, setModel] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useTheme();

  const load = useCallback(() => {
    setLoading(true); setErr(null);
    fetch(`/api/tower?project=${project}&days=${days}`)
      .then((r) => r.json().then((j) => ({ ok: r.ok, j })))
      .then(({ ok, j }) => { if (!ok || j.error) throw new Error(j.error || "request failed"); setModel(j); })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [project, days]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <header className="mast">
        <div>
          <h1>L1/L2 Control Tower</h1>
          <div className="sub">
            {model ? `${model.project} · ${model.window_label} · ${model.volume} in window · ${model.pages} request(s)` : "live from Jira"}
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
          <button onClick={load} title="refetch">↻</button>
          <button onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "auto" : "dark")} title="theme">
            {theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐"}
          </button>
        </div>
      </header>

      <main>
        {loading && <div className="state">reading {project} from Jira …</div>}
        {err && <div className="state err">could not load: {err}<br /><br />is the API running?  <span className="mono">python3 -m app.server</span></div>}
        {model && !loading && !err && (
          <>
            <div className="grid">
              <Scoreboard model={model} />
              <PairingPanel model={model} />
              <Analysts model={model} />
              <KBGap model={model} />
              <Towers model={model} />
              <Intake model={model} />
              <Ageing model={model} />
            </div>
            <p className="note">
              Every figure is computed server-side by <span className="mono">app/analytics.py</span> — the same code the static
              control tower and the metrics CLI use, so they cannot disagree. Read-only against Jira.
              {model.warnings?.length ? ` ${model.warnings.length} data warning(s).` : ""}
            </p>
          </>
        )}
      </main>
    </>
  );
}
