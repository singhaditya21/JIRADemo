import React, { useEffect, useState } from "react";
import { Sparkline, Bars } from "./charts.jsx";

// Drill-down detail. Clicking any chart element opens this drawer with the numbers behind
// the mark and a deep link into Jira's issue navigator. The link JQL uses cf[<id>] clause
// names (this instance's custom-field ids) so it resolves even where a field name is
// duplicated (e.g. Urgency); system fields need no id.
const F = {
  tower: "cf[10042]", tier: "cf[10043]", channel: "cf[10045]",
  impact: "cf[10004]", urgency: "cf[10044]", reopened: "cf[10052]",
  resSla: "cf[10051]", respSla: "cf[10050]", escReason: "cf[10046]", kbChecked: "cf[10047]",
  rootCause: "cf[10048]",
};
const KB_NONE = "Yes - none found";

const f1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toFixed(1));
const pct = (v) => (v == null ? "—" : f1(v) + "%");
export const jira = (site, clause) => `${site}/issues/?jql=${encodeURIComponent(clause)}`;
const q = (s) => `"${String(s).replace(/"/g, '\\"')}"`;

function KV({ rows }) {
  return (
    <dl className="kv">
      {rows.filter(Boolean).map(([k, v], i) => (
        <React.Fragment key={i}><dt>{k}</dt><dd className="tnum">{v}</dd></React.Fragment>
      ))}
    </dl>
  );
}

