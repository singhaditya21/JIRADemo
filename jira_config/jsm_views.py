#!/usr/bin/env python3
"""Build the CONTROL TOWER views for the ITSM service project.

Four surfaces, in the order an agent actually uses them:

  1. AGENT QUEUES   - the JSM-native surface. Creatable over REST via the internal
                      endpoint POST/PUT /rest/servicedesk/1/servicedesk/ITSM/queues.
                      There is NO delete over REST or GraphQL on this instance, so
                      every queue here is permanent: names are final and the script
                      renames in place (PUT) rather than recreating on a re-run.
  2. SAVED FILTERS  - the 20-filter mirror of OPS's jira_config/views.py, retargeted at ITSM.
  3. DASHBOARD      - "ITSM - L1/L2 Control Tower", with gadgets CONFIGURED over REST
                      (see note below).
  4. PORTAL         - one organization, linked to the service desk, plus the existing
                      admin account added as a portal customer.

Idempotent - safe to re-run. Filters are updated in place, queues are updated in
place, dashboard gadgets are reconciled (dropped and re-added) so re-running never
duplicates them.

GADGET CONFIG IS REST-WRITABLE. jira_config/views.py added three gadgets to the OPS dashboard
but never configured them, so they render as an unconfigured "select a filter" prompt.
The missing step is a second call after the add:
    PUT /rest/api/3/dashboard/{dashboardId}/items/{gadgetId}/properties/config
Verified working on a throwaway dashboard for filter-results, pie-chart,
two-dimensional-stats, stats and heat-map gadgets. OPS's dashboard is NOT touched
here - views.py has since been rewritten to reconcile gadgets (matching on title,
binding each to its filter, adding only what is missing) rather than appending them,
so that defect is closed at the source. The reconciler lives in
jira_config/reconcile.py; this module still carries its own delete-then-rebuild
dashboard logic and is the next thing that should adopt it.

DATES. Every window keys off "Reported At" (customfield_10057), never `created`.
`created` is read-only over REST so all 420 seeded tickets carry today's date; any
filter keyed off it returns everything or nothing.

PRIORITIES. At-risk JQL uses the FULL priority names ("P1 - Critical"), not "P1".
`priority = "P1"` matches nothing on this instance.

OPS SAFETY. OPS is live and demoed tomorrow. This script writes only to:
  - project ITSM (queues), - NEW filters named "ITSM - ...", - a NEW dashboard,
  - a NEW organization, - service desk 8.
It never writes to OPS, never touches an OPS filter or the OPS dashboard, and never
writes state/.build_state.json. guard_ops() runs before the first write and after the last,
and additionally asserts every OPS filter recorded in state/.build_state.json still resolves.

Writes jira_config/state/.jsm_state.json.

Usage:  python3 -m jira_config.jsm_views
"""

import argparse
import json
import sys

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config.reconcile import Writer
from jira_config import BUILD_STATE as OPS_STATE, JSM_STATE as STATE

P = S.JSM_PROJECT_KEY
SERVICE_DESK_ID = S.SERVICE_DESK_ID
DASH_NAME = "ITSM - L1/L2 Control Tower"
ORG_NAME = "Northwind Manufacturing"

# ITSM runs the stock ITIL workflows, so the paused-status names differ from OPS's
# own (domain.SLA_PAUSED_STATUSES). These are the ITSM statuses where the clock is
# legitimately stopped - the ball is not in our court.
_PAUSED_JQL = ", ".join(f'"{s}"' for s in S.JSM_PAUSED_STATUSES)


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def load_state():
    if not STATE.exists():
        sys.exit(f"{STATE.name} missing - run python3 -m jira_config.jsm_build first.")
    return json.loads(STATE.read_text())


def save_state(s, dry=False):
    """A rehearsal must not mutate the artifact it is rehearsing."""
    if dry:
        return
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


def load_ops_state():
    if not OPS_STATE.exists():
        sys.exit(f"{OPS_STATE.name} missing - run python3 -m jira_config.build first.")
    return json.loads(OPS_STATE.read_text())


