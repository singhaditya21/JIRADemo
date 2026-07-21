#!/usr/bin/env python3
"""Create the seven automation rules over Jira's internal automation API.

Jira Cloud has no *public* automation-rule API (`/rest/api/3/automation/rules` -> 404),
but the Automation UI drives an internal one the token can reach:

    POST /gateway/api/automation/internal-api/jira/{cloudId}/pro/rest/{projectId}/rule

The catch: the create payload needs the *full* rule wrapper (ruleScope, ruleHome, actor,
writeAccessType, ...), not just the minimal envelope - a minimal body returns a useless
"systems are unavailable" 400. So this templates from a REAL rule captured out of the UI
(`schema/example-transition-edit.rule.json`, read back over the same API) and edits only
name / description / state / trigger / components.

How the component value schemas were obtained WITHOUT a working UI capture:
the Flows builder freezes the CDP-driven renderer on save, so click-through capture is
unreliable. Instead every component below was discovered by **empirical round-trip**: POST
a rule with a candidate `value`, GET it back, read the canonical shape the server
normalises to, then DELETE the probe. Confirmed shapes are documented in
`schema/component-schemas.md`. Two sub-shapes could not be pinned this way because they
resolve entities server-side (they 500 on every wrong guess): the field-changed trigger's
per-field scoping, and the outgoing-email recipient list. Where those were needed the rule
uses an equivalent verified construct instead (ANY_CHANGE + explicit value conditions for
priority derivation; an in-issue comment flag instead of an email for the major-incident
alert) - see the notes on each rule.

Idempotent: a rule whose name already exists is skipped. Run with --dry-run to preview.

    python3 automation/build_rules.py [--dry-run]
"""

import argparse
import base64
import copy
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

CLOUD_ID = "520438e0-67f8-4ad6-a730-1e078094903e"
PROJECT_ID = "10034"
PROJECT_ARI = f"ari:cloud:jira:{CLOUD_ID}:project/{PROJECT_ID}"
BASE = f"/gateway/api/automation/internal-api/jira/{CLOUD_ID}/pro/rest/{PROJECT_ID}"
TEMPLATE = Path(__file__).parent / "schema" / "example-transition-edit.rule.json"

SELECT = "com.atlassian.jira.plugin.system.customfieldtypes:select"
PRIORITY_FT = "priority"

# The Impact x Urgency -> Priority matrix, using the *exact* priority names on the
# instance (verified live: 'P1 - Critical' ... not 'P1'). Impact/Urgency options are
# High/Medium/Low, which is what the seeded tickets actually carry.
PRIORITY_MATRIX = {
    ("High", "High"): "P1 - Critical", ("High", "Medium"): "P2 - High",
    ("High", "Low"): "P3 - Medium", ("Medium", "High"): "P2 - High",
    ("Medium", "Medium"): "P3 - Medium", ("Medium", "Low"): "P3 - Medium",
    ("Low", "High"): "P3 - Medium", ("Low", "Medium"): "P3 - Medium",
    ("Low", "Low"): "P4 - Low",
}


# --- component builders (shapes verified by round-trip; see component-schemas.md) --------

def status_refs(*names):
    return [{"type": "NAME", "value": n} for n in names]


def edit_op(field, value, field_type=SELECT):
    return {"field": {"type": "NAME", "value": field}, "fieldType": field_type,
            "type": "SET", "value": {"type": "NAME", "value": value}}


def action_edit(pairs, field_type=SELECT):
    return {"component": "ACTION", "type": "jira.issue.edit",
            "value": {"operations": [edit_op(f, v, field_type) for f, v in pairs],
                      "advancedFields": None, "sendNotifications": False},
            "children": []}


def action_comment(text, once=False):
    return {"component": "ACTION", "type": "jira.issue.comment",
            "value": {"comment": text, "publicComment": False, "commentVisibility": None,
                      "sendNotifications": True, "addCommentOnce": once},
            "children": []}


def action_transition(to_status):
    return {"component": "ACTION", "type": "jira.issue.transition",
            "value": {"operations": [], "advancedFields": None, "sendNotifications": False,
                      "destinationStatus": {"type": "NAME", "value": to_status},
                      "transitionMatch": None},
            "children": []}


def condition_field(field, value, field_type=SELECT, compare=None):
    # A field-value condition. The compareValue reference differs by field type, and the
    # difference only bites when the rule is ENABLED (server-side validation):
    #   - select custom fields (Impact/Urgency): compareValue by NAME
    #   - the system Priority field:             compareValue by ID (see condition_priority)
    if compare is None:
        compare = {"type": "NAME", "value": value}
    return {"component": "CONDITION", "type": "jira.issue.condition",
            "value": {"selectedField": {"type": "NAME", "value": field},
                      "selectedFieldType": field_type, "comparison": "EQUALS",
                      "compareValue": compare},
            "children": []}


