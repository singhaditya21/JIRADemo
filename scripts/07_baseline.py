#!/usr/bin/env python3
"""Measure the six scoreboard metrics from live Jira data.

This is the script that replaces invented targets with measured ones. Run it before
the pilot to establish a baseline, then weekly during the pilot to see movement.

Every window is computed against `Reported At`, not `created` - see SCHEMA.md.

Usage:  python3 scripts/07_baseline.py [--days 90] [--by-tower] [--json out.json]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
P = C.PROJECT_KEY


def count(j, jql):
    return j.post("/rest/api/3/search/approximate-count", {"jql": jql}).get("count", 0)


def pct(n, d):
    return (100.0 * n / d) if d else 0.0


def measure(j, window, scope=""):
    """scope is an extra JQL clause, e.g. ' AND Tower = "Database"'."""
    base = f'project = {P}{scope} AND "Reported At" >= -{window}d'
    m = {}

    m["volume"] = count(j, base)

    # First-time resolution: finished, never left L1. Problems are excluded because
    # they are investigations by definition and would drag FTR down for doing the
    # right thing.
    done = f'{base} AND statusCategory = Done AND issuetype != Problem'
    m["closed"] = count(j, done)
    m["ftr"] = count(j, f'{done} AND "Support Tier" = L1')
    m["ftr_pct"] = pct(m["ftr"], m["closed"])

    m["escalated"] = count(j, f'{base} AND "Support Tier" = L2')
    m["escalation_pct"] = pct(m["escalated"], m["volume"])

    m["reopened"] = count(j, f'{base} AND Reopened = Yes')
    m["reopen_pct"] = pct(m["reopened"], m["closed"])

    met = count(j, f'{base} AND "Resolution SLA" = Met')
    breached = count(j, f'{base} AND "Resolution SLA" = Breached')
    m["sla_met"], m["sla_breached"] = met, breached
    m["sla_pct"] = pct(met, met + breached)

    resp_met = count(j, f'{base} AND "Response SLA" = Met')
    resp_br = count(j, f'{base} AND "Response SLA" = Breached')
    m["response_pct"] = pct(resp_met, resp_met + resp_br)

    m["aged_14d"] = count(j, f'project = {P}{scope} AND statusCategory != Done '
                             f'AND "Reported At" <= -14d')
    m["open"] = count(j, f'project = {P}{scope} AND statusCategory != Done')

    # The KB gap is the lever that lifts L1's ceiling over time.
    m["kb_gap"] = count(j, f'{base} AND "KB Article Checked" = "Yes - none found"')
    m["kb_gap_pct"] = pct(m["kb_gap"], m["escalated"])

    m["shadow_chat"] = count(j, f'{base} AND "Intake Channel" = Chat')
    return m


TARGETS = {"ftr_pct": (65, "ge"), "reopen_pct": (5, "le"),
           "sla_pct": (95, "ge"), "response_pct": (95, "ge")}


def verdict(key, value):
    if key not in TARGETS:
        return ""
    target, direction = TARGETS[key]
    ok = value >= target if direction == "ge" else value <= target
    return f"  [{'PASS' if ok else 'GAP '}] target {'>=' if direction=='ge' else '<='}{target}%"


def report(label, m):
    log(f"\n=== {label} ===")
    log(f"  volume (reported in window)     {m['volume']:>6}")
    log(f"  closed (excl. problems)         {m['closed']:>6}")
    log(f"  first-time resolution at L1     {m['ftr_pct']:>5.1f}%  ({m['ftr']}/{m['closed']})"
        + verdict("ftr_pct", m["ftr_pct"]))
    log(f"  escalation rate                 {m['escalation_pct']:>5.1f}%  ({m['escalated']}/{m['volume']})")
    log(f"  reopen rate                     {m['reopen_pct']:>5.1f}%  ({m['reopened']}/{m['closed']})"
        + verdict("reopen_pct", m["reopen_pct"]))
    log(f"  resolution SLA attainment       {m['sla_pct']:>5.1f}%  ({m['sla_met']} met / {m['sla_breached']} breached)"
        + verdict("sla_pct", m["sla_pct"]))
    log(f"  response SLA attainment         {m['response_pct']:>5.1f}%"
        + verdict("response_pct", m["response_pct"]))
    log(f"  open now                        {m['open']:>6}")
    log(f"  aged over 14 days               {m['aged_14d']:>6}   target 0")
    log(f"  escalated with no KB article    {m['kb_gap']:>6}   ({m['kb_gap_pct']:.0f}% of escalations)"
        f"  <- KB backlog")
    log(f"  arrived via chat                {m['shadow_chat']:>6}   <- shadow support pulled in")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--by-tower", action="store_true")
    ap.add_argument("--json", type=str)
    args = ap.parse_args()

    require_env()
    j = Jira()

    log(f"Baseline over the last {args.days} days, measured on 'Reported At'.")
    log("Targets are PLACEHOLDERS (CLAIMS.md #15) - replace them with a target set")
    log("from this baseline once it reflects a real organisation.")

    out = {"window_days": args.days, "overall": measure(j, args.days)}
    report(f"ALL TOWERS - last {args.days}d", out["overall"])

    if args.by_tower:
        out["towers"] = {}
        for tower, _ in C.TOWERS:
            m = measure(j, args.days, f' AND Tower = "{tower}"')
            out["towers"][tower] = m
            report(tower, m)

        log("\n=== pilot candidate ranking ===")
        log("  Best pilot tower: enough volume to be significant, worst FTR to improve.")
        log(f"  {'tower':<26}{'volume':>8}{'FTR%':>8}{'esc%':>8}{'SLA%':>8}")
        ranked = sorted(out["towers"].items(),
                        key=lambda kv: (-kv[1]["volume"] * (100 - kv[1]["ftr_pct"])))
        for t, m in ranked:
            log(f"  {t:<26}{m['volume']:>8}{m['ftr_pct']:>7.1f}%{m['escalation_pct']:>7.1f}%"
                f"{m['sla_pct']:>7.1f}%")
        log(f"\n  -> recommended pilot tower: {ranked[0][0]}")

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
        log(f"\nwritten to {args.json}")


if __name__ == "__main__":
    main()