# ---------------------------------------------------------------------------
# safety
# ---------------------------------------------------------------------------

def guard_ops(j, ops, when):
    """Abort loudly if anything OPS depends on has moved. Read-only."""
    problems = []

    proj = j.try_get(f"/rest/api/3/project/{S.PROJECT_KEY}")
    if not proj or proj.get("id") != ops["project_id"]:
        problems.append(f"project {S.PROJECT_KEY} missing or moved")
    else:
        have_types = {t["id"] for t in proj.get("issueTypes", [])}
        for name, tid in ops.get("issue_types", {}).items():
            if tid not in have_types:
                problems.append(f"OPS lost issue type {name} ({tid})")

    all_fields = {f["id"] for f in j.get("/rest/api/3/field")}
    for name, fid in ops["fields"].items():
        if fid not in all_fields:
            problems.append(f"custom field {name} ({fid}) no longer exists")

    prio = {p["id"] for p in j.get("/rest/api/3/priority")}
    for name, pid in ops.get("priorities", {}).items():
        if pid not in prio:
            problems.append(f"priority {name} ({pid}) no longer exists")

    wf_name = ops.get("workflow_name")
    if wf_name:
        found = j.try_get("/rest/api/3/workflow/search?maxResults=200", {}) or {}
        names = {w.get("id", {}).get("name") for w in found.get("values", [])}
        if wf_name not in names:
            problems.append(f"workflow '{wf_name}' not found")

    # This script's whole job is creating filters and a dashboard, so the OPS
    # filters are the objects most plausibly at risk from a bug here. Check each.
    ops_filters = ops.get("filters", {}) or {}
    for name, fid in ops_filters.items():
        if j.try_get(f"/rest/api/3/filter/{fid}") is None:
            problems.append(f"OPS filter '{name}' ({fid}) no longer resolves")

    if problems:
        for p in problems:
            log(f"  !! OPS GUARD ({when}): {p}")
        sys.exit("ABORTING - OPS integrity check failed. Nothing further was written.")
    log(f"  OPS intact ({when}): project, {len(ops['fields'])} fields, "
        f"{len(ops.get('priorities', {}))} priorities, workflow, "
        f"{len(ops_filters)} filters")


# ---------------------------------------------------------------------------
# 2. saved filters - the 20-filter mirror of OPS
# ---------------------------------------------------------------------------

