// Tests for the SFC lens's own rules — the at-risk predicates, the stall thresholds, the
// agent map and the stage-of-flight flow. These decide what the lens ASSERTS to a reader,
// and until now only the Python bake was tested, so the rules the user actually sees were
// unverified. No DOM, no React: sfc-logic.js is deliberately pure.
//
//     cd webapp && bun test

import { describe, expect, test } from "bun:test";
import {
  STALL_H, isStalled, AT_RISK_REASONS, atRiskRows,
  STAGE_AGENT, STATUS_STAGE, agentOf, agentHandoffs,
  SOF, SOF_ORDER, stageFlow, sofNodes, SFC_STAGES,
} from "./sfc-logic.js";

const rec = (o = {}) => ({
  key: "SFC-1", status: "In Build", stage: "Build", is_done: false,
  org_deploys: [], cab_approval: "Approved", evidence_pack_ready: true,
  change_risk: "Low", time_in_stage_h: 1, timeline: [], ...o,
});
const dep = (o = {}) => ({ org: "Prod", deploy_state: "Deployed", config_health: "Healthy", ...o });
const hop = (from, to) => ({ at: null, field: "status", from, to });
const reason = (r, k) => AT_RISK_REASONS.find((x) => x.k === k).test(r);

describe("stall thresholds", () => {
  test("every stage has a threshold and they are all positive", () => {
    for (const s of SFC_STAGES) expect(STALL_H[s]).toBeGreaterThan(0);
  });

  test("comparison is inclusive at the boundary", () => {
    expect(isStalled(rec({ stage: "Review", time_in_stage_h: STALL_H.Review }))).toBe(true);
    expect(isStalled(rec({ stage: "Review", time_in_stage_h: STALL_H.Review - 0.1 }))).toBe(false);
  });

  test("thresholds are per-stage, not one global number", () => {
    // 100h is stalled in Review (48h) but NOT in Audit (120h) — the whole point of the map
    expect(isStalled(rec({ stage: "Review", time_in_stage_h: 100 }))).toBe(true);
    expect(isStalled(rec({ stage: "Audit", time_in_stage_h: 100 }))).toBe(false);
  });

  test("a missing clock is never reported as stalled", () => {
    expect(isStalled(rec({ time_in_stage_h: null }))).toBe(false);
    expect(isStalled(rec({ time_in_stage_h: undefined }))).toBe(false);
  });

  test("an unknown stage falls back to a threshold rather than throwing", () => {
    expect(isStalled(rec({ stage: "Nonsense", time_in_stage_h: 1000 }))).toBe(true);
  });
});

describe("at-risk reasons", () => {
  test("a healthy in-flight request carries no reason", () => {
    expect(atRiskRows([rec()]).length).toBe(0);
  });

  test("deploy_failed fires on a failed org OR the request status", () => {
    expect(reason(rec({ org_deploys: [dep({ deploy_state: "Failed" })] }), "deploy_failed")).toBe(true);
    expect(reason(rec({ status: "Deploy Failed" }), "deploy_failed")).toBe(true);
  });

  test("rolled_back does not fire on a merely failed deploy", () => {
    // the two are separate reasons on purpose; deploy_rollup collapses them, so predicates
    // must read org_deploys directly or the counter-metric pairing breaks
    expect(reason(rec({ org_deploys: [dep({ deploy_state: "Failed" })] }), "rolled_back")).toBe(false);
    expect(reason(rec({ org_deploys: [dep({ deploy_state: "Rolled back" })] }), "rolled_back")).toBe(true);
  });

  test("deploy-state matching is case-exact ('Rolled back', not 'Rolled Back')", () => {
    expect(reason(rec({ org_deploys: [dep({ deploy_state: "Rolled Back" })] }), "rolled_back")).toBe(false);
  });

  test("evidence gap only applies from Deploy onwards", () => {
    expect(reason(rec({ stage: "Build", evidence_pack_ready: false }), "evidence_gap")).toBe(false);
    expect(reason(rec({ stage: "Deploy", evidence_pack_ready: false }), "evidence_gap")).toBe(true);
    expect(reason(rec({ stage: "Audit", evidence_pack_ready: false }), "evidence_gap")).toBe(true);
  });

  test("degraded health fires on Degraded or Failing, not Unknown", () => {
    expect(reason(rec({ org_deploys: [dep({ config_health: "Degraded" })] }), "health")).toBe(true);
    expect(reason(rec({ org_deploys: [dep({ config_health: "Failing" })] }), "health")).toBe(true);
    expect(reason(rec({ org_deploys: [dep({ config_health: "Unknown" })] }), "health")).toBe(false);
  });

  test("risk matching is case-insensitive (data is 'High', spec says 'high')", () => {
    const r = rec({ change_risk: "High", stage: "Review", time_in_stage_h: 999 });
    expect(reason(r, "risky_stall")).toBe(true);
    expect(reason({ ...r, change_risk: "high" }, "risky_stall")).toBe(true);
    expect(reason({ ...r, change_risk: "Low" }, "risky_stall")).toBe(false);
  });

  test("a done request is excluded from the queue even when it carries reasons", () => {
    const done = rec({ is_done: true, org_deploys: [dep({ deploy_state: "Failed" })] });
    expect(atRiskRows([done]).length).toBe(0);
  });

  test("a Deploy-Failed request IS in the queue — it is not done", () => {
    const r = rec({ status: "Deploy Failed", stage: "Deploy", is_done: false });
    expect(atRiskRows([r]).length).toBe(1);
  });

  test("rows are sorted worst-first by reason count", () => {
    const one = rec({ key: "A", org_deploys: [dep({ deploy_state: "Failed" })] });
    const many = rec({ key: "B", stage: "Deploy", evidence_pack_ready: false,
      cab_approval: "Rejected", org_deploys: [dep({ deploy_state: "Rolled back", config_health: "Failing" })] });
    expect(atRiskRows([one, many])[0].r.key).toBe("B");
  });

  test("the distinct union is never larger than the sum of per-reason hits", () => {
    const rs = [
      rec({ key: "A", stage: "Deploy", evidence_pack_ready: false, org_deploys: [dep({ config_health: "Degraded" })] }),
      rec({ key: "B", cab_approval: "Rejected" }),
    ];
    const union = atRiskRows(rs).length;
    const summed = AT_RISK_REASONS.reduce((a, x) => a + rs.filter(x.test).length, 0);
    expect(union).toBeLessThanOrEqual(summed);
    expect(union).toBe(2);
  });

  test("missing org_deploys/timeline never throws", () => {
    expect(() => atRiskRows([{ is_done: false, stage: "Build" }])).not.toThrow();
  });
});

