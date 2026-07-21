// Inline-SVG chart primitives. No chart library - the same discipline as the static
// control tower: every coordinate is computed here, nothing external is loaded.
import React from "react";

const AX = "var(--muted)";
const GRID = "var(--rule)";

// Weekly sparkline with an area fill and an emphasised endpoint.
export function Sparkline({ points, w = 520, h = 90, pad = 6, fmt = (v) => v, color = "var(--accent)" }) {
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
      <text x={pad} y={h - 1} fontSize="9" fill={AX} fontFamily="var(--mono)">{fmt(points[0]?.y)}</text>
      <text x={w - pad} y={h - 1} fontSize="9" fill={AX} textAnchor="end" fontFamily="var(--mono)">
        {fmt(points[points.length - 1]?.y)}
      </text>
    </svg>
  );
}

// Horizontal bars for a labelled distribution.
export function Bars({ rows, w = 520, barH = 22, gap = 6, color = "var(--accent)", fmt = (v) => v }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const h = rows.length * (barH + gap);
  const labW = 150, valW = 56;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      {rows.map((r, i) => {
        const y = i * (barH + gap);
        const bw = ((w - labW - valW) * r.value) / max;
        return (
          <g key={i}>
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
export function AnalystBand({ people, mean, lo, hi, w = 640, rowH = 20 }) {
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
        return (
          <g key={i}>
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

// FTR vs reopen scatter over weeks - the pairing that makes gaming visible.
export function Pairing({ weeks, r, w = 480, h = 260, pad = 34 }) {
  const pts = weeks.filter((p) => p.ftr != null && p.reopen != null);
  if (pts.length < 2) return <div className="state">not enough weeks</div>;
  const xs = pts.map((p) => p.ftr), ys = pts.map((p) => p.reopen);
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const ymin = Math.min(...ys), ymax = Math.max(...ys);
  const sx = (v) => pad + ((v - xmin) / (xmax - xmin || 1)) * (w - 2 * pad);
  const sy = (v) => h - pad - ((v - ymin) / (ymax - ymin || 1)) * (h - 2 * pad);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke={GRID} />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke={GRID} />
      {pts.map((p, i) => (
        <circle key={i} cx={sx(p.ftr)} cy={sy(p.reopen)} r="4" fill="var(--accent)" opacity={0.35 + (0.6 * i) / pts.length} />
      ))}
      <text x={w / 2} y={h - 6} fontSize="10" textAnchor="middle" fill={AX} fontFamily="var(--mono)">first-time resolution %  →</text>
      <text x={12} y={h / 2} fontSize="10" textAnchor="middle" fill={AX} fontFamily="var(--mono)" transform={`rotate(-90 12 ${h / 2})`}>
        reopen %  →
      </text>
    </svg>
  );
}