// type -> { title, body, jql } given the click payload and the model.
function detail(d, model) {
  const P = model.project, weekly = model.weekly || [];
  switch (d.type) {
    case "metric": {
      const m = model.scoreboard[d.key] || {};
      const clauseByKey = {
        ftr_pct: `project = ${P} AND ${F.tier} = L1 AND resolution is not EMPTY`,
        escalation_pct: `project = ${P} AND ${F.tier} = L2`,
        reopen_pct: `project = ${P} AND ${F.reopened} = Yes`,
        sla_pct: `project = ${P} AND ${F.resSla} = Breached`,
        response_pct: `project = ${P} AND ${F.respSla} = Breached`,
        aged_14d: `project = ${P} AND resolution is EMPTY AND created <= -14d`,
      };
      return {
        title: d.lab,
        jql: clauseByKey[d.key],
        body: (
          <>
            <div className="drill-big tnum">{d.unit === "%" ? pct(m.value) : (m.value ?? m.num ?? "—")}</div>
            <KV rows={[
              m.num != null && m.den != null && ["Numerator / denominator", `${m.num} / ${m.den}`],
              m.target != null && ["Target", `${m.direction === "ge" ? "≥" : m.direction === "le" ? "≤" : ""}${m.target}${m.target <= 100 ? "%" : ""}`],
              m.verdict && ["Verdict", m.verdict],
              ["Metric", d.note],
            ]} />
            <p className="drill-note">Weekly trend over the window:</p>
            <Sparkline points={weekly.map((w) => ({ x: w.week, y: w[d.key] }))} h={90}
              fmt={(v) => (d.unit === "%" ? pct(v) : (v ?? ""))} />
          </>
        ),
      };
    }
    case "tower": {
      const r = d.row;
      return {
        title: `Tower · ${r.tower}`,
        jql: `project = ${P} AND ${F.tower} = ${q(r.tower)}`,
        body: <KV rows={[
          ["Volume", r.volume], ["Closed", r.closed],
          ["First-time resolution", pct(r.ftr_pct)],
          ["Escalation rate", pct(r.escalation_pct)],
          ["Resolution SLA", pct(r.sla_pct)],
        ]} />,
      };
    }
    case "analyst": {
      const p = d.p, rate = p.rate == null ? null : p.rate * 100;
      const out = p.rate != null && (p.rate < d.lo || p.rate > d.hi);
      return {
        title: `Analyst · ${p.analyst}`,
        jql: `project = ${P} AND assignee in (${q(p.analyst)}) ORDER BY updated DESC`,
        body: <>
          <div className="drill-big tnum">{pct(rate)}</div>
          <KV rows={[
            ["Escalation rate", pct(rate)],
            p.count != null && ["Tickets handled", p.count],
            ["Tower mean", pct(d.mean * 100)],
            ["2σ band", `${pct(d.lo * 100)} – ${pct(d.hi * 100)}`],
            ["Status", out ? "outside 2σ — investigate" : "within 2σ"],
          ]} />
          <p className="drill-note">The Jira link matches by display name; confirm the account if names collide.</p>
        </>,
      };
    }
    case "channel": {
      const r = d.row;
      return {
        title: `Channel · ${r.channel}`,
        jql: `project = ${P} AND ${F.channel} = ${q(r.channel)}`,
        body: <KV rows={[
          ["Volume", r.n],
          r.ftr_pct != null && ["First-time resolution", pct(r.ftr_pct)],
          r.escalation_pct != null && ["Escalation rate", pct(r.escalation_pct)],
          d.shadow && ["Note", "shadow support pulled into the record"],
        ]} />,
      };
    }
    case "ageing": {
      const b = d.b;
      // bucket labels like "0–3d", "3–7d", "7–14d", "14–30d", "> 30d"
      const m = /(\d+)\s*[–-]\s*(\d+)/.exec(b.label);
      const gt = /(?:>|over)\s*(\d+)/i.exec(b.label);
      let clause = `project = ${P} AND resolution is EMPTY`;
      if (m) clause += ` AND created <= -${m[1]}d AND created > -${m[2]}d`;
      else if (gt) clause += ` AND created <= -${gt[1]}d`;
      return {
        title: `Open work · ${b.label}`,
        jql: clause,
        body: <KV rows={[
          ["Open items in bucket", b.n],
          b.breach != null && ["Breaching / at-risk", b.breach ? "yes" : "no"],
        ]} />,
      };
    }
    case "ageStatus": {
      const b = d.b;
      return {
        title: `Ageing · ${b.label}`,
        jql: `project = ${P} AND resolution is EMPTY`,
        body: <KV rows={[
          ["Owned (SLA running)", b.owned], ["Paused (waiting)", b.paused],
          ["Total open in band", (b.owned || 0) + (b.paused || 0)],
        ]} />,
      };
    }
    case "sla": {
      const s = model.sla_detail || {};
      const met = d.kind === "resolution" ? s.resolution_met : s.response_met;
      const br = d.kind === "resolution" ? s.resolution_breached : s.response_breached;
      const fld = d.kind === "resolution" ? F.resSla : F.respSla;
      const total = (met || 0) + (br || 0);
      return {
        title: `${d.kind === "resolution" ? "Resolution" : "Response"} SLA`,
        jql: `project = ${P} AND ${fld} in (Met, Breached)`,
        body: <KV rows={[
          ["Met", met], ["Breached", br], ["Total measured", total],
          ["Attainment", total ? pct((met / total) * 100) : "—"],
        ]} />,
      };
    }
    case "kbtower": {
      return {
        title: `KB gap · ${d.label}`,
        jql: `project = ${P} AND ${F.tier} = L2 AND ${F.tower} = ${q(d.label)}`,
        body: <KV rows={[["Escalations with no KB article", d.value], ["Tower", d.label]]} />,
      };
    }
    case "week": {
      const w = d.w;
      return {
        title: `Week of ${w.week}`,
        jql: null,
        body: <KV rows={[
          w.n != null && ["Created", w.n],
          w.closed != null && ["Closed", w.closed],
          w.open != null && ["Open backlog", w.open],
          w.aged != null && ["Aged > 14d", w.aged],
          w.ftr_pct != null && ["First-time resolution", pct(w.ftr_pct)],
          w.reopen_pct != null && ["Reopen rate", pct(w.reopen_pct)],
          w.sla_pct != null && ["Resolution SLA", pct(w.sla_pct)],
        ]} />,
      };
    }
    case "statusgroup": {
      const bs = Object.fromEntries((model.ageing_by_status?.by_status || []).map(([s, n]) => [s, n]));
      const inList = d.statuses.map((s) => [s, bs[s] || 0]);
      const total = inList.reduce((a, [, n]) => a + n, 0);
      const clause = `project = ${P} AND resolution is EMPTY AND status in (${d.statuses.map(q).join(", ")})`;
      return {
        title: d.label,
        jql: clause,
        body: <>
          <div className="drill-big tnum">{total}</div>
          <KV rows={inList.map(([s, n]) => [s, n])} />
        </>,
      };
    }
    case "reason": {
      return {
        title: `KB gap by reason`,
        jql: `project = ${P} AND ${F.tier} = L2 AND ${F.escReason} = ${q(d.reason)} AND ${F.kbChecked} = ${q(KB_NONE)}`,
        body: <>
          <div className="drill-big tnum">{d.n}</div>
          <KV rows={[["Reason", d.reason], ["Escalations with no KB article", d.n]]} />
          <p className="drill-note">These are escalations for this reason that found no KB article — the ones to document first, because that is what stops L1 escalating them again.</p>
        </>,
      };
    }
    case "kbgap": {
      return {
        title: "KB gap — the biggest lever",
        jql: `project = ${P} AND ${F.tier} = L2`,
        body: <>
          <div className="drill-big tnum">{pct(d.pct)}</div>
          <KV rows={[
            ["Escalations with no KB article", d.gap],
            ["Total escalations", d.escalated],
            ["Gap", pct(d.pct)],
          ]} />
          <p className="drill-note">Each gap is an article L2 can write so the same issue resolves at L1 next time.</p>
        </>,
      };
    }
    case "impacturgency":
      return {
        title: `Impact ${d.impact} · Urgency ${d.urgency}`,
        jql: `project = ${P} AND ${F.impact} = ${q(d.impact)} AND ${F.urgency} = ${q(d.urgency)}`,
        body: <p className="drill-note">Tickets at Impact {d.impact} × Urgency {d.urgency}, and the priority they derive to. Priority is a derivation, not a negotiation.</p>,
      };
    case "majorincident":
      return {
        title: "Major incidents — P1 – Critical",
        jql: `project = ${P} AND priority = ${q("P1 - Critical")}`,
        body: <p className="drill-note">The fast-path tickets: gate-free escalation, Major Incident Manager engaged. Watch how long they stay open.</p>,
      };
    case "records":
      return { title: d.label || "Records", jql: d.jql || null,
        body: d.note ? <p className="drill-note">{d.note}</p> : <div /> };
    default:
      return { title: "Detail", body: <p>No detail.</p>, jql: null };
  }
}

