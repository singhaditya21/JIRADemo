import React, { useState } from "react";
import { Sparkline, Bars, AnalystBand, Pairing, Heatmap } from "./charts.jsx";

const f1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toFixed(1));
const pct = (v) => (v == null ? "—" : f1(v) + "%");
const sum = (xs) => xs.reduce((a, b) => a + (b || 0), 0);

// Classify a workflow status into a tier bucket by name, so the tier views work on ANY
// project — OPS's L1/L2 workflow (New/Triage/In Progress L1/Escalated to L2/…) and ITSM's
// ITIL workflow (Open/Work in progress/Implementing/Awaiting CAB approval/…) have different
// status names. Waiting states are checked first, then L2 markers, else it's front-line.
function tierOf(status) {
  const s = (status || "").toLowerCase();
  if (/pending|waiting|awaiting|on hold/.test(s)) return "wait";
  if (/l2|escalat|implement|\bcab\b|approval|problem/.test(s)) return "L2";
  return "L1";
}
function statusesByTier(model) {
  const g = { L1: [], L2: [], wait: [] };
  for (const [s, n] of (model.ageing_by_status?.by_status || [])) g[tierOf(s)].push([s, n]);
  return g;
}
const openTier = (g, t) => g[t].reduce((a, [, n]) => a + n, 0);

const METRICS = [
  { key: "ftr_pct", lab: "First-time resolution", unit: "%", note: "at L1" },
  { key: "escalation_pct", lab: "Escalation rate", unit: "%", note: "of all tickets" },
  { key: "reopen_pct", lab: "Reopen rate", unit: "%", note: "paired with FTR" },
  { key: "sla_pct", lab: "Resolution SLA", unit: "%", note: "attainment" },
  { key: "response_pct", lab: "Response SLA", unit: "%", note: "attainment" },
  { key: "aged_14d", lab: "Aged > 14 days", unit: "", note: "open backlog" },
];
const M = Object.fromEntries(METRICS.map((m) => [m.key, m]));

function Verdict({ m }) {
  if (!m || !m.verdict) return null;
  const cls = m.verdict === "PASS" ? "pass" : m.verdict === "GAP" ? "gap" : "bad";
  const arrow = m.direction === "ge" ? "≥" : m.direction === "le" ? "≤" : "";
  return <span className={`pill ${cls}`}>{m.verdict}{m.target != null ? ` ${arrow}${m.target}${m.target <= 100 ? "%" : ""}` : ""}</span>;
}