def build_filters():
    """Returns [(name, jql, description)]. Mirrors jira_config/views.py, retargeted at ITSM."""
    f = [
        ("ITSM - L1 queue (open)",
         f'project = {P} AND "Support Tier" = L1 AND statusCategory != Done '
         f'ORDER BY priority DESC, "Reported At" ASC',
         "Everything sitting at L1 and not finished."),

        ("ITSM - L2 queue (open)",
         f'project = {P} AND "Support Tier" = L2 AND statusCategory != Done '
         f'ORDER BY priority DESC, "Reported At" ASC',
         "Escalated work in flight, across all towers."),

        ("ITSM - Major incidents (Impact High + Urgency High)",
         f'project = {P} AND Impact = High AND Urgency = High ORDER BY "Reported At" DESC',
         "The P1 war-room view. Priority is derived from Impact x Urgency, so this "
         "is the real definition rather than a restatement of the priority field."),

        ("ITSM - SLA breached (resolution)",
         f'project = {P} AND "Resolution SLA" = Breached ORDER BY "Reported At" DESC',
         "Resolution target missed. Attainment reporting starts here. Note this is "
         "the MODELLED SLA field, not the JSM SLA engine - the engine measures from "
         "`created`, which is today for every seeded ticket."),

        ("ITSM - SLA paused (waiting on customer, vendor or approval)",
         f'project = {P} AND (status IN ({_PAUSED_JQL}) OR "Resolution SLA" = Paused) '
         f'ORDER BY "Reported At" ASC',
         "Ball is not in our court. Excluded from attainment - this is what makes the "
         "report trustworthy. Status-based OR field-based, so it holds whether the "
         "clock was stopped by a transition or by the seeder."),

        ("ITSM - Aged backlog over 14 days",
         f'project = {P} AND statusCategory != Done AND "Reported At" <= -14d '
         f'ORDER BY "Reported At" ASC',
         "What is quietly rotting. Keys off Reported At, not created."),

        ("ITSM - Reopened tickets",
         f'project = {P} AND Reopened = Yes ORDER BY "Reported At" DESC',
         "Paired with first-time resolution - closing early to flatter FTR shows up here."),

        ("ITSM - Escalated in last 30 days",
         f'project = {P} AND "Support Tier" = L2 AND "Reported At" >= -30d '
         f'ORDER BY "Reported At" DESC',
         "Feeds escalation rate per analyst and per tower."),

        ("ITSM - Escalated with no KB article found",
         f'project = {P} AND "KB Article Checked" = "Yes - none found" '
         f'ORDER BY "Reported At" DESC',
         "Every row is a candidate knowledge-base article. This is the loop that "
         "lifts L1's ceiling and pulls the escalation rate down."),

        ("ITSM - Intake via chat (shadow support pulled in)",
         f'project = {P} AND "Intake Channel" = Chat ORDER BY "Reported At" DESC',
         "Demand that would otherwise be invisible. See PROBLEM.md 3.6."),
    ]

    # One L2 queue per tower - escalated work lands in the tower pool, not on a person.
    for tower, _ in D.TOWERS:
        f.append((
            f"ITSM - L2 queue: {tower}",
            f'project = {P} AND "Support Tier" = L2 AND Tower = "{tower}" '
            f'AND statusCategory != Done ORDER BY priority DESC, "Reported At" ASC',
            f"Escalated {tower} work awaiting or in progress at L2.",
        ))

    # At-risk: past 75% of the resolution target, clock still running.
    for p, (_resp, res) in D.SLA_TARGETS.items():
        threshold = int(res * 0.75)
        f.append((
            f"ITSM - {p} at risk (past 75% of target)",
            f'project = {P} AND priority = "{D.PRIORITY_LABELS[p]}" AND statusCategory != Done '
            f'AND status NOT IN ({_PAUSED_JQL}) '
            f'AND "Reported At" <= -{threshold}h ORDER BY "Reported At" ASC',
            f"{D.PRIORITY_LABELS[p]} tickets past {threshold}h of a {res}h resolution "
            f"target with the clock still running.",
        ))

    return f


def ensure_filter(w, name, jql, desc, existing):
    if name in existing:
        fid = existing[name]
        w.put(f"/rest/api/3/filter/{fid}",
              {"name": name, "jql": jql, "description": desc})
        return fid, False
    res = w.post("/rest/api/3/filter",
                 {"name": name, "jql": jql, "description": desc,
                  "favourite": True,
                  "sharePermissions": [{"type": "authenticated"}]})
    return res["id"], True


def list_all_filters(j):
    """Paginate - the instance already carries OPS's 20 plus template filters."""
    out, start = {}, 0
    while True:
        page = j.try_get(
            f"/rest/api/3/filter/search?maxResults=100&startAt={start}", {}) or {}
        for f in page.get("values", []):
            out[f["name"]] = f["id"]
        if page.get("isLast", True) or not page.get("values"):
            break
        start += len(page["values"])
    return out


# ---------------------------------------------------------------------------
# 1. agent queues
# ---------------------------------------------------------------------------
# The internal endpoint auto-prepends `project = ITSM` into completeJql, so the
# jql below must NOT carry its own project clause or it is doubled.

QUEUE_COLS = ["issuekey", "summary", "priority", "status", "assignee",
              "customfield_10042", "customfield_10043", "customfield_10057"]


