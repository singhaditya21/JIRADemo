// Inline-SVG chart primitives. No chart library - the same discipline as the static
// control tower: every coordinate is computed here, nothing external is loaded.
import React from "react";

const AX = "var(--muted)";
const GRID = "var(--rule)";

// Weekly sparkline with an area fill and an emphasised endpoint.
export function Sparkline({ points, w = 520, h = 90, pad = 6, fmt = (v) => v, color = "var(--accent)", onPick }) {
  const vals = points.map((p) => p.y).filter((v) => v != null);
  if (!vals.length) return <div className="state">no data in window</div>;
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const n = points.length;
  const x = (i) => pad + (i * (w - 2 * pad)) / Math.max(1, n - 1);
  const y = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const drawn = points.map((p, i) => (p.y == null ? null : [x(i), y(p.y)])).filter(Boolean);
  const line = drawn.map(([a, b], i) => `${i ? "L" : "M"}${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
  const area = drawn.length
    ? `M${drawn[0][0].toFixed(1)},${(h - pad).toFixed(1)} ` +
      drawn.map(([a, b]) => `L${a.toFixed(1)},${b.toFixed(1)}`).join(" ") +
      ` L${drawn[drawn.length - 1][0].toFixed(1)},${(h - pad).toFixed(1)} Z`
    : "";
  const last = drawn[drawn.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" preserveAspectRatio="none" style={{ display: "block" }}>
      <path d={area} fill={color} opacity="0.12" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" />
      {last && <circle cx={last[0]} cy={last[1]} r="3" fill={color} />}
      {onPick && points.map((p, i) => p.y == null ? null : (
        <circle key={i} cx={x(i)} cy={y(p.y)} r="7" fill="transparent" style={{ cursor: "pointer" }}
          onClick={() => onPick(p, i)}><title>{fmt(p.y)}</title></circle>
      ))}
      <text x={pad} y={h - 1} fontSize="9" fill={AX} fontFamily="var(--mono)">{fmt(points[0]?.y)}</text>
      <text x={w - pad} y={h - 1} fontSize="9" fill={AX} textAnchor="end" fontFamily="var(--mono)">
        {fmt(points[points.length - 1]?.y)}
      </text>
    </svg>
  );
}

// Horizontal bars for a labelled distribution.
export function Bars({ rows, w = 520, barH = 22, gap = 6, color = "var(--accent)", fmt = (v) => v, onPick }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const h = rows.length * (barH + gap);
  const labW = 150, valW = 56;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {rows.map((r, i) => {
        const y = i * (barH + gap);
        const bw = ((w - labW - valW) * r.value) / max;
        const pick = onPick ? () => onPick(r, i) : undefined;
        return (
          <g key={i} onClick={pick} style={pick ? { cursor: "pointer" } : undefined}>
            {pick && <rect x={0} y={y} width={w} height={barH} fill="transparent" />}
            <text x={0} y={y + barH * 0.7} fontSize="11" fill="var(--ink)">{r.label}</text>
            <rect x={labW} y={y} width={Math.max(1, bw)} height={barH} rx="2" fill={r.color || color} opacity={r.dim ? 0.5 : 1} />
            <text x={w} y={y + barH * 0.7} fontSize="11" textAnchor="end" fontFamily="var(--mono)" fill="var(--ink-soft)">
              {fmt(r.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// Analyst escalation rate with the mean line and a 2-sigma band (PILOT exit criterion 6).
export function AnalystBand({ people, mean, lo, hi, w = 640, rowH = 20, onPick }) {
  const sorted = [...people].sort((a, b) => (b.rate ?? 0) - (a.rate ?? 0));
  const max = Math.max(hi, ...sorted.map((p) => p.rate ?? 0), 0.01);
  const labW = 140, h = sorted.length * rowH + 24;
  const x = (v) => labW + (v * (w - labW - 20)) / max;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      <rect x={x(Math.max(0, lo))} y={0} width={Math.max(0, x(hi) - x(Math.max(0, lo)))} height={h - 20}
        fill="var(--accent)" opacity="0.08" />
      <line x1={x(mean)} x2={x(mean)} y1={0} y2={h - 20} stroke="var(--accent)" strokeDasharray="3 3" strokeWidth="1" />
      {sorted.map((p, i) => {
        const y = i * rowH;
        const out = p.rate != null && (p.rate < lo || p.rate > hi);
        const pick = onPick ? () => onPick(p, i) : undefined;
        return (
          <g key={i} onClick={pick} style={pick ? { cursor: "pointer" } : undefined}>
            {pick && <rect x={0} y={y} width={w} height={rowH} fill="transparent" />}
            <text x={0} y={y + rowH * 0.72} fontSize="10.5" fill="var(--ink)">{p.analyst}</text>
            {p.rate != null && (
              <>
                <line x1={labW} x2={x(p.rate)} y1={y + rowH / 2} y2={y + rowH / 2} stroke="var(--rule)" strokeWidth="1" />
                <circle cx={x(p.rate)} cy={y + rowH / 2} r="4" fill={out ? "var(--crit)" : "var(--accent)"} />
              </>
            )}
            {p.rate == null && <text x={labW} y={y + rowH * 0.72} fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">too few</text>}
          </g>
        );
      })}
      <text x={x(mean)} y={h - 6} fontSize="9" fill="var(--muted)" textAnchor="middle" fontFamily="var(--mono)">mean</text>
    </svg>
  );
}

// A labelled matrix (e.g. Impact × Urgency). cell(rowLabel, colLabel) -> {value, sub?}.
export function Heatmap({ rows, cols, cell, onPick, w = 380, cellH = 46, labW = 96 }) {
  const vals = rows.flatMap((r) => cols.map((c) => (cell(r, c) || {}).value || 0));
  const max = Math.max(1, ...vals);
  const cw = (w - labW) / cols.length;
  const h = rows.length * cellH + 22;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {cols.map((c, ci) => (
        <text key={ci} x={labW + ci * cw + cw / 2} y={13} fontSize="10" textAnchor="middle" fill={AX} fontFamily="var(--mono)">{c}</text>
      ))}
      {rows.map((r, ri) => (
        <g key={ri}>
          <text x={0} y={22 + ri * cellH + cellH / 2 + 4} fontSize="10.5" fill="var(--ink)">{r}</text>
          {cols.map((c, ci) => {
            const d = cell(r, c) || { value: 0 };
            const pick = onPick ? () => onPick(r, c, d) : undefined;
            return (
              <g key={ci} onClick={pick} style={pick ? { cursor: "pointer" } : undefined}>
                <rect x={labW + ci * cw + 1.5} y={22 + ri * cellH + 1.5} width={cw - 3} height={cellH - 3} rx="3"
                  fill="var(--accent)" opacity={0.1 + 0.72 * ((d.value || 0) / max)} />
                <text x={labW + ci * cw + cw / 2} y={22 + ri * cellH + cellH / 2 - 1} fontSize="13" textAnchor="middle"
                  fontWeight="650" fontFamily="var(--mono)" fill="var(--ink)">{d.value || ""}</text>
                {d.sub && <text x={labW + ci * cw + cw / 2} y={22 + ri * cellH + cellH - 7} fontSize="8"
                  textAnchor="middle" fill={AX} fontFamily="var(--mono)">{d.sub}</text>}
              </g>
            );
          })}
        </g>
      ))}
    </svg>
  );
}

// Horizontal box-plots — one row per group. `groups`: [{label, min,q1,med,q3,max,n}].
// The distribution the mean hides: MTTR per priority, dwell per tower, etc.
export function BoxPlot({ groups, w = 520, rowH = 30, gap = 8, fmt = (v) => v, unit = "" }) {
  const all = groups.flatMap((g) => [g.min, g.max]).filter((v) => v != null);
  const max = Math.max(1, ...all);
  const labW = 74, axW = w - labW - 96;
  const x = (v) => labW + (v / max) * axW;
  const h = groups.length * (rowH + gap) + 6;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {groups.map((g, i) => {
        const y = i * (rowH + gap) + rowH / 2;
        if (!g.n || g.med == null) return (
          <g key={i}><text x={0} y={y + 4} fontSize="11" fill="var(--ink)">{g.label}</text>
            <text x={labW} y={y + 4} fontSize="10" fill="var(--muted)" fontFamily="var(--mono)">no data</text></g>);
        return (
          <g key={i}>
            <text x={0} y={y + 4} fontSize="11" fill="var(--ink)">{g.label}</text>
            <line x1={x(g.min)} x2={x(g.max)} y1={y} y2={y} stroke="var(--rule)" />
            <line x1={x(g.min)} x2={x(g.min)} y1={y - 5} y2={y + 5} stroke="var(--rule)" />
            <line x1={x(g.max)} x2={x(g.max)} y1={y - 5} y2={y + 5} stroke="var(--rule)" />
            <rect x={x(g.q1)} y={y - 8} width={Math.max(1, x(g.q3) - x(g.q1))} height="16" rx="2" fill="var(--accent)" opacity="0.28" stroke="var(--accent)" />
            <line x1={x(g.med)} x2={x(g.med)} y1={y - 8} y2={y + 8} stroke="var(--accent)" strokeWidth="2" />
            <text x={w} y={y + 4} fontSize="9" textAnchor="end" fill="var(--muted)" fontFamily="var(--mono)">{fmt(g.med)}{unit} · n{g.n}</text>
          </g>
        );
      })}
    </svg>
  );
}

// Dot-plot on a shared 0–100% axis — attainment per category, one dot each, target line.
export function DotPlot({ rows, w = 520, rowH = 24, target = null }) {
  const labW = 140, axW = w - labW - 48;
  const x = (v) => labW + (v / 100) * axW;
  const h = rows.length * rowH + 18;
  const r1 = (v) => Math.round(v * 10) / 10;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {[0, 50, 100].map((t) => (
        <g key={t}><line x1={x(t)} x2={x(t)} y1={0} y2={h - 16} stroke="var(--rule)" opacity="0.5" />
          <text x={x(t)} y={h - 4} fontSize="8" textAnchor="middle" fill="var(--muted)" fontFamily="var(--mono)">{t}%</text></g>))}
      {target != null && <line x1={x(target)} x2={x(target)} y1={0} y2={h - 16} stroke="var(--accent)" strokeDasharray="3 3" />}
      {rows.map((r, i) => {
        const y = i * rowH + rowH / 2;
        const col = r.value >= (target ?? 0) ? "var(--ok)" : "var(--crit)";
        return (
          <g key={i} onClick={r.onPick} style={r.onPick ? { cursor: "pointer" } : undefined}>
            {r.onPick && <rect x={0} y={i * rowH} width={w} height={rowH} fill="transparent" />}
            <text x={0} y={y + 4} fontSize="11" fill="var(--ink)">{r.label}</text>
            <line x1={labW} x2={x(r.value)} y1={y} y2={y} stroke="var(--rule)" />
            <circle cx={x(r.value)} cy={y} r="5" fill={col} />
            <text x={w} y={y + 4} fontSize="10" textAnchor="end" fill="var(--ink-soft)" fontFamily="var(--mono)">{r1(r.value)}%{r.n != null ? ` (${r.n})` : ""}</text>
          </g>
        );
      })}
    </svg>
  );
}

// Donut with an optional center label. `slices`: [{label,value,color}].
export function Donut({ slices, w = 190, thickness = 30, center = null, onPick }) {
  const total = slices.reduce((a, s) => a + s.value, 0) || 1;
  const r = w / 2 - 3, ir = r - thickness, cx = w / 2, cy = w / 2;
  let a0 = -Math.PI / 2;
  const arc = (s, e) => {
    const x0 = cx + r * Math.cos(s), y0 = cy + r * Math.sin(s), x1 = cx + r * Math.cos(e), y1 = cy + r * Math.sin(e);
    const xi1 = cx + ir * Math.cos(e), yi1 = cy + ir * Math.sin(e), xi0 = cx + ir * Math.cos(s), yi0 = cy + ir * Math.sin(s);
    const large = e - s > Math.PI ? 1 : 0;
    return `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${xi1},${yi1} A${ir},${ir} 0 ${large} 0 ${xi0},${yi0} Z`;
  };
  return (
    <svg viewBox={`0 0 ${w} ${w}`} width={w} style={{ maxWidth: "100%" }}>
      {slices.map((s, i) => {
        const a1 = a0 + (s.value / total) * 2 * Math.PI, d = arc(a0, a1); a0 = a1;
        return <path key={i} d={d} fill={s.color} opacity="0.9" onClick={onPick ? () => onPick(s) : undefined}
          style={onPick ? { cursor: "pointer" } : undefined}><title>{s.label}: {s.value}</title></path>;
      })}
      {center && <text x={cx} y={cy - 1} fontSize="20" textAnchor="middle" fontWeight="650" fontFamily="var(--mono)" fill="var(--ink)">{center.v}</text>}
      {center && <text x={cx} y={cy + 15} fontSize="9" textAnchor="middle" fill="var(--muted)" fontFamily="var(--mono)">{center.k}</text>}
    </svg>
  );
}

// Two-column Sankey — left nodes flow to right nodes, ribbon width ∝ value. Used for
// tier→tier transition flow. `left`/`right`: [{id,label,value,color}]; `links`: [{from,to,value}].
export function Sankey({ left, right, links, w = 560, h = 250, nodeW = 12, gap = 12, pad = 18, onPick }) {
  const leftTot = left.reduce((a, n) => a + n.value, 0) || 1;
  const rightTot = right.reduce((a, n) => a + n.value, 0) || 1;
  const availL = h - pad * 2 - gap * Math.max(0, left.length - 1);
  const availR = h - pad * 2 - gap * Math.max(0, right.length - 1);
  const scaleL = availL / leftTot, scaleR = availR / rightTot;
  const L = {}, R = {};
  let y = pad; for (const n of left) { const hh = Math.max(2, n.value * scaleL); L[n.id] = { ...n, x: pad, y, h: hh, off: 0 }; y += hh + gap; }
  y = pad; for (const n of right) { const hh = Math.max(2, n.value * scaleR); R[n.id] = { ...n, x: w - pad - nodeW, y, h: hh, off: 0 }; y += hh + gap; }
  const ribbons = links.filter((l) => L[l.from] && R[l.to] && l.value > 0).map((l, i) => {
    const ln = L[l.from], rn = R[l.to], thL = l.value * scaleL, thR = l.value * scaleR;
    const y0 = ln.y + ln.off, y1 = y0 + thL; ln.off += thL;
    const y2 = rn.y + rn.off, y3 = y2 + thR; rn.off += thR;
    const x0 = ln.x + nodeW, x1 = rn.x, mx = (x0 + x1) / 2;
    const d = `M${x0},${y0} C${mx},${y0} ${mx},${y2} ${x1},${y2} L${x1},${y3} C${mx},${y3} ${mx},${y1} ${x0},${y1} Z`;
    return { d, l, color: ln.color };
  });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {ribbons.map((rb, i) => (
        <path key={i} d={rb.d} fill={rb.color} opacity="0.28"
          onClick={onPick ? () => onPick(rb.l) : undefined} style={onPick ? { cursor: "pointer" } : undefined}>
          <title>{L[rb.l.from].label} → {R[rb.l.to].label}: {rb.l.value}</title></path>
      ))}
      {[...Object.values(L), ...Object.values(R)].map((n, i) => (
        <g key={i}>
          <rect x={n.x} y={n.y} width={nodeW} height={n.h} rx="2" fill={n.color} />
          <text x={n.x < w / 2 ? n.x + nodeW + 4 : n.x - 4} y={n.y + n.h / 2 + 3} fontSize="10"
            textAnchor={n.x < w / 2 ? "start" : "end"} fill="var(--ink)">{n.label} <tspan fill="var(--muted)" fontFamily="var(--mono)">{n.value}</tspan></text>
        </g>
      ))}
    </svg>
  );
}

// FTR vs reopen scatter over weeks - the pairing that makes gaming visible.
export function Pairing({ weeks, r, w = 480, h = 260, pad = 34, onPick }) {
  // The model (app/analytics.ftr_vs_reopen) keys these ftr_pct / reopen_pct.
  const pts = weeks.filter((p) => p.ftr_pct != null && p.reopen_pct != null);
  if (pts.length < 2) return <div className="state">not enough weeks</div>;
  const xs = pts.map((p) => p.ftr_pct), ys = pts.map((p) => p.reopen_pct);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const ymin = Math.min(...ys), ymax = Math.max(...ys);
  const sx = (v) => pad + ((v - xmin) / (xmax - xmin || 1)) * (w - 2 * pad);
  const sy = (v) => h - pad - ((v - ymin) / (ymax - ymin || 1)) * (h - 2 * pad);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke={GRID} />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke={GRID} />
      {pts.map((p, i) => {
        const pick = onPick ? () => onPick(p, i) : undefined;
        return (
          <g key={i} onClick={pick} style={pick ? { cursor: "pointer" } : undefined}>
            {pick && <circle cx={sx(p.ftr_pct)} cy={sy(p.reopen_pct)} r="11" fill="transparent" />}
            <circle cx={sx(p.ftr_pct)} cy={sy(p.reopen_pct)} r="4" fill="var(--accent)" opacity={0.35 + (0.6 * i) / pts.length}><title>{p.week}</title></circle>
          </g>
        );
      })}
      <text x={w / 2} y={h - 6} fontSize="10" textAnchor="middle" fill={AX} fontFamily="var(--mono)">first-time resolution %  →</text>
      <text x={12} y={h / 2} fontSize="10" textAnchor="middle" fill={AX} fontFamily="var(--mono)" transform={`rotate(-90 12 ${h / 2})`}>
        reopen %  →
      </text>
    </svg>
  );
}
