#!/usr/bin/env python3
"""Seed the real SFC project with Salesforce Config Requests + Org Deploy sub-tasks.

This is the live-Jira counterpart of app/sfc_seed.py. It REUSES that module's
build() as the single source of truth for the data shape, so a real request and a
preview request are identical by construction — the panels cannot tell them apart,
and once these issues exist the "Delivery / SF Config" lens shows real Jira data.

Per request it: creates the "Salesforce Config Request", walks the DeliveryIQ
workflow to the record's status, then creates one "Org Deploy" sub-task per target
org (Model A) carrying that org's Deploy State / Config Health / Health Checked At /
Deploy Source. If the SFC workflow was not bound (the API declined and the UI step
is still pending), the transition walk simply finds no matching transitions and the
issue rests in the initial status — reported honestly, never silently.

    python3 -m fixtures.sfc_seed [--n 64] [--days 180] [--dry-run] [--workers 6]

Requires jira_config/state/.sfc_state.json — run `python3 -m jira_config.sfc_build`
first. The token is CI-only, so the intended path is the sfc-build.yml Action.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from shared.jira_client import Jira, adf, log, require_env
from jira_config import SFC_STATE as STATE
from jira_config import merge_state, read_state
from app.sfc_seed import build  # single source of truth for the record shape

REQUEST_TYPE = "Salesforce Config Request"
SUBTASK_TYPE = "Org Deploy"
PROJECT_KEY = "SFC"

# Status -> the transition names that reach it, walking the graph in
# jira_config.sfc_build.TRANSITIONS. Only statuses app/sfc_seed emits are listed.
PATHS = {
    "Intake": [],
    "In Build": ["Start build"],
    "In Review": ["Start build", "Submit for review"],
    "Awaiting CAB": ["Start build", "Submit for review", "Request CAB"],
    "Deploying": ["Start build", "Submit for review", "Request CAB", "Begin deploy"],
    "Deployed": ["Start build", "Submit for review", "Request CAB", "Begin deploy",
                 "Deploy succeeded"],
    "Deploy Failed": ["Start build", "Submit for review", "Request CAB", "Begin deploy",
                      "Deploy failed"],
    "Audit": ["Start build", "Submit for review", "Request CAB", "Begin deploy",
              "Deploy succeeded", "Enter audit"],
    "Done": ["Start build", "Submit for review", "Request CAB", "Begin deploy",
             "Deploy succeeded", "Enter audit", "Complete"],
    "Cancelled": ["Cancel"],
    "Rolled Back": ["Roll back"],
}

# record key -> (SFC field name, how to wrap the value). Wrappers:
#   "select"  -> {"value": v}          "multi" -> [{"value": x}, ...]
#   "date"    -> jira datetime string  "number" -> float   "text" -> str
#   "yesno"   -> {"value": "Yes"/"No"} for a boolean
REQUEST_MAP = [
    ("tower", "Delivery Squad", "select"),
    ("impact", "Impact", "select"),
    ("urgency", "Urgency", "select"),
    ("change_risk", "Change Risk", "select"),
    ("cab_approval", "CAB Approval", "select"),
    ("config_component_type", "Config Component Type", "multi"),
    ("target_orgs", "Target Orgs", "multi"),
    ("package_ref", "Package Ref", "text"),
    ("l2_analyst", "L2 Analyst", "text"),
    ("reported_at", "Reported At", "date"),
    ("first_response_at", "First Response At", "date"),
    ("escalated_at", "Escalated At", "date"),
    ("resolved_at", "Resolved At", "date"),
    ("build_tested", "Build Tested", "yesno"),
    ("comply_authorized", "Compliance Authorized", "yesno"),
    ("comply_evidence", "Compliance Evidence", "yesno"),
    ("evidence_pack_ready", "Evidence Pack Ready", "yesno"),
    ("coord_conflicts", "Coord Conflicts", "number"),
    ("coord_dependencies", "Coord Dependencies", "number"),
]

# org_deploys[] key -> (SFC field name, wrapper), for the Org Deploy sub-task.
SUBTASK_MAP = [
    ("deploy_state", "Deploy State", "select"),
    ("config_health", "Config Health", "select"),
    ("health_checked_at", "Health Checked At", "date"),
    ("source", "Deploy Source", "select"),
]


def jira_dt(iso):
    if not iso:
        return None
    dt = datetime.fromisoformat(iso)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def wrap(kind, value):
    if value is None:
        return None
    if kind == "select":
        return {"value": value}
    if kind == "multi":
        return [{"value": v} for v in value] or None
    if kind == "yesno":
        return {"value": "Yes" if value else "No"}
    if kind == "date":
        return jira_dt(value)
    if kind == "number":
        return float(value)
    return value  # text


def _apply(fields, F, settable, pairs, source):
    """Set each mapped field on `fields` if it exists and is settable on create."""
    for src_key, fname, kind in pairs:
        val = wrap(kind, source.get(src_key))
        if val is None:
            continue
        fid = F.get(fname)
        if fid and fid in settable:
            fields[fid] = val


def request_fields(rec, F, settable, allowed_priorities):
    fields = {
        "project": {"key": PROJECT_KEY},
        "issuetype": {"name": REQUEST_TYPE},
        "summary": rec["summary"],
        "description": adf(
            "Salesforce Config Request — %s.\n\n"
            "Stage %s (status %s). Change risk %s. Target orgs: %s.\n\n"
            "Impact %s / Urgency %s -> %s (derived)."
            % (rec["tower"], rec["stage"], rec["status"], rec["change_risk"],
               ", ".join(rec["target_orgs"]), rec["impact"], rec["urgency"],
               rec["priority"])),
    }
    # Native priority only if this instance's SFC scheme actually offers it by name.
    if rec.get("priority") in allowed_priorities:
        fields["priority"] = {"name": rec["priority"]}
    _apply(fields, F, settable, REQUEST_MAP, rec)
    return fields


def subtask_fields(parent_key, rec, dep, F, settable):
    fields = {
        "project": {"key": PROJECT_KEY},
        "issuetype": {"name": SUBTASK_TYPE},
        "parent": {"key": parent_key},
        "summary": "Deploy to %s — %s" % (dep["org"], parent_key),
    }
    _apply(fields, F, settable, SUBTASK_MAP, dep)
    return fields


def walk(j, key, steps):
    """Transition `key` along `steps`; return how many hops actually landed."""
    reached = 0
    for step in steps:
        avail = j.get("/rest/api/3/issue/%s/transitions" % key).get("transitions", [])
        match = next((x for x in avail if x["name"].lower() == step.lower()), None)
        if not match:
            break  # workflow not bound yet, or path diverged — stop honestly
        j.post("/rest/api/3/issue/%s/transitions" % key, {"transition": {"id": match["id"]}})
        reached += 1
    return reached


def create_request(j, rec, F, settable_req, settable_sub, allowed_priorities):
    issue = j.post("/rest/api/3/issue",
                   {"fields": request_fields(rec, F, settable_req, allowed_priorities)})
    key = issue["key"]
    reached = walk(j, key, PATHS.get(rec["status"], []))
    at_target = (reached == len(PATHS.get(rec["status"], [])))
    subs = 0
    for dep in rec["org_deploys"]:
        try:
            j.post("/rest/api/3/issue",
                   {"fields": subtask_fields(key, rec, dep, F, settable_sub)})
            subs += 1
        except RuntimeError as e:
            log("    ! sub-task on %s: %s" % (key, str(e)[:120]))
    return key, at_target, subs


def createmeta(j):
    """(settable-by-type, allowed-priority-names). Empty if createmeta is blank."""
    meta = j.get("/rest/api/3/issue/createmeta?projectKeys=%s"
                 "&expand=projects.issuetypes.fields" % PROJECT_KEY)
    per_type, priorities = {}, set()
    for p in meta.get("projects", []):
        for it in p.get("issuetypes", []):
            flds = it.get("fields", {})
            per_type[it["name"]] = set(flds.keys())
            for av in (flds.get("priority") or {}).get("allowedValues", []):
                if av.get("name"):
                    priorities.add(av["name"])
    return per_type, priorities


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fixtures.sfc_seed")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    require_env()
    j = Jira()
    if not STATE.exists():
        sys.exit("%s not found — run python3 -m jira_config.sfc_build first." % STATE.name)
    state = read_state(STATE)
    if "fields" not in state:
        sys.exit("%s has no 'fields' — re-run python3 -m jira_config.sfc_build." % STATE.name)
    F = state["fields"]

    now = datetime.now(timezone.utc)
    _, records = build(args.n, args.days, now)   # same generator the preview lens uses

    per_type, allowed_priorities = createmeta(j)
    settable_req = per_type.get(REQUEST_TYPE, set())
    settable_sub = per_type.get(SUBTASK_TYPE, set())
    usable = [n for r, n, _ in REQUEST_MAP if F.get(n) in settable_req]
    log("  %d request fields settable on create; %d org-deploy fields on the sub-task"
        % (len(usable), len([1 for r, n, _ in SUBTASK_MAP if F.get(n) in settable_sub])))
    if not settable_req:
        log("  ! createmeta returned no settable fields for %r — is the SFC project "
            "built and are you its lead? Continuing; issues may 400." % REQUEST_TYPE)

    total_subs = sum(len(r["org_deploys"]) for r in records)
    log("\n== plan ==")
    log("  %d Salesforce Config Requests + %d Org Deploy sub-tasks" % (len(records), total_subs))
    dist = {}
    for r in records:
        dist[r["status"]] = dist.get(r["status"], 0) + 1
    log("  status: " + "  ".join("%s:%d" % kv for kv in sorted(dist.items(), key=lambda x: -x[1])))
    if not allowed_priorities:
        log("  (native priority not offered by createmeta — requests seed without a priority)")

    if args.dry_run:
        log("\ndry run — nothing written")
        return

    log("\n== creating in Jira (%d workers) ==" % args.workers)
    ok, failed, at_target, subs_made = [], [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(create_request, j, r, F, settable_req, settable_sub,
                          allowed_priorities): r for r in records}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                key, hit, subs = fut.result()
                ok.append(key)
                at_target += 1 if hit else 0
                subs_made += subs
            except Exception as e:
                failed.append(str(e)[:160])
            if n % 20 == 0:
                log("  %d/%d  ok=%d failed=%d" % (n, len(records), len(ok), len(failed)))

    log("\n  created %d requests (%d reached their target status), %d sub-tasks, %d failed"
        % (len(ok), at_target, subs_made, len(failed)))
    for f in failed[:3]:
        log("    ! %s" % f)
    if ok and at_target == 0:
        log("  ! no request reached a non-initial status — the SFC workflow is not bound "
            "to the project yet. Finish the workflow-scheme step (see sfc_build output), "
            "then re-run, or transition in the UI.")
    state["seeded_requests"] = len(ok)
    state["seeded_subtasks"] = subs_made
    merge_state(STATE, state, ("seeded_requests", "seeded_subtasks"), dry=args.dry_run)


if __name__ == "__main__":
    main()
