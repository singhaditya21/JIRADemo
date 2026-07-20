#!/usr/bin/env python3
"""Measure the six scoreboard metrics from live Jira data.

This is the script that replaces invented targets with measured ones. Run it before
the pilot to establish a baseline, then weekly during the pilot to see movement.

Every window is computed against `Reported At`, not `created` - see SCHEMA.md.

Usage:  python3 -m app.cli metrics --project OPS [--days 90] [--by-tower] [--json out.json]
"""

import argparse
import json
import os
from pathlib import Path

from shared.jira_client import Jira, log, require_env, warn
from shared import domain as D
from shared import fields as FIELDS


def count(j, jql):
    return j.post("/rest/api/3/search/approximate-count", {"jql": jql}).get("count", 0)


def pct(n, d):
    return (100.0 * n / d) if d else 0.0


def measure(j, project, F, window, scope=""):
    """scope is an extra JQL clause, e.g. ' AND "Tower" = "Database"'.

    Field names go through F.jql() rather than being written out by hand. For an
    unambiguous field that returns the quoted name and the JQL reads exactly as
    before; for a field whose display name is duplicated on the instance it
    returns cf[id], because Jira's tie-break between two identically named fields
    is undocumented. Hand-writing a field name here would silently reintroduce
    that ambiguity into the one place it is hardest to notice - a count that is
    wrong but plausible.
    """
    base = f'project = {project}{scope} AND {F.jql("Reported At")} >= -{window}d'
    m = {}

    m["volume"] = count(j, base)

    # First-time resolution: finished, never left L1. Problems are excluded because
    # they are investigations by definition and would drag FTR down for doing the
    # right thing.
    done = f'{base} AND statusCategory = Done AND issuetype != Problem'
    m["closed"] = count(j, done)
    m["ftr"] = count(j, f'{done} AND {F.jql("Support Tier")} = L1')
    m["ftr_pct"] = pct(m["ftr"], m["closed"])

    m["escalated"] = count(j, f'{base} AND {F.jql("Support Tier")} = L2')
    m["escalation_pct"] = pct(m["escalated"], m["volume"])

    m["reopened"] = count(j, f'{base} AND {F.jql("Reopened")} = Yes')
    m["reopen_pct"] = pct(m["reopened"], m["closed"])

    met = count(j, f'{base} AND {F.jql("Resolution SLA")} = Met')
    breached = count(j, f'{base} AND {F.jql("Resolution SLA")} = Breached')
    m["sla_met"], m["sla_breached"] = met, breached
    m["sla_pct"] = pct(met, met + breached)

    resp_met = count(j, f'{base} AND {F.jql("Response SLA")} = Met')
    resp_br = count(j, f'{base} AND {F.jql("Response SLA")} = Breached')
    m["response_pct"] = pct(resp_met, resp_met + resp_br)

    m["aged_14d"] = count(j, f'project = {project}{scope} AND statusCategory != Done '
                             f'AND {F.jql("Reported At")} <= -14d')
    m["open"] = count(j, f'project = {project}{scope} AND statusCategory != Done')

    # The KB gap is the lever that lifts L1's ceiling over time.
    m["kb_gap"] = count(j, f'{base} AND {F.jql("KB Article Checked")} = "Yes - none found"')
    m["kb_gap_pct"] = pct(m["kb_gap"], m["escalated"])

    m["shadow_chat"] = count(j, f'{base} AND {F.jql("Intake Channel")} = Chat')
    return m


def verdict(key, value):
    if key not in D.SCORECARD_TARGETS:
        return ""
    target, direction = D.SCORECARD_TARGETS[key]
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


def add_arguments(ap):
    # The project key is an ARGUMENT, not a constant. app/ cannot import
    # jira_config.jira_schema, and that is the point: this script has to run
    # against OPS, ITSM or a fresh instance without knowing which one it is.
    ap.add_argument("--project", default=os.environ.get("JIRA_PROJECT"),
                    help="Jira project key, e.g. OPS or ITSM (or set JIRA_PROJECT)")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--by-tower", action="store_true")
    ap.add_argument("--json", type=str)
    return ap


def run(args):
    if not args.project:
        raise SystemExit("--project is required (or set JIRA_PROJECT)")

    require_env()
    j = Jira()

    # Resolve the schema by NAME before measuring anything. This script reads no
    # build artifact and never did, but it used to query field names in JQL with
    # no validation at all - against an instance missing a field, every count that
    # depended on it came back 0 and the report looked merely disappointing rather
    # than broken. Now it fails here, with the field named.
    F = FIELDS.resolve(j)
    for w in F.warnings():
        warn("  ! " + w)

    log(f"Baseline for {args.project} over the last {args.days} days, "
        f"measured on 'Reported At'.")
    log("Targets are PLACEHOLDERS (CLAIMS.md #15) - replace them with a target set")
    log("from this baseline once it reflects a real organisation.")

    out = {"project": args.project, "window_days": args.days,
           "overall": measure(j, args.project, F, args.days)}
    report(f"{args.project} ALL TOWERS - last {args.days}d", out["overall"])

    if args.by_tower:
        out["towers"] = {}
        for tower, _ in D.TOWERS:
            m = measure(j, args.project, F, args.days,
                        f' AND {F.jql("Tower")} = "{tower}"')
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


def main(argv=None):
    ap = add_arguments(argparse.ArgumentParser(prog="app.cli metrics"))
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
