#!/usr/bin/env python3
"""Build the OPS project structure: project, custom fields, issue types, screens.

Idempotent — safe to re-run. Existing objects are reused, not duplicated.
Writes jira_config/state/.build_state.json. Consumed by jira_config only — app/
resolves field ids by name at runtime rather than reading this artifact.

Usage:  python3 -m jira_config.build [--dry-run]

--dry-run is a real rehearsal, not a listing: every mutating call goes through
Writer, which logs the method and path and issues nothing. A dry run also writes
no state, so it cannot perturb the artifact it would otherwise produce.

This module OWNS exactly two state keys: project_id and fields. It used to
round-trip the whole dict, which meant a stale in-memory copy could rewrite keys
belonging to other steps — workflow_created (owned by workflow.py) was observed
flipping true -> false that way. save_state now re-reads from disk and merges
only the owned keys, so a build can never answer for work it did not do.
"""

import argparse

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config import merge_state, read_state
from jira_config.reconcile import Writer

OWNED_KEYS = ("project_id", "fields")


def load_state():
    return read_state(STATE)


def save_state(s, dry=False):
    """Merge this module's own keys into whatever is on disk now."""
    if not merge_state(STATE, s, OWNED_KEYS, dry):
        log("  [dry] state not written")


def ensure_project(w, state):
    j = w.j
    key = S.PROJECT_KEY
    existing = j.try_get(f"/rest/api/3/project/{key}")
    if existing and existing.get("key") == key:
        log(f"  project {key} already exists (id {existing['id']})")
        state["project_id"] = existing["id"]
        return existing["id"]

    me = j.get("/rest/api/3/myself")["accountId"]
    body = {
        "key": key,
        "name": S.PROJECT_NAME,
        "projectTypeKey": S.PROJECT_TYPE_KEY,
        "projectTemplateKey": S.PROJECT_TEMPLATE_KEY,
        "leadAccountId": me,
        "assigneeType": "UNASSIGNED",
        "description": "L1/L2 support tower. Built from jira_config/ - see PLAN.md.",
    }
    res = w.post("/rest/api/3/project", body)
    log(f"  created project {key} (id {res['id']})")
    state["project_id"] = res["id"]
    return res["id"]


def existing_fields(j):
    return {f["name"]: f["id"] for f in j.get("/rest/api/3/field") if f.get("custom")}


def ensure_field(w, name, ftype, have):
    if name in have:
        return have[name], False
    body = {"name": name, "type": ftype, "searcherKey": S.SEARCHER[ftype],
            "description": f"OPS tower schema - {name}"}
    res = w.post("/rest/api/3/field", body)
    return res["id"], True


def ensure_options(w, field_id, values, is_new=False):
    # A field that does not exist yet has no context to read. Under --dry-run its
    # id is a placeholder, so querying it would 404 on a live instance; report the
    # options as planned instead of pretending to have diffed them.
    if is_new and w.dry:
        log("      [dry] would add %d options once the field exists" % len(values))
        return len(values)
    ctxs = w.j.get(f"/rest/api/3/field/{field_id}/context")["values"]
    if not ctxs:
        return 0
    ctx = ctxs[0]["id"]
    url = f"/rest/api/3/field/{field_id}/context/{ctx}/option"
    have = {o["value"] for o in w.j.get(url).get("values", [])}
    missing = [v for v in values if v not in have]
    if missing:
        w.post(url, {"options": [{"value": v, "disabled": False} for v in missing]})
    return len(missing)


def add_fields_to_screens(w, field_ids):
    """Fields must sit on a screen before REST can set them on create/edit."""
    j = w.j
    added = 0
    screens = j.get("/rest/api/3/screens?maxResults=100").get("values", [])
    targets = [s for s in screens if S.PROJECT_KEY.lower() in (s.get("name") or "").lower()]
    if not targets:
        log("  ! no project-specific screens found; falling back to all editable screens")
        targets = screens
    for sc in targets:
        tabs = j.try_get(f"/rest/api/3/screens/{sc['id']}/tabs", [])
        if not tabs:
            continue
        tab = tabs[0]["id"]
        present = {f["id"] for f in j.try_get(
            f"/rest/api/3/screens/{sc['id']}/tabs/{tab}/fields", []) or []}
        for fid in field_ids:
            if fid in present:
                continue
            try:
                w.post(f"/rest/api/3/screens/{sc['id']}/tabs/{tab}/fields", {"fieldId": fid})
                added += 1
            except RuntimeError:
                pass  # already present on another tab, or not addable
    return added


def add_arguments(ap):
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it, and write no state")
    return ap


def main(argv=None):
    args = add_arguments(argparse.ArgumentParser(prog="jira_config.build")).parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    state = load_state()

    log("== project ==")
    ensure_project(w, state)

    log("== custom fields ==")
    have = existing_fields(j)
    fields = state.get("fields", {})
    created = 0

    for name, values in D.SELECT_FIELDS.items():
        fid, is_new = ensure_field(w, name, S.SELECT_TYPE, have)
        fields[name] = fid
        created += is_new
        n = ensure_options(w, fid, values, is_new)
        log(f"  {'+' if is_new else '='} {name:<28} {fid}  (+{n} options)")

    for name, kind in D.TEXT_FIELDS.items():
        ftype = S.AREA_TYPE if kind == "long" else S.TEXT_TYPE
        fid, is_new = ensure_field(w, name, ftype, have)
        fields[name] = fid
        created += is_new
        log(f"  {'+' if is_new else '='} {name:<28} {fid}")

    for name in D.DATE_FIELDS:
        fid, is_new = ensure_field(w, name, S.DATE_TYPE, have)
        fields[name] = fid
        created += is_new
        log(f"  {'+' if is_new else '='} {name:<28} {fid}")

    state["fields"] = fields
    log(f"  {len(fields)} fields total, {created} newly created")

    log("== screens ==")
    n = add_fields_to_screens(w, list(fields.values()))
    log(f"  {n} field/screen associations added")

    save_state(state, dry=args.dry_run)
    log("\n%d writes%s" % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))
    if not args.dry_run:
        log(f"state written to {STATE.name}")
    log("next: python3 -m jira_config.workflow")


if __name__ == "__main__":
    main()
