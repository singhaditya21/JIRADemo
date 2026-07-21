import React, { useState } from "react";
import { Sparkline, Bars, AnalystBand, Pairing } from "./charts.jsx";

const f1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toFixed(1));
const pct = (v) => (v == null ? "—" : f1(v) + "%");

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

export function Scoreboard({ model }) {
  const sb = model.scoreboard;
  const weekly = model.weekly || [];
  return (
    <div className="panel col-12">
      <h2>The scoreboard</h2>
      <p className="why">Six metrics, chosen so gaming one shows up in another. Targets are placeholders — the pilot replaces them with a measured baseline.</p>
      <div className="tiles">
        {METRICS.map(({ key, lab, unit, note }) => {
          const m = sb[key] || {};
          return (
            <div className="tile" key={key}>
              <span className="lab">{lab}</span>
              <span className="val tnum">{unit === "%" ? pct(m.value) : m.value ?? m.num ?? "—"}</span>
              <span className="meta">
                {m.num != null && m.den != null ? `${m.num}/${m.den} · ` : ""}{note} <Verdict m={m} />
              </span>
              <div style={{ marginTop: 4 }}>
                <Sparkline
                  points={weekly.map((w) => ({ x: w.week, y: w[key] ?? (key === "aged_14d" ? null : w[key]) }))}
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

export function PairingPanel({ model }) {
  const p = model.pairing || {};
  return (
    <div className="panel col-6">
      <h2>FTR vs reopen — the honesty pair</h2>
      <p className="why">Closing early lifts first-time resolution and wrecks reopen rate, so neither moves alone. Correlation r = {f1((p.r ?? 0) * 100) / 100 || p.r}.</p>
      <Pairing weeks={model.ftr_vs_reopen || []} r={p.r} />
    </div>
  );
}

export function Analysts({ model }) {
  const a = model.analysts || {};
  return (
    <div className="panel col-6">
      <h2>Escalation rate per analyst</h2>
      <p className="why">Pilot exit criterion 6: no analyst diverges beyond 2σ of the tower mean. Red dots are outside the band.</p>
      <AnalystBand people={a.people || []} mean={a.mean ?? a.pooled ?? 0} lo={a.lo ?? 0} hi={a.hi ?? 0} />
      <div className="legend">
        <span><span className="dot" style={{ background: "var(--accent)" }} />within 2σ</span>
        <span><span className="dot" style={{ background: "var(--crit)" }} />outside 2σ</span>
        <span>mean {pct((a.pooled ?? a.mean) * (a.pooled <= 1 ? 100 : 1))}</span>
      </div>
    </div>
  );
}

export function KBGap({ model }) {
  const kb = model.kb || {};
  return (
    <div className="panel col-6">
      <h2>KB gap — the biggest lever</h2>
      <p className="why">{kb.gap} of {kb.escalated} escalations ({pct(kb.pct)}) found no KB article. That is L1's ceiling made visible — trended weekly below.</p>
      <Sparkline points={(kb.series || []).map((s) => ({ x: s.week, y: s.gap_pct }))} fmt={pct} color="var(--warn)" />
      <div className="scrollx" style={{ marginTop: "0.8rem" }}>
        <Bars rows={(kb.by_tower || []).map(([label, n]) => ({ label, value: n }))} barH={16} />
      </div>
    </div>
  );
}

export function Towers({ model }) {
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
      <p className="why">Sortable. The pilot ranks on volume × improvement headroom.</p>
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
              <tr key={r.tower}>
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

export function Intake({ model }) {
  const rows = (model.intake || []).map((r) => ({
    label: r.channel + (r.shadow ? " (shadow)" : ""), value: r.n, dim: r.shadow,
    color: r.shadow ? "var(--warn)" : "var(--accent)",
  }));
  return (
    <div className="panel col-6">
      <h2>Intake mix</h2>
      <p className="why">Chat is shadow support pulled into the record — otherwise invisible demand.</p>
      <Bars rows={rows} barH={26} fmt={(v) => v} />
    </div>
  );
}

export function Ageing({ model }) {
  const a = model.ageing || {};
  const rows = (a.buckets || []).map((b) => ({ label: b.label, value: b.n, color: b.breach ? "var(--crit)" : "var(--accent)" }));
  return (
    <div className="panel col-6">
      <h2>Open-work ageing</h2>
      <p className="why">{a.total} open · median {f1(a.median)}d · oldest {f1(a.oldest)}d · {a.over_30} over 30 days.</p>
      <Bars rows={rows} barH={22} />
    </div>
  );
}