def build_queues():
    q = [
        ("L1 Queue",
         'resolution = Unresolved AND "Support Tier" = L1 '
         'ORDER BY priority DESC, "Reported At" ASC'),
        ("L2 Queue - All Towers",
         'resolution = Unresolved AND "Support Tier" = L2 '
         'ORDER BY priority DESC, "Reported At" ASC'),
    ]
    for tower, _ in D.TOWERS:
        q.append((
            f"L2 - {tower}",
            f'resolution = Unresolved AND "Support Tier" = L2 AND Tower = "{tower}" '
            f'ORDER BY priority DESC, "Reported At" ASC',
        ))
    q += [
        ("Major Incidents",
         'resolution = Unresolved AND Impact = High AND Urgency = High '
         'ORDER BY "Reported At" DESC'),
        ("SLA Breached - Resolution",
         '"Resolution SLA" = Breached ORDER BY "Reported At" DESC'),
        ("Aged Backlog - 14 days and older",
         'resolution = Unresolved AND "Reported At" <= -14d ORDER BY "Reported At" ASC'),
        ("KB Gap - Escalated, no article found",
         '"KB Article Checked" = "Yes - none found" ORDER BY "Reported At" DESC'),
    ]
    return q


def ensure_queues(w, state):
    j = w.j
    """Create or update agent queues.

    NO DELETE EXISTS over REST or GraphQL on this instance, so a botched name is
    permanent. Everything here is therefore check-then-PUT, never create-then-fix.
    """
    live = j.try_get(f"/rest/servicedeskapi/servicedesk/{SERVICE_DESK_ID}/queue", {}) or {}
    by_name = {x["name"]: x["id"] for x in live.get("values", [])}
    log(f"  {len(by_name)} queues already on service desk {SERVICE_DESK_ID}: "
        f"{', '.join(sorted(by_name))}")

    ids, created, updated, failed = {}, 0, 0, 0
    for name, jql in build_queues():
        body = {"name": name, "jql": jql, "columns": QUEUE_COLS}
        try:
            if name in by_name:
                qid = by_name[name]
                w.put(f"/rest/servicedesk/1/servicedesk/{P}/queues/{qid}", body)
                ids[name], updated = qid, updated + 1
                log(f"  = {name}")
            else:
                res = w.post(f"/rest/servicedesk/1/servicedesk/{P}/queues", body)
                ids[name], created = res["id"], created + 1
                log(f"  + {name} (id {res['id']})")
        except RuntimeError as e:
            failed += 1
            log(f"  ! {name}: {str(e)[:200]}")

    state["queues"] = ids
    log(f"  queues: {created} created, {updated} updated, {failed} failed")
    return ids


# ---------------------------------------------------------------------------
# 3. dashboard
# ---------------------------------------------------------------------------

G = "rest/gadgets/1.0/g/com.atlassian.jira.gadgets:"
URI = {
    "filter-results": G + "filter-results-gadget/gadgets/filter-results-gadget.xml",
    "pie": G + "pie-chart-gadget/gadgets/piechart-gadget.xml",
    "two-dim": G + "two-dimensional-stats-gadget/gadgets/two-dimensional-stats-gadget.xml",
    "stats": G + "stats-gadget/gadgets/stats-gadget.xml",
    "heat-map": G + "heat-map-gadget/gadgets/heatmap-gadget.xml",
}
# JSM-specific dashboard items are addressed by moduleKey, not uri.
MODULE = {
    "filter-count": "com.atlassian.servicedesk.dashboard-items-plugin:"
                    "filter-count-dashboard-item",
}

F_TOWER = "customfield_10042"
F_TIER = "customfield_10043"
F_RES_SLA = "customfield_10051"
F_KB = "customfield_10047"
F_INTAKE = "customfield_10045"


