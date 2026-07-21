import React, { useEffect, useState, useCallback, useRef } from "react";
import { KpiStrip, PairingPanel, Analysts, KBGap, Towers, Intake, Ageing,
  SlaOutcomes, BacklogFlow, ChannelQuality, AgeingByStatus,
  QueueByStatus, EscalationReasons, InsightsFeed, IntegrityStrip, ImpactUrgency,
  MajorIncident } from "./panels.jsx";
import { Drawer } from "./drill.jsx";

const PROJECTS = ["OPS", "ITSM"];
const WINDOWS = [30, 90, 180];
const LENSES = [
  { id: "overview", lab: "Overview", blurb: "The whole system — how the tower is performing end to end." },
  { id: "L1", lab: "L1", blurb: "The front line — triage, deflection, response SLA, and what to escalate." },
  { id: "L2", lab: "L2", blurb: "Second line — escalations coming in, resolution SLA, and the KB debt to clear." },
];

// Which panels each lens shows, in order. Tier lenses reframe shared panels and add their own.
// `records` powers the panels computed from the record layer (Impact×Urgency, Major incident).
function lensPanels(lens, model, open, records) {
  const P = { model, open };
  const R = { model, open, records };
  if (lens === "L1") return [
    <InsightsFeed key="ins" {...P} />,
    <QueueByStatus key="q" {...P} tier="L1" />,
    <SlaOutcomes key="sla" {...P} lens="L1" />,
    <PairingPanel key="pair" {...P} />,
    <Analysts key="an" {...P} />,
    <ImpactUrgency key="iu" {...R} />,
    <KBGap key="kb" {...P} lens="L1" />,
    <ChannelQuality key="ch" {...P} />,
    <Intake key="in" {...P} />,
  ];
  if (lens === "L2") return [
    <InsightsFeed key="ins" {...P} />,
    <QueueByStatus key="q" {...P} tier="L2" />,
    <SlaOutcomes key="sla" {...P} lens="L2" />,
    <KBGap key="kb" {...P} lens="L2" />,
    <EscalationReasons key="er" {...P} />,
    <MajorIncident key="mi" {...R} />,
    <Towers key="tw" {...P} />,
    <AgeingByStatus key="abs" {...P} />,
    <BacklogFlow key="bf" {...P} />,
  ];
  return [
    <InsightsFeed key="ins" {...P} />,
    <PairingPanel key="pair" {...P} />,
    <Analysts key="an" {...P} />,
    <SlaOutcomes key="sla" {...P} />,
    <BacklogFlow key="bf" {...P} />,
    <KBGap key="kb" {...P} />,
    <Towers key="tw" {...P} />,
    <ImpactUrgency key="iu" {...R} />,
    <MajorIncident key="mi" {...R} />,
    <ChannelQuality key="ch" {...P} />,
    <Intake key="in" {...P} />,
    <Ageing key="ag" {...P} />,
    <AgeingByStatus key="abs" {...P} />,
    <IntegrityStrip key="int" {...P} />,
  ];
}

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
  const [records, setRecords] = useState({}); // {project: [...]}, lazy-loaded for drills
  const [lens, setLens] = useState(() => localStorage.getItem("ct-lens") || "overview");
  useEffect(() => { localStorage.setItem("ct-lens", lens); }, [lens]);
  const reqId = useRef(0);

  // Lazy-load the record-level dataset once the aggregate model is up (record-driven panels
  // and drills both use it); cached per project.
  useEffect(() => {
    if (!model || records[project]) return;
    fetch(`${BASE}data/${project}-records.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j?.records && setRecords((prev) => ({ ...prev, [project]: j.records })))
      .catch(() => {});
  }, [model, project, records]);

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
          <div className="seg seg-lens">
            {LENSES.map((l) => (
              <button key={l.id} className={l.id === lens ? "on" : ""} onClick={() => setLens(l.id)} title={l.blurb}>{l.lab}</button>
            ))}
          </div>
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
            <div className="lens-caption">
              <strong>{LENSES.find((l) => l.id === lens).lab}</strong>
              <span>{LENSES.find((l) => l.id === lens).blurb}</span>
            </div>
            <KpiStrip model={model} lens={lens} open={setDrill} />
            <div className="grid">
              {lensPanels(lens, model, setDrill, records[project] || null)}
            </div>
            <p className="note">
              Every figure is computed by <span className="mono">app/analytics.py</span> — the same code the static
              control tower and the metrics CLI use, so they cannot disagree.
              {DATA_MODE === "static"
                ? " Baked to static JSON by a scheduled GitHub Action (the Jira token stays in CI, never in the browser)."
                : " Read-only against Jira."}
              {model.warnings?.length ? ` ${model.warnings.length} data warning(s).` : ""}
            </p>
            <Drawer drill={drill} model={model} records={records[project] || null} onClose={() => setDrill(null)} />
          </>
        )}
      </main>
    </>
  );
}
