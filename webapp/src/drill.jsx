import React, { useEffect } from "react";
import { Sparkline, Bars } from "./charts.jsx";

// Drill-down detail. Clicking any chart element opens this drawer with the numbers behind
// the mark and a deep link into Jira's issue navigator. The link JQL uses cf[<id>] clause
// names (this instance's custom-field ids) so it resolves even where a field name is
// duplicated (e.g. Urgency); system fields need no id.
const F = {
  tower: "cf[10042]", tier: "cf[10043]", channel: "cf[10045]",
  impact: "cf[10004]", urgency: "cf[10044]", reopened: "cf[10052]",
  resSla: "cf[10051]", respSla: "cf[10050]", escReason: "cf[10046]",
};

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
        title: `Escalation reason`,
        jql: `project = ${P} AND ${F.tier} = L2 AND ${F.escReason} = ${q(d.reason)}`,
        body: <>
          <div className="drill-big tnum">{d.n}</div>
          <KV rows={[["Reason", d.reason], ["Escalations", d.n]]} />
          <p className="drill-note">Recurring reasons with no KB article are the ones to document first — that is what stops L1 escalating them.</p>
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
    default:
      return { title: "Detail", body: <p>No detail.</p>, jql: null };
  }
}

export function Drawer({ drill, model, onClose }) {
  useEffect(() => {
    if (!drill) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drill, onClose]);
  if (!drill) return null;
  const { title, body, jql: clause } = detail(drill, model);
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-head">
          <h3>{title}</h3>
          <button className="drawer-x" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="drawer-body">{body}</div>
        {clause && (
          <a className="drawer-jira" href={jira(model.site, clause)} target="_blank" rel="noreferrer">
            Open matching issues in Jira ↗
          </a>
        )}
      </aside>
    </div>
  );
}
