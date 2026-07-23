import React, { useEffect, useLayoutEffect, useState, useCallback, useRef } from "react";
import { KpiStrip, PairingPanel, Analysts, KBGap, Towers, Intake, Ageing,
  SlaOutcomes, BacklogFlow, ChannelQuality, AgeingByStatus,
  QueueByStatus, EscalationReasons, InsightsFeed, IntegrityStrip, ImpactUrgency,
  MajorIncident, TierFlow, PracticeMix, IncidentManagement, ChangeManagement,
  ProblemManagement, RequestFulfilment, SlaByType, CustomerSatisfaction,
  SnapshotTrends, BenchmarkLeague, WhatChanged, AnomalyWatch, Recommendations,
  Forecast, CriteriaScorecard, EscalationReasonMatrix, IntakeByTower, AnalystLoad,
  AskTower, TierSankey, DemandCurve, TriageDwell, EscalationLatency, TimeInTier,
  ReasonRootCause, SlaByPriority, KBDiscipline, ResolutionCodeMix, RootCausePareto,
  OpenByPriority, FlowBalance, GateBypass, InvariantFooter,
  IncidentVolByTower, IncidentEscByTower, MTTAByPriority, OLAHandoff, SlaOutcomeMix,
  SlaTypePriority, RequestAging, ApprovalAging, RCACycle, CSATvsSLA, CSATByTower,
  QueueDepth, ChangeSuccess, ProblemBacklog, DQBoard,
  HeadlineBanner, PilotProgress, AtRiskToday, RuleHealth, DeflectionFunnel,
  DeliveryPreviewBanner, SFCKpi, StageFunnel, DeployMatrix, ConfigHealthBoard, AgentLedger, CABGate,
  SFCTrend, DeployFailureByOrg, SFCLeadWip, SFCOutcomes,
  AgentWorkload, AgentHandoff, MockAgentFeed,
  MockNlqAnswer, MockCsatFeed, MockBreachRisk, MockMultiInstance, MockOutcomes18mo } from "./panels.jsx";
import { Drawer } from "./drill.jsx";

const PROJECTS = ["OPS", "ITSM", "SFC"];
const WINDOWS = [30, 90, 180];
const LENSES = [
  { id: "overview", lab: "Overview", blurb: "The whole system — how the tower is performing end to end." },
  { id: "L1", lab: "L1", blurb: "The front line — triage, deflection, response SLA, and what to escalate." },
  { id: "L2", lab: "L2", blurb: "Second line — escalations coming in, resolution SLA, and the KB debt to clear." },
];

