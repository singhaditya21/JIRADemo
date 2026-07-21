#!/usr/bin/env python3
"""Add the escalation path to the ITSM Incident and Problem workflows.

The defect (CLAIMS #49): `Escalated to L2` exists in no ITSM workflow, so an ITSM
Incident carrying `Support Tier = L2` has a history that contradicts its own field.
This weaves the same escalation path OPS has into the two JSM-generated workflows,
using the rule keys proven on OPS:

  gate validator      system:validate-field-value  (ruleType: fieldRequired)
  fast-path restrict   system:restrict-issue-transition  (roleIds)

It ADDS only - every existing status, transition, screen and property is preserved.
It is idempotent: a second run detects the escalation transition already present and
does nothing. It validates against /workflows/update/validation before applying, and
carries the workflow version for optimistic locking so a concurrent edit fails loudly.

Historical ITSM tickets keep their old history; re-run fixtures.jsm_seed to make the
seeded population flow through the new path.

Usage:  python3 -m jira_config.jsm_workflow [--dry-run] [--only incident|problem]
"""

import argparse
import json
import uuid

from shared.jira_client import Jira, log, require_env
from jira_config import read_state, BUILD_STATE

# Stable per-status UUID: the update API (like create, CLAIMS #8c) requires
# statusReference to be a UUID, with the numeric status id supplied alongside as `id`.
_NS = uuid.UUID("7a2c1b90-3e4d-4a5f-8b6c-000000000002")


def sref(status_id):
    return str(uuid.uuid5(_NS, str(status_id)))

GATE_FIELDS = ["Escalation Reason", "Troubleshooting Performed", "KB Article Checked"]
MIM_ROLE_NAME = "Major Incident Manager"
ESCALATED = "Escalated to L2"          # global status, id in build state
WIP_CANDIDATES = ["Work in progress", "Under investigation", "Investigating",
                  "In Progress"]

TARGETS = [
    ("incident", "ITSM: Incident Management workflow for Jira Service Management"),
    ("problem", "ITSM: Problem Management workflow for Jira Service Management"),
]


def find_workflow(j, name):
    r = j.get("/rest/api/3/workflow/search?maxResults=100")
    for w in r["values"]:
        if w["id"]["name"] == name:
            return w["id"]["entityId"]
    return None


def read_workflow(j, entity_id):
    return j.post("/rest/api/3/workflows", {"workflowIds": [entity_id]})["workflows"][0]


def status_catalog(j):
    """id -> {name, statusCategory} for building the update's top-level statuses."""
    page = j.get("/rest/api/3/statuses/search?maxResults=200")
    return {v["id"]: {"name": v["name"], "statusCategory": v["statusCategory"]}
            for v in page["values"]}