// Layer (b): small-multiples of the population behind a mark, sliced several ways.
function Cohort({ rows }) {
  if (!rows || rows.length < 3) return null;
  const dims = [["tower", "by tower"], ["priority", "by priority"], ["status", "by status"], ["intake", "by channel"]];
  const countBy = (k) => {
    const c = {};
    for (const r of rows) { const v = r[k] || "—"; c[v] = (c[v] || 0) + 1; }
    return Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([label, value]) => ({ label, value }));
  };
  return (
    <div className="cohort">
      {dims.map(([k, h]) => {
        const rs = countBy(k);
        if (rs.length < 2) return null;   // no signal if everything is one value
        return (
          <div key={k} className="cohort-dim">
            <span className="cohort-h">{h}</span>
            <Bars rows={rs} barH={12} w={360} />
          </div>
        );
      })}
    </div>
  );
}

// ---- record layer: which records sit behind a mark, and how they reconcile --------------
// Booleans on each record encode the same population rules app/analytics uses, so a filter
// on them reconciles with the aggregate's numerator/denominator (roadmap Part III).
const CLOSED_DEN = (r) => r.counts_as_closed && !r.is_problem;
const slaVal = (r, kind) => (kind === "resolution" ? r.resolution_sla : r.response_sla);

function recordSpec(d, model) {
  const sb = model.scoreboard || {};
  switch (d.type) {
    case "metric": {
      const M = {
        ftr_pct: { pred: CLOSED_DEN, hi: (r) => r.counts_as_ftr, hiLab: "first-time-resolved", reconcile: sb.ftr_pct?.den, windowed: true },
        reopen_pct: { pred: CLOSED_DEN, hi: (r) => r.is_reopened, hiLab: "reopened", reconcile: sb.reopen_pct?.den, windowed: true },
        escalation_pct: { pred: () => true, hi: (r) => r.is_escalated, hiLab: "escalated to L2", reconcile: sb.escalation_pct?.den, windowed: true },
        sla_pct: { pred: (r) => ["Met", "Breached"].includes(r.resolution_sla), hi: (r) => r.resolution_sla === "Breached", hiLab: "breached", reconcile: sb.sla_pct?.den, windowed: true },
        response_pct: { pred: (r) => ["Met", "Breached"].includes(r.response_sla), hi: (r) => r.response_sla === "Breached", hiLab: "breached", reconcile: sb.response_pct?.den, windowed: true },
        aged_14d: { pred: (r) => r.is_open && r.age_days >= 14, windowed: false, reconcile: null },
      };
      return M[d.key] || null;
    }
    case "tower": return { pred: (r) => r.tower === d.row.tower, windowed: true, reconcile: d.row.volume };
    case "channel": return { pred: (r) => r.intake === d.row.channel, windowed: true, reconcile: d.row.n };
    case "analyst": return { pred: (r) => r.l1_analyst === d.p.analyst, hi: (r) => r.is_escalated, hiLab: "escalated", windowed: true, reconcile: null };
    case "statusgroup": {
      const bs = Object.fromEntries((model.ageing_by_status?.by_status || []).map(([s, n]) => [s, n]));
      const target = d.statuses.reduce((a, s) => a + (bs[s] || 0), 0);
      return { pred: (r) => r.is_open && d.statuses.includes(r.status), windowed: false, reconcile: target };
    }
    case "kbtower": return { pred: (r) => r.is_escalated && r.kb_gap && r.tower === d.label, windowed: true, reconcile: d.value };
    case "kbgap": return { pred: (r) => r.is_escalated && r.kb_gap, windowed: true, reconcile: d.gap };
    case "reason": return { pred: (r) => r.is_escalated && r.kb_gap && r.escalation_reason === d.reason, windowed: true, reconcile: d.n };
    case "sla": return { pred: (r) => ["Met", "Breached"].includes(slaVal(r, d.kind)), hi: (r) => slaVal(r, d.kind) === "Breached", hiLab: "breached", windowed: true, reconcile: null };
    case "ageing": {
      const m = /(\d+)\s*[–-]\s*(\d+)/.exec(d.b.label), gt = /(?:>|over)\s*(\d+)/i.exec(d.b.label);
      const pred = m ? (r) => r.is_open && r.age_days >= +m[1] && r.age_days < +m[2]
        : gt ? (r) => r.is_open && r.age_days >= +gt[1] : (r) => r.is_open;
      return { pred, windowed: false, reconcile: d.b.n };
    }
    case "impacturgency": return { pred: (r) => r.impact === d.impact && r.urgency === d.urgency, windowed: true, reconcile: null };
    case "majorincident": return { pred: (r) => r.priority === "P1 - Critical", hi: (r) => r.is_open, hiLab: "still open", windowed: true, reconcile: null };
    // Generic record drill: panels pass their own predicate/label/jql. Lets the many ITIL
    // panels drill to records without a bespoke case each.
    case "records": return { pred: d.pred, hi: d.hi, hiLab: d.hiLab, windowed: d.windowed !== false, reconcile: d.reconcile ?? null };
    default: return null;   // week, ageStatus — aggregate-only
  }
}