// Which panels each lens shows, in order — now project-aware: the ITSM project gets ITIL
// panels (incident/change/problem/request/SLA-by-type), OPS gets its L1/L2-native ones
// (tier-flow, Impact×Urgency, major incident). `records` powers the record-derived panels.
function lensPanels(lens, project, model, open, records, history, baseline) {
  const P = { model, open };
  const R = { model, open, records };
  const itsm = project === "ITSM";
  // SFC (DeliveryIQ) is its own delivery-pipeline lens — same panels for every tab.
  if (project === "SFC") return [
    <DeliveryPreviewBanner key="pre" {...P} />,
    <SFCKpi key="kpi" {...R} />,
    <StageFunnel key="fun" {...R} />,
    <DeployMatrix key="dm" {...R} />,
    <ConfigHealthBoard key="chb" {...R} />,
    <CABGate key="cab" {...R} />,
    <AgentWorkload key="aw" {...R} />,
    <AgentHandoff key="ah" {...R} />,
    <AgentLedger key="led" {...R} />,
    <MockAgentFeed key="maf" {...R} />,
    <DeployFailureByOrg key="dfo" {...R} />,
    <SFCLeadWip key="lw" {...R} />,
    <SFCTrend key="strend" history={history} />,
    <SFCOutcomes key="sout" model={model} records={records} baseline={baseline} />,
    // mocks compatible with the SFC record shape (is_done/priority/age_days), badged MOCK
    <MockBreachRisk key="mbr" {...R} />,
    <MockMultiInstance key="mmi" {...R} />,
    <MockOutcomes18mo key="mo18" {...R} />,
    // The tower's signature discipline, previously absent from SFC: the self-checks that
    // gate whether a panel may render, plus the wart-catchers that surface the instance's
    // own contradictions rather than hiding them (model.invariants, emitted by the bake).
    <InvariantFooter key="inv" {...P} />,
  ];
  if (lens === "L1") return [
    <InsightsFeed key="ins" {...P} />,
    <QueueByStatus key="q" {...P} tier="L1" />,
    <SlaOutcomes key="sla" {...P} lens="L1" />,
    ...(itsm ? [<IncidentManagement key="im" {...R} />, <RequestFulfilment key="rf" {...R} />, <CustomerSatisfaction key="csat" {...R} />] : []),
    <PairingPanel key="pair" {...P} />,
    <Analysts key="an" {...P} />,
    <AnalystLoad key="al" {...R} />,
    <ImpactUrgency key="iu" {...R} />,
    <KBGap key="kb" {...P} lens="L1" />,
    <ChannelQuality key="ch" {...P} />,
    <IntakeByTower key="ibt" {...R} />,
    <Intake key="in" {...P} />,
  ];
  if (lens === "L2") return [
    <InsightsFeed key="ins" {...P} />,
    <QueueByStatus key="q" {...P} tier="L2" />,
    <SlaOutcomes key="sla" {...P} lens="L2" />,
    ...(itsm ? [<ProblemManagement key="pm" {...R} />, <ChangeManagement key="cm" {...R} />]
            : [<TierFlow key="tf" {...R} />, <TierSankey key="tsk" {...R} />]),
    <KBGap key="kb" {...P} lens="L2" />,
    <EscalationReasons key="er" {...P} />,
    ...(itsm ? [] : [<EscalationReasonMatrix key="erm" {...R} />]),
    <MajorIncident key="mi" {...R} />,
    <Towers key="tw" {...P} />,
    <AgeingByStatus key="abs" {...P} />,
    <BacklogFlow key="bf" {...P} />,
  ];
  return [
    <HeadlineBanner key="hl" {...P} />,
    <AskTower key="ask" {...R} />,
    <InsightsFeed key="ins" {...P} />,
    <PilotProgress key="pp" model={model} baseline={baseline} history={history} />,
    <Recommendations key="rec" {...P} />,
    <AtRiskToday key="risk" {...R} />,
    <DeflectionFunnel key="def" {...R} />,
    ...(itsm ? [] : [<RuleHealth key="rh" {...R} />]),
    <WhatChanged key="chg" history={history} />,
    <AnomalyWatch key="anom" {...P} />,
    <BenchmarkLeague key="league" {...P} />,
    <Forecast key="fc" {...P} />,
    <CriteriaScorecard key="crit" {...P} />,
    <SnapshotTrends key="trend" history={history} />,
    ...(itsm
      ? [<PracticeMix key="pmx" {...R} />, <IncidentManagement key="im" {...R} />,
         <IncidentVolByTower key="ivt" {...R} />, <IncidentEscByTower key="iet" {...R} />, <MTTAByPriority key="mtp" {...R} />,
         <ChangeManagement key="cm" {...R} />, <ChangeSuccess key="cs" {...R} />,
         <ProblemManagement key="pm" {...R} />, <ProblemBacklog key="pb" {...R} />, <RCACycle key="rca" {...R} />,
         <RequestFulfilment key="rf" {...R} />, <RequestAging key="ra" {...R} />, <ApprovalAging key="aa" {...R} />,
         <CustomerSatisfaction key="csat" {...R} />, <CSATvsSLA key="cvs" {...R} />, <CSATByTower key="cbt" {...R} />,
         <SlaByType key="sbt" {...R} />, <SlaTypePriority key="stp" {...R} />, <SlaOutcomeMix key="som" {...R} />,
         <OLAHandoff key="ola" {...R} />, <QueueDepth key="qd" {...R} />, <DQBoard key="dq" {...R} />]
      : [<TierFlow key="tf" {...R} />, <TierSankey key="tsk" {...R} />, <TimeInTier key="tit" {...R} />,
         <EscalationLatency key="elat" {...R} />, <ImpactUrgency key="iu" {...R} />, <MajorIncident key="mi" {...R} />,
         <EscalationReasonMatrix key="erm" {...R} />, <ReasonRootCause key="rrc" {...R} />, <GateBypass key="gb" {...R} />,
         <IntakeByTower key="ibt" {...R} />, <DemandCurve key="dc" {...P} />, <TriageDwell key="td" {...R} />,
         <SlaByPriority key="sbp" {...R} />, <OpenByPriority key="obp" {...R} />, <KBDiscipline key="kbd" {...R} />,
         <ResolutionCodeMix key="rcm" {...R} />, <RootCausePareto key="rcp" {...R} />, <FlowBalance key="fb2" {...P} />,
         <AnalystLoad key="al" {...R} />]),
    <PairingPanel key="pair" {...P} />,
    <Analysts key="an" {...P} />,
    <SlaOutcomes key="sla" {...P} />,
    <BacklogFlow key="bf" {...P} />,
    <KBGap key="kb" {...P} />,
    <Towers key="tw" {...P} />,
    <ChannelQuality key="ch" {...P} />,
    <Intake key="in" {...P} />,
    <Ageing key="ag" {...P} />,
    <AgeingByStatus key="abs" {...P} />,
    // Labs — clearly-badged MOCKS of features that need systems this demo doesn't have
    // (a runtime LLM, a survey tool, a trained model, multiple instances, 18 months).
    <MockNlqAnswer key="mnlq" {...R} />,
    <MockBreachRisk key="mbr" {...R} />,
    <MockCsatFeed key="mcsat" {...R} />,
    <MockMultiInstance key="mmi" {...R} />,
    <MockOutcomes18mo key="mo18" {...R} />,
    <IntegrityStrip key="int" {...P} />,
    <InvariantFooter key="inv" {...P} />,
  ];
}

