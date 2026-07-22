#!/usr/bin/env python3
"""Provision the real SFC project — DeliveryIQ / Salesforce Config Request tracking.

This is P0 for the DeliveryIQ lens (see DELIVERYIQ-SF-CONFIG.md). It flips the
"Delivery / SF Config" tab from the deterministic PREVIEW seed (app/sfc_seed.py) to
a real Jira project whose bake emits the identical schema, so the panels render
unchanged once real requests flow.

It creates, idempotently and in one pass:
  * the SFC company-managed software project;
  * the "Salesforce Config Request" issue type and the "Org Deploy" sub-task, bound
    to SFC via a dedicated issue-type scheme (Model A — one Org Deploy sub-task per
    target org, so per-org deploy/health reconciles natively);
  * the DeliveryIQ custom fields at cf_10061+ (Target Orgs, Config Component Type,
    Change Risk, Deploy State, Config Health, Health Checked At, Deploy Source, CAB
    Approval, the agent-action ledger fields, Package Ref), with options, added to
    the SFC screens (global field contexts — a field is only visible where it is on
    a screen, so no per-project scoping is needed and none is faked);
  * the five-stage statuses (Intake → Build → Review → Deploy → Audit) and a
    workflow with a CAB gate (a change cannot be sent to CAB until what it changes is
    recorded — the DeliveryIQ analogue of the OPS escalation gate), THEN a workflow
    scheme that binds that workflow to the SFC project so the statuses are actually
    reachable. The bind is one synchronous PUT because it runs against the freshly
    created, still-empty project (no async status migration) — this is why sfc_build
    must run before fixtures.sfc_seed.

Idempotent — safe to re-run. Existing objects are reused, never duplicated. Writes
jira_config/state/.sfc_state.json (consumed by the seeder; the app resolves field
ids by name at runtime and never reads it).

    python3 -m jira_config.sfc_build [--dry-run]

--dry-run is a real rehearsal: every mutating call goes through Writer, which logs
the method and path and issues nothing, and writes no state. The token is CI-only,
so the intended path is: run this from the sfc-build.yml Action with dry-run first,
read the plan, then re-run with dry-run off. Fields the model REUSES from OPS
(Impact, Urgency, the four lifecycle dates, L2 Analyst) keep their global context
and are only added to SFC screens — they are never scoped, which would break OPS.

Python 3.9. %-formatting, no f-strings with backslashes.
"""

import argparse
import uuid

from shared.jira_client import Jira, log, require_env
from shared import fields as SF          # proper duplicate-name field disambiguation
from jira_config import jira_schema as S
from jira_config import SFC_STATE as STATE
from jira_config import merge_state, read_state
from jira_config.reconcile import Writer
from jira_config.build import ensure_options  # generic context/option reconciler

OWNED_KEYS = ("project_id", "issue_types", "issue_type_scheme_id", "fields",
              "statuses", "workflow_created", "workflow_scheme_id")

# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------

PROJECT_KEY = "SFC"
PROJECT_NAME = "Delivery / SF Config"
# Company-managed software, same template as OPS — required for shared schemes and
# for the workflow/status machinery this script drives over REST.
PROJECT_TYPE_KEY = S.PROJECT_TYPE_KEY
PROJECT_TEMPLATE_KEY = S.PROJECT_TEMPLATE_KEY

ISSUE_TYPE_SCHEME_NAME = "SFC Issue Type Scheme"

# (name, description, hierarchy level). "subtask" carries the per-org deploy so the
# rollup reconciles natively — see Model A in the spec.
ISSUE_TYPES = [
    ("Salesforce Config Request",
     "A Salesforce configuration change tracked through the DeliveryIQ pipeline "
     "(Intake -> Build -> Review -> Deploy -> Audit).", "standard"),
    ("Org Deploy",
     "One target org's deployment of a Salesforce Config Request. Carries the "
     "per-org deploy state and config health.", "subtask"),
]