def condition_priority(priority_name):
    return condition_field("Priority", priority_name, field_type=PRIORITY_FT,
                           compare={"type": "ID", "value": _priority_id(priority_name)})


_PRIORITY_IDS = {}


def _priority_id(name):
    if not _PRIORITY_IDS:
        _, body = http("GET", "/rest/api/3/priority")
        for p in json.loads(body):
            _PRIORITY_IDS[p["name"]] = p["id"]
    return _PRIORITY_IDS[name]


def block(children):
    """An IF block: its children run only when the CONDITION children all match. Sibling
    blocks evaluate independently, so a list of blocks is a branch matrix."""
    return {"component": "CONDITION", "type": "jira.condition.container.block",
            "value": {}, "children": children}


def trigger_transitioned(from_status, to_status):
    return ("jira.issue.event.trigger:transitioned",
            {"eventFilters": [PROJECT_ARI], "fromStatus": from_status,
             "toStatus": to_status, "eventKey": "jira:issue_updated",
             "issueEvent": "issue_generic"})


def trigger_created():
    # eventKey/issueEvent must be populated or ENABLED validation rejects the trigger with
    # "Rule trigger value of 'null' is not valid" (DISABLED normalises them to null).
    return ("jira.issue.event.trigger:created",
            {"eventFilters": [PROJECT_ARI], "eventKey": "jira:issue_created",
             "issueEvent": "issue_created"})


def trigger_scheduled(cron, jql):
    # method must be "CRON" (not null) or ENABLED validation 500s.
    return ("jira.jql.scheduled",
            {"schedule": {"cronExpression": cron, "method": "CRON", "rate": 0,
                          "rateInterval": 0, "rRule": None},
             "jql": jql, "executionMode": "jql", "onlyUpdatedIssues": False})


def priority_matrix_blocks():
    blocks = []
    for (impact, urgency), priority in PRIORITY_MATRIX.items():
        blocks.append(block([
            condition_field("Impact", impact),
            condition_field("Urgency", urgency),
            action_edit([("Priority", priority)], field_type=PRIORITY_FT),
        ]))
    return blocks


# --- the seven rules ---------------------------------------------------------------------
# Each: {name, description, state, trigger:(type,value), components:[...]}.
# The first three already exist live (created earlier from the same template); they are
# listed here so this file is the single source, and skipped by name when they exist.
#
# ENABLE safety: the two scheduled rules mutate tickets on their next run. Their JQL is
# written to match ZERO of the freshly-seeded rows (everything was `updated` today, so
# `updated <= -Nd` selects nothing now) while still being correct going forward. So the
# seeded demo snapshot is preserved on enable, per the design decision recorded in CLAIMS.
# The field-changed and created rules only fire on future events, so enabling them can
# never touch existing tickets.

