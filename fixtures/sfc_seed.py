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

Resolves field ids by NAME from the live instance (no build-artifact/state file), so
it runs standalone in its own CI job — but the SFC project + fields + bound workflow
must already exist, so run `python3 -m jira_config.sfc_build` first. The token is
CI-only, so the intended path is the sfc-build.yml Action (mode=seed).
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from shared.jira_client import Jira, adf, log, require_env
from shared import fields as SF          # disambiguates the OPS-shared field names
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
    walk(j, key, PATHS.get(rec["status"], []))
    # Confirm the issue actually LANDED in the intended status. reached==len(path) is
    # not enough: an Intake-target record has an EMPTY path and would look "at target"
    # even if the workflow is unbound and the issue is really sitting in the template's
    # default "To Do". Re-read the real status so the unbound-workflow diagnostic is
    # honest.
    try:
        final = j.get("/rest/api/3/issue/%s?fields=status" % key)["fields"]["status"]["name"]
    except (RuntimeError, KeyError, TypeError):
        final = None
    at_target = (final == rec["status"])
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
    """(settable-by-type, allowed-priority-names).

    Prefers the paginated GET /createmeta/{key}/issuetypes[/{id}] endpoints (the
    classic ?expand=projects.issuetypes.fields form is deprecated and being removed
    from Jira Cloud). Falls back to the classic form, then returns (None, ...) if
    BOTH are unavailable so the caller can abort with a clear message rather than
    mass-create field-less shells.
    """
    per_type, priorities = {}, set()

    def note_priority(field_entry):
        for av in (field_entry or {}).get("allowedValues", []):
            if av.get("name"):
                priorities.add(av["name"])

    # 1. Newer paginated endpoint.
    its = j.try_get("/rest/api/3/issue/createmeta/%s/issuetypes" % PROJECT_KEY, None)
    if its and its.get("issueTypes"):
        for it in its["issueTypes"]:
            name, tid, fids = it.get("name"), it.get("id"), set()
            start = 0
            while True:
                page = j.try_get(
                    "/rest/api/3/issue/createmeta/%s/issuetypes/%s?maxResults=100&startAt=%d"
                    % (PROJECT_KEY, tid, start), {}) or {}
                flds = page.get("fields", [])
                for f in flds:
                    fid = f.get("fieldId") or f.get("key")
                    if fid:
                        fids.add(fid)
                    if fid == "priority":
                        note_priority(f)
                if page.get("isLast", True) or not flds:
                    break
                start += len(flds)
            per_type[name] = fids
        return per_type, priorities

    # 2. Classic (deprecated) fallback.
    meta = j.try_get("/rest/api/3/issue/createmeta?projectKeys=%s"
                     "&expand=projects.issuetypes.fields" % PROJECT_KEY, None)
    if meta and meta.get("projects"):
        for p in meta["projects"]:
            for it in p.get("issuetypes", []):
                flds = it.get("fields", {})
                per_type[it["name"]] = set(flds.keys())
                note_priority(flds.get("priority"))
        return per_type, priorities

    # 3. Neither available.
    return None, priorities


def resolve_fields(j):
    """Resolve every SFC field NAME the seeder sets to a customfield id, from the live
    instance — no build-artifact/state file required.

    This matches the repo's own principle (shared/fields.py): the contract between the
    configurator and everything downstream is the field NAME; ids are per-instance. It
    also means the seeder runs in a different CI job than sfc_build without needing the
    ephemeral .sfc_state.json. SFC-owned names are unique on the instance, so a plain
    name->id map is safe for them; the OPS-shared names (Impact/Urgency/L2 Analyst/the
    four dates) are disambiguated through shared.fields.resolve (this instance has two
    "Urgency" fields). Returns (name->id, [unresolved names]).
    """
    allcf = {}
    for f in j.get("/rest/api/3/field"):
        if f.get("custom"):
            allcf.setdefault(f["name"], f["id"])  # first-wins; SFC names are unique
    try:
        shared = SF.resolve(j)
    except SF.FieldResolutionError:
        shared = {}
    names = {n for _, n, _ in REQUEST_MAP} | {n for _, n, _ in SUBTASK_MAP}
    F, missing = {}, []
    for name in sorted(names):
        if name in shared:
            F[name] = shared[name]          # disambiguated OPS-shared id
        elif name in allcf:
            F[name] = allcf[name]
        else:
            missing.append(name)
    return F, missing


