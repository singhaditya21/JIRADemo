#!/usr/bin/env python3
"""Build the OPS project structure: project, custom fields, issue types, screens.

Idempotent — safe to re-run. Existing objects are reused, not duplicated.
Writes scripts/.build_state.json so the seeder knows the field IDs.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"

SELECT_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:select"
TEXT_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:textfield"
AREA_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:textarea"
DATE_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:datetime"

SEARCHER = {
    SELECT_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:multiselectsearcher",
    TEXT_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
    AREA_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
    DATE_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:datetimerange",
}


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))


def ensure_project(j, state):
    key = C.PROJECT_KEY
    existing = j.try_get(f"/rest/api/3/project/{key}")
    if existing and existing.get("key") == key:
        log(f"  project {key} already exists (id {existing['id']})")
        state["project_id"] = existing["id"]
        return existing["id"]

    me = j.get("/rest/api/3/myself")["accountId"]
    body = {
        "key": key,
        "name": C.PROJECT_NAME,
        "projectTypeKey": "software",
        # classic == company-managed; required for shared schemes and workflow rules
        "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-simplified-kanban-classic",
        "leadAccountId": me,
        "assigneeType": "UNASSIGNED",
        "description": "L1/L2 support tower. Built from scripts/ - see PLAN.md.",
    }
    res = j.post("/rest/api/3/project", body)
    log(f"  created project {key} (id {res['id']})")
    state["project_id"] = res["id"]
    return res["id"]


def existing_fields(j):
    return {f["name"]: f["id"] for f in j.get("/rest/api/3/field") if f.get("custom")}


def ensure_field(j, name, ftype, have):
    if name in have:
        return have[name], False
    body = {"name": name, "type": ftype, "searcherKey": SEARCHER[ftype],
            "description": f"OPS tower schema - {name}"}
    res = j.post("/rest/api/3/field", body)
    return res["id"], True


def ensure_options(j, field_id, values):
    ctxs = j.get(f"/rest/api/3/field/{field_id}/context")["values"]
    if not ctxs:
        return 0
    ctx = ctxs[0]["id"]
    url = f"/rest/api/3/field/{field_id}/context/{ctx}/option"
    have = {o["value"] for o in j.get(url).get("values", [])}
    missing = [v for v in values if v not in have]
    if missing:
        j.post(url, {"options": [{"value": v, "disabled": False} for v in missing]})
    return len(missing)


def add_fields_to_screens(j, field_ids):
    """Fields must sit on a screen before REST can set them on create/edit."""
    added = 0
    screens = j.get(f"/rest/api/3/screens?maxResults=100").get("values", [])
    targets = [s for s in screens if C.PROJECT_KEY.lower() in (s.get("name") or "").lower()]
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
                j.post(f"/rest/api/3/screens/{sc['id']}/tabs/{tab}/fields", {"fieldId": fid})
                added += 1
            except RuntimeError:
                pass  # already present on another tab, or not addable
    return added


def main():
    require_env()
    j = Jira()
    state = load_state()

    log("== project ==")
    ensure_project(j, state)

    log("== custom fields ==")
    have = existing_fields(j)
    fields = state.get("fields", {})
    created = 0

    for name, values in C.SELECT_FIELDS.items():
        fid, is_new = ensure_field(j, name, SELECT_TYPE, have)
        fields[name] = fid
        created += is_new
        n = ensure_options(j, fid, values)
        log(f"  {'+' if is_new else '='} {name:<28} {fid}  (+{n} options)")

    for name, kind in C.TEXT_FIELDS.items():
        ftype = AREA_TYPE if kind == "long" else TEXT_TYPE
        fid, is_new = ensure_field(j, name, ftype, have)
        fields[name] = fid
        created += is_new
        log(f"  {'+' if is_new else '='} {name:<28} {fid}")

    for name in C.DATE_FIELDS:
        fid, is_new = ensure_field(j, name, DATE_TYPE, have)
        fields[name] = fid
        created += is_new
        log(f"  {'+' if is_new else '='} {name:<28} {fid}")

    state["fields"] = fields
    save_state(state)
    log(f"  {len(fields)} fields total, {created} newly created")

    log("== screens ==")
    n = add_fields_to_screens(j, list(fields.values()))
    log(f"  {n} field/screen associations added")

    save_state(state)
    log(f"\nstate written to {STATE.name}")
    log("next: python3 scripts/02_seed.py")


if __name__ == "__main__":
    main()