# ---------------------------------------------------------------------------
# Jira custom-field wire formats. Single/multi-select and number are not in
# jira_schema (OPS uses only single selects, text, dates), so they live here.
# ---------------------------------------------------------------------------

SELECT1 = "com.atlassian.jira.plugin.system.customfieldtypes:select"
SELECTN = "com.atlassian.jira.plugin.system.customfieldtypes:multiselect"
NUMBER = "com.atlassian.jira.plugin.system.customfieldtypes:float"
DATETIME = S.DATE_TYPE
TEXT = S.TEXT_TYPE

SEARCHER = {
    SELECT1: "com.atlassian.jira.plugin.system.customfieldtypes:multiselectsearcher",
    SELECTN: "com.atlassian.jira.plugin.system.customfieldtypes:multiselectsearcher",
    NUMBER: "com.atlassian.jira.plugin.system.customfieldtypes:exactnumber",
    DATETIME: "com.atlassian.jira.plugin.system.customfieldtypes:datetimerange",
    TEXT: "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
}

# ---------------------------------------------------------------------------
# The DeliveryIQ schema. Enum values are the canonical §0 sets and MUST match
# app/sfc_seed.py exactly, or the panels split on a value the real data never uses.
# ---------------------------------------------------------------------------

SQUADS = ["Sales Cloud", "Service Cloud", "Platform / Core", "Revenue / CPQ",
          "Data & Integrations", "Experience Cloud"]
ORGS = ["Prod", "Full-copy UAT", "QA", "Staging", "Dev"]
COMPONENTS = ["Field", "Flow", "Validation Rule", "Permission Set", "Page Layout",
              "Custom Object", "Apex-adjacent", "LWC-adjacent"]

# Single-select: name -> option values.
SELECT1_FIELDS = {
    "Delivery Squad": SQUADS,
    "Change Risk": ["Low", "Medium", "High"],
    "CAB Approval": ["Not required", "Pending", "Approved", "Rejected"],
    # Carried on the Org Deploy sub-task.
    "Deploy State": ["Not started", "Validated", "Deploying", "Deployed",
                     "Failed", "Rolled back"],
    "Config Health": ["Healthy", "Degraded", "Failing", "Unknown"],
    "Deploy Source": ["CI writeback", "Manual", "Seeded"],
    # Agent-action ledger (Build / Compliance) — Yes/No so the boolean reconciles.
    "Build Tested": ["Yes", "No"],
    "Compliance Authorized": ["Yes", "No"],
    "Compliance Evidence": ["Yes", "No"],
    "Evidence Pack Ready": ["Yes", "No"],
}

# Multi-select: name -> option values.
SELECTN_FIELDS = {
    "Target Orgs": ORGS,
    "Config Component Type": COMPONENTS,
}

TEXT_FIELDS = ["Package Ref"]
NUMBER_FIELDS = ["Coord Conflicts", "Coord Dependencies"]   # Coordination agent
DATETIME_FIELDS = ["Health Checked At"]                     # on the Org Deploy sub-task

# Fields SHARED with OPS. They exist globally already; SFC reuses them by name so
# the bake resolves one id per concept across projects. They are added to SFC
# screens but NEVER scoped — scoping a shared field to SFC would strand it on OPS.
# ensure_field still creates any that are somehow missing (with a global context).
REUSED_SELECT_FIELDS = {
    "Impact": ["High", "Medium", "Low"],
    "Urgency": ["High", "Medium", "Low"],
}
REUSED_TEXT_FIELDS = ["L2 Analyst"]
REUSED_DATE_FIELDS = ["Reported At", "First Response At", "Escalated At", "Resolved At"]

FIELD_DESC = "SFC / DeliveryIQ schema"   # stamped on every field this script creates

# ---------------------------------------------------------------------------
# Statuses & workflow. Stage is DERIVED from status by the bake (see the map in
# DELIVERYIQ-SF-CONFIG.md); these are the concrete Jira statuses the funnel needs.
# ---------------------------------------------------------------------------

