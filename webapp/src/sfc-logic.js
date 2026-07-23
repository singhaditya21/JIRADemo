// Pure SFC (DeliveryIQ) logic — no React, no DOM, no imports.
//
// These predicates decide what the lens ASSERTS: which requests are at risk and why, which
// agent holds a request, where work leaks backwards through the pipeline. They lived inline
// in panels.jsx, which made them untestable without a DOM — so the Python bake had 45 tests
// while the rules the user actually reads were unverified. Extracted here so sfc-logic.test.js
// can pin them; panels.jsx imports and renders, nothing more.

export const SFC_STAGES = ["Intake", "Build", "Review", "Deploy", "Audit"];
export const DEPLOY_ORDER = ["Not started", "Validated", "Deploying", "Deployed", "Failed", "Rolled back"];
export const HEALTH_COLOR = { Healthy: "var(--ok)", Degraded: "var(--warn)", Failing: "var(--crit)", Unknown: "var(--muted)" };

// ---- agents -------------------------------------------------------------------------
// The three DeliveryIQ agents mapped onto the five-stage pipeline: Build delivers
// (Intake→Build), Compliance reviews and audits (Review, Audit), Coordination orchestrates
// the multi-org deploy (Deploy).
export const SFC_AGENTS = ["Build", "Compliance", "Coordination"];
export const AGENT_COLOR = { Build: "var(--accent)", Compliance: "var(--ok)", Coordination: "var(--warn)" };
export const STAGE_AGENT = { Intake: "Build", Build: "Build", Review: "Compliance", Deploy: "Coordination", Audit: "Compliance" };
// Frontend mirror of the bake's status→stage map, so a changelog `to` status resolves.
export const STATUS_STAGE = { Intake: "Intake", "In Build": "Build", "In Review": "Review",
  "Awaiting CAB": "Deploy", Deploying: "Deploy", Deployed: "Deploy", "Deploy Failed": "Deploy",
  "Rolled Back": "Deploy", Audit: "Audit", Done: "Audit", Cancelled: "Audit" };
export const agentOf = (stage) => STAGE_AGENT[stage] || "Build";

/** Agent→agent handoff counts from the real changelog. Every request starts at Intake, which
 *  Build owns, so the walk seeds `prev` with Build rather than the first hop's agent. */
export function agentHandoffs(records) {
  const out = {};
  for (const r of records || []) {
    let prev = "Build";
    for (const ev of (r.timeline || [])) {
      const ag = agentOf(STATUS_STAGE[ev.to] || ev.to);
      if (ag && ag !== prev) { const k = prev + "→" + ag; out[k] = (out[k] || 0) + 1; prev = ag; }
    }
  }
  return out;
}

// ---- §5.7 at-risk reasons ------------------------------------------------------------
// Hours a request may sit in a stage before it counts as stalled. Comparison is inclusive.
export const STALL_H = { Intake: 24, Build: 72, Review: 48, Deploy: 24, Audit: 120 };
export const isStalled = (r) => {
  const t = r.time_in_stage_h;
  return t != null && t >= (STALL_H[r.stage] ?? 72);
};

// Three spec tokens do not exist on this instance and are substituted honestly rather than
// faked: statuses "Build Blocked"/"Changes Requested" (a rejected CAB is the real analogue),
// health "Drifted" (the vocabulary is Healthy/Degraded/Failing/Unknown), lower-case risk.
export const AT_RISK_REASONS = [
  { k: "stalled", lab: (r) => `stalled @ ${r && r.stage ? r.stage : "stage"}`, test: isStalled },
  { k: "deploy_failed", lab: () => "deploy failed",
    test: (r) => (r.org_deploys || []).some((d) => d.deploy_state === "Failed") || r.status === "Deploy Failed" },
  { k: "rolled_back", lab: () => "rolled back",
    test: (r) => (r.org_deploys || []).some((d) => d.deploy_state === "Rolled back") || r.status === "Rolled Back" },
  { k: "cab_rejected", lab: () => "CAB rejected", test: (r) => r.cab_approval === "Rejected" },
  { k: "evidence_gap", lab: () => "evidence incomplete",
    test: (r) => ["Deploy", "Audit"].includes(r.stage) && !r.evidence_pack_ready },
  { k: "health", lab: () => "config degraded",
    test: (r) => (r.org_deploys || []).some((d) => ["Degraded", "Failing"].includes(d.config_health)) },
  { k: "risky_stall", lab: () => "high-risk & stalled",
    test: (r) => String(r.change_risk || "").toLowerCase() === "high" && isStalled(r) },
];

/** The queue: open requests carrying at least one reason, worst-first.
 *  Population is `!is_done` — a Deploy-Failed request is exactly what belongs here. */
export function atRiskRows(records) {
  return (records || []).filter((r) => !r.is_done)
    .map((r) => ({ r, reasons: AT_RISK_REASONS.filter((x) => x.test(r)) }))
    .filter((x) => x.reasons.length)
    .sort((a, b) => b.reasons.length - a.reasons.length
      || (b.r.time_in_stage_h || 0) - (a.r.time_in_stage_h || 0));
}

// ---- §2.5 stage-of-flight ------------------------------------------------------------
// SIX nodes: `done` is a terminal distinct from the record's five-bucket `stage` field.
export const SOF = { Intake: "intake", "In Build": "build", "In Review": "review",
  "Awaiting CAB": "deploy", Deploying: "deploy", Deployed: "deploy",
  "Deploy Failed": "deploy", "Rolled Back": "deploy", Audit: "audit",
  Done: "done", Cancelled: "done" };
export const SOF_ORDER = ["intake", "build", "review", "deploy", "audit", "done"];
export const SOF_COLOR = { intake: "var(--muted)", build: "var(--accent)", review: "var(--ok)",
  deploy: "var(--warn)", audit: "var(--accent-dim)", done: "var(--ok)" };

/** Stage-to-stage transition counts from the changelog.
 *  Same-node hops (e.g. Deploying→Deployed, both `deploy`) carry no flow and are dropped.
 *  A hop is BACKWARD when it moves left in SOF_ORDER — that is the leakage the panel exists
 *  to surface (review ping-pong, deploy rework, post-audit rollback). */
export function stageFlow(records) {
  const counts = {};
  let hops = 0;
  for (const r of records || []) {
    for (const c of (r.timeline || []).filter((x) => x.field === "status")) {
      const f = SOF[c.from], t = SOF[c.to];
      if (!f || !t || f === t) continue;
      counts[f + "|" + t] = (counts[f + "|" + t] || 0) + 1;
      hops++;
    }
  }
  const links = Object.entries(counts).map(([k, v]) => {
    const [f, t] = k.split("|");
    return { from: "L" + f, to: "R" + t, value: v,
             back: SOF_ORDER.indexOf(f) > SOF_ORDER.indexOf(t) };
  });
  return { counts, hops, links, backward: links.filter((l) => l.back) };
}

/** A node's value is the flow through it on that side of the diagram. */
export function sofNodes(counts, side) {
  return SOF_ORDER.map((id) => ({
    id: side + id, label: id, color: SOF_COLOR[id],
    value: Object.entries(counts).reduce((a, [k, v]) =>
      a + ((side === "L" ? k.split("|")[0] : k.split("|")[1]) === id ? v : 0), 0),
  })).filter((n) => n.value > 0);
}