def build_gadgets():
    """(label, kind, filter name, config-without-filterId, row, column).

    Covers the five briefed views: volume by tower, escalation split L1 vs L2,
    SLA breach, aged backlog, KB gap.
    """
    return [
        # --- left column: the charts that answer "what is the shape of demand" ---
        ("Volume by tower", "pie", "ITSM - L1 queue (open)",
         {"statType": F_TOWER}, 0, 0),
        ("Escalation split: tower x L1/L2", "two-dim", "ITSM - Escalated in last 30 days",
         {"xstattype": F_TOWER, "ystattype": F_TIER,
          "sortDirection": "desc", "sortBy": "total", "numberToShow": "10"}, 1, 0),
        # NOTE "priorities", not "priority". The classic gadget stat vocabulary is
        # plural for the system fields (priorities / statuses / assignees) and does
        # NOT match JQL field names. Validated against /rest/gadget/1.0/statTypes.
        ("Open work by priority", "stats", "ITSM - L1 queue (open)",
         {"statType": "priorities"}, 2, 0),
        ("Resolution SLA outcome", "pie", "ITSM - SLA breached (resolution)",
         {"statType": F_RES_SLA}, 3, 0),
        ("Intake channel mix", "pie", "ITSM - Intake via chat (shadow support pulled in)",
         {"statType": F_INTAKE}, 4, 0),

        # --- right column: the queues an agent actually works ---
        ("SLA breached - resolution", "filter-results", "ITSM - SLA breached (resolution)",
         {"num": "15",
          "columnNames": "issuekey|summary|priority|status|" + F_TOWER + "|" + F_TIER},
         0, 1),
        ("Aged backlog over 14 days", "filter-results", "ITSM - Aged backlog over 14 days",
         {"num": "15",
          "columnNames": "issuekey|summary|priority|status|" + F_TOWER + "|assignee"},
         1, 1),
        ("KB gap queue", "filter-results", "ITSM - Escalated with no KB article found",
         {"num": "15",
          "columnNames": "issuekey|summary|" + F_TOWER + "|" + F_KB + "|assignee"},
         2, 1),
        ("Major incidents", "filter-results",
         "ITSM - Major incidents (Impact High + Urgency High)",
         {"num": "10", "columnNames": "issuekey|summary|status|" + F_TOWER}, 3, 1),
        ("L2 queue - all towers", "filter-results", "ITSM - L2 queue (open)",
         {"num": "10",
          "columnNames": "issuekey|summary|priority|status|" + F_TOWER}, 4, 1),
        ("KB gap by tower (heat map)", "heat-map",
         "ITSM - Escalated with no KB article found",
         {"statType": F_TOWER}, 5, 1),
    ]


def validate_stat_types(j):
    """Assert every statType/xstattype/ystattype we use is one Jira accepts.

    A wrong value is NOT rejected by the config PUT - the property round-trips
    happily and the gadget then renders broken on the dashboard. The only way to
    catch it is to check against the live vocabulary, which is plural for system
    fields ("priorities", not "priority") and does not match JQL field names.
    """
    live = j.try_get("/rest/gadget/1.0/statTypes")
    if not live:
        log("  ~ /rest/gadget/1.0/statTypes unavailable - statTypes NOT validated")
        return
    valid = {str(v.get("value")) for v in (live.get("stats") or live)}
    bad = []
    for label, _kind, _f, cfg, _r, _c in build_gadgets():
        for key in ("statType", "xstattype", "ystattype"):
            if key in cfg and cfg[key] not in valid:
                bad.append(f"{label}: {key}={cfg[key]!r} is not a valid stat type")
    if bad:
        for b in bad:
            log(f"  !! {b}")
        sys.exit("ABORTING - a gadget would have rendered broken. Fix build_gadgets().")
    log(f"  statTypes validated against {len(valid)} live values")