STATUSES = [
    ("Intake", "new"),
    ("In Build", "indeterminate"),
    ("In Review", "indeterminate"),
    ("Awaiting CAB", "indeterminate"),
    ("Deploying", "indeterminate"),
    ("Deployed", "indeterminate"),
    ("Deploy Failed", "indeterminate"),
    ("Rolled Back", "indeterminate"),
    ("Audit", "indeterminate"),
    ("Done", "done"),
    ("Cancelled", "done"),
]

# (transition name, type, from-status, to-status). GLOBAL transitions have no
# from-status (available from anywhere). This is the graph the seeder walks.
TRANSITIONS = [
    ("Create", "INITIAL", None, "Intake"),
    ("Start build", "DIRECTED", "Intake", "In Build"),
    ("Submit for review", "DIRECTED", "In Build", "In Review"),
    ("Request CAB", "DIRECTED", "In Review", "Awaiting CAB"),   # <- CAB gate lives here
    ("Begin deploy", "DIRECTED", "Awaiting CAB", "Deploying"),
    ("Deploy succeeded", "DIRECTED", "Deploying", "Deployed"),
    ("Deploy failed", "DIRECTED", "Deploying", "Deploy Failed"),
    ("Retry deploy", "DIRECTED", "Deploy Failed", "Deploying"),
    ("Enter audit", "DIRECTED", "Deployed", "Audit"),
    ("Complete", "DIRECTED", "Audit", "Done"),
    ("Roll back", "GLOBAL", None, "Rolled Back"),
    ("Cancel", "GLOBAL", None, "Cancelled"),
    ("Reopen", "DIRECTED", "Done", "In Build"),
]

# The CAB gate: you cannot ask CAB to approve a change until you have recorded WHAT
# it changes and WHERE it lands. The DeliveryIQ analogue of the OPS escalation gate,
# built with the same proven rule key (system:validate-field-value / fieldRequired).
GATE_TRANSITION = "Request CAB"
GATE_FIELDS = ["Change Risk", "Config Component Type", "Target Orgs"]

WORKFLOW_NAME = "SFC DeliveryIQ Workflow"
WORKFLOW_SCHEME_NAME = "SFC DeliveryIQ Workflow Scheme"

NS = uuid.UUID("6f1e5d6c-0a4b-4f2e-9c3d-000000000002")  # distinct from OPS's namespace


def sref(name):
    return str(uuid.uuid5(NS, name))


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------

def ensure_project(w, state):
    j = w.j
    existing = j.try_get("/rest/api/3/project/%s" % PROJECT_KEY)
    if existing and existing.get("key") == PROJECT_KEY:
        log("  project %s already exists (id %s)" % (PROJECT_KEY, existing["id"]))
        state["project_id"] = existing["id"]
        return existing["id"]
    me = j.get("/rest/api/3/myself")["accountId"]
    res = w.post("/rest/api/3/project", {
        "key": PROJECT_KEY,
        "name": PROJECT_NAME,
        "projectTypeKey": PROJECT_TYPE_KEY,
        "projectTemplateKey": PROJECT_TEMPLATE_KEY,
        "leadAccountId": me,
        "assigneeType": "UNASSIGNED",
        "description": "DeliveryIQ / Salesforce Config Request tracking. Built from "
                       "jira_config/sfc_build.py - see DELIVERYIQ-SF-CONFIG.md.",
    })
    log("  created project %s (id %s)" % (PROJECT_KEY, res["id"]))
    state["project_id"] = res["id"]
    return res["id"]


# ---------------------------------------------------------------------------
# issue types + scheme
# ---------------------------------------------------------------------------

def ensure_types(w):
    have = {t["name"]: t["id"] for t in w.j.get("/rest/api/3/issuetype")}
    ids = {}
    for name, desc, level in ISSUE_TYPES:
        if name in have:
            ids[name] = have[name]
            log("  = %-26s %s" % (name, have[name]))
            continue
        res = w.post("/rest/api/3/issuetype",
                     {"name": name, "description": desc, "type": level})
        ids[name] = res["id"]
        log("  + %-26s %s" % (name, res["id"]))
    return ids


