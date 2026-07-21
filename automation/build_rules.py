#!/usr/bin/env python3
"""Create automation rules over Jira's internal automation API.

Jira Cloud has no *public* automation-rule API (`/rest/api/3/automation/rules` -> 404),
but the Automation UI drives an internal one the token can reach:

    POST /gateway/api/automation/internal-api/jira/{cloudId}/pro/rest/{projectId}/rule

The catch: the create payload needs the *full* rule wrapper (ruleScope, ruleHome, actor,
writeAccessType, …), not just the minimal envelope - a minimal body returns a useless
"systems are unavailable" 400. So this templates from a REAL rule captured out of the UI
(`schema/example-transition-edit.rule.json`, read back over the same API) and edits only
name / trigger / components. That is how the component *value* schemas were obtained
without guessing: build one rule by hand, GET it back, template the rest.

Component schemas known so far (from the captured rule):
  - trigger  jira.issue.event.trigger:transitioned
  - action   jira.issue.edit   (SET a select field by NAME)

Rules that need only those two are built here. The rest (priority derivation, alerts,
breach warnings, auto-close) need a scheduled trigger, a field-changed trigger, and
comment / notify / transition actions - capture one rule using each, GET it back, add it
below. See automation/README.md.

Everything is created **DISABLED** so nothing rewrites the seeded tickets. Idempotent:
a rule whose name already exists is skipped.

    python3 automation/build_rules.py [--dry-run]
"""

import argparse
import base64
import copy
import json
import os
import sys
import urllib.request
from pathlib import Path

CLOUD_ID = "520438e0-67f8-4ad6-a730-1e078094903e"
PROJECT_ID = "10034"
PROJECT_ARI = f"ari:cloud:jira:{CLOUD_ID}:project/{PROJECT_ID}"
BASE = f"/gateway/api/automation/internal-api/jira/{CLOUD_ID}/pro/rest/{PROJECT_ID}"
TEMPLATE = Path(__file__).parent / "schema" / "example-transition-edit.rule.json"

SELECT = "com.atlassian.jira.plugin.system.customfieldtypes:select"

# Status references use {"type": "NAME", "value": "<status>"} - captured from a real rule.
def status(*names):
    return [{"type": "NAME", "value": n} for n in names]


# Rules expressible with the captured transitioned-trigger + edit-action, now with proper
# status scoping so they fire only on the right transition and are safe to ENABLE.
# Each: (name, description, fromStatus, toStatus, [edit operations], state).
RULES = [
    ("Reopen handling",
     "When a resolved ticket is reopened, flag it and route it back to L1.",
     status("Resolved"), status("Triage"),
     [("Reopened", "Yes"), ("Support Tier", "L1")], "ENABLED"),
    ("SLA pause on Pending",
     "Pause the resolution SLA while a ticket waits on the customer or a vendor.",
     [], status("Pending Customer", "Pending Vendor"),
     [("Resolution SLA", "Paused")], "ENABLED"),
    ("Route on escalation",
     "Set Support Tier = L2 when a ticket is escalated to L2.",
     [], status("Escalated to L2"),
     [("Support Tier", "L2")], "ENABLED"),
]


def http(method, path, body=None):
    site = os.environ["JIRA_SITE"].rstrip("/")
    auth = base64.b64encode(
        f'{os.environ["JIRA_EMAIL"]}:{os.environ["JIRA_TOKEN"]}'.encode()).decode()
    req = urllib.request.Request(
        site + path,
        data=json.dumps(body).encode() if body is not None else None,
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


def edit_operations(pairs):
    return [{"field": {"type": "NAME", "value": name},
             "fieldType": SELECT, "type": "SET",
             "value": {"type": "NAME", "value": val}}
            for name, val in pairs]


def build_bean(template, name, description, from_status, to_status, ops, state):
    bean = copy.deepcopy(template)
    for k in ("id", "idUuid", "checksum", "currentVersionId", "created", "updated",
              "clientKey", "partitionId"):
        bean.pop(k, None)
    bean["name"] = name
    bean["description"] = description
    bean["state"] = state
    bean["trigger"]["value"] = {"eventFilters": [PROJECT_ARI],
                                "fromStatus": from_status, "toStatus": to_status,
                                "eventKey": "jira:issue_updated",
                                "issueEvent": "issue_generic"}
    bean["components"] = [{"component": "ACTION", "type": "jira.issue.edit",
                           "value": {"operations": edit_operations(ops),
                                     "advancedFields": None, "sendNotifications": False},
                           "children": []}]
    return bean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for v in ("JIRA_SITE", "JIRA_EMAIL", "JIRA_TOKEN"):
        if not os.environ.get(v):
            sys.exit(f"missing {v}")
    if not TEMPLATE.exists():
        sys.exit(f"template not found: {TEMPLATE} - capture one rule from the UI first")
    template = json.loads(TEMPLATE.read_text())

    have = existing_names()
    print(f"  {len(have)} rule(s) already on the project")
    for name, desc, frm, to, ops, state in RULES:
        if name in have:
            print(f"  = {name}  (exists, id {have[name]['id']}, {have[name]['state']})")
            continue
        if args.dry_run:
            print(f"  + {name}  (would create {state}: "
                  f"{', '.join(f'{f}={v}' for f, v in ops)})")
            continue
        bean = build_bean(template, name, desc, frm, to, ops, state)
        code, body = http("POST", BASE + "/rule", {"ruleConfigBean": bean})
        if code == 200:
            rid = json.loads(body).get("ruleConfigBean", {}).get("id") \
                or json.loads(body).get("id")
            print(f"  + {name}  created {state} (id {rid})")
        else:
            print(f"  ! {name}  FAILED {code}: {body[:160]}")

    print("\n  NOT built (need more captured component schemas - see README):")
    print("    1 Derive priority  (field-changed trigger + if-else branch)")
    print("    3 Major-incident alert  (created/field-changed trigger + send-notification)")
    print("    4 SLA breach warning  (scheduled trigger + add-comment)")
    print("    7 Auto-close  (scheduled trigger + transition-issue action)")


if __name__ == "__main__":
    main()