function filterRecords(records, spec, model) {
  const ws = model.window_start_ts;
  let rows = spec.windowed && ws != null ? records.filter((r) => r.reported_ts != null && r.reported_ts >= ws) : records;
  return rows.filter(spec.pred);
}

const COLUMNS = [
  { k: "key", h: "Key", cls: "mono", link: true },
  { k: "summary", h: "Summary", grow: true },
  { k: "issue_type", h: "Type" },
  { k: "status", h: "Status" },
  { k: "tier", h: "Tier" },
  { k: "tower", h: "Tower" },
  { k: "priority", h: "Priority" },
  { k: "l1_analyst", h: "L1" },
  { k: "age_days", h: "Age", num: true, fmt: (v) => (v == null ? "" : Math.round(v)) },
  { k: "resolution_sla", h: "Res SLA" },
  { k: "escalation_reason", h: "Esc reason" },
  { k: "kb_checked", h: "KB checked" },
  { k: "reopened", h: "Reopen" },
];

function RecordList({ rows, spec, loading, onPick }) {
  const [numOnly, setNumOnly] = useState(false);
  const hiCount = spec.hi ? rows.filter(spec.hi).length : null;
  const shown = numOnly && spec.hi ? rows.filter(spec.hi) : rows;
  return (
    <div className="rl">
      <div className="rl-head">
        <span><strong className="tnum">{rows.length}</strong> record{rows.length === 1 ? "" : "s"}</span>
        {spec.reconcile != null && (
          <span className={"rl-recon " + (rows.length === spec.reconcile ? "ok" : "warn")}>
            {rows.length === spec.reconcile ? `matches ${spec.reconcile} ✓` : `≠ expected ${spec.reconcile}`}
          </span>
        )}
        {spec.hi && (
          <button className={"rl-toggle" + (numOnly ? " on" : "")} onClick={() => setNumOnly((v) => !v)}>
            {numOnly ? "show all" : `only ${spec.hiLab} (${hiCount})`}
          </button>
        )}
      </div>
      {loading ? <div className="state">loading records …</div> : (
        <div className="rl-scroll">
          <table className="rl-table">
            <thead><tr>{COLUMNS.map((c) => <th key={c.k} className={c.num ? "num" : ""}>{c.h}</th>)}</tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.key} className={"clickable" + (spec.hi && spec.hi(r) ? " hi" : "")} onClick={() => onPick(r)}>
                  {COLUMNS.map((c) => (
                    <td key={c.k} className={(c.num ? "num " : "") + (c.cls || "") + (c.grow ? " grow" : "")}>
                      {c.link ? <a href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{r.key}</a>
                        : c.fmt ? c.fmt(r[c.k]) : (r[c.k] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RecordDetail({ record, onBack }) {
  const fields = [
    ["Type", record.issue_type], ["Status", record.status], ["Tier", record.tier],
    ["Tower", record.tower], ["Priority", record.priority], ["Impact", record.impact],
    ["Urgency", record.urgency], ["Channel", record.intake],
    ["L1 analyst", record.l1_analyst], ["L2 analyst", record.l2_analyst],
    ["Reported", record.reported_at ? new Date(record.reported_at).toLocaleString() : null],
    ["Age (days)", record.age_days != null ? Math.round(record.age_days) : null],
    ["Response SLA", record.response_sla], ["Resolution SLA", record.resolution_sla],
    ["Escalation reason", record.escalation_reason], ["KB checked", record.kb_checked],
    ["Reopened", record.reopened], ["Root cause", record.root_cause], ["Resolution", record.resolution_code],
  ].filter(([, v]) => v != null && v !== "");
  const hops = (record.timeline || []).filter((c) => c.field === "status");
  return (
    <div className="rd">
      <button className="rl-back" onClick={onBack}>← records</button>
      <div className="rd-sum">{record.summary}</div>
      <KV rows={fields} />
      {hops.length > 0 && (
        <>
          <p className="drill-note">Status timeline — {record.changelog_hops} changes in history:</p>
          <ol className="rd-timeline">
            {hops.map((c, i) => (
              <li key={i}><span className="rd-when">{c.at ? new Date(c.at).toLocaleDateString() : ""}</span>{c.from} <b>→</b> {c.to}</li>
            ))}
          </ol>
        </>
      )}
      <a className="drawer-jira inline" href={record.url} target="_blank" rel="noreferrer">Open {record.key} in Jira ↗</a>
    </div>
  );
}

export function Drawer({ drill, model, records, onClose }) {
  const [sel, setSel] = useState(null);
  useEffect(() => { setSel(null); }, [drill]);
  useEffect(() => {
    if (!drill) return;
    const onKey = (e) => e.key === "Escape" && (sel ? setSel(null) : onClose());
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drill, onClose, sel]);
  if (!drill) return null;
  const { title, body, jql: clause } = detail(drill, model);
  const spec = recordSpec(drill, model);
  const rows = spec && records ? filterRecords(records, spec, model) : null;
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className={"drawer" + (spec ? " drawer-wide" : "")} onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-head">
          <h3>{sel ? sel.key : title}</h3>
          <button className="drawer-x" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="drawer-body">
          {sel
            ? <RecordDetail record={sel} onBack={() => setSel(null)} />
            : <>
                {body}
                {spec && rows && <Cohort rows={rows} />}
                {spec && <RecordList rows={rows || []} spec={spec} loading={!records} onPick={setSel} />}
              </>}
        </div>
        {!sel && clause && (
          <a className="drawer-jira" href={jira(model.site, clause)} target="_blank" rel="noreferrer">
            Open matching issues in Jira ↗
          </a>
        )}
      </aside>
    </div>
  );
}