def ensure_scheme(w, type_ids, project_id):
    j = w.j
    order = [type_ids[n] for n, _, _ in ISSUE_TYPES]
    schemes = j.get("/rest/api/3/issuetypescheme?maxResults=100").get("values", [])
    hit = [s for s in schemes if s["name"] == ISSUE_TYPE_SCHEME_NAME]
    if hit:
        sid = hit[0]["id"]
        log("  = scheme exists (%s)" % sid)
        try:
            w.put("/rest/api/3/issuetypescheme/%s" % sid,
                  {"name": ISSUE_TYPE_SCHEME_NAME, "defaultIssueTypeId": order[0]})
        except RuntimeError:
            pass
    else:
        res = w.post("/rest/api/3/issuetypescheme", {
            "name": ISSUE_TYPE_SCHEME_NAME,
            "description": "Salesforce Config Request + Org Deploy sub-task.",
            "defaultIssueTypeId": order[0],
            "issueTypeIds": order,
        })
        sid = res.get("issueTypeSchemeId") or res.get("id")
        log("  + scheme created (%s)" % sid)
    try:
        w.put("/rest/api/3/issuetypescheme/%s/issuetype" % sid, {"issueTypeIds": order})
    except RuntimeError as e:
        log("    membership: %s" % str(e)[:110])
    try:
        w.put("/rest/api/3/issuetypescheme/project",
              {"issueTypeSchemeId": str(sid), "projectId": str(project_id)})
        log("  scheme bound to %s" % PROJECT_KEY)
    except RuntimeError as e:
        log("  ! bind failed: %s" % str(e)[:220])
    return sid


# ---------------------------------------------------------------------------
# custom fields
# ---------------------------------------------------------------------------

def existing_custom_fields(j):
    return {f["name"]: f["id"] for f in j.get("/rest/api/3/field") if f.get("custom")}


def ensure_field(w, name, ftype, have):
    """Create a custom field of `ftype`, or return the existing id by name.

    Mirrors jira_config.build.ensure_field but stamps an SFC description and reads
    its searcher from the local SEARCHER map (which knows multiselect and number).
    """
    if name in have:
        return have[name], False
    res = w.post("/rest/api/3/field", {
        "name": name, "type": ftype, "searcherKey": SEARCHER[ftype],
        "description": "%s - %s" % (FIELD_DESC, name)})
    return res["id"], True


def resolve_shared(j):
    """Correct ids for the OPS-shared fields, disambiguated by shared.fields.

    This instance carries TWO custom fields named "Urgency" (and one "Impact" that is
    a Jira built-in) — see shared/fields.py. A raw {name: id} map is last-one-wins and
    can hand the seeder a JSM look-alike whose option set differs, 400-ing every issue
    create. shared.fields.resolve() applies the same type+description-tag tie-break the
    app uses at runtime, so the seeder gets the OPS-owned id. Returns {} if OPS's schema
    is not fully present (then we fall back to creating the fields ourselves).
    """
    try:
        return SF.resolve(j)
    except SF.FieldResolutionError:
        return {}


