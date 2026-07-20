#!/usr/bin/env python3
"""Build the ITSM JSM service project - the L1/L2 control tower on Jira Service Management.

Idempotent - safe to re-run. Every step is check-then-act; nothing is duplicated.

REUSE, NEVER RECREATE. OPS is live and demoed tomorrow. The 20 tower custom fields,
the P1-P4 priorities and the priority scheme are GLOBAL objects that OPS depends on.
This script reads their ids out of state/.build_state.json and reuses them; it never creates
a second copy and never deletes anything. Two hard guards enforce that:

  * guard_ops()      - asserts OPS, its issue types, its workflow and P1-P4 are intact
                       before any write and again after the last one.
  * screen scoping   - fields are only ever added to screens reachable from ITSM's own
                       issue type screen scheme, and the script aborts if any of those
                       screens is also reachable from OPS's.

Writes jira_config/state/.jsm_state.json.
Never touches jira_config/state/.build_state.json.

Usage:  python3 -m jira_config.jsm_build
"""

import argparse
import json
import sys
import time

from shared.jira_client import Jira, log, require_env
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as OPS_STATE, JSM_STATE as STATE
from jira_config.reconcile import Writer


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


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
        found = j.try_get(
            "/rest/api/3/workflow/search?maxResults=200", {}) or {}
        names = {w.get("id", {}).get("name") for w in found.get("values", [])}
        if wf_name not in names:
            problems.append(f"workflow '{wf_name}' not found")

    if problems:
        for p in problems:
            log(f"  !! OPS GUARD ({when}): {p}")
        sys.exit("ABORTING - OPS integrity check failed. Nothing further was written.")
    log(f"  OPS intact ({when}): project, {len(ops['fields'])} fields, "
        f"{len(ops.get('priorities', {}))} priorities, workflow")


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------

def ensure_project(w, state):
    j = w.j
    existing = j.try_get(f"/rest/api/3/project/{S.JSM_PROJECT_KEY}")
    if existing and existing.get("key") == S.JSM_PROJECT_KEY:
        log(f"  = project {S.JSM_PROJECT_KEY} exists (id {existing['id']}, "
            f"type {existing.get('projectTypeKey')})")
        state["project_id"] = existing["id"]
        return existing["id"]

    me = j.get("/rest/api/3/myself")["accountId"]
    res = w.post("/rest/api/3/project", {
        "key": S.JSM_PROJECT_KEY,
        "name": S.JSM_PROJECT_NAME,
        "projectTypeKey": "service_desk",
        "projectTemplateKey": S.JSM_TEMPLATE,
        "leadAccountId": me,
        "assigneeType": "PROJECT_LEAD",
        "description": "L1/L2 control tower on JSM. Built by jira_config/jsm_build.py.",
    })
    pid = str(res["id"])
    log(f"  + created project {S.JSM_PROJECT_KEY} (id {pid})")

    # Project creation is ASYNC - issue types and screens are not populated at 201.
    for attempt in range(12):
        time.sleep(3)
        p = j.try_get(f"/rest/api/3/project/{S.JSM_PROJECT_KEY}") or {}
        if len(p.get("issueTypes", [])) >= 5:
            log(f"  provisioned after ~{(attempt + 1) * 3}s "
                f"({len(p['issueTypes'])} issue types)")
            break
    else:
        log("  ! project still provisioning; re-run this script to finish setup")

    state["project_id"] = pid
    return pid


def find_service_desk(j, project_id, state):
    for sd in (j.try_get("/rest/servicedeskapi/servicedesk", {}) or {}).get("values", []):
        if str(sd.get("projectId")) == str(project_id):
            log(f"  = service desk id {sd['id']} (portal {sd.get('projectKey')})")
            state["service_desk_id"] = str(sd["id"])
            return str(sd["id"])
    log("  ! no service desk found for the project yet")
    return None


def ensure_post_incident_review(w, project_id, state):
    j = w.j
    """Add [System] Post-incident review to ITSM's OWN issue type scheme.

    Guarded: the scheme must be bound to ITSM and nothing else, so this can never
    reach into a scheme OPS shares.
    """
    res = j.try_get(f"/rest/api/3/issuetypescheme/project?projectId={project_id}", {}) or {}
    vals = res.get("values", [])
    if not vals:
        log("  ! no issue type scheme found for the project")
        return None

    scheme = vals[0]["issueTypeScheme"]
    sid, bound = scheme["id"], [str(x) for x in vals[0].get("projectIds", [])]
    state["issue_type_scheme_id"] = str(sid)

    if bound != [str(project_id)]:
        log(f"  ! scheme {sid} is shared with projects {bound} - NOT modifying it")
        return sid

    proj = j.get(f"/rest/api/3/project/{S.JSM_PROJECT_KEY}")
    have = {t["id"] for t in proj.get("issueTypes", [])}
    if S.PIR_ISSUE_TYPE_ID in have:
        log(f"  = [System] Post-incident review already on scheme {sid}")
        return sid

    w.put(f"/rest/api/3/issuetypescheme/{sid}/issuetype",
          {"issueTypeIds": [S.PIR_ISSUE_TYPE_ID]})
    log(f"  + [System] Post-incident review ({S.PIR_ISSUE_TYPE_ID}) added to scheme {sid}")
    return sid