def rule_specs():
    """Built lazily (not at import) because condition_priority() resolves a priority id
    over the network, and that must happen after http()/env are ready, not at module load."""
    return [
    {"name": "Reopen handling",
     "description": "When a resolved ticket is reopened, flag it and route it back to L1.",
     "state": "ENABLED", "trigger": trigger_transitioned(status_refs("Resolved"),
                                                          status_refs("Triage")),
     "components": [action_edit([("Reopened", "Yes"), ("Support Tier", "L1")])]},

    {"name": "SLA pause on Pending",
     "description": "Pause the resolution SLA while a ticket waits on the customer or a vendor.",
     "state": "ENABLED",
     "trigger": trigger_transitioned([], status_refs("Pending Customer", "Pending Vendor")),
     "components": [action_edit([("Resolution SLA", "Paused")])]},

    {"name": "Route on escalation",
     "description": "Set Support Tier = L2 when a ticket is escalated to L2.",
     "state": "ENABLED", "trigger": trigger_transitioned([], status_refs("Escalated to L2")),
     "components": [action_edit([("Support Tier", "L2")])]},

    # --- the four that needed the newly-discovered component schemas ---
    {"name": "Derive priority from Impact x Urgency",
     "description": ("When a work item is created, set Priority from the Impact x Urgency "
                     "matrix. Each branch sets Priority only when both Impact and Urgency "
                     "match. (Fires on create; the 're-derive whenever Impact/Urgency later "
                     "change' variant needs the field-changed trigger, which cannot be "
                     "enabled over the API - add it in the UI if wanted.)"),
     "state": "ENABLED", "trigger": trigger_created(),
     "components": priority_matrix_blocks()},

    {"name": "Major incident alert",
     "description": ("When a P1 - Critical work item is raised, flag it for the Major "
                     "Incident Manager with a bridge/comms note. (A comment is used rather "
                     "than an email action because the email recipient shape could not be "
                     "built over the API; swap in Send email in the UI to notify externally.)"),
     "state": "ENABLED", "trigger": trigger_created(),
     "components": [
         condition_priority("P1 - Critical"),
         action_comment("Major incident raised (P1 - Critical). Major Incident Manager "
                        "engaged - open the bridge and start comms per the P1 runbook."),
     ]},

    {"name": "SLA breach warning",
     "description": ("Daily sweep: comment on open P1/P2 tickets that have gone quiet, so "
                     "they get prioritised before the resolution SLA breaches."),
     "state": "ENABLED",
     "trigger": trigger_scheduled(
         "0 0 8 ? * *",
         'project = OPS AND resolution = EMPTY AND priority in ("P1 - Critical", "P2 - High") '
         'AND updated <= -1d'),
     "components": [action_comment("SLA breach warning - this ticket is open, high priority "
                                   "and has had no update in over a day. Prioritise or "
                                   "escalate before the resolution SLA breaches.")]},

    {"name": "Auto-close resolved tickets",
     "description": ("Daily sweep: close tickets that have sat in Resolved for a week with "
                     "no further activity."),
     "state": "ENABLED",
     "trigger": trigger_scheduled(
         "0 0 2 ? * *",
         "project = OPS AND status = Resolved AND updated <= -7d"),
     "components": [action_transition("Closed")]},
    ]


def http(method, path, body=None):
    site = os.environ["JIRA_SITE"].rstrip("/")
    auth = base64.b64encode(
        f'{os.environ["JIRA_EMAIL"]}:{os.environ["JIRA_TOKEN"]}'.encode()).decode()
    req = urllib.request.Request(
        site + path, data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.getcode(), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def existing_names():
    code, body = http("POST", BASE + "/rules", {"offset": 0, "limit": 100})
    if code != 200:
        return {}
    return {r["name"]: r for r in json.loads(body).get("values", [])}


def build_bean(template, rule):
    bean = copy.deepcopy(template)
    for k in ("id", "idUuid", "checksum", "currentVersionId", "created", "updated",
              "clientKey", "partitionId"):
        bean.pop(k, None)
    bean["name"] = rule["name"]
    bean["description"] = rule["description"]
    bean["state"] = rule["state"]
    trig_type, trig_value = rule["trigger"]
    # A clean minimal trigger - the server fills in the rest. Copying the template's
    # trigger instead carries transitioned-specific fields that break the other trigger
    # types (created/scheduled/field-changed) with a null-value / 500 error.
    bean["trigger"] = {"component": "TRIGGER", "type": trig_type,
                       "value": trig_value, "children": []}
    bean["components"] = copy.deepcopy(rule["components"])
    return bean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", choices=("ENABLED", "DISABLED"),
                    help="override the state every rule is created with")
    args = ap.parse_args()
    for v in ("JIRA_SITE", "JIRA_EMAIL", "JIRA_TOKEN"):
        if not os.environ.get(v):
            sys.exit(f"missing {v}")
    if not TEMPLATE.exists():
        sys.exit(f"template not found: {TEMPLATE}")
    template = json.loads(TEMPLATE.read_text())

    have = existing_names()
    print(f"  {len(have)} rule(s) already on the project")
    for rule in rule_specs():
        name = rule["name"]
        if args.state:
            rule = {**rule, "state": args.state}
        if name in have:
            print(f"  = {name}  (exists, id {have[name]['id']}, {have[name]['state']})")
            continue
        ncomp = len(rule["components"])
        if args.dry_run:
            print(f"  + {name}  (would create {rule['state']}, "
                  f"trigger {rule['trigger'][0].split(':')[-1].split('.')[-1]}, "
                  f"{ncomp} top-level component(s))")
            continue
        bean = build_bean(template, rule)
        code, body = http("POST", BASE + "/rule", {"ruleConfigBean": bean})
        if code == 200:
            rid = json.loads(body).get("ruleConfigBean", {}).get("id") \
                or json.loads(body).get("id")
            print(f"  + {name}  created {rule['state']} (id {rid})")
        else:
            print(f"  ! {name}  FAILED {code}: {body[:200]}")


if __name__ == "__main__":
    main()