describe("agent map + handoffs", () => {
  test("every stage maps to one of the three agents", () => {
    for (const s of SFC_STAGES) expect(["Build", "Compliance", "Coordination"]).toContain(STAGE_AGENT[s]);
  });

  test("every workflow status resolves to a stage", () => {
    for (const st of Object.keys(SOF)) expect(STATUS_STAGE[st]).toBeDefined();
  });

  test("an unknown stage falls back rather than returning undefined", () => {
    expect(agentOf("Nonsense")).toBe("Build");
  });

  test("a forward walk counts one handoff per agent change, not per hop", () => {
    // Intake→Build is Build→Build (no handoff); Build→Review crosses to Compliance
    const r = rec({ timeline: [hop("Intake", "In Build"), hop("In Build", "In Review")] });
    expect(agentHandoffs([r])).toEqual({ "Build→Compliance": 1 });
  });

  test("the walk seeds at Build, so a first hop into Review still counts", () => {
    const r = rec({ timeline: [hop("Intake", "In Review")] });
    expect(agentHandoffs([r])["Build→Compliance"]).toBe(1);
  });

  test("a full pipeline produces the expected handoff chain", () => {
    const r = rec({ timeline: [
      hop("Intake", "In Build"), hop("In Build", "In Review"),
      hop("In Review", "Deploying"), hop("Deploying", "Audit")] });
    expect(agentHandoffs([r])).toEqual({
      "Build→Compliance": 1, "Compliance→Coordination": 1, "Coordination→Compliance": 1 });
  });
});

describe("stage-of-flight flow", () => {
  test("done is a node distinct from the five record stages", () => {
    expect(SOF.Done).toBe("done");
    expect(SOF_ORDER).toContain("done");
    expect(SFC_STAGES).not.toContain("done");
  });

  test("same-node hops carry no flow", () => {
    // Deploying→Deployed are both `deploy`, so the ribbon would be a self-loop
    const r = rec({ timeline: [hop("Deploying", "Deployed")] });
    expect(stageFlow([r]).hops).toBe(0);
  });

  test("a forward hop is not marked backward", () => {
    const f = stageFlow([rec({ timeline: [hop("In Build", "In Review")] })]);
    expect(f.hops).toBe(1);
    expect(f.backward.length).toBe(0);
  });

  test("review ping-pong is detected as backward leakage", () => {
    const f = stageFlow([rec({ timeline: [hop("In Review", "In Build")] })]);
    expect(f.backward.length).toBe(1);
    expect(f.backward[0].from).toBe("Lreview");
    expect(f.backward[0].to).toBe("Rbuild");
  });

  test("post-audit rollback is backward", () => {
    expect(stageFlow([rec({ timeline: [hop("Audit", "Rolled Back")] })]).backward.length).toBe(1);
  });

  test("unknown statuses are ignored rather than crashing the panel", () => {
    const f = stageFlow([rec({ timeline: [hop("Nonsense", "In Review"), hop("In Build", "Whatever")] })]);
    expect(f.hops).toBe(0);
  });

  test("non-status changelog entries are filtered out", () => {
    const r = rec({ timeline: [{ at: null, field: "priority", from: "Intake", to: "In Review" }] });
    expect(stageFlow([r]).hops).toBe(0);
  });

  test("node values equal the flow through that side", () => {
    const rs = [rec({ timeline: [hop("Intake", "In Build")] }),
                rec({ timeline: [hop("Intake", "In Build")] })];
    const { counts } = stageFlow(rs);
    expect(sofNodes(counts, "L").find((n) => n.label === "intake").value).toBe(2);
    expect(sofNodes(counts, "R").find((n) => n.label === "build").value).toBe(2);
  });

  test("zero-flow nodes are dropped so the diagram has no empty stubs", () => {
    const { counts } = stageFlow([rec({ timeline: [hop("Intake", "In Build")] })]);
    expect(sofNodes(counts, "L").map((n) => n.label)).toEqual(["intake"]);
  });

  test("empty input yields an empty, non-throwing flow", () => {
    const f = stageFlow([]);
    expect(f.hops).toBe(0);
    expect(f.links).toEqual([]);
  });
});