def ensure_dashboard(w, state, filter_ids):
    j = w.j
    validate_stat_types(j)
    dashes = j.try_get("/rest/api/3/dashboard/search?maxResults=100", {}) or {}
    hit = [d for d in dashes.get("values", []) if d["name"] == DASH_NAME]
    if hit:
        did = hit[0]["id"]
        log(f"  = dashboard exists ({did})")
    else:
        d = w.post("/rest/api/3/dashboard", {
            "name": DASH_NAME,
            "description": "L1/L2 control tower for the ITSM service project. Every "
                           "date window keys off Reported At, never created.",
            "sharePermissions": [{"type": "authenticated"}]})
        did = d["id"]
        log(f"  + dashboard created ({did})")
    state["dashboard_id"] = did

    # Reconcile: drop every gadget on OUR dashboard and re-add, so a re-run does
    # not stack duplicates. Scoped to this dashboard id only - never OPS's.
    if hit:
        old = (j.try_get(f"/rest/api/3/dashboard/{did}/gadget", {}) or {}).get("gadgets", [])
        for g in old:
            try:
                w.delete(f"/rest/api/3/dashboard/{did}/gadget/{g['id']}")
            except RuntimeError as e:
                log(f"  ! could not clear gadget {g['id']}: {str(e)[:120]}")
        if old:
            log(f"  - cleared {len(old)} existing gadget(s) for a clean rebuild")

    worked, config_failed, add_failed = [], [], []
    for label, kind, fname, cfg, row, col in build_gadgets():
        fid = filter_ids.get(fname)
        if not fid:
            add_failed.append(f"{label} (filter '{fname}' missing)")
            continue
        payload = {"color": "blue", "title": label,
                   "position": {"row": row, "column": col}}
        if kind in URI:
            payload["uri"] = URI[kind]
        else:
            payload["moduleKey"] = MODULE[kind]
        try:
            g = w.post(f"/rest/api/3/dashboard/{did}/gadget", payload)
            gid = g["id"]
        except RuntimeError as e:
            add_failed.append(f"{label} [{kind}]: {str(e)[:120]}")
            log(f"  ! add {label}: {str(e)[:150]}")
            continue

        full = dict(cfg)
        full["filterId"] = f"filter-{fid}"
        try:
            w.put(f"/rest/api/3/dashboard/{did}/items/{gid}/properties/config", full)
            # The read-back is the proof the gadget is really bound to its filter.
            # A dry run created no gadget, so there is nothing to read back and the
            # GET would 404 on a placeholder id - skip it rather than fake a pass.
            if not w.dry:
                back = j.get(f"/rest/api/3/dashboard/{did}/items/{gid}/properties/config")
                if back.get("value", {}).get("filterId") != full["filterId"]:
                    raise RuntimeError("config did not round-trip")
            worked.append(f"{label} [{kind}]")
            log(f"  + {label} [{kind}] -> filter {fid}")
        except RuntimeError as e:
            config_failed.append(f"{label} [{kind}]: {str(e)[:120]}")
            log(f"  ~ {label} [{kind}] added but NOT configured: {str(e)[:120]}")

    state["gadgets"] = worked
    log(f"  gadgets: {len(worked)} configured, {len(config_failed)} unconfigured, "
        f"{len(add_failed)} not added")
    return did, worked, config_failed, add_failed


# ---------------------------------------------------------------------------
# 4. portal: organization + customers
# ---------------------------------------------------------------------------