def build_update(wf, esc_id, wip_ref, field_ids, mim_role_id):
    """Return an updated copy of wf with the escalation path added, or None if present."""
    names = {t["name"] for t in wf["transitions"]}
    if "Escalate to L2" in names:
        return None  # idempotent

    ids = ",".join(field_ids[f] for f in GATE_FIELDS if f in field_ids)
    max_id = max((int(t["id"]) for t in wf["transitions"] if t["id"].isdigit()), default=200)

    # Rewrite every existing status/transition reference from numeric id to UUID.
    existing_ids = [s["statusReference"] for s in wf["statuses"]]
    statuses = []
    for s in wf["statuses"]:
        s2 = dict(s)
        s2["statusReference"] = sref(s["statusReference"])
        statuses.append(s2)
    if esc_id not in existing_ids:
        statuses.append({"statusReference": sref(esc_id),
                         "layout": {"x": 350.0, "y": 200.0}, "properties": {}})

    transitions = []
    for t in wf["transitions"]:
        t2 = json.loads(json.dumps(t))  # deep copy
        if t2.get("toStatusReference"):
            t2["toStatusReference"] = sref(t2["toStatusReference"])
        for lk in (t2.get("links") or []):
            if lk.get("fromStatusReference"):
                lk["fromStatusReference"] = sref(lk["fromStatusReference"])
        transitions.append(t2)

    def transition(tid, name, frm, to, validators=None, conditions=None):
        t = {"id": str(tid), "type": "DIRECTED", "toStatusReference": sref(to),
             "links": [{"fromStatusReference": sref(frm), "fromPort": 0, "toPort": 0}],
             "name": name, "description": "", "actions": [], "triggers": [],
             "validators": validators or [], "properties": {}}
        if conditions:
            t["conditions"] = conditions
        return t

    gate = [{"ruleKey": "system:validate-field-value",
             "parameters": {"ruleType": "fieldRequired", "fieldsRequired": ids,
                            "ignoreContext": "false",
                            "errorMessage": ("Record what you tried before escalating "
                                             "to L2.")}}]
    restrict = {"operation": "ALL", "conditionGroups": [],
                "conditions": [{"ruleKey": "system:restrict-issue-transition",
                                "parameters": {"accountIds": "", "roleIds": str(mim_role_id),
                                               "groupIds": "", "permissionKeys": "",
                                               "groupCustomFields": "",
                                               "allowUserCustomFields": "",
                                               "denyUserCustomFields": ""}}]}

    new_transitions = [
        transition(max_id + 1, "Escalate to L2", wip_ref, esc_id, validators=gate),
        transition(max_id + 2, "Escalate - major incident", wip_ref, esc_id,
                   conditions=restrict if mim_role_id else None),
        transition(max_id + 3, "Accept at L2", esc_id, wip_ref),
    ]
    transitions += new_transitions

    # let an escalated ticket be resolved: extend the existing Resolve transition
    esc_uuid = sref(esc_id)
    for t in transitions:
        if t["name"] == "Resolve":
            if not any(l["fromStatusReference"] == esc_uuid for l in t["links"]):
                t["links"].append({"fromStatusReference": esc_uuid, "fromPort": 0, "toPort": 0})

    return {"id": wf["id"], "version": wf["version"], "name": wf["name"],
            "description": wf.get("description", ""),
            "startPointLayout": wf.get("startPointLayout"),
            "statuses": statuses, "transitions": transitions,
            "_status_ids": existing_ids + ([esc_id] if esc_id not in existing_ids else [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["incident", "problem"])
    args = ap.parse_args()

    require_env()
    j = Jira()
    state = read_state(BUILD_STATE)
    esc_id = state["statuses"][ESCALATED]
    field_ids = state["fields"]
    roles = j.get("/rest/api/3/role")
    mim = next((r["id"] for r in roles if r["name"] == MIM_ROLE_NAME), None)
    log(f"  Escalated status id={esc_id}  MIM role id={mim}")
    catalog = status_catalog(j)
    names = {sid: v["name"] for sid, v in catalog.items()}

    for key, wfname in TARGETS:
        if args.only and args.only != key:
            continue
        log(f"\n== {key}: {wfname} ==")
        eid = find_workflow(j, wfname)
        if not eid:
            log("  ! workflow not found")
            continue
        wf = read_workflow(j, eid)

        wip_ref = None
        for s in wf["statuses"]:
            if names.get(s["statusReference"]) in WIP_CANDIDATES:
                wip_ref = s["statusReference"]
                break
        if not wip_ref:
            log(f"  ! no in-progress status found among "
                f"{[names.get(s['statusReference']) for s in wf['statuses']]}")
            continue
        log(f"  in-progress status: {names.get(wip_ref)} ({wip_ref})")

        update = build_update(wf, esc_id, wip_ref, field_ids, mim)
        if update is None:
            log("  = escalation path already present, nothing to do")
            continue

        # every status the workflow references must be defined at the top level, by UUID
        # reference with the numeric id supplied so Jira binds to the existing global status
        status_ids = update.pop("_status_ids")
        top_statuses = [{"statusReference": sref(sid), "id": sid,
                         "name": catalog[sid]["name"],
                         "statusCategory": catalog[sid]["statusCategory"]}
                        for sid in status_ids if sid in catalog]
        payload = {"statuses": top_statuses, "workflows": [update]}
        # validate first, always. The validation endpoint wraps the update in `payload`.
        val = j.post("/rest/api/3/workflows/update/validation", {"payload": payload})
        errs = (val.get("errors") if isinstance(val, dict) else None) or []
        if errs:
            log(f"  ! validation errors: {json.dumps(errs)[:500]}")
            continue
        log("  validation: OK")

        if args.dry_run:
            log("  [dry] would add: Escalate to L2 (gate), "
                "Escalate - major incident (role), Accept at L2; extend Resolve")
            continue

        res = j.post("/rest/api/3/workflows/update", payload)
        log(f"  updated workflow version -> "
            f"{res['workflows'][0]['version']['versionNumber'] if res.get('workflows') else '?'}")

        # verify the gate landed
        back = read_workflow(j, eid)
        gate_t = next((t for t in back["transitions"] if t["name"] == "Escalate to L2"), None)
        rk = (gate_t.get("validators") or [{}])[0].get("ruleKey") if gate_t else None
        log(f"  verify: Escalate to L2 present={bool(gate_t)} validator={rk}")


if __name__ == "__main__":
    main()
