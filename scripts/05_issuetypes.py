#!/usr/bin/env python3
"""Create the four ITSM issue types and bind them to OPS via an issue type scheme.

Four types, not more. Every extra issue type multiplies workflow, screen and report
maintenance, and ITIL's full catalogue buys nothing a six-tower shop can use.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
SCHEME_NAME = "OPS Issue Type Scheme"


def ensure_types(j):
    have = {t["name"]: t["id"] for t in j.get("/rest/api/3/issuetype")}
    ids = {}
    for name, desc, level in C.ISSUE_TYPES:
        if name in have:
            ids[name] = have[name]
            log(f"  = {name:<18} {have[name]}")
            continue
        res = j.post("/rest/api/3/issuetype",
                     {"name": name, "description": desc, "type": "standard"})
        ids[name] = res["id"]
        log(f"  + {name:<18} {res['id']}")
    return ids


def ensure_scheme(j, type_ids, project_id):
    schemes = j.get("/rest/api/3/issuetypescheme?maxResults=100").get("values", [])
    hit = [s for s in schemes if s["name"] == SCHEME_NAME]
    order = [type_ids[n] for n, _, _ in C.ISSUE_TYPES]

    if hit:
        sid = hit[0]["id"]
        log(f"  = scheme exists ({sid})")
        try:
            j.put(f"/rest/api/3/issuetypescheme/{sid}",
                  {"name": SCHEME_NAME, "defaultIssueTypeId": order[0]})
        except RuntimeError:
            pass
    else:
        res = j.post("/rest/api/3/issuetypescheme", {
            "name": SCHEME_NAME,
            "description": "Incident, Service Request, Change, Problem.",
            "defaultIssueTypeId": order[0],
            "issueTypeIds": order,
        })
        sid = res["issueTypeSchemeId"]
        log(f"  + scheme created ({sid})")

    # Ensure every type is a member (idempotent re-add is rejected, so ignore failures)
    try:
        j.put(f"/rest/api/3/issuetypescheme/{sid}/issuetype", {"issueTypeIds": order})
    except RuntimeError as e:
        log(f"    membership: {str(e)[:110]}")

    try:
        j.put("/rest/api/3/issuetypescheme/project",
              {"issueTypeSchemeId": str(sid), "projectId": str(project_id)})
        log("  scheme bound to OPS")
    except RuntimeError as e:
        log(f"  ! bind failed: {str(e)[:220]}")
    return sid


def main():
    require_env()
    j = Jira()
    state = json.loads(STATE.read_text())

    log("== issue types ==")
    type_ids = ensure_types(j)
    state["issue_types"] = type_ids

    log("== issue type scheme ==")
    state["issue_type_scheme_id"] = ensure_scheme(j, type_ids, state["project_id"])

    log("== verify on project ==")
    for it in j.get(f"/rest/api/3/project/{C.PROJECT_KEY}/statuses"):
        log(f"  {it['name']:<18} {len(it['statuses'])} statuses")

    STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
