import React, { useState } from "react";
import { Sparkline, Bars, AnalystBand, Pairing } from "./charts.jsx";

const f1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toFixed(1));
const pct = (v) => (v == null ? "—" : f1(v) + "%");
const sum = (xs) => xs.reduce((a, b) => a + (b || 0), 0);

// The six scoreboard metrics, each with its value, placeholder target, and a weekly trend.
const METRICS = [
  { key: "ftr_pct", lab: "First-time resolution", unit: "%", note: "at L1" },
  { key: "escalation_pct", lab: "Escalation rate", unit: "%", note: "of all tickets" },
  { key: "reopen_pct", lab: "Reopen rate", unit: "%", note: "paired with FTR" },
  { key: "sla_pct", lab: "Resolution SLA", unit: "%", note: "attainment" },
  { key: "response_pct", lab: "Response SLA", unit: "%", note: "attainment" },
  { key: "aged_14d", lab: "Aged > 14 days", unit: "", note: "open backlog" },
];

function Verdict({ m }) {
  if (!m || !m.verdict) return null;
  const cls = m.verdict === "PASS" ? "pass" : m.verdict === "GAP" ? "gap" : "bad";
  const arrow = m.direction === "ge" ? "≥" : m.direction === "le" ? "≤" : "";
  return <span className={`pill ${cls}`}>{m.verdict}{m.target != null ? ` ${arrow}${m.target}${m.target <= 100 ? "%" : ""}` : ""}</span>;
}

export function Scoreboard({ model, open }) {
  const sb = model.scoreboard;
  const weekly = model.weekly || [];
  return (
    <div className="panel col-12">
      <h2>The scoreboard</h2>
      <p className="why">Six metrics, chosen so gaming one shows up in another. Targets are placeholders — the pilot replaces them with a measured baseline. <span className="hint">Click any tile to drill in.</span></p>
      <div className="tiles">
        {METRICS.map(({ key, lab, unit, note }) => {
          const m = sb[key] || {};
          return (
            <div className="tile clickable" key={key} role="button" tabIndex={0}
              onClick={() => open({ type: "metric", key, lab, note, unit })}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && open({ type: "metric", key, lab, note, unit })}>
              <span className="lab">{lab}</span>
              <span className="val tnum">{unit === "%" ? pct(m.value) : m.value ?? m.num ?? "—"}</span>
              <span className="meta">
                {m.num != null && m.den != null ? `${m.num}/${m.den} · ` : ""}{note} <Verdict m={m} />
              </span>
              <div style={{ marginTop: 4 }}>
                <Sparkline
                  points={weekly.map((w) => ({ x: w.week, y: w[key] ?? null }))}
                  h={40}
                  fmt={(v) => (unit === "%" ? pct(v) : v ?? "")}
                  color={m.verdict === "PASS" ? "var(--ok)" : m.verdict === "GAP" ? "var(--warn)" : "var(--accent)"}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PairingPanel({ model, open }) {
  const p = model.pairing || {};
  return (
    <div className="panel col-6">
      <h2>FTR vs reopen — the honesty pair</h2>
      <p className="why">Closing early lifts first-time resolution and wrecks reopen rate, so neither moves alone. Correlation r = {f1((p.r ?? 0) * 100) / 100 || p.r}. <span className="hint">Click a week.</span></p>
      <Pairing weeks={model.ftr_vs_reopen || []} r={p.r} onPick={(w) => open({ type: "week", w })} />
    </div>
  );
}

export function Analysts({ model, open }) {
  const a = model.analysts || {};
  return (
    <div className="panel col-6">
      <h2>Escalation rate per analyst</h2>
      <p className="why">Pilot exit criterion 6: no analyst diverges beyond 2σ of the tower mean. Red dots are outside the band. <span className="hint">Click a name.</span></p>
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

export function KBGap({ model, open }) {
  const kb = model.kb || {};
  return (
    <div className="panel col-6">
      <h2>KB gap — the biggest lever</h2>
      <p className="why">{kb.gap} of {kb.escalated} escalations ({pct(kb.pct)}) found no KB article. That is L1's ceiling made visible — trended weekly below. <span className="hint">Click a tower bar.</span></p>
      <Sparkline points={(kb.series || []).map((s) => ({ x: s.week, y: s.gap_pct }))} fmt={pct} color="var(--warn)" />
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
    <div className="panel col-6">
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
    <div className="panel col-6">
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
    <div className="panel col-6">
      <h2>Open-work ageing</h2>
      <p className="why">{a.total} open · median {f1(a.median)}d · oldest {f1(a.oldest)}d · {a.over_30} over 30 days. <span className="hint">Click a bucket.</span></p>
      <Bars rows={rows} barH={22} onPick={(r) => open({ type: "ageing", b: r._b })} />
    </div>
  );
}

// ---- new metric panels (surface model data the tower did not previously show) ----------

export function SlaOutcomes({ model, open }) {
  const s = model.sla_detail || {};
  const row = (kind, met, br) => {
    const total = (met || 0) + (br || 0);
    return { kind, met: met || 0, br: br || 0, total, att: total ? (met / total) * 100 : null };
  };
  const rows = [row("resolution", s.resolution_met, s.resolution_breached),
               row("response", s.response_met, s.response_breached)];
  return (
    <div className="panel col-6">
      <h2>SLA outcomes</h2>
      <p className="why">Met vs breached for both clocks. The scoreboard shows attainment; this shows the counts behind it. <span className="hint">Click a row.</span></p>
      <div className="scrollx">
        <table>
          <thead><tr><th>Clock</th><th className="num">Met</th><th className="num">Breached</th><th className="num">Attainment</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.kind} className="clickable" onClick={() => open({ type: "sla", kind: r.kind })}>
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
    <div className="panel col-6">
      <h2>Backlog &amp; flow</h2>
      <p className="why">Open backlog over time, and intake vs throughput across the window. Net flow tells you whether the tower is keeping up. <span className="hint">Click a point.</span></p>
      <Sparkline points={bk.map((b) => ({ x: b.week, y: b.open }))} h={70} fmt={(v) => v}
        onPick={(p, i) => open({ type: "week", w: { ...bk[i], ...(weekly[weekly.length - bk.length + i] || {}) } })} />
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
    <div className="panel col-6">
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
  const rows = buckets.map((b) => ({ label: b.label, value: (b.owned || 0) + (b.paused || 0), _b: b }));
  return (
    <div className="panel col-6">
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
