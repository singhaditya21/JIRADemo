#!/usr/bin/env python3
"""Create the four ITSM issue types and bind them to OPS via an issue type scheme.

Four types, not more. Every extra issue type multiplies workflow, screen and report
maintenance, and ITIL's full catalogue buys nothing a six-tower shop can use.

Usage:  python3 -m jira_config.issuetypes [--dry-run]
"""

import argparse
import sys

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config import merge_state, read_state
from jira_config.reconcile import Writer

OWNED_KEYS = ("issue_types", "issue_type_scheme_id")


def ensure_types(w):
    have = {t["name"]: t["id"] for t in w.j.get("/rest/api/3/issuetype")}
    ids = {}
    for name, desc, level in D.ISSUE_TYPES:
        if name in have:
            ids[name] = have[name]
            log(f"  = {name:<18} {have[name]}")
            continue
        # `level` is the domain's declared hierarchy level. It used to be unpacked
        # and then ignored in favour of a hardcoded "standard", so a future
        # ("Sub-task", ..., "subtask") entry would have been created silently as a
        # standard type - an expensive thing to unwind on a live instance.
        res = w.post("/rest/api/3/issuetype",
                     {"name": name, "description": desc, "type": level})
        ids[name] = res["id"]
        log(f"  + {name:<18} {res['id']}")
    return ids


def ensure_scheme(w, type_ids, project_id):
    j = w.j
    schemes = j.get("/rest/api/3/issuetypescheme?maxResults=100").get("values", [])
    hit = [s for s in schemes if s["name"] == S.ISSUE_TYPE_SCHEME_NAME]
    order = [type_ids[n] for n, _, _ in D.ISSUE_TYPES]

    if hit:
        sid = hit[0]["id"]
        log(f"  = scheme exists ({sid})")
        try:
            w.put(f"/rest/api/3/issuetypescheme/{sid}",
                  {"name": S.ISSUE_TYPE_SCHEME_NAME, "defaultIssueTypeId": order[0]})
        except RuntimeError:
            pass
    else:
        res = w.post("/rest/api/3/issuetypescheme", {
            "name": S.ISSUE_TYPE_SCHEME_NAME,
            "description": "Incident, Service Request, Change, Problem.",
            "defaultIssueTypeId": order[0],
            "issueTypeIds": order,
        })
        sid = res.get("issueTypeSchemeId") or res.get("id")
        log(f"  + scheme created ({sid})")

    # Ensure every type is a member (idempotent re-add is rejected, so ignore failures)
    try:
        w.put(f"/rest/api/3/issuetypescheme/{sid}/issuetype", {"issueTypeIds": order})
    except RuntimeError as e:
        log(f"    membership: {str(e)[:110]}")

    try:
        w.put("/rest/api/3/issuetypescheme/project",
              {"issueTypeSchemeId": str(sid), "projectId": str(project_id)})
        log("  scheme bound to OPS")
    except RuntimeError as e:
        log(f"  ! bind failed: {str(e)[:220]}")
    return sid


def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(
        argparse.ArgumentParser(prog="jira_config.issuetypes")).parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    if not STATE.exists():
        sys.exit("%s missing - run python3 -m jira_config.build first." % STATE.name)
    state = read_state(STATE)

    log("== issue types ==")
    type_ids = ensure_types(w)
    state["issue_types"] = type_ids

    log("== issue type scheme ==")
    state["issue_type_scheme_id"] = ensure_scheme(w, type_ids, state["project_id"])

    log("== verify on project ==")
    for it in j.get(f"/rest/api/3/project/{S.PROJECT_KEY}/statuses"):
        log(f"  {it['name']:<18} {len(it['statuses'])} statuses")

    merge_state(STATE, state, OWNED_KEYS, dry=args.dry_run)
    log("\n%d writes%s" % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
