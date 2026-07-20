#!/usr/bin/env python3
"""Create the 11 OPS statuses and attempt the full workflow with the escalation gate.

Status creation is well-supported. Workflow creation via the Cloud API is stricter,
so this attempts it once and reports honestly rather than pretending. If it fails the
seeder falls back to the statuses that do exist, and the workflow is built in the UI
from the transition table printed at the end.
"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"

CATEGORY = {"new": "TODO", "indeterminate": "IN_PROGRESS", "done": "DONE"}


def cleanup_probe(j):
    found = j.try_get("/rest/api/3/statuses/search?searchString=OPS%20Probe%20Status", {})
    for v in (found or {}).get("values", []):
        if v["name"] == "OPS Probe Status":
            try:
                j.delete(f"/rest/api/3/statuses?id={v['id']}")
                log(f"  removed probe status {v['id']}")
            except RuntimeError as e:
                log(f"  could not remove probe status: {e}")


def ensure_statuses(j):
    have = {}
    page = j.try_get("/rest/api/3/statuses/search?maxResults=200", {}) or {}
    for v in page.get("values", []):
        have[v["name"]] = v["id"]

    ids, to_create = {}, []
    for name, cat in C.STATUSES:
        if name in have:
            ids[name] = have[name]
        else:
            to_create.append({"name": name, "statusCategory": CATEGORY[cat],
                              "description": f"OPS tower - {name}"})
    if to_create:
        res = j.post("/rest/api/3/statuses",
                     {"scope": {"type": "GLOBAL"}, "statuses": to_create})
        for s in res:
            ids[s["name"]] = s["id"]
    for name, _ in C.STATUSES:
        log(f"  {name:<20} {ids.get(name, 'MISSING')}")
    return ids


TRANSITIONS = [
    ("Create", "INITIAL", None, "New"),
    ("Begin triage", "DIRECTED", "New", "Triage"),
    ("Start L1 work", "DIRECTED", "Triage", "In Progress L1"),
    ("Escalate to L2", "DIRECTED", "In Progress L1", "Escalated to L2"),
    ("Escalate - major incident", "DIRECTED", "In Progress L1", "Escalated to L2"),
    ("Accept at L2", "DIRECTED", "Escalated to L2", "In Progress L2"),
    ("Refer to vendor", "DIRECTED", "In Progress L2", "L3 / Vendor"),
    ("Await customer", "GLOBAL", None, "Pending Customer"),
    ("Await vendor", "GLOBAL", None, "Pending Vendor"),
    ("Resolve", "GLOBAL", None, "Resolved"),
    ("Close", "DIRECTED", "Resolved", "Closed"),
    ("Reopen", "DIRECTED", "Resolved", "Triage"),
    ("Cancel", "GLOBAL", None, "Cancelled"),
]


NS = uuid.UUID("6f1e5d6c-0a4b-4f2e-9c3d-000000000001")


def sref(name):
    return str(uuid.uuid5(NS, name))


GATE_FIELDS = ["Escalation Reason", "Troubleshooting Performed", "KB Article Checked"]


def attempt_workflow(j, status_ids, field_ids):
    """One careful attempt. Returns True on success."""
    statuses = [{"statusReference": sref(n), "layout": {"x": (i % 4) * 220.0,
                 "y": (i // 4) * 140.0}} for i, (n, _) in enumerate(C.STATUSES)]

    transitions = []
    for idx, (name, ttype, frm, to) in enumerate(TRANSITIONS, start=1):
        t = {"id": str(idx), "name": name, "type": ttype,
             "toStatusReference": sref(to), "properties": {}}
        if ttype == "DIRECTED":
            t["links"] = [{"fromStatusReference": sref(frm),
                           "toPort": 0, "fromPort": 0}]
        # The escalation gate: three required fields, except on the major-incident path.
        if name == "Escalate to L2":
            ids = ",".join(field_ids[f] for f in GATE_FIELDS if f in field_ids)
            t["validators"] = [
                {"ruleKey": "system:field-required",
                 "parameters": {"fieldsRequired": ids, "ignoreContext": "true",
                                "errorMessage":
                                    "Record what you tried before escalating to L2."}}
            ]
        transitions.append(t)

    body = {
        "scope": {"type": "GLOBAL"},
        # `id` present => reference the existing global status instead of creating it
        "statuses": [
            {"statusReference": sref(n), "id": status_ids[n], "name": n,
             "statusCategory": CATEGORY[cat], "description": f"OPS tower - {n}"}
            for n, cat in C.STATUSES
        ],
        "workflows": [{
            "name": "OPS L1/L2 Support Workflow",
            "description": "L1/L2 tower with escalation gate and major-incident fast path.",
            "statuses": statuses,
            "transitions": transitions,
        }],
    }
    try:
        res = j.post("/rest/api/3/workflows/create", body)
        log(f"  workflow created: {[w['name'] for w in res.get('workflows', [])]}")
        return True
    except RuntimeError as e:
        log(f"  workflow creation FAILED\n    {str(e)[:400]}")
        return False


def main():
    require_env()
    j = Jira()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    log("== cleanup ==")
    cleanup_probe(j)

    log("== statuses ==")
    status_ids = ensure_statuses(j)
    state["statuses"] = status_ids

    log("== workflow ==")
    ok = attempt_workflow(j, status_ids, state.get('fields', {}))
    state["workflow_created"] = ok
    STATE.write_text(json.dumps(state, indent=2))

    if not ok:
        log("\n  Build this in the UI instead — transition table:")
        log(f"  {'TRANSITION':<28}{'FROM':<18}{'TO':<18}VALIDATORS")
        for name, ttype, frm, to in TRANSITIONS:
            v = "3 required fields" if name == "Escalate to L2" else (
                "none - MIM role only" if "major" in name else "-")
            log(f"  {name:<28}{(frm or ttype.lower()):<18}{to:<18}{v}")
    log("\nnext: python3 scripts/03_seed.py")


if __name__ == "__main__":
    main()
