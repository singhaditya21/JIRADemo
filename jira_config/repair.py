#!/usr/bin/env python3
"""Repair two defects in OPS that would have shown on screen during the demo.

1. Dashboard 10001 rendered as 12 blank gadgets. jira_config/views.py created them but never
   passed a filter id, so nothing was bound. The run sheet tells the presenter to open
   this dashboard, so this was a live-demo failure waiting to happen.

2. 358 Done tickets carried no `resolution`, so every Closed ticket displayed
   "Resolution: Unresolved". The resolution is derived from the Resolution Code field
   already on each ticket rather than blanket-set to Done, so the data stays coherent.

Both are idempotent. Use --dry-run first.

Usage:  python3 -m jira_config.repair [--dry-run] [--only dashboard|resolution]
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from shared.jira_client import Jira, log, require_env
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE

# The dashboard plan is OWNED by jira_config/views.py and imported here, not
# copied. This file used to carry its own twelve-entry copy alongside views.py's
# three-entry one; two definitions of the same dashboard in two files is exactly
# how the live dashboard drifted from what either of them believed.
#
# views.py is now the idempotent owner of the dashboard - it reconciles gadgets
# rather than appending them. This script is the ONE-SHOT fixer that repaired the
# twelve already-blank gadgets, kept because it is the tool that is known to have
# worked on this instance. Prefer `python3 -m jira_config.views` for anything new.
from jira_config.views import COLUMNS, GADGET_PLAN  # noqa: F401  (COLUMNS re-used below)


def repair_dashboard(j, dashboard, filters, dry):
    gadgets = j.get(f"/rest/api/3/dashboard/{dashboard}/gadget").get("gadgets", [])
    log(f"  {len(gadgets)} gadgets on dashboard {dashboard}")
    # Stable order so re-runs bind the same gadget to the same filter. This
    # positional zip is why GADGET_PLAN must stay in creation/id order.
    gadgets = sorted(gadgets, key=lambda g: g["id"])
    bound = 0
    for gadget, (fname, title, _row) in zip(gadgets, GADGET_PLAN):
        fid = filters.get(fname)
        if not fid:
            log(f"  ! no filter named {fname!r}")
            continue
        if dry:
            log(f"  would bind gadget {gadget['id']} -> {title} (filter {fid})")
            bound += 1
            continue
        cfg = {"filterId": f"filter-{fid}", "num": "10",
               "columnNames": COLUMNS, "refresh": "false"}
        j.put(f"/rest/api/3/dashboard/{dashboard}/items/{gadget['id']}/properties/config", cfg)
        try:
            j.put(f"/rest/api/3/dashboard/{dashboard}/gadget/{gadget['id']}", {"title": title})
        except RuntimeError:
            pass  # title is cosmetic; binding is what matters
        log(f"  bound gadget {gadget['id']} -> {title} (filter {fid})")
        bound += 1
    return bound


def fetch_unresolved(j, F):
    """Done tickets with no resolution, plus their Resolution Code."""
    out, token = [], None
    while True:
        body = {"jql": f"project = {S.PROJECT_KEY} AND statusCategory = Done "
                       f"AND resolution = Unresolved ORDER BY created ASC",
                "maxResults": 100,
                "fields": ["key", "status", F["Resolution Code"]]}
        if token:
            body["nextPageToken"] = token
        r = j.post("/rest/api/3/search/jql", body)
        for i in r.get("issues", []):
            rc = i["fields"].get(F["Resolution Code"])
            out.append((i["key"], (rc or {}).get("value"), i["fields"]["status"]["name"]))
        token = r.get("nextPageToken")
        if not token:
            break
    return out


def set_resolution(j, key, name):
    j.put(f"/rest/api/3/issue/{key}", {"fields": {"resolution": {"name": name}}})


def repair_resolutions(j, F, dry, workers):
    rows = fetch_unresolved(j, F)
    log(f"  {len(rows)} Done tickets with no resolution")
    plan = []
    for key, code, status in rows:
        if status == "Cancelled":
            target = "Won't Do"
        else:
            target = S.RESOLUTION_MAP.get(code, S.DEFAULT_RESOLUTION)
        plan.append((key, target))
    log("  mapping: " + ", ".join(f"{k}={v}" for k, v in Counter(t for _, t in plan).items()))
    if dry:
        log("  dry run - nothing written")
        return 0, 0
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(set_resolution, j, k, t) for k, t in plan]
        for n, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 3:
                    log(f"    ! {str(e)[:150]}")
            if n % 100 == 0:
                log(f"  {n}/{len(plan)}")
    return ok, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["dashboard", "resolution"])
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    require_env()
    j = Jira()
    if not STATE.exists():
        sys.exit("%s missing - run python3 -m jira_config.build first." % STATE.name)
    state = json.loads(STATE.read_text())

    # The dashboard id is recorded by jira_config/views.py. Hardcoding it (this
    # script used to carry DASHBOARD = "10001") made repair.py unusable anywhere
    # but the one instance it was written against.
    dashboard = state.get("dashboard_id")

    if args.only != "resolution":
        log("== dashboard gadgets ==")
        if not dashboard:
            sys.exit("no dashboard_id in %s - run python3 -m jira_config.views first."
                     % STATE.name)
        n = repair_dashboard(j, dashboard, state["filters"], args.dry_run)
        log(f"  {n} gadgets bound")

    if args.only != "dashboard":
        log("\n== resolutions ==")
        ok, fail = repair_resolutions(j, state["fields"], args.dry_run, args.workers)
        log(f"  set {ok}, failed {fail}")

    if not args.dry_run:
        log("\n== verify ==")
        def c(q):
            return j.post("/rest/api/3/search/approximate-count", {"jql": q}).get("count")
        pk = S.PROJECT_KEY
        unresolved = c(f"project={pk} AND statusCategory=Done AND resolution=Unresolved")
        total = c(f"project={pk}")
        tier2 = c(f'project={pk} AND "Support Tier"=L2')
        gate = c(f'project={pk} AND "Troubleshooting Performed" is not EMPTY')
        log(f"  Done without resolution: {unresolved}  (target 0)")
        # The three counts below are reported, not asserted. 420 / 171 / 171 are
        # facts about the 2026-07-20 demo seed, not invariants of the schema, and
        # a repair script that "fails" on a differently-sized project is useless.
        log(f"  total issues:            {total}  (420 at the 2026-07-20 demo seed)")
        log(f"  tier L2:                 {tier2}  (171 at the 2026-07-20 demo seed)")
        log(f"  gate evidence:           {gate}  (171 at the 2026-07-20 demo seed)")
        gl = j.get(f"/rest/api/3/dashboard/{dashboard}/gadget").get("gadgets", [])
        wired = 0
        for g in gl:
            p = j.try_get(f"/rest/api/3/dashboard/{dashboard}/items/{g['id']}/properties/config")
            if p and p.get("value", {}).get("filterId"):
                wired += 1
        log(f"  gadgets bound to a filter: {wired}/{len(gl)}")


if __name__ == "__main__":
    main()