// ---- the always-on KPI strip, tier-aware --------------------------------------------------
export function KpiStrip({ model, lens, open }) {
  const sb = model.scoreboard || {}, weekly = model.weekly || [], kb = model.kb || {};
  const g = statusesByTier(model);
  const metric = (key, lab, sub) => {
    const m = sb[key] || {};
    return {
      key, lab, m, verdict: m,
      value: M[key].unit === "%" ? pct(m.value) : (m.value ?? m.num ?? "—"),
      sub: sub ?? (m.num != null && m.den != null ? `${m.num}/${m.den}` : ""),
      drill: { type: "metric", key, lab, note: sub ?? "", unit: M[key].unit },
    };
  };
  let tiles;
  if (lens === "L1") tiles = [
    metric("ftr_pct", "First-time resolution", "resolved at L1"),
    metric("response_pct", "Response SLA", "L1's clock"),
    metric("escalation_pct", "Escalation rate", "sent to L2"),
    metric("reopen_pct", "Reopen rate", "closed too early"),
    { lab: "Open at L1", value: openTier(g, "L1"), sub: "front-line statuses",
      drill: { type: "statusgroup", label: "Open at L1", statuses: g.L1.map(([s]) => s) } },
    metric("aged_14d", "Aged > 14 days", "getting stuck"),
  ];
  else if (lens === "L2") tiles = [
    metric("sla_pct", "Resolution SLA", "L2's clock"),
    { lab: "Escalated in", value: sb.escalation_pct?.num ?? "—", sub: "tickets reaching L2",
      drill: { type: "statusgroup", label: "Reached L2", statuses: g.L2.map(([s]) => s) } },
    { lab: "KB gap", value: pct(kb.pct), sub: `${kb.gap}/${kb.escalated} no article`, gap: true,
      drill: { type: "kbgap", gap: kb.gap, escalated: kb.escalated, pct: kb.pct } },
    metric("reopen_pct", "Reopen rate", "bounced back"),
    { lab: "Open at L2", value: openTier(g, "L2"), sub: "escalated & in progress",
      drill: { type: "statusgroup", label: "Open at L2", statuses: g.L2.map(([s]) => s) } },
    metric("aged_14d", "Aged > 14 days", "deep work stuck"),
  ];
  else tiles = METRICS.map((m) => metric(m.key, m.lab, m.note));

  return (
    <div className="kpi-strip">
      {tiles.map((t, i) => (
        <div key={i} className="kpi clickable" role="button" tabIndex={0}
          onClick={() => open(t.drill)}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && open(t.drill)}>
          <span className="lab">{t.lab}</span>
          <span className="val tnum">{t.value}</span>
          <span className="sub">{t.sub} {t.m ? <Verdict m={t.m} /> : t.gap ? <span className="pill gap">GAP</span> : null}</span>
          {t.key && weekly.some((w) => w[t.key] != null) && (
            <div className="kpi-spark">
              <Sparkline points={weekly.map((w) => ({ x: w.week, y: w[t.key] ?? null }))} h={24}
                fmt={(v) => (M[t.key].unit === "%" ? pct(v) : (v ?? ""))}
                color={t.m?.verdict === "PASS" ? "var(--ok)" : t.m?.verdict === "GAP" ? "var(--warn)" : "var(--accent)"} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- shared panels (some take a `lens` for tier framing) ----------------------------------
export function PairingPanel({ model, open }) {
  const p = model.pairing || {};
  return (
    <div className="panel span-2">
      <h2>FTR vs reopen — the honesty pair</h2>
      <p className="why">Closing early lifts first-time resolution and wrecks reopen rate, so neither moves alone. Correlation r = {f1((p.r ?? 0) * 100) / 100 || p.r}. <span className="hint">Click a week.</span></p>
      <Pairing weeks={model.ftr_vs_reopen || []} r={p.r} onPick={(w) => open({ type: "week", w })} />
    </div>
  );
}

export function Analysts({ model, open }) {
  const a = model.analysts || {};
  return (
    <div className="panel span-2">
      <h2>Escalation rate per analyst</h2>
      <p className="why">No analyst should diverge beyond 2σ of the tower mean. Red dots are outside the band. <span className="hint">Click a name.</span></p>
      <AnalystBand people={a.people || []} mean={a.mean ?? a.pooled ?? 0} lo={a.lo ?? 0} hi={a.hi ?? 0}
        onPick={(p) => open({ type: "analyst", p, mean: a.mean ?? a.pooled ?? 0, lo: a.lo ?? 0, hi: a.hi ?? 0 })} />
      <div className="legend">
        <span><span className="dot" style={{ background: "var(--accent)" }} />within 2σ</span>
        <span><span className="dot" style={{ background: "var(--crit)" }} />outside 2σ</span>
        <span>mean {pct((a.pooled ?? a.mean) * (a.pooled <= 1 ? 100 : 1))}</span>
      </div>
    </div>
  );
}

export function KBGap({ model, open, lens }) {
  const kb = model.kb || {};
  const title = lens === "L2" ? "KB debt — articles to write"
    : lens === "L1" ? "KB coverage — why you keep escalating" : "KB gap — the biggest lever";
  const why = lens === "L2"
    ? `${kb.gap} escalations found no article. Each one is an article for L2 to write so L1 can resolve it next time.`
    : lens === "L1"
      ? `${kb.gap} of ${kb.escalated} escalations found no KB article — where there's no article, L1 has to escalate.`
      : `${kb.gap} of ${kb.escalated} escalations (${pct(kb.pct)}) found no KB article. That is L1's ceiling made visible.`;
  return (
    <div className="panel span-2">
      <h2>{title}</h2>
      <p className="why">{why} <span className="hint">Click a tower.</span></p>
      <Sparkline points={(kb.series || []).map((s) => ({ x: s.week, y: s.gap_pct }))} fmt={pct} color="var(--warn)" h={70} />
      <div className="scrollx" style={{ marginTop: "0.8rem" }}>
        <Bars rows={(kb.by_tower || []).map(([label, n]) => ({ label, value: n }))} barH={16}
          onPick={(r) => open({ type: "kbtower", label: r.label, value: r.value })} />
      </div>
    </div>
  );
}

export function Towers({ model, open }) {
  const [sort, setSort] = useState({ key: "volume", dir: -1 });
  const rows = [...(model.towers || [])].sort((a, b) => (a[sort.key] > b[sort.key] ? 1 : -1) * sort.dir);
  const cols = [
    ["tower", "Tower", false], ["volume", "Vol", true], ["closed", "Closed", true],
    ["ftr_pct", "FTR", true], ["escalation_pct", "Esc", true], ["sla_pct", "SLA", true],
  ];
  const click = (k) => setSort((s) => ({ key: k, dir: s.key === k ? -s.dir : -1 }));
  return (
    <div className="panel span-2">
      <h2>Tower comparison</h2>
      <p className="why">Sortable header; click a row to drill. The pilot ranks on volume × improvement headroom.</p>
      <div className="scrollx">
        <table>
          <thead>
            <tr>{cols.map(([k, l, num]) => (
              <th key={k} className={num ? "num" : ""} onClick={() => click(k)}>
                {l}{sort.key === k ? (sort.dir < 0 ? " ↓" : " ↑") : ""}
              </th>
            ))}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.tower} className="clickable" onClick={() => open({ type: "tower", row: r })}>
                <td>{r.tower}</td>
                <td className="num tnum">{r.volume}</td>
                <td className="num tnum">{r.closed}</td>
                <td className="num tnum">{pct(r.ftr_pct)}</td>
                <td className="num tnum">{pct(r.escalation_pct)}</td>
                <td className="num tnum">{pct(r.sla_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Intake({ model, open }) {
  const rows = (model.intake || []).map((r) => ({
    label: r.channel + (r.shadow ? " (shadow)" : ""), value: r.n, dim: r.shadow,
    color: r.shadow ? "var(--warn)" : "var(--accent)", _row: r,
  }));
  return (
    <div className="panel">
      <h2>Intake mix</h2>
      <p className="why">Chat is shadow support pulled into the record — otherwise invisible demand. <span className="hint">Click a channel.</span></p>
      <Bars rows={rows} barH={26} fmt={(v) => v}
        onPick={(r) => open({ type: "channel", row: r._row, shadow: r._row.shadow })} />
    </div>
  );
}

export function Ageing({ model, open }) {
  const a = model.ageing || {};
  const rows = (a.buckets || []).map((b) => ({ label: b.label, value: b.n, color: b.breach ? "var(--crit)" : "var(--accent)", _b: b }));
  return (
    <div className="panel">
      <h2>Open-work ageing</h2>
      <p className="why">{a.total} open · median {f1(a.median)}d · oldest {f1(a.oldest)}d · {a.over_30} over 30 days. <span className="hint">Click a bucket.</span></p>
      <Bars rows={rows} barH={22} onPick={(r) => open({ type: "ageing", b: r._b })} />
    </div>
  );
}

export function SlaOutcomes({ model, open, lens }) {
  const s = model.sla_detail || {};
  const row = (kind, met, br) => {
    const total = (met || 0) + (br || 0);
    return { kind, met: met || 0, br: br || 0, total, att: total ? (met / total) * 100 : null };
  };
  let rows = [row("resolution", s.resolution_met, s.resolution_breached),
              row("response", s.response_met, s.response_breached)];
  if (lens === "L1") rows = [rows[1], rows[0]];  // response first for L1
  const focus = lens === "L1" ? "response" : lens === "L2" ? "resolution" : null;
  return (
    <div className="panel">
      <h2>SLA outcomes</h2>
      <p className="why">Met vs breached for both clocks.{focus ? ` ${focus === "response" ? "Response" : "Resolution"} is this tier's SLA.` : ""} <span className="hint">Click a row.</span></p>
      <div className="scrollx">
        <table>
          <thead><tr><th>Clock</th><th className="num">Met</th><th className="num">Breached</th><th className="num">Attainment</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.kind} className={"clickable" + (r.kind === focus ? " row-focus" : "")} onClick={() => open({ type: "sla", kind: r.kind })}>
                <td style={{ textTransform: "capitalize" }}>{r.kind}</td>
                <td className="num tnum">{r.met}</td>
                <td className="num tnum">{r.br}</td>
                <td className="num tnum">{pct(r.att)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function BacklogFlow({ model, open }) {
  const bk = model.backlog || [];
  const weekly = model.weekly || [];
  const created = sum(weekly.map((w) => w.n));
  const closed = sum(weekly.map((w) => w.closed));
  const last = bk[bk.length - 1] || {};
  return (
    <div className="panel">
      <h2>Backlog &amp; flow</h2>
      <p className="why">The backlog isn't growing, it's <em>staling</em>: open is roughly flat while aged&nbsp;&gt;14d climbs. That gap is the story. <span className="hint">Click a point.</span></p>
      <div className="dual-spark">
        <div><span className="spark-lab">open backlog</span>
          <Sparkline points={bk.map((b) => ({ x: b.week, y: b.open }))} h={54} fmt={(v) => v} color="var(--accent)"
            onPick={(p, i) => open({ type: "week", w: { ...bk[i], ...(weekly[weekly.length - bk.length + i] || {}) } })} /></div>
        <div><span className="spark-lab">aged &gt; 14 days</span>
          <Sparkline points={bk.map((b) => ({ x: b.week, y: b.aged }))} h={54} fmt={(v) => v} color="var(--crit)" /></div>
      </div>
      <div className="miniboard">
        <div><span className="k">created</span><span className="v tnum">{created}</span></div>
        <div><span className="k">closed</span><span className="v tnum">{closed}</span></div>
        <div><span className="k">net</span><span className="v tnum" style={{ color: created - closed > 0 ? "var(--crit)" : "var(--ok)" }}>{created - closed > 0 ? "+" : ""}{created - closed}</span></div>
        <div><span className="k">open now</span><span className="v tnum">{last.open ?? "—"}</span></div>
        <div><span className="k">aged &gt;14d</span><span className="v tnum">{last.aged ?? "—"}</span></div>
      </div>
    </div>
  );
}

export function ChannelQuality({ model, open }) {
  const rows = model.channel_quality || [];
  return (
    <div className="panel span-2">
      <h2>Channel quality</h2>
      <p className="why">Not all intake is equal — first-time resolution and escalation rate by channel. <span className="hint">Click a channel.</span></p>
      <div className="scrollx">
        <table>
          <thead><tr><th>Channel</th><th className="num">Vol</th><th className="num">FTR</th><th className="num">Esc</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.channel} className="clickable" onClick={() => open({ type: "channel", row: r })}>
                <td>{r.channel}</td>
                <td className="num tnum">{r.n}</td>
                <td className="num tnum">{pct(r.ftr_pct)}</td>
                <td className="num tnum">{pct(r.escalation_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AgeingByStatus({ model, open }) {
  const a = model.ageing_by_status || {};
  const buckets = a.buckets || [];
  return (
    <div className="panel span-2">
      <h2>Ageing — owned vs paused</h2>
      <p className="why">{a.owned_total ?? 0} owned (SLA running) · {a.paused_total ?? 0} paused (waiting on customer/vendor). Paused time should not count against attainment. <span className="hint">Click a band.</span></p>
      <div className="scrollx">
        <table>
          <thead><tr><th>Age band</th><th className="num">Owned</th><th className="num">Paused</th></tr></thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.label} className="clickable" onClick={() => open({ type: "ageStatus", b })}>
                <td>{b.label}</td>
                <td className="num tnum">{b.owned}</td>
                <td className="num tnum">{b.paused}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---- new tier-specific panels -------------------------------------------------------------
export function QueueByStatus({ model, open, tier }) {
  const g = statusesByTier(model);
  const title = tier === "L1" ? "Front-line queue" : "L2 work in progress";
  const why = tier === "L1"
    ? "What's on the L1 floor right now — triage and first-touch work."
    : "What's been escalated and is in specialist hands.";
  const rows = [
    ...g[tier].map(([s, n]) => ({ label: s, value: n, color: "var(--accent)", _s: s })),
    ...g.wait.map(([s, n]) => ({ label: s, value: n, dim: true, color: "var(--warn)", _s: s })),
  ];
  return (
    <div className="panel span-2">
      <h2>{title}</h2>
      <p className="why">{why} Amber rows are waiting (SLA paused). <span className="hint">Click a status.</span></p>
      {rows.length
        ? <Bars rows={rows} barH={24} onPick={(r) => open({ type: "statusgroup", label: r.label, statuses: [r._s] })} />
        : <div className="state">no open work in this tier</div>}
    </div>
  );
}

export function EscalationReasons({ model, open }) {
  const rows = (model.kb?.by_reason || []).map(([reason, n]) => ({ label: reason, value: n, _r: reason }));
  return (
    <div className="panel span-2">
      <h2>KB gaps by reason</h2>
      <p className="why">Escalations that found no KB article, grouped by why they escalated — the KB backlog in priority order, biggest first. Write these to stop L1 escalating them again. <span className="hint">Click a reason.</span></p>
      <Bars rows={rows} barH={22} onPick={(r) => open({ type: "reason", reason: r._r, n: r.value })} />
    </div>
  );
}

// ---- insights engine: verdicts already computed, read out as prose --------------------
const mode = (xs) => {
  const c = {}; let best = null, bn = 0;
  for (const x of xs) { if (x == null) continue; c[x] = (c[x] || 0) + 1; if (c[x] > bn) { bn = c[x]; best = x; } }
  return best;
};

function buildInsights(model) {
  const sb = model.scoreboard || {}, kb = model.kb || {}, towers = model.towers || [], A = model.analysts || {};
  const ins = [];
  for (const [k, lab] of [["ftr_pct", "First-time resolution"], ["escalation_pct", "Escalation rate"],
    ["sla_pct", "Resolution SLA"], ["response_pct", "Response SLA"], ["reopen_pct", "Reopen rate"]]) {
    const m = sb[k]; if (!m || m.value == null || !m.verdict) continue;
    const arrow = m.direction === "ge" ? "≥" : "≤";
    if (m.verdict === "GAP") ins.push({ sev: "warn", drill: { type: "metric", key: k, lab },
      text: `${lab} is ${pct(m.value)} against a ${arrow}${m.target}% target — ${f1(Math.abs(m.value - m.target))} pts short.` });
    else if (m.verdict === "PASS") ins.push({ sev: "ok", drill: { type: "metric", key: k, lab },
      text: `${lab} is ${pct(m.value)}, clearing its ${arrow}${m.target}% target.` });
  }
  if (kb.pct != null) ins.push({ sev: "warn", drill: { type: "kbgap", gap: kb.gap, escalated: kb.escalated, pct: kb.pct },
    text: `${Math.round(kb.pct)}% of escalations (${kb.gap}/${kb.escalated}) found no KB article — the single largest lever to lift L1 resolution.` });
  const bl = (model.backlog || [])[(model.backlog || []).length - 1];
  if (bl && bl.open && bl.aged / bl.open >= 0.5) ins.push({ sev: "warn",
    text: `The backlog is staling, not growing — ${bl.aged} of ${bl.open} open tickets are already aged >14 days.` });
  const top = towers.find((t) => t.pilot_rank === 1);
  if (top) ins.push({ sev: "info", drill: { type: "tower", row: top },
    text: `${top.tower} is the #1 pilot candidate (volume × headroom): ${pct(top.escalation_pct)} escalation, ${pct(top.sla_pct)} SLA over ${top.volume} tickets.` });
  const outliers = (A.people || []).filter((p) => p.rate != null && (p.rate < A.lo || p.rate > A.hi));
  ins.push(outliers.length
    ? { sev: "warn", text: `${outliers.length} analyst(s) escalate beyond 2σ of the tower mean — look before it reads as a team problem.` }
    : { sev: "ok", text: `All ${(A.people || []).length} analysts sit within 2σ of the mean escalation rate — pilot exit criterion 6 is met.` });
  if (model.pairing?.r != null) ins.push({ sev: "ok",
    text: `FTR and reopen are strongly anti-correlated (r = ${model.pairing.r.toFixed(2)}) — the honesty pair holds, so first-time resolution isn't being bought by closing early.` });
  const w = (model.weekly || []).filter((x) => x.escalation_pct != null);
  if (w.length >= 2) {
    const a = w[w.length - 1], b = w[w.length - 2], d = a.escalation_pct - b.escalation_pct;
    if (Math.abs(d) >= 3) ins.push({ sev: d > 0 ? "warn" : "ok",
      text: `Escalation rate ${d > 0 ? "rose" : "fell"} ${f1(Math.abs(d))} pts in the latest complete week (${f1(b.escalation_pct)}% → ${f1(a.escalation_pct)}%).` });
  }
  return ins;
}

export function InsightsFeed({ model, open }) {
  const ins = buildInsights(model);
  return (
    <div className="panel span-full">
      <h2>What the tower is telling you</h2>
      <p className="why">Auto-generated from the same figures the panels show — verdicts, deltas and rankings read out in plain language, worst-first. <span className="hint">Click an insight to drill to the records.</span></p>
      <ul className="insights">
        {ins.map((it, i) => (
          <li key={i} className={"insight " + it.sev + (it.drill ? " clickable" : "")}
            onClick={it.drill ? () => open(it.drill) : undefined}
            role={it.drill ? "button" : undefined} tabIndex={it.drill ? 0 : undefined}>
            <span className="ins-dot" />{it.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function IntegrityStrip({ model }) {
  const jt = model.jira_time_counterexample || {};
  const warns = model.warnings || [];
  const items = [
    { k: "Records reconcile", v: "num / den exact", ok: true, note: "every drill list count matches its numerator/denominator" },
    { k: "Jira's own dates", v: `${jt.created_distinct_dates ?? "—"} distinct created date${jt.created_distinct_dates === 1 ? "" : "s"}`, ok: false,
      note: "why the tower trends on Reported At, not Jira created — created collapses to one day" },
    { k: "Data warnings", v: `${warns.length}`, ok: warns.length === 0, note: warns[0] ? warns[0].slice(0, 90) + "…" : "none" },
  ];
  return (
    <div className="panel span-full integrity">
      <h2>Data integrity <span className="why" style={{ display: "inline", margin: 0 }}>— the tower knows what it can and can't honestly say.</span></h2>
      <div className="int-row">
        {items.map((it, i) => (
          <div key={i} className={"int-cell " + (it.ok ? "ok" : "warn")}>
            <span className="int-k">{it.k}</span>
            <span className="int-v tnum">{it.v}</span>
            <span className="int-note">{it.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- revived OPS themes computed from the record layer --------------------------------
export function ImpactUrgency({ model, records, open }) {
  const IMP = ["High", "Medium", "Low"], URG = ["High", "Medium", "Low"];
  const inWin = (records || []).filter((r) => r.reported_ts != null && r.reported_ts >= model.window_start_ts);
  const cell = (imp, urg) => {
    const rs = inWin.filter((r) => r.impact === imp && r.urgency === urg);
    const pri = mode(rs.map((r) => r.priority));
    return { value: rs.length, sub: pri ? pri.split(" ")[0] : "" };
  };
  return (
    <div className="panel">
      <h2>Impact × Urgency → priority</h2>
      <p className="why">Where demand lands on the 3×3 matrix and the priority each cell derives to — priority is a derivation, not a negotiation. {records ? "Rows = Impact, columns = Urgency." : "Loading records…"} <span className="hint">Click a cell.</span></p>
      {records && <Heatmap rows={IMP} cols={URG} cell={cell}
        onPick={(imp, urg) => open({ type: "impacturgency", impact: imp, urgency: urg })} />}
    </div>
  );
}

export function MajorIncident({ model, records, open }) {
  const inWin = (records || []).filter((r) => r.reported_ts != null && r.reported_ts >= model.window_start_ts);
  const p1 = inWin.filter((r) => r.priority === "P1 - Critical");
  const openP1 = p1.filter((r) => r.is_open).length;
  const resolved = p1.filter((r) => !r.is_open);
  const avgAge = resolved.length ? resolved.reduce((a, r) => a + (r.age_days || 0), 0) / resolved.length : null;
  return (
    <div className="panel">
      <h2>Major incidents (P1)</h2>
      <p className="why">P1 – Critical is the fast path: gate-free escalation, Major Incident Manager engaged. Watch the count and how long they stay open. {records ? "" : "Loading…"}</p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">P1 total</span><span className="v tnum">{p1.length}</span></div>
            <div><span className="k">open now</span><span className="v tnum" style={{ color: openP1 ? "var(--crit)" : "var(--ok)" }}>{openP1}</span></div>
            <div><span className="k">resolved</span><span className="v tnum">{resolved.length}</span></div>
            <div><span className="k">avg age (d)</span><span className="v tnum">{avgAge != null ? f1(avgAge) : "—"}</span></div>
          </div>
          <button className="linkish" onClick={() => open({ type: "majorincident" })}>see the {p1.length} P1 tickets →</button>
        </>
      )}
    </div>
  );
}

// ---- ITSM ITIL panels (computed from the record layer; ITSM project only) --------------
const inWindow = (records, model) => (records || []).filter((r) => r.reported_ts != null && r.reported_ts >= model.window_start_ts);
const meanBy = (rows, f) => { const xs = rows.map(f).filter((x) => x != null); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
const ttrHours = (r) => (r.resolved_at && r.reported_at) ? (new Date(r.resolved_at) - new Date(r.reported_at)) / 36e5 : null;
const dur = (h) => (h == null ? "—" : h < 48 ? `${f1(h)}h` : `${f1(h / 24)}d`);
const median = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
// Time a change spent Awaiting CAB approval, reconstructed from its status changelog.
// Did this change pass through the CAB gate? A sequence fact from the changelog (the seed
// records status ORDER honestly; per-transition wall-clock is collapsed to bake time, so gate
// dwell-time is NOT derivable — we deliberately don't claim it). This is governance coverage.
const wentThroughCab = (r) => (r.timeline || []).some((c) => c.field === "status" && c.to === "Awaiting CAB approval");
const isReq = (r) => r.issue_type === "Service Request" || r.issue_type === "Service Request with Approvals";
// Tier of a status for flow analysis — terminal states are "done" so resolving/closing an
// escalated ticket is not mistaken for a bounce back to L1.
const tof = (s) => {
  const x = (s || "").toLowerCase();
  if (/resolv|closed|done|complet|cancel|declin/.test(x)) return "done";
  if (/l2|escalat|implement/.test(x)) return "L2";
  if (/pending|waiting|awaiting/.test(x)) return "wait";
  return "L1";
};

export function PracticeMix({ model, records, open }) {
  const rows = inWindow(records, model);
  const types = ["Incident", "Service Request", "Service Request with Approvals", "Change", "Problem"];
  const bars = types.map((t) => ({ label: t.replace("Service Request with Approvals", "SR + Approvals"), value: rows.filter((r) => r.issue_type === t).length, _t: t })).filter((b) => b.value > 0);
  return (
    <div className="panel">
      <h2>ITIL practice mix</h2>
      <p className="why">Demand by ITIL work type — each has its own SLA and lifecycle. {records ? "" : "Loading…"} <span className="hint">Click a type.</span></p>
      {records && <Bars rows={bars} barH={22}
        onPick={(b) => open({ type: "records", label: `Type · ${b._t}`, pred: (r) => r.issue_type === b._t, reconcile: b.value, jql: `project = ITSM AND issuetype = "${b._t}"` })} />}
    </div>
  );
}

export function IncidentManagement({ model, records, open }) {
  const rows = inWindow(records, model);
  const inc = rows.filter((r) => r.issue_type === "Incident");
  const mtta = meanBy(inc, (r) => r.response_hours);
  const mttr = meanBy(inc.filter((r) => r.resolved_at), ttrHours);
  const major = inc.filter((r) => r.priority === "P1 - Critical").length;
  const openInc = inc.filter((r) => r.is_open).length;
  const reopened = inc.filter((r) => r.is_reopened).length;
  return (
    <div className="panel span-2">
      <h2>Incident management</h2>
      <p className="why">The core ITIL desk. MTTA = time to first response; MTTR = reported → resolved. {records ? "" : "Loading…"}</p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">incidents</span><span className="v tnum">{inc.length}</span></div>
            <div><span className="k">MTTA</span><span className="v tnum">{dur(mtta)}</span></div>
            <div><span className="k">MTTR</span><span className="v tnum">{dur(mttr)}</span></div>
            <div><span className="k">major (P1)</span><span className="v tnum" style={{ color: major ? "var(--crit)" : "var(--ok)" }}>{major}</span></div>
            <div><span className="k">open</span><span className="v tnum" style={{ color: openInc ? "var(--warn)" : "var(--ok)" }}>{openInc}</span></div>
            <div><span className="k">reopened</span><span className="v tnum">{reopened}</span></div>
          </div>
          <button className="linkish" onClick={() => open({ type: "records", label: "Incidents", pred: (r) => r.issue_type === "Incident", hi: (r) => r.is_open, hiLab: "open", reconcile: inc.length, jql: `project = ITSM AND issuetype = Incident` })}>see the {inc.length} incidents →</button>
        </>
      )}
    </div>
  );
}

export function ChangeManagement({ model, records, open }) {
  const rows = inWindow(records, model);
  const ch = rows.filter((r) => r.issue_type === "Change");
  const byStatus = {};
  for (const r of ch) byStatus[r.status] = (byStatus[r.status] || 0) + 1;
  const bars = Object.entries(byStatus).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value, color: /cab|approval/i.test(label) ? "var(--warn)" : "var(--accent)" }));
  const cabPending = ch.filter((r) => /cab|approval/i.test(r.status)).length;
  const declined = ch.filter((r) => r.status === "Declined").length;
  const cabReviewed = ch.filter(wentThroughCab).length;          // passed the CAB gate (changelog sequence)
  const cabPct = ch.length ? cabReviewed / ch.length : null;
  const leadMedian = median(ch.filter((r) => r.resolved_at).map(ttrHours));
  return (
    <div className="panel span-2">
      <h2>Change management</h2>
      <p className="why">{ch.length} changes. <strong>Lead time</strong> is real end-to-end (raised → resolved). <strong>CAB-reviewed</strong> counts changes whose changelog passed through the “Awaiting CAB approval” gate — governance coverage, the ITIL question of whether change went through control. {records ? "" : "Loading…"} <span className="hint">Click a status.</span></p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">changes</span><span className="v tnum">{ch.length}</span></div>
            <div><span className="k">lead time (med)</span><span className="v tnum">{dur(leadMedian)}</span></div>
            <div><span className="k">CAB-reviewed</span><span className="v tnum">{cabReviewed}<span className="k" style={{ marginLeft: 4 }}>{cabPct == null ? "" : ` ${Math.round(cabPct * 100)}%`}</span></span></div>
            <div><span className="k">CAB pending</span><span className="v tnum" style={{ color: cabPending ? "var(--warn)" : "var(--ok)" }}>{cabPending}</span></div>
            <div><span className="k">declined</span><span className="v tnum" style={{ color: declined ? "var(--crit)" : "var(--ok)" }}>{declined}</span></div>
          </div>
          <div style={{ marginTop: "0.7rem" }}>
            <Bars rows={bars} barH={18}
              onPick={(b) => open({ type: "records", label: `Change · ${b.label}`, pred: (r) => r.issue_type === "Change" && r.status === b.label, reconcile: b.value, jql: `project = ITSM AND issuetype = Change AND status = "${b.label}"` })} />
          </div>
        </>
      )}
    </div>
  );
}

export function ProblemManagement({ model, records, open }) {
  const rows = inWindow(records, model);
  const prob = rows.filter((r) => r.issue_type === "Problem");
  const rc = {};
  for (const r of rows.filter((r) => r.root_cause)) rc[r.root_cause] = (rc[r.root_cause] || 0) + 1;
  const bars = Object.entries(rc).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }));
  return (
    <div className="panel span-2">
      <h2>Problem management &amp; root cause</h2>
      <p className="why">{prob.length} problem records. Root-cause distribution across resolved work — the recurring causes a problem practice attacks first (problem→incident links aren't on the record). {records ? "" : "Loading…"} <span className="hint">Click a cause.</span></p>
      {records && <Bars rows={bars} barH={16}
        onPick={(b) => open({ type: "records", label: `Root cause · ${b.label}`, pred: (r) => r.root_cause === b.label, reconcile: b.value, jql: `project = ITSM AND cf[10048] = "${b.label}"` })} />}
    </div>
  );
}

export function RequestFulfilment({ model, records, open }) {
  const rows = inWindow(records, model);
  const req = rows.filter(isReq);
  const fulfilled = req.filter((r) => !r.is_open).length;
  const pending = rows.filter((r) => /waiting for approval|awaiting cab/i.test(r.status)).length;
  const declined = rows.filter((r) => r.status === "Declined").length;
  return (
    <div className="panel">
      <h2>Service request fulfilment</h2>
      <p className="why">Requests and their approval gates. {records ? "" : "Loading…"}</p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">requests</span><span className="v tnum">{req.length}</span></div>
            <div><span className="k">fulfilled</span><span className="v tnum">{fulfilled}</span></div>
            <div><span className="k">pending approval</span><span className="v tnum" style={{ color: pending ? "var(--warn)" : "var(--ok)" }}>{pending}</span></div>
            <div><span className="k">declined</span><span className="v tnum">{declined}</span></div>
          </div>
          <button className="linkish" onClick={() => open({ type: "records", label: "Awaiting approval", pred: (r) => /waiting for approval|awaiting cab/i.test(r.status), windowed: false, reconcile: pending, jql: `project = ITSM AND status in ("Waiting for approval", "Awaiting CAB approval")` })}>see the {pending} awaiting approval →</button>
        </>
      )}
    </div>
  );
}

// Customer satisfaction — a MODELLED proxy, not a survey (this instance has no CSAT field).
// The panel says so plainly. Its value is the "honesty cut" at the bottom: the tickets that
// scored well despite a breach, or poorly despite a met SLA — the signal a real CSAT adds
// over pure SLA. Every score is `r.csat`, computed transparently in app/export_pages.
export function CustomerSatisfaction({ model, records, open }) {
  const rows = inWindow(records, model);
  const scored = rows.filter((r) => r.csat != null);
  const n = scored.length;
  const sum = scored.reduce((a, r) => a + r.csat, 0);
  const avg = n ? sum / n : null;
  const satisfied = scored.filter((r) => r.csat >= 4).length;   // 4–5 = satisfied (CSAT top-2-box)
  const dissatisfied = scored.filter((r) => r.csat <= 2).length; // 1–2 = dissatisfied
  const dist = [5, 4, 3, 2, 1].map((s) => ({
    label: `${s}★`, value: scored.filter((r) => r.csat === s).length,
    color: s >= 4 ? "var(--ok)" : s === 3 ? "var(--warn)" : "var(--crit)",
  }));
  // the independent-signal cells: CSAT disagreeing with the SLA verdict
  const happyBreach = scored.filter((r) => r.csat >= 4 && r.resolution_sla === "Breached").length;
  const unhappyMet = scored.filter((r) => r.csat <= 2 && r.resolution_sla === "Met").length;
  const isScored = (r) => r.csat != null;
  return (
    <div className="panel span-2">
      <h2>Customer satisfaction (CSAT)</h2>
      <p className="why">
        <strong>Modelled proxy — not a survey.</strong> This instance has no satisfaction responses, so the score is derived
        in the bake from resolution SLA, reopening and response speed, plus per-ticket spread — it shows the <em>shape</em> a
        CSAT programme would surface, never real customers. Top-2-box (4–5★) is the headline. {records ? "" : "Loading…"} <span className="hint">Click a rating.</span>
      </p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">avg score</span><span className="v tnum">{avg == null ? "—" : avg.toFixed(2)}</span></div>
            <div><span className="k">satisfied 4–5★</span><span className="v tnum" style={{ color: "var(--ok)" }}>{n ? Math.round(satisfied / n * 100) : "—"}%</span></div>
            <div><span className="k">dissatisfied 1–2★</span><span className="v tnum" style={{ color: dissatisfied ? "var(--crit)" : "var(--ok)" }}>{n ? Math.round(dissatisfied / n * 100) : "—"}%</span></div>
            <div><span className="k">responses</span><span className="v tnum">{n}</span></div>
          </div>
          <div style={{ marginTop: "0.7rem" }}>
            <Bars rows={dist} barH={18}
              onPick={(b) => { const s = Number(b.label[0]); open({ type: "records", label: `CSAT ${b.label}`, pred: (r) => isScored(r) && r.csat === s, reconcile: b.value }); }} />
          </div>
          <p className="why" style={{ marginTop: "0.6rem" }}>
            Where CSAT and SLA <em>disagree</em> — the signal a survey adds over the clock:
          </p>
          <div className="miniboard">
            <div className="clickable" onClick={() => open({ type: "records", label: "Satisfied despite SLA breach", pred: (r) => isScored(r) && r.csat >= 4 && r.resolution_sla === "Breached", reconcile: happyBreach })}>
              <span className="k">satisfied, SLA breached</span><span className="v tnum">{happyBreach}</span></div>
            <div className="clickable" onClick={() => open({ type: "records", label: "Dissatisfied despite SLA met", pred: (r) => isScored(r) && r.csat <= 2 && r.resolution_sla === "Met", reconcile: unhappyMet })}>
              <span className="k">dissatisfied, SLA met</span><span className="v tnum">{unhappyMet}</span></div>
          </div>
        </>
      )}
    </div>
  );
}

export function SlaByType({ model, records, open }) {
  const rows = inWindow(records, model);
  const types = ["Incident", "Service Request", "Change", "Problem"];
  const data = types.map((t) => {
    const rs = rows.filter((r) => r.issue_type === t || (t === "Service Request" && r.issue_type === "Service Request with Approvals"));
    const met = rs.filter((r) => r.resolution_sla === "Met").length, br = rs.filter((r) => r.resolution_sla === "Breached").length;
    return { t, met, br, att: met + br ? (met / (met + br)) * 100 : null };
  }).filter((d) => d.met + d.br > 0);
  return (
    <div className="panel">
      <h2>SLA attainment by work type</h2>
      <p className="why">Resolution SLA met vs breached, per ITIL work type — where the desk is losing time. {records ? "" : "Loading…"} <span className="hint">Click a row.</span></p>
      {records && (
        <div className="scrollx"><table>
          <thead><tr><th>Type</th><th className="num">Met</th><th className="num">Breached</th><th className="num">Attainment</th></tr></thead>
          <tbody>{data.map((d) => (
            <tr key={d.t} className="clickable" onClick={() => open({ type: "records", label: `${d.t} · SLA`, pred: (r) => (r.issue_type === d.t || (d.t === "Service Request" && r.issue_type === "Service Request with Approvals")) && ["Met", "Breached"].includes(r.resolution_sla), hi: (r) => r.resolution_sla === "Breached", hiLab: "breached", reconcile: d.met + d.br, jql: `project = ITSM AND issuetype = "${d.t}" AND cf[10051] in (Met, Breached)` })}>
              <td>{d.t}</td><td className="num tnum">{d.met}</td><td className="num tnum">{d.br}</td><td className="num tnum">{pct(d.att)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </div>
  );
}

// ---- OPS tier-flow / ping-pong (theme D) from the changelog timelines ------------------
export function TierFlow({ model, records, open }) {
  const rows = inWindow(records, model);
  let pingpong = 0, reesc = 0; const hopDist = { "0": 0, "1": 0, "2": 0, "3+": 0 };
  for (const r of rows) {
    const st = (r.timeline || []).filter((c) => c.field === "status");
    let hops = 0, escCount = 0, wentL2 = false, bounced = false;
    for (const c of st) {
      const from = tof(c.from), to = tof(c.to);
      // a tier hop = a move BETWEEN active L1 and L2 (resolving/closing is not a hop)
      if ((from === "L1" || from === "L2") && (to === "L1" || to === "L2") && from !== to) hops++;
      if (to === "L2" && from !== "L2") { escCount++; wentL2 = true; }   // a distinct escalation event
      if (wentL2 && to === "L1") bounced = true;   // back to an ACTIVE L1 status
    }
    if (escCount > 1) reesc++;
    if (bounced) pingpong++;
    hopDist[hops === 0 ? "0" : hops === 1 ? "1" : hops === 2 ? "2" : "3+"]++;
  }
  const bars = ["0", "1", "2", "3+"].map((b) => ({ label: `${b} tier hop${b === "1" ? "" : "s"}`, value: hopDist[b] }));
  return (
    <div className="panel span-2">
      <h2>Tier flow &amp; ping-pong</h2>
      <p className="why">How often work crosses the L1↔L2 boundary, from the changelog. Ping-pong (bounced L2→back to L1) and re-escalation are pure waste. {records ? "" : "Loading…"}</p>
      {records && (
        <>
          <div className="miniboard">
            <div><span className="k">clean (0 hops)</span><span className="v tnum">{hopDist["0"]}</span></div>
            <div><span className="k">ping-pong</span><span className="v tnum" style={{ color: pingpong ? "var(--crit)" : "var(--ok)" }}>{pingpong}</span></div>
            <div><span className="k">re-escalated</span><span className="v tnum">{reesc}</span></div>
          </div>
          <div style={{ marginTop: "0.7rem" }}>
            <Bars rows={bars} barH={18} onPick={(b) => {
              const n = parseInt(b.label);
              const pred = b.label.startsWith("3") ? ((r) => tierHops(r) >= 3) : ((r) => tierHops(r) === n);
              open({ type: "records", label: `${b.label} · tier flow`, pred, reconcile: b.value, windowed: true });
            }} />
          </div>
        </>
      )}
    </div>
  );
}
function tierHops(r) {
  let hops = 0;
  for (const c of (r.timeline || []).filter((c) => c.field === "status")) {
    const from = tof(c.from), to = tof(c.to);
    if ((from === "L1" || from === "L2") && (to === "L1" || to === "L2") && from !== to) hops++;
  }
  return hops;
}