def build_fields(w):
    """Create/resolve every SFC field. Returns name -> customfield id."""
    have = existing_custom_fields(w.j)
    shared = resolve_shared(w.j)
    fields = {}

    def do(name, ftype, options=None):
        fid, is_new = ensure_field(w, name, ftype, have)
        fields[name] = fid
        extra = ""
        if options:
            n = ensure_options(w, fid, options, is_new)
            extra = "  (+%d options)" % n
        log("  %s %-24s %s%s" % ("+" if is_new else "=", name, fid, extra))

    def reuse(name, ftype, options=None):
        # Prefer the disambiguated id; only create if OPS's schema is absent here.
        if name in shared:
            fields[name] = shared[name]
            log("  = %-24s %s  (shared with OPS, disambiguated)" % (name, shared[name]))
        else:
            do(name, ftype, options)

    log("  -- SFC-owned fields (global context; visible only on SFC screens) --")
    for name, opts in SELECT1_FIELDS.items():
        do(name, SELECT1, opts)
    for name, opts in SELECTN_FIELDS.items():
        do(name, SELECTN, opts)
    for name in TEXT_FIELDS:
        do(name, TEXT)
    for name in NUMBER_FIELDS:
        do(name, NUMBER)
    for name in DATETIME_FIELDS:
        do(name, DATETIME)

    # Shared with OPS: reuse the disambiguated id, add to SFC screens, never touch its
    # global context (scoping a shared field to SFC would strand it on OPS).
    log("  -- shared fields (reused from OPS) --")
    for name, opts in REUSED_SELECT_FIELDS.items():
        reuse(name, SELECT1, opts)
    for name in REUSED_TEXT_FIELDS:
        reuse(name, TEXT)
    for name in REUSED_DATE_FIELDS:
        reuse(name, DATETIME)

    return fields


def add_fields_to_screens(w, field_ids):
    """Put every SFC field on the SFC screens so REST can set it on create/edit.

    Matched by project KEY in the screen name (as OPS does). If NO SFC-named screen is
    found we WARN and skip rather than spraying SFC fields across every project's
    screens (the old all-screens fallback could land them on OPS/ITSM). A freshly
    created company-managed project always has key-named screens, so this is a
    belt-and-braces guard, not the expected path.
    """
    j = w.j
    added = 0
    screens = j.get("/rest/api/3/screens?maxResults=100").get("values", [])
    targets = [s for s in screens if PROJECT_KEY.lower() in (s.get("name") or "").lower()]
    if not targets:
        log("  ! no SFC-specific screens found — skipping (refusing to touch other "
            "projects' screens). Add the SFC fields to the SFC create/edit screens in "
            "the UI, then re-run the seeder.")
        return 0
    for sc in targets:
        tabs = j.try_get("/rest/api/3/screens/%s/tabs" % sc["id"], [])
        if not tabs:
            continue
        tab = tabs[0]["id"]
        present = {f["id"] for f in j.try_get(
            "/rest/api/3/screens/%s/tabs/%s/fields" % (sc["id"], tab), []) or []}
        for fid in field_ids:
            if fid in present:
                continue
            try:
                w.post("/rest/api/3/screens/%s/tabs/%s/fields" % (sc["id"], tab),
                       {"fieldId": fid})
                added += 1
            except RuntimeError:
                pass  # already present on another tab, or not addable
    return added


# ---------------------------------------------------------------------------
# statuses + workflow
# ---------------------------------------------------------------------------

def ensure_statuses(w):
    j = w.j
    have = {}
    page = j.try_get("/rest/api/3/statuses/search?maxResults=200", {}) or {}
    for v in page.get("values", []):
        have[v["name"]] = v["id"]
    ids, to_create = {}, []
    for name, cat in STATUSES:
        if name in have:
            ids[name] = have[name]
        else:
            to_create.append({"name": name, "statusCategory": S.STATUS_CATEGORY[cat],
                              "description": "SFC / DeliveryIQ - %s" % name})
    if to_create:
        res = w.post("/rest/api/3/statuses",
                     {"scope": {"type": "GLOBAL"}, "statuses": to_create})
        for s in (res if isinstance(res, list) else []):
            ids[s["name"]] = s["id"]
    for name, _ in STATUSES:
        log("  %-16s %s" % (name, ids.get(name, "MISSING")))
    return ids