// Where the data comes from:
//   - "static" (GitHub Pages):  fetch the JSON baked at deploy time by app.export_pages.
//   - "api"    (dev / live):    fetch app.server, which holds the token and computes live.
// Production defaults to static (Pages has no backend); dev defaults to api. Override with
// VITE_DATA_MODE. In static mode the page also re-polls so it picks up each CI redeploy.
//
// NEAR-REAL-TIME: build the Pages app with VITE_DATA_MODE=api and VITE_API_BASE=<backend url>
// to read live from a hosted app.server instead of the baked files. VITE_API_BASE is empty in
// dev (Vite proxies /api to localhost); set it to the deployed backend's origin for Pages.
// See webapp/DEPLOY-BACKEND.md.
const DATA_MODE = import.meta.env.VITE_DATA_MODE || (import.meta.env.PROD ? "static" : "api");
const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
const BASE = import.meta.env.BASE_URL || "/";
const REFRESH_MS = 5 * 60 * 1000; // re-check for a fresher deploy every 5 min (static mode)

function dataUrl(project, days) {
  return DATA_MODE === "static"
    ? `${BASE}data/${project}-${days}.json?_=${Date.now()}` // cache-bust so a redeploy shows
    : `${API_BASE}/api/tower?project=${project}&days=${days}`;
}