def ensure_portal(w, state):
    j = w.j
    """Create one organization, link it to the service desk, and add the existing
    admin account as a portal customer.

    DELIBERATELY NOT DONE: provisioning NEW portal customer accounts.
    POST /rest/servicedeskapi/customer creates a real Atlassian account and emails a
    signup invitation to the address, and servicedeskapi exposes no delete for it -
    cleanup requires manual work in admin.atlassian.com. Creating accounts and
    sending mail on the user's behalf is not something this script should do
    unattended. The endpoint IS reachable and permission-granted; see the report.
    """
    orgs = j.try_get("/rest/servicedeskapi/organization?limit=50", {}) or {}
    hit = [o for o in orgs.get("values", []) if o["name"] == ORG_NAME]
    if hit:
        oid = hit[0]["id"]
        log(f"  = organization '{ORG_NAME}' exists (id {oid})")
    else:
        o = w.post("/rest/servicedeskapi/organization", {"name": ORG_NAME})
        oid = o["id"]
        log(f"  + organization '{ORG_NAME}' (id {oid})")
    state["organization_id"] = oid

    linked = j.try_get(
        f"/rest/servicedeskapi/servicedesk/{SERVICE_DESK_ID}/organization?limit=50", {}) or {}
    if any(o["id"] == oid for o in linked.get("values", [])):
        log(f"  = organization already linked to service desk {SERVICE_DESK_ID}")
    else:
        try:
            w.post(f"/rest/servicedeskapi/servicedesk/{SERVICE_DESK_ID}/organization",
                   {"organizationId": int(oid)})
            log(f"  + organization linked to service desk {SERVICE_DESK_ID}")
        except RuntimeError as e:
            log(f"  ! link organization: {str(e)[:200]}")

    me = j.get("/rest/api/3/myself")["accountId"]
    try:
        w.post(f"/rest/servicedeskapi/servicedesk/{SERVICE_DESK_ID}/customer",
               {"accountIds": [me]})
        log("  + admin account added as a portal customer")
    except RuntimeError as e:
        log(f"  ~ add customer: {str(e)[:160]}")
    state["portal_customer_accounts"] = [me]
    return oid


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def verify(j, filter_ids, queue_ids):
    log("\n== verify ==")
    empty, errored = [], []
    for name in sorted(filter_ids):
        fid = filter_ids[name]
        f = j.try_get(f"/rest/api/3/filter/{fid}?expand=jql")
        if not f:
            errored.append(f"{name}: filter {fid} does not resolve")
            continue
        try:
            n = j.post("/rest/api/3/search/approximate-count", {"jql": f["jql"]})["count"]
        except RuntimeError as e:
            errored.append(f"{name}: JQL rejected - {str(e)[:120]}")
            continue
        if n == 0:
            empty.append(name)
        log(f"  {n:>5}  {name}")

    live = j.try_get(f"/rest/servicedeskapi/servicedesk/{SERVICE_DESK_ID}/queue"
                     f"?includeCount=true", {}) or {}
    counts = {x["name"]: x.get("issueCount") for x in live.get("values", [])}
    log("\n  -- agent queues (live counts) --")
    for name in queue_ids:
        log(f"  {str(counts.get(name, '?')):>5}  {name}")

    return empty, errored


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="jira_config.jsm_views")
    ap.add_argument("--skip-queues", action="store_true",
                    help="queues are PERMANENT (no REST delete) - skip to avoid them")
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    args = ap.parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    state = load_state()
    ops = load_ops_state()

    log("== OPS guard (pre) ==")
    guard_ops(j, ops, "pre")

    log("\n== agent queues ==")
    if args.skip_queues:
        log("  skipped (--skip-queues)")
        queue_ids = state.get("queues", {})
    else:
        queue_ids = ensure_queues(w, state)
    save_state(state, args.dry_run)

    log("\n== saved filters ==")
    existing = list_all_filters(j)
    filter_ids = {}
    for name, jql, desc in build_filters():
        try:
            fid, is_new = ensure_filter(w, name, jql, desc, existing)
            filter_ids[name] = fid
            log(f"  {'+' if is_new else '='} {name}")
        except RuntimeError as e:
            log(f"  ! {name}: {str(e)[:200]}")
    state["filters"] = filter_ids
    save_state(state, args.dry_run)

    log("\n== dashboard ==")
    did, worked, cfg_failed, add_failed = ensure_dashboard(w, state, filter_ids)
    save_state(state, args.dry_run)

    log("\n== portal ==")
    ensure_portal(w, state)
    save_state(state, args.dry_run)

    empty, errored = verify(j, filter_ids, queue_ids)

    log("\n== OPS guard (post) ==")
    guard_ops(j, ops, "post")

    site = j.site
    log("\n== open these ==")
    log(f"  Dashboard: {site}/jira/dashboards/{did}")
    log(f"  Agent queues: {site}/jira/servicedesk/projects/{P}/queues")
    log(f"  Project: {site}/browse/{P}")
    log(f"  Portal: {site}/servicedesk/customer/portal/{SERVICE_DESK_ID}")
    log(f"  Filters: {site}/jira/filters")

    log(f"\n  {len(filter_ids)} filters, {len(queue_ids)} queues, "
        f"{len(worked)} configured gadgets")
    if empty:
        log(f"  EMPTY filters ({len(empty)}): {', '.join(empty)}")
    if errored:
        for e in errored:
            log(f"  ERROR: {e}")
    if cfg_failed:
        for e in cfg_failed:
            log(f"  UNCONFIGURED GADGET: {e}")
    if add_failed:
        for e in add_failed:
            log(f"  GADGET NOT ADDED: {e}")
    log("\n  %d write(s) issued%s"
        % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