# ---------------------------------------------------------------------------
# fields (reuse only)
# ---------------------------------------------------------------------------

def resolve_fields(j, ops):
    """Map the tower schema onto the EXISTING global field ids. Creates nothing."""
    by_id = {f["id"]: f for f in j.get("/rest/api/3/field")}
    out, missing = {}, []
    for name in S.SCREEN_FIELD_ORDER:
        fid = ops["fields"].get(name)
        if not fid:
            missing.append(f"{name} (absent from state/.build_state.json)")
        elif fid not in by_id:
            missing.append(f"{name} ({fid} not on the instance)")
        else:
            out[name] = fid
    if missing:
        for m in missing:
            log(f"  !! {m}")
        sys.exit("ABORTING - refusing to recreate OPS fields. Fix jira_config/state/.build_state.json.")

    # A global context is what makes reuse work: the field is valid in every project
    # and on every issue type, so ITSM needs no context change at all.
    non_global = []
    for name, fid in out.items():
        ctxs = (j.try_get(f"/rest/api/3/field/{fid}/context", {}) or {}).get("values", [])
        if not any(c.get("isGlobalContext") for c in ctxs):
            non_global.append(name)
    if non_global:
        log(f"  ! not globally scoped, may not appear in ITSM: {', '.join(non_global)}")
    else:
        log(f"  {len(out)} fields resolved, all on global contexts - reusable as-is")
    return out


# ---------------------------------------------------------------------------
# screens
# ---------------------------------------------------------------------------

def project_screen_ids(j, project_id):
    """Every screen reachable from a project's issue type screen scheme."""
    res = j.try_get(
        f"/rest/api/3/issuetypescreenscheme/project?projectId={project_id}", {}) or {}
    vals = res.get("values", [])
    if not vals:
        return None, set()
    itss_id = vals[0]["issueTypeScreenScheme"]["id"]

    mapping = j.try_get(
        f"/rest/api/3/issuetypescreenscheme/mapping"
        f"?issueTypeScreenSchemeId={itss_id}&maxResults=100", {}) or {}
    ss_ids = {str(m["screenSchemeId"]) for m in mapping.get("values", [])}
    if not ss_ids:
        return itss_id, set()

    q = "&".join(f"id={i}" for i in sorted(ss_ids))
    schemes = j.try_get(f"/rest/api/3/screenscheme?{q}&maxResults=100", {}) or {}
    screens = set()
    for s in schemes.get("values", []):
        for sid in (s.get("screens") or {}).values():
            screens.add(str(sid))
    return itss_id, screens


def add_fields_to_screens(w, screen_ids, fields, state):
    j = w.j
    """Put the tower fields on ITSM's screens so REST can set them on create."""
    added, touched = 0, {}
    for sid in sorted(screen_ids, key=int):
        tabs = j.try_get(f"/rest/api/3/screens/{sid}/tabs", []) or []
        if not tabs:
            continue
        tab = tabs[0]["id"]
        present = {f["id"] for f in
                   (j.try_get(f"/rest/api/3/screens/{sid}/tabs/{tab}/fields", []) or [])}
        n = 0
        for name in S.SCREEN_FIELD_ORDER:
            fid = fields[name]
            if fid in present:
                continue
            try:
                w.post(f"/rest/api/3/screens/{sid}/tabs/{tab}/fields", {"fieldId": fid})
                n += 1
            except RuntimeError as e:
                # Already on another tab of the same screen, or not addable there.
                log(f"    - {name} on screen {sid}: {str(e)[:90]}")
        touched[str(sid)] = len(present | set(fields.values()))
        added += n
        log(f"  screen {sid}: +{n} fields ({len(present)} were already there)")
    state["screens"] = touched
    return added


# ---------------------------------------------------------------------------
# priorities
# ---------------------------------------------------------------------------