function recordsUrl(project) {
  return DATA_MODE === "static"
    ? `${BASE}data/${project}-records.json`
    : `${API_BASE}/api/records?project=${project}`;
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

// Board state lives in the URL hash (#/PROJECT/LENS/DAYS) so any view is a shareable,
// bookmarkable link. Parsed on load; kept in sync as the controls change.
// Drill types whose whole state is data (no predicate function), so they round-trip through
// a URL. Record-filter drills carry a function and are deliberately not link-encoded.
const SHAREABLE_DRILL = ["metric", "kbgap", "statusgroup", "tower"];
function encodeDrill(d) { try { return btoa(unescape(encodeURIComponent(JSON.stringify(d)))); } catch { return ""; } }
function decodeDrill(s) { try { const d = JSON.parse(decodeURIComponent(escape(atob(s)))); return SHAREABLE_DRILL.includes(d.type) ? d : undefined; } catch { return undefined; } }

function parseHash() {
  const h = window.location.hash || "";
  const m = h.match(/^#\/([A-Za-z]+)(?:\/([A-Za-z0-9]+))?(?:\/(\d+))?/);
  if (!m) return {};
  const days = m[3] ? Number(m[3]) : undefined;
  const dm = h.match(/\/d\/([^/]+)/);
  return {
    project: PROJECTS.includes(m[1]) ? m[1] : undefined,
    lens: LENSES.some((l) => l.id === m[2]) ? m[2] : undefined,
    days: WINDOWS.includes(days) ? days : undefined,
    drill: dm ? decodeDrill(dm[1]) : undefined,
  };
}

export default function App() {
  const boot = parseHash();
  const [project, setProject] = useState(boot.project || "OPS");
  const [days, setDays] = useState(boot.days || 90);
  const [model, setModel] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useTheme();
  const [drill, setDrill] = useState(boot.drill || null);   // the clicked-into detail, or null
  const [records, setRecords] = useState({}); // {project: [...]}, lazy-loaded for drills
  const [history, setHistory] = useState({}); // {project: [points]}, the daily snapshot trend
  const [baseline, setBaseline] = useState({}); // {project: {ftr_pct,...}}, frozen pilot baseline
  const [lens, setLens] = useState(boot.lens || localStorage.getItem("ct-lens") || "overview");
  useEffect(() => { localStorage.setItem("ct-lens", lens); }, [lens]);
  // keep the URL in sync so the current view is a shareable link
  useEffect(() => {
    const h = `#/${project}/${lens}/${days}`;
    if (window.location.hash !== h) window.history.replaceState(null, "", h);
  }, [project, lens, days]);
  const reqId = useRef(0);
  const gridRef = useRef(null);

  // Masonry: size each panel's grid-row-end to its own content height (+ a 16px vertical gap)
  // so a short panel never leaves empty space under a taller row-mate. align-items:start keeps
  // panels content-height, so measuring is idempotent; a ResizeObserver re-packs on any change.
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid || typeof ResizeObserver === "undefined") return;
    let raf = 0;
    const pack = () => {
      const panels = [...grid.querySelectorAll(":scope > .panel")];
      const heights = panels.map((p) => Math.round(p.getBoundingClientRect().height)); // read all first
      panels.forEach((p, i) => { p.style.gridRowEnd = "span " + (heights[i] + 16); });   // then write all
    };
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(pack); };
    schedule();
    const ro = new ResizeObserver(schedule);
    for (const p of grid.querySelectorAll(":scope > .panel")) ro.observe(p);
    window.addEventListener("resize", schedule);
    const onLoad = () => schedule();
    window.addEventListener("load", onLoad);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); window.removeEventListener("resize", schedule); window.removeEventListener("load", onLoad); };
  }, [lens, project, model, records, history, baseline]);

  // Lazy-load the record-level dataset once the aggregate model is up (record-driven panels
  // and drills both use it); cached per project.
  useEffect(() => {
    if (!model || records[project]) return;
    fetch(recordsUrl(project))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j?.records && setRecords((prev) => ({ ...prev, [project]: j.records })))
      .catch(() => {});
  }, [model, project, records]);

  // Lazy-load the daily snapshot history (static-only; the file is committed back by CI).
  // Absent/empty is fine — the trend panel says "building history".
  useEffect(() => {
    if (!model || history[project] || DATA_MODE !== "static") return;
    fetch(`${BASE}data/${project}-history.json?_=${Date.now()}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setHistory((prev) => ({ ...prev, [project]: (j && j.points) || [] })))
      .catch(() => {});
  }, [model, project, history]);

  // Lazy-load the frozen pilot baseline (for baseline → current → target framing).
  useEffect(() => {
    if (!model || baseline[project] || DATA_MODE !== "static") return;
    fetch(`${BASE}data/${project}-baseline.json?_=${Date.now()}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setBaseline((prev) => ({ ...prev, [project]: (j && j.baseline) || null })))
      .catch(() => {});
  }, [model, project, baseline]);

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

      <main className={drill ? "drawer-open" : ""}>
        {loading && !model && <div className="state">loading {project} …</div>}
        {/* A user-initiated load (switch/refresh) that fails shows the error rather than
            stale, wrong-labelled data. Quiet auto-poll failures stay silent (last good data
            remains on screen), so `err` is only ever set by a non-quiet load. */}
        {err && <div className="state err">could not load: {err}<br /><br />{backendHint}</div>}
        {model && !err && (
          <>
            <div className="lens-caption">
              <strong>{project === "SFC" ? "Delivery / SF Config" : LENSES.find((l) => l.id === lens).lab}</strong>
              <span>{project === "SFC" ? "DeliveryIQ — Salesforce config requests through the five-stage pipeline (Intake → Build → Review → Deploy → Audit)." : LENSES.find((l) => l.id === lens).blurb}</span>
            </div>
            {project !== "SFC" && <KpiStrip model={model} lens={lens} open={setDrill} />}
            <div className="grid" ref={gridRef}>
              {lensPanels(lens, project, model, setDrill, records[project] || null, history[project] || null, baseline[project] || null)}
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
