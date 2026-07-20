#!/usr/bin/env python3
"""Create P1-P4 priorities and bind them to OPS via a priority scheme.

Jira ships Highest/High/Medium/Low/Lowest, which carry no agreed meaning and invite
exactly the negotiation the Impact x Urgency matrix exists to prevent. P1-P4 are
contractual terms with SLA targets attached, so the project gets its own scheme.

Usage:  python3 -m jira_config.priority [--dry-run]
"""

import argparse
import sys

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config import merge_state, read_state
from jira_config.reconcile import Writer

OWNED_KEYS = ("priorities", "priority_scheme_id")


def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(
        argparse.ArgumentParser(prog="jira_config.priority")).parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    if not STATE.exists():
        sys.exit("%s missing - run python3 -m jira_config.build first." % STATE.name)
    state = read_state(STATE)

    log("== priorities ==")
    have = {p["name"]: p["id"] for p in j.get("/rest/api/3/priority")}
    ids = {}
    for name, desc, color, icon in S.PRIORITY_SPECS:
        if name in have:
            ids[name] = have[name]
            log(f"  = {name:<16} {have[name]}")
            continue
        r = w.post("/rest/api/3/priority", {
            "name": name, "description": desc, "statusColor": color,
            "iconUrl": f"/images/icons/priorities/{icon}.svg"})
        ids[name] = r["id"]
        log(f"  + {name:<16} {r['id']}")
    state["priorities"] = ids

    log("== priority scheme ==")
    order = [ids[n] for n, _, _, _ in S.PRIORITY_SPECS]
    schemes = j.try_get("/rest/api/3/priorityscheme?maxResults=50", {}) or {}
    hit = [s for s in schemes.get("values", []) if s["name"] == S.PRIORITY_SCHEME_NAME]
    if hit:
        sid = hit[0]["id"]
        log(f"  = scheme exists ({sid})")
        try:
            w.put(f"/rest/api/3/priorityscheme/{sid}",
                  {"projects": {"add": [str(state["project_id"])]}})
            log("  project association refreshed")
        except RuntimeError as e:
            log(f"  ! associate: {str(e)[:180]}")
    elif w.dry and not all(str(v).isdigit() for v in order):
        # The scheme body casts every priority id to int. On a dry run against an
        # instance where the priorities do not exist yet, those ids are Writer
        # placeholders, so building the body would raise ValueError and abort the
        # rehearsal. Report the plan instead of crashing on fictional ids.
        sid = None
        log("      [dry] POST /rest/api/3/priorityscheme "
            "(deferred - needs the real priority ids created above)")
    else:
        try:
            r = w.post("/rest/api/3/priorityscheme", {
                "name": S.PRIORITY_SCHEME_NAME,
                "description": "P1-P4 with SLA targets attached.",
                "defaultPriorityId": int(ids[D.PRIORITY_LABELS["P3"]]),
                "priorityIds": [int(x) for x in order],
                "projectIds": [int(state["project_id"])],
                # Jira requires a landing place for any issue still on a built-in
                # priority before it will remove them from the project's scheme.
                "mappings": {"in": {
                    "1": int(ids[D.PRIORITY_LABELS["P1"]]),   # Highest
                    "2": int(ids[D.PRIORITY_LABELS["P2"]]),       # High
                    "3": int(ids[D.PRIORITY_LABELS["P3"]]),     # Medium
                    "4": int(ids[D.PRIORITY_LABELS["P4"]]),        # Low
                    "5": int(ids[D.PRIORITY_LABELS["P4"]]),        # Lowest
                }},
            })
            sid = r.get("id")
            log(f"  + scheme created ({sid})")
        except RuntimeError as e:
            sid = None
            log(f"  ! scheme creation failed: {str(e)[:260]}")
    state["priority_scheme_id"] = sid

    log("== verify on project ==")
    meta = j.get(f"/rest/api/3/issue/createmeta?projectKeys={S.PROJECT_KEY}"
                 f"&expand=projects.issuetypes.fields")
    for p in meta.get("projects", []):
        for it in p.get("issuetypes", [])[:1]:
            pf = it.get("fields", {}).get("priority", {})
            log(f"  allowed: {[a['name'] for a in pf.get('allowedValues', [])]}")

    merge_state(STATE, state, OWNED_KEYS, dry=args.dry_run)
    log("\n%d writes%s" % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
