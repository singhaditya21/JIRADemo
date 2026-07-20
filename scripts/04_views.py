#!/usr/bin/env python3
"""Create saved filters and a dashboard for the OPS tower.

These stand in for JSM agent queues, which need Service Management. Every filter
keys off `Reported At` rather than `created`, because the seeded history lives there.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
P = C.PROJECT_KEY

FILTERS = [
    ("OPS - L1 queue (open)",
     f'project = {P} AND "Support Tier" = L1 AND statusCategory != Done ORDER BY priority DESC',
     "Everything sitting at L1 and not finished."),
    ("OPS - L2 queue (open)",
     f'project = {P} AND "Support Tier" = L2 AND statusCategory != Done ORDER BY priority DESC',
     "Escalated work in flight, across all towers."),
    ("OPS - Major incidents (Impact High + Urgency High)",
     f'project = {P} AND Impact = High AND Urgency = High ORDER BY "Reported At" DESC',
     "The P1 war-room view. Priority is derived, so this is the real definition."),
    ("OPS - SLA breached (resolution)",
     f'project = {P} AND "Resolution SLA" = Breached ORDER BY "Reported At" DESC',
     "Resolution target missed. Attainment reporting starts here."),
    ("OPS - SLA paused (waiting on customer or vendor)",
     f'project = {P} AND status IN ("Pending Customer", "Pending Vendor") ORDER BY "Reported At" ASC',
     "Ball is not in our court. Excluded from attainment - this is what makes the report trustworthy."),
    ("OPS - Aged backlog over 14 days",
     f'project = {P} AND statusCategory != Done AND "Reported At" <= -14d ORDER BY "Reported At" ASC',
     "What is quietly rotting."),
    ("OPS - Reopened tickets",
     f'project = {P} AND Reopened = Yes ORDER BY "Reported At" DESC',
     "Paired with first-time resolution - closing early to flatter FTR shows up here."),
    ("OPS - Escalated in last 30 days",
     f'project = {P} AND "Support Tier" = L2 AND "Reported At" >= -30d ORDER BY "Reported At" DESC',
     "Feeds escalation rate per analyst and per tower."),
    ("OPS - Escalated with no KB article found",
     f'project = {P} AND "KB Article Checked" = "Yes - none found" ORDER BY "Reported At" DESC',
     "Every row is a candidate knowledge-base article. This is the loop that lifts L1's ceiling."),
    ("OPS - Intake via chat (shadow support pulled in)",
     f'project = {P} AND "Intake Channel" = Chat ORDER BY "Reported At" DESC',
     "Demand that would otherwise be invisible. See PROBLEM.md 3.6."),
]

# One L2 queue per tower. This is the JSM agent-queue equivalent: escalated work
# lands in the tower's pool rather than on a named person, which is what the
# escalation post-function is for.
for _tower, _ in C.TOWERS:
    FILTERS.append((
        f"OPS - L2 queue: {_tower}",
        f'project = {P} AND "Support Tier" = L2 AND Tower = "{_tower}" '
        f'AND statusCategory != Done ORDER BY priority DESC, "Reported At" ASC',
        f"Escalated {_tower} work awaiting or in progress at L2.",
    ))

# SLA at-risk: past 75% of the resolution target and still not done. Approximated
# against Reported At because the native SLA engine needs Service Management.
_PRIORITY_NAME = {"P1": "P1 - Critical", "P2": "P2 - High",
                  "P3": "P3 - Medium", "P4": "P4 - Low"}
for _p, (_resp, _res) in C.SLA_TARGETS.items():
    _threshold = int(_res * 0.75)
    FILTERS.append((
        f"OPS - {_p} at risk (past 75% of target)",
        f'project = {P} AND priority = "{_PRIORITY_NAME[_p]}" AND statusCategory != Done '
        f'AND status NOT IN ("Pending Customer", "Pending Vendor") '
        f'AND "Reported At" <= -{_threshold}h ORDER BY "Reported At" ASC',
        f"{_p} tickets past {_threshold}h of a {_res}h resolution target, clock still running.",
    ))

GADGETS = [
    ("OPS - L1 queue (open)", "filter-results"),
    ("OPS - SLA breached (resolution)", "filter-results"),
    ("OPS - Aged backlog over 14 days", "filter-results"),
]


def ensure_filter(j, name, jql, desc, existing):
    if name in existing:
        fid = existing[name]
        try:
            j.put(f"/rest/api/3/filter/{fid}",
                  {"name": name, "jql": jql, "description": desc})
        except RuntimeError:
            pass
        return fid, False
    res = j.post("/rest/api/3/filter",
                 {"name": name, "jql": jql, "description": desc,
                  "favourite": True,
                  "sharePermissions": [{"type": "authenticated"}]})
    return res["id"], True


def main():
    require_env()
    j = Jira()
    state = json.loads(STATE.read_text())

    existing = {}
    page = j.try_get("/rest/api/3/filter/search?maxResults=100&expand=jql", {}) or {}
    for f in page.get("values", []):
        existing[f["name"]] = f["id"]

    log("== filters ==")
    ids = {}
    for name, jql, desc in FILTERS:
        try:
            fid, is_new = ensure_filter(j, name, jql, desc, existing)
            ids[name] = fid
            log(f"  {'+' if is_new else '='} {name}")
        except RuntimeError as e:
            log(f"  ! {name}: {str(e)[:150]}")
    state["filters"] = ids

    log("== dashboard ==")
    dash_name = "OPS - L1/L2 Tower"
    dashes = j.try_get("/rest/api/3/dashboard/search?maxResults=50", {}) or {}
    hit = [d for d in dashes.get("values", []) if d["name"] == dash_name]
    if hit:
        did = hit[0]["id"]
        log(f"  = dashboard exists ({did})")
    else:
        d = j.post("/rest/api/3/dashboard",
                   {"name": dash_name,
                    "description": "L1/L2 tower operating view. All dates key off Reported At.",
                    "sharePermissions": [{"type": "authenticated"}]})
        did = d["id"]
        log(f"  + dashboard created ({did})")
    state["dashboard_id"] = did

    for fname, _ in GADGETS:
        if fname not in ids:
            continue
        try:
            j.post(f"/rest/api/3/dashboard/{did}/gadget", {
                "uri": "rest/gadgets/1.0/g/com.atlassian.jira.gadgets:filter-results-gadget/"
                       "gadgets/filter-results-gadget.xml",
                "color": "blue",
                "position": {"row": GADGETS.index((fname, "filter-results")), "column": 0},
            })
            log(f"  + gadget: {fname}")
        except RuntimeError as e:
            log(f"  ! gadget {fname}: {str(e)[:120]}")

    STATE.write_text(json.dumps(state, indent=2))
    site = j.site
    log(f"\n  Project:   {site}/browse/{P}")
    log(f"  Dashboard: {site}/jira/dashboards/{did}")


if __name__ == "__main__":
    main()
