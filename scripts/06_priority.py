#!/usr/bin/env python3
"""Create P1-P4 priorities and bind them to OPS via a priority scheme.

Jira ships Highest/High/Medium/Low/Lowest, which carry no agreed meaning and invite
exactly the negotiation the Impact x Urgency matrix exists to prevent. P1-P4 are
contractual terms with SLA targets attached, so the project gets its own scheme.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
SCHEME = "OPS Priority Scheme"

SPECS = [
    ("P1 - Critical", "Business stopped or major incident", "#B3352A", "highest"),
    ("P2 - High", "Severe degradation, workaround limited", "#96610C", "high"),
    ("P3 - Medium", "Standard fault or request", "#3B5057", "medium"),
    ("P4 - Low", "Minor, no business impact", "#64787E", "low"),
]


def main():
    require_env()
    j = Jira()
    state = json.loads(STATE.read_text())

    log("== priorities ==")
    have = {p["name"]: p["id"] for p in j.get("/rest/api/3/priority")}
    ids = {}
    for name, desc, color, icon in SPECS:
        if name in have:
            ids[name] = have[name]
            log(f"  = {name:<16} {have[name]}")
            continue
        r = j.post("/rest/api/3/priority", {
            "name": name, "description": desc, "statusColor": color,
            "iconUrl": f"/images/icons/priorities/{icon}.svg"})
        ids[name] = r["id"]
        log(f"  + {name:<16} {r['id']}")
    state["priorities"] = ids

    log("== priority scheme ==")
    order = [ids[n] for n, _, _, _ in SPECS]
    schemes = j.try_get("/rest/api/3/priorityscheme?maxResults=50", {}) or {}
    hit = [s for s in schemes.get("values", []) if s["name"] == SCHEME]
    if hit:
        sid = hit[0]["id"]
        log(f"  = scheme exists ({sid})")
        try:
            j.put(f"/rest/api/3/priorityscheme/{sid}",
                  {"projects": {"add": [str(state["project_id"])]}})
            log("  project association refreshed")
        except RuntimeError as e:
            log(f"  ! associate: {str(e)[:180]}")
    else:
        try:
            r = j.post("/rest/api/3/priorityscheme", {
                "name": SCHEME,
                "description": "P1-P4 with SLA targets attached.",
                "defaultPriorityId": int(ids["P3 - Medium"]),
                "priorityIds": [int(x) for x in order],
                "projectIds": [int(state["project_id"])],
                # Jira requires a landing place for any issue still on a built-in
                # priority before it will remove them from the project's scheme.
                "mappings": {"in": {
                    "1": int(ids["P1 - Critical"]),   # Highest
                    "2": int(ids["P2 - High"]),       # High
                    "3": int(ids["P3 - Medium"]),     # Medium
                    "4": int(ids["P4 - Low"]),        # Low
                    "5": int(ids["P4 - Low"]),        # Lowest
                }},
            })
            sid = r.get("id")
            log(f"  + scheme created ({sid})")
        except RuntimeError as e:
            sid = None
            log(f"  ! scheme creation failed: {str(e)[:260]}")
    state["priority_scheme_id"] = sid

    log("== verify on project ==")
    meta = j.get(f"/rest/api/3/issue/createmeta?projectKeys={C.PROJECT_KEY}"
                 f"&expand=projects.issuetypes.fields")
    for p in meta.get("projects", []):
        for it in p.get("issuetypes", [])[:1]:
            pf = it.get("fields", {}).get("priority", {})
            log(f"  allowed: {[a['name'] for a in pf.get('allowedValues', [])]}")

    STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