def existing_request_count(j):
    """How many Salesforce Config Requests already exist. 0 means the project is empty.

    Used as the idempotency guard: this seeder CREATES issues, so unlike jira_config.sfc_build
    it is not naturally re-runnable — a second run would mint a second full set.
    """
    jql = 'project = %s AND issuetype = "%s"' % (PROJECT_KEY, REQUEST_TYPE)
    try:                      # modern count endpoint
        res = j.post("/rest/api/3/search/approximate-count", {"jql": jql})
        if isinstance(res, dict) and res.get("count") is not None:
            return int(res["count"])
    except RuntimeError:
        pass
    try:                      # fallback: does at least one exist?
        page = j.post("/rest/api/3/search/jql", {"jql": jql, "maxResults": 1, "fields": ["key"]})
        return len(page.get("issues") or [])
    except RuntimeError:
        return 0              # project absent / unreadable — the createmeta gate will catch it


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fixtures.sfc_seed")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true",
                    help="seed even though SFC already holds requests (ADDS a duplicate batch)")
    args = ap.parse_args(argv)

    require_env()
    j = Jira()

    # IDEMPOTENCY GUARD. This seeder is not idempotent by nature (every run POSTs new
    # issues), so re-running silently doubled the dataset: 64 -> 128 -> 192. Refuse unless
    # the operator explicitly asks for another batch.
    n_existing = existing_request_count(j)
    if n_existing:
        log("  ! SFC already holds %d Salesforce Config Request(s)." % n_existing)
        if not args.force:
            msg = ("Refusing to seed: this would create a SECOND full set (duplicates), not "
                   "update the existing one. Delete the current batch first (JQL: project = "
                   "%s) or pass --force to deliberately add another." % PROJECT_KEY)
            if args.dry_run:
                log("  ! [dry] %s" % msg)   # let the rehearsal still print the plan
            else:
                sys.exit(msg)
    F, missing = resolve_fields(j)
    log("  resolved %d/%d SFC field names to ids" % (len(F), len(F) + len(missing)))
    if missing:
        log("  ! unresolved (not on the instance yet): %s" % ", ".join(missing))
        log("    Run `python3 -m jira_config.sfc_build` (dry_run=false) first if this is unexpected.")

    now = datetime.now(timezone.utc)
    _, records = build(args.n, args.days, now)   # same generator the preview lens uses

    per_type, allowed_priorities = createmeta(j)
    if per_type is None:
        sys.exit("createmeta is unavailable (both the paginated and classic endpoints "
                 "failed) — cannot tell which fields the create screen accepts. Aborting "
                 "rather than mass-create field-less issues. Check the SFC project exists "
                 "and your token can read it.")
    settable_req = per_type.get(REQUEST_TYPE, set())
    settable_sub = per_type.get(SUBTASK_TYPE, set())
    if not settable_req:
        sys.exit("No SFC request field is settable on the %r create screen — the fields "
                 "are not on the screen yet. Run `python3 -m jira_config.sfc_build` "
                 "(screens step) first, then re-run this seeder." % REQUEST_TYPE)
    usable = [n for r, n, _ in REQUEST_MAP if F.get(n) in settable_req]
    log("  %d/%d request fields settable on create; %d/%d org-deploy fields on the sub-task"
        % (len(usable), len(REQUEST_MAP),
           len([1 for r, n, _ in SUBTASK_MAP if F.get(n) in settable_sub]), len(SUBTASK_MAP)))
    # The Org Deploy sub-task fields ARE the point of Model A. If they are not on the
    # sub-task create screen, every sub-task would be an empty shell and the per-org
    # deploy/health panels would render blank — warn loudly rather than seed silently.
    sub_missing = [n for r, n, _ in SUBTASK_MAP if F.get(n) not in settable_sub]
    if sub_missing:
        log("  ! Org Deploy sub-task is MISSING these fields on its create screen: %s"
            % ", ".join(sub_missing))
        log("    Sub-tasks would carry no per-org deploy/health. Add them to the sub-task")
        log("    screen (sfc_build screens step / UI) before a real seed if you want that data.")

    total_subs = sum(len(r["org_deploys"]) for r in records)
    log("\n== plan ==")
    log("  %d Salesforce Config Requests + %d Org Deploy sub-tasks" % (len(records), total_subs))
    dist = {}
    for r in records:
        dist[r["status"]] = dist.get(r["status"], 0) + 1
    log("  status: " + "  ".join("%s:%d" % kv for kv in sorted(dist.items(), key=lambda x: -x[1])))
    if not allowed_priorities:
        log("  ! native priority not offered on the SFC create screen — requests will seed")
        log("    WITHOUT a priority, blanking priority-based views. If you want priorities,")
        log("    associate the P1–P4 priority scheme with SFC (Project settings -> Details),")
        log("    then re-run. (The default scheme usually already exposes them.)")

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


if __name__ == "__main__":
    main()
