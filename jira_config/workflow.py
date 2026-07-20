#!/usr/bin/env python3
"""Create the 11 OPS statuses and attempt the full workflow with the escalation gate.

Status creation is well-supported. Workflow creation via the Cloud API is stricter,
so this attempts it once and reports honestly rather than pretending. If it fails the
seeder falls back to the statuses that do exist, and the workflow is built in the UI
from the transition table printed at the end.

Usage:  python3 -m jira_config.workflow [--dry-run]

This module owns the `statuses` and `workflow_created` state keys and writes only
those; see jira_config.merge_state for why that matters.
"""

import argparse
import uuid

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config import merge_state, read_state
from jira_config.reconcile import Writer

OWNED_KEYS = ("statuses", "workflow_created")


def cleanup_probe(w):
    found = w.j.try_get("/rest/api/3/statuses/search?searchString=OPS%20Probe%20Status", {})
    for v in (found or {}).get("values", []):
        if v["name"] == "OPS Probe Status":
            try:
                w.delete(f"/rest/api/3/statuses?id={v['id']}")
                log(f"  removed probe status {v['id']}")
            except RuntimeError as e:
                log(f"  could not remove probe status: {e}")


def ensure_statuses(w):
    j = w.j
    have = {}
    page = j.try_get("/rest/api/3/statuses/search?maxResults=200", {}) or {}
    for v in page.get("values", []):
        have[v["name"]] = v["id"]

    ids, to_create = {}, []
    for name, cat in D.STATUSES:
        if name in have:
            ids[name] = have[name]
        else:
            to_create.append({"name": name, "statusCategory": S.STATUS_CATEGORY[cat],
                              "description": f"OPS tower - {name}"})
    if to_create:
        res = w.post("/rest/api/3/statuses",
                     {"scope": {"type": "GLOBAL"}, "statuses": to_create})
        # Under --dry-run the Writer returns a placeholder rather than a list of
        # created statuses; keep the names visible without inventing ids.
        for s in (res if isinstance(res, list) else []):
            ids[s["name"]] = s["id"]
    for name, _ in D.STATUSES:
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

# The role that may use the major-incident fast path. Resolved by name so the build
# works on any instance; None means the restriction is skipped with a warning.
MIM_ROLE_NAME = "Major Incident Manager"


def find_mim_role(w):
    """Resolve the Major Incident Manager project role id, or None."""
    # Writer wraps only the mutating verbs; reads go straight to the client so the
    # lookup still works under --dry-run.
    try:
        roles = w.j.get("/rest/api/3/role")
    except RuntimeError:
        return None
    for r in roles:
        if r.get("name") == MIM_ROLE_NAME:
            return r.get("id")
    return None


def attempt_workflow(w, status_ids, field_ids, mim_role_id=None):
    """One careful attempt. Returns True on success."""
    statuses = [{"statusReference": sref(n), "layout": {"x": (i % 4) * 220.0,
                 "y": (i // 4) * 140.0}} for i, (n, _) in enumerate(D.STATUSES)]

    transitions = []
    for idx, (name, ttype, frm, to) in enumerate(TRANSITIONS, start=1):
        t = {"id": str(idx), "name": name, "type": ttype,
             "toStatusReference": sref(to), "properties": {}}
        if ttype == "DIRECTED":
            t["links"] = [{"fromStatusReference": sref(frm),
                           "toPort": 0, "fromPort": 0}]
        # The escalation gate: three required fields, except on the major-incident path.
        #
        # The rule key here matters and cost a detour to find. `system:field-required`
        # is rejected with "Rule cannot be applied to this type or is unsupported",
        # which led to the wrong conclusion that validators were UI-only. The actual
        # key is `system:validate-field-value` with ruleType=fieldRequired - read back
        # off a validator built by hand in the workflow editor. Confirmed creatable
        # over REST.
        if name == "Escalate to L2":
            ids = ",".join(field_ids[f] for f in GATE_FIELDS if f in field_ids)
            t["validators"] = [
                {"ruleKey": "system:validate-field-value",
                 "parameters": {
                     "ruleType": "fieldRequired",
                     "fieldsRequired": ids,
                     "ignoreContext": "false",
                     "errorMessage": (
                         "Record what you tried before escalating to L2. If no KB "
                         "article covered this, say so - that gap becomes the next "
                         "article."),
                 }}
            ]

        # The major-incident fast path carries NO validators - gating a P1 trades
        # outage minutes for paperwork. It is restricted by ROLE instead, so the
        # bypass is a deliberate, accountable act rather than a free choice under
        # pressure. roleIds is resolved at build time from the project roles.
        if name == "Escalate - major incident" and mim_role_id:
            t["conditions"] = {
                "operation": "ALL",
                "conditionGroups": [],
                "conditions": [
                    {"ruleKey": "system:restrict-issue-transition",
                     "parameters": {"accountIds": "", "roleIds": str(mim_role_id),
                                    "groupIds": "", "permissionKeys": "",
                                    "groupCustomFields": "",
                                    "allowUserCustomFields": "",
                                    "denyUserCustomFields": ""}}
                ],
            }
        transitions.append(t)

    body = {
        "scope": {"type": "GLOBAL"},
        # `id` present => reference the existing global status instead of creating it
        "statuses": [
            {"statusReference": sref(n), "id": status_ids.get(n), "name": n,
             "statusCategory": S.STATUS_CATEGORY[cat], "description": f"OPS tower - {n}"}
            for n, cat in D.STATUSES
        ],
        "workflows": [{
            "name": "OPS L1/L2 Support Workflow",
            "description": "L1/L2 tower with escalation gate and major-incident fast path.",
            "statuses": statuses,
            "transitions": transitions,
        }],
    }
    try:
        res = w.post("/rest/api/3/workflows/create", body)
        if w.dry:
            log("  [dry] workflow creation not attempted")
            return None
        log(f"  workflow created: {[x['name'] for x in res.get('workflows', [])]}")
        return True
    except RuntimeError as e:
        log(f"  workflow creation FAILED\n    {str(e)[:400]}")
        return False


def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(
        argparse.ArgumentParser(prog="jira_config.workflow")).parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    state = read_state(STATE)

    log("== cleanup ==")
    cleanup_probe(w)

    log("== statuses ==")
    status_ids = ensure_statuses(w)
    state["statuses"] = status_ids

    log("== workflow ==")
    mim = find_mim_role(w)
    log(f"  major-incident role: {mim if mim else 'NOT FOUND - fast path left unrestricted'}")
    ok = attempt_workflow(w, status_ids, state.get('fields', {}), mim)
    # A dry run learns nothing about whether creation would succeed, so it must
    # not overwrite the recorded answer with a guess.
    if ok is not None:
        state["workflow_created"] = ok
    merge_state(STATE, state, OWNED_KEYS, dry=args.dry_run)
    log("\n%d writes%s" % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))

    if ok is False:
        log("\n  Build this in the UI instead — transition table:")
        log(f"  {'TRANSITION':<28}{'FROM':<18}{'TO':<18}VALIDATORS")
        for name, ttype, frm, to in TRANSITIONS:
            v = "3 required fields" if name == "Escalate to L2" else (
                "none - MIM role only" if "major" in name else "-")
            log(f"  {name:<28}{(frm or ttype.lower()):<18}{to:<18}{v}")
    log("\nnext: python3 -m fixtures.seed")


if __name__ == "__main__":
    main()