def attempt_workflow(w, status_ids, field_ids):
    """One careful attempt at the SFC workflow with the CAB gate. True on success.

    Same shape as jira_config.workflow.attempt_workflow; the Cloud workflow API is
    strict, so this reports honestly rather than pretending. On success, main() binds
    it to the project via ensure_workflow_scheme so the statuses become reachable. If
    creation fails, the workflow is assembled in the UI from print_transition_table().
    Returns True (created), False (declined), or None (dry-run rehearsal).
    """
    layout_statuses = [
        {"statusReference": sref(n), "layout": {"x": (i % 4) * 220.0,
         "y": (i // 4) * 150.0}} for i, (n, _) in enumerate(STATUSES)]

    transitions = []
    for idx, (name, ttype, frm, to) in enumerate(TRANSITIONS, start=1):
        t = {"id": str(idx), "name": name, "type": ttype,
             "toStatusReference": sref(to), "properties": {}}
        if ttype == "DIRECTED":
            t["links"] = [{"fromStatusReference": sref(frm), "toPort": 0, "fromPort": 0}]
        if name == GATE_TRANSITION:
            ids = ",".join(field_ids[f] for f in GATE_FIELDS if f in field_ids)
            t["validators"] = [
                {"ruleKey": "system:validate-field-value",
                 "parameters": {
                     "ruleType": "fieldRequired",
                     "fieldsRequired": ids,
                     "ignoreContext": "false",
                     "errorMessage": ("Record what you're changing, where it lands, "
                                      "and its risk before asking CAB to approve it."),
                 }}]
        transitions.append(t)

    body = {
        "scope": {"type": "GLOBAL"},
        "statuses": [
            {"statusReference": sref(n), "id": status_ids.get(n), "name": n,
             "statusCategory": S.STATUS_CATEGORY[cat],
             "description": "SFC / DeliveryIQ - %s" % n}
            for n, cat in STATUSES],
        "workflows": [{
            "name": WORKFLOW_NAME,
            "description": "Intake -> Build -> Review -> Deploy -> Audit, with a CAB gate.",
            "statuses": layout_statuses,
            "transitions": transitions,
        }],
    }
    try:
        res = w.post("/rest/api/3/workflows/create", body)
        if w.dry:
            log("  [dry] workflow creation not attempted")
            return None
        log("  workflow created: %s" % [x.get("name") for x in res.get("workflows", [])])
        return True
    except RuntimeError as e:
        log("  workflow creation FAILED\n    %s" % str(e)[:400])
        return False


def print_transition_table():
    log("\n  -- SFC workflow transition table (for UI assembly if the API declined) --")
    log("  %-20s %-9s %-16s -> %s" % ("transition", "type", "from", "to"))
    for name, ttype, frm, to in TRANSITIONS:
        log("  %-20s %-9s %-16s -> %s" % (name, ttype, frm or "(any)", to))
    log("  gate: %r requires %s" % (GATE_TRANSITION, ", ".join(GATE_FIELDS)))
    log("  Then bind %r to the SFC project's issue types via a workflow scheme" % WORKFLOW_NAME)
    log("  (Project settings -> Workflows) so the statuses are reachable.")


def current_scheme_id(j, project_id):
    """The id of the workflow scheme currently bound to `project_id`, or None.

    The built-in Default Workflow Scheme has no id, so a project on it returns None
    (which is exactly the 'not yet ours' signal we want).
    """
    resp = j.try_get("/rest/api/3/workflowscheme/project?projectId=%s" % project_id, {}) or {}
    for v in resp.get("values", []):
        ws = v.get("workflowScheme") or {}
        if ws.get("id") is not None:
            return str(ws["id"])
    ws = resp.get("workflowScheme") or {}
    return str(ws["id"]) if ws.get("id") is not None else None


def ensure_workflow_scheme(w, project_id):
    """Create the SFC workflow scheme and bind it to the (empty) SFC project.

    This is what makes the five stages REACHABLE: a workflow from /workflows/create is
    inert until a scheme maps it onto the project's issue types and the scheme is
    assigned to the project. The classic scheme references the workflow by NAME.

    The assignment is a single synchronous PUT because it runs against the freshly
    created, still-empty project — Jira only triggers the async status-migration when
    issues already exist. So sfc_build MUST run before fixtures.sfc_seed. On an
    idempotent re-run (scheme already bound), the PUT is skipped. If the project
    already holds issues under a different scheme, the PUT is refused and we fall back
    to the printed UI instructions rather than pretend. Returns (scheme_id, bound?).
    """
    j = w.j
    schemes = j.get("/rest/api/3/workflowscheme?maxResults=100").get("values", [])
    hit = [s for s in schemes if s.get("name") == WORKFLOW_SCHEME_NAME]
    if hit:
        sid = str(hit[0]["id"])
        log("  = workflow scheme exists (%s)" % sid)
    else:
        res = w.post("/rest/api/3/workflowscheme", {
            "name": WORKFLOW_SCHEME_NAME,
            "description": "Maps SFC issue types onto the DeliveryIQ funnel workflow.",
            # Classic scheme binds by workflow NAME; the default covers every SFC type
            # (incl. the Org Deploy sub-task, which simply rests in the initial status —
            # the seeder never transitions sub-tasks).
            "defaultWorkflow": WORKFLOW_NAME,
        })
        sid = str(res.get("id") or res.get("workflowSchemeId") or "DRY")
        log("  + workflow scheme created (%s), default workflow %r" % (sid, WORKFLOW_NAME))

    if not w.dry and current_scheme_id(j, project_id) == sid:
        log("  = %s already bound to %s (statuses reachable)" % (WORKFLOW_SCHEME_NAME, PROJECT_KEY))
        return sid, True
    try:
        # Empty project -> 204 synchronous, no migration. This is the whole point of
        # binding before seeding.
        w.put("/rest/api/3/workflowscheme/project",
              {"workflowSchemeId": sid, "projectId": str(project_id)})
        log("  workflow scheme bound to %s — Intake/Build/Review/Deploy/Audit now reachable"
            % PROJECT_KEY)
        return sid, True
    except RuntimeError as e:
        log("  ! workflow-scheme bind FAILED: %s" % str(e)[:220])
        log("    If the project already has issues, assignment needs the async migration —")
        log("    switch it to %r in the UI (Project settings -> Workflows)." % WORKFLOW_SCHEME_NAME)
        return sid, False


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(argparse.ArgumentParser(prog="jira_config.sfc_build")).parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    state = read_state(STATE)

    log("== project ==")
    project_id = ensure_project(w, state)

    log("== issue types ==")
    state["issue_types"] = ensure_types(w)

    log("== issue type scheme ==")
    state["issue_type_scheme_id"] = ensure_scheme(w, state["issue_types"], project_id)

    log("== custom fields ==")
    fields = build_fields(w)
    state["fields"] = fields
    log("  %d fields total" % len(fields))

    log("== screens ==")
    n = add_fields_to_screens(w, list(fields.values()))
    log("  %d field/screen associations added" % n)

    log("== statuses ==")
    status_ids = ensure_statuses(w)
    state["statuses"] = status_ids

    log("== workflow ==")
    ok = attempt_workflow(w, status_ids, fields)
    # A dry run learns nothing about whether creation would succeed, so it must not
    # overwrite the recorded answer with a guess (matches jira_config.workflow).
    if ok is not None:
        state["workflow_created"] = ok

    # Bind the workflow to the project so the statuses are reachable. Rehearse it on a
    # dry run (ok is None); attempt it for real when the workflow was created (ok True).
    # Only skip when creation genuinely declined (ok False) — nothing to bind then.
    if ok is not False:
        log("== workflow scheme (bind) ==")
        sid, bound = ensure_workflow_scheme(w, project_id)
        if sid and sid != "DRY":
            state["workflow_scheme_id"] = sid
        if not bound and not args.dry_run:
            print_transition_table()
    else:
        print_transition_table()

    merge_state(STATE, state, OWNED_KEYS, dry=args.dry_run)
    log("\n%d writes%s" % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))
    if not args.dry_run:
        log("state written to %s" % STATE.name)
    log("next: python3 -m fixtures.sfc_seed   (seed real SFC requests + Org Deploy sub-tasks)")


if __name__ == "__main__":
    main()