def apply_priority_scheme(w, ops, project_id, state):
    j = w.j
    """Associate ITSM with OPS's existing P1-P4 scheme. Additive only.

    The scheme's project list is snapshotted before and re-checked after; if OPS
    were to drop out of it the script aborts rather than leaving the live project
    on a scheme it no longer belongs to.
    """
    sid = ops.get("priority_scheme_id")
    if not sid:
        log("  ! no priority_scheme_id in state/.build_state.json - skipping")
        return None

    def projects():
        r = j.try_get(f"/rest/api/3/priorityscheme/{sid}/projects?maxResults=50", {}) or {}
        return {str(p["id"]) for p in r.get("values", [])}

    before = projects()
    if str(ops["project_id"]) not in before:
        log(f"  ! OPS is not on scheme {sid} - refusing to modify it")
        return None

    if str(project_id) in before:
        log(f"  = ITSM already on priority scheme {sid}")
        state["priority_scheme_id"] = str(sid)
        return sid

    # Payload shape is fussy and the error messages are unhelpful (a bare 400 "Invalid
    # request payload"). Two things are required and neither is obvious:
    #   * projects.add must be an OBJECT {"ids": [...]}, not a bare list;
    #   * a top-level mappings.in is mandatory even for a project with zero issues,
    #     because Jira insists on a landing priority for every built-in it is removing.
    p = ops["priorities"]
    mappings = {
        "1": int(p["P1 - Critical"]),  # Highest
        "2": int(p["P2 - High"]),      # High
        "3": int(p["P3 - Medium"]),    # Medium
        "4": int(p["P4 - Low"]),       # Low
        "5": int(p["P4 - Low"]),       # Lowest
    }
    try:
        w.put(f"/rest/api/3/priorityscheme/{sid}", {
            "projects": {"add": {"ids": [int(project_id)]}},
            "mappings": {"in": mappings},
        })
    except RuntimeError as e:
        log(f"  ! association failed: {str(e)[:200]}")
        return None

    # Association is applied asynchronously by a background task.
    for _ in range(10):
        time.sleep(2)
        after = projects()
        if str(project_id) in after:
            break
    else:
        after = projects()

    if str(ops["project_id"]) not in after:
        sys.exit(f"ABORTING - OPS fell off priority scheme {sid}. Restore it immediately.")
    if str(project_id) not in after:
        log(f"  ! ITSM did not appear on scheme {sid}; OPS is still safely attached")
        return None

    log(f"  + ITSM added to priority scheme {sid} (OPS still attached)")
    state["priority_scheme_id"] = str(sid)
    return sid


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def verify_createmeta(j, fields, state):
    """The only proof that matters: are the fields settable on create, per issue type?"""
    types = j.get(f"/rest/api/3/project/{S.JSM_PROJECT_KEY}").get("issueTypes", [])
    wanted = set(fields.values())
    report, worst = {}, None
    for t in types:
        if t.get("subtask"):
            continue
        meta = j.try_get(
            f"/rest/api/3/issue/createmeta/{S.JSM_PROJECT_KEY}/issuetypes/{t['id']}"
            f"?maxResults=200", {}) or {}
        have = {f["fieldId"] for f in meta.get("fields", [])}
        hit = len(wanted & have)
        report[t["name"]] = hit
        if worst is None or hit < worst[1]:
            worst = (t["name"], hit, sorted(n for n, i in fields.items() if i not in have))
        log(f"  {t['name']:<34} {hit}/{len(wanted)} tower fields on create")
    state["createmeta"] = report
    if worst and worst[1] < len(wanted):
        log(f"  missing on '{worst[0]}': {', '.join(worst[2])}")
    return report


def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(
        argparse.ArgumentParser(prog="jira_config.jsm_build")).parse_args(argv)
    dry = args.dry_run

    require_env()
    j = Jira()
    w = Writer(j, dry=dry)
    ops = load_ops_state()
    state = load_state()

    log("== OPS pre-flight guard ==")
    guard_ops(j, ops, "before")

    log("== project ==")
    pid = ensure_project(w, state)
    state["project_key"] = S.JSM_PROJECT_KEY
    state["project_name"] = S.JSM_PROJECT_NAME
    state["template"] = S.JSM_TEMPLATE
    save_state(state, dry)

    log("== service desk ==")
    find_service_desk(j, pid, state)

    log("== issue types ==")
    ensure_post_incident_review(w, pid, state)
    proj = j.get(f"/rest/api/3/project/{S.JSM_PROJECT_KEY}")
    state["issue_types"] = {t["name"]: t["id"] for t in proj.get("issueTypes", [])}
    for n, i in sorted(state["issue_types"].items()):
        log(f"  = {n:<38} {i}")
    save_state(state, dry)

    log("== tower fields (reused, not recreated) ==")
    fields = resolve_fields(j, ops)
    state["fields"] = fields
    save_state(state, dry)

    log("== screens ==")
    itss_id, screens = project_screen_ids(j, pid)
    state["issue_type_screen_scheme_id"] = str(itss_id) if itss_id else None
    _, ops_screens = project_screen_ids(j, ops["project_id"])
    shared = screens & ops_screens
    if shared:
        sys.exit(f"ABORTING - screens {sorted(shared)} are shared with OPS. "
                 f"Editing them would change the live project.")
    log(f"  {len(screens)} ITSM screens, none shared with OPS "
        f"({len(ops_screens)} OPS screens untouched)")
    n = add_fields_to_screens(w, screens, fields, state)
    log(f"  {n} field/screen associations added")
    save_state(state, dry)

    log("== priority scheme ==")
    apply_priority_scheme(w, ops, pid, state)
    save_state(state, dry)

    log("== verify: fields settable on create ==")
    verify_createmeta(j, fields, state)

    log("== OPS post-flight guard ==")
    guard_ops(j, ops, "after")

    save_state(state, dry)
    log("\n%d writes%s" % (w.writes,
                          " [DRY RUN - none applied]" if dry else ""))
    if not dry:
        log(f"state written to {STATE.name}")
    log(f"portal/agent view: see Project settings > SLAs, Queues and Request types "
        f"for the UI-only steps.")


if __name__ == "__main__":
    main()
