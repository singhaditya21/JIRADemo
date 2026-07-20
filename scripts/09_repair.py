#!/usr/bin/env python3
"""Repair two defects in OPS that would have shown on screen during the demo.

1. Dashboard 10001 rendered as 12 blank gadgets. 04_views.py created them but never
   passed a filter id, so nothing was bound. The run sheet tells the presenter to open
   this dashboard, so this was a live-demo failure waiting to happen.

2. 358 Done tickets carried no `resolution`, so every Closed ticket displayed
   "Resolution: Unresolved". The resolution is derived from the Resolution Code field
   already on each ticket rather than blanket-set to Done, so the data stays coherent.

Both are idempotent. Use --dry-run first.

Usage:  python3 scripts/09_repair.py [--dry-run] [--only dashboard|resolution]
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
DASHBOARD = "10001"

# The twelve views worth a gadget, in reading order.
GADGET_PLAN = [
    ("OPS - L1 queue (open)", "L1 queue"),
    ("OPS - L2 queue (open)", "L2 queue"),
    ("OPS - Major incidents (Impact High + Urgency High)", "Major incidents"),
    ("OPS - SLA breached (resolution)", "SLA breached"),
    ("OPS - SLA paused (waiting on customer or vendor)", "SLA paused - clock stopped"),
    ("OPS - Aged backlog over 14 days", "Aged over 14 days"),
    ("OPS - Reopened tickets", "Reopened - paired with FTR"),
    ("OPS - Escalated in last 30 days", "Escalated last 30 days"),
    ("OPS - Escalated with no KB article found", "KB gap - the biggest lever"),
    ("OPS - Intake via chat (shadow support pulled in)", "Shadow support via chat"),
    ("OPS - P1 at risk (past 75% of target)", "P1 at risk"),
    ("OPS - P2 at risk (past 75% of target)", "P2 at risk"),
]

COLUMNS = "issuetype|issuekey|summary|priority|status|updated"

# Resolution Code (our field) -> Jira's native resolution. Blanket-setting everything to
# "Done" would make the closure data say something untrue.
RESOLUTION_MAP = {
    "Fixed": "Done",
    "Workaround applied": "Done",
    "Implemented": "Done",
    "Fulfilled": "Done",
    "Referred to vendor": "Done",
    "Known error documented": "Done",
    "No fault found": "Cannot Reproduce",
    "Duplicate": "Duplicate",
    "Withdrawn by requester": "Won't Do",
    "Rolled back": "Won't Do",
}
DEFAULT_RESOLUTION = "Done"


def repair_dashboard(j, filters, dry):
    gadgets = j.get(f"/rest/api/3/dashboard/{DASHBOARD}/gadget").get("gadgets", [])
    log(f"  {len(gadgets)} gadgets on dashboard {DASHBOARD}")
    # Stable order so re-runs bind the same gadget to the same filter.
    gadgets = sorted(gadgets, key=lambda g: g["id"])
    bound = 0
    for gadget, (fname, title) in zip(gadgets, GADGET_PLAN):
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
        j.put(f"/rest/api/3/dashboard/{DASHBOARD}/items/{gadget['id']}/properties/config", cfg)
        try:
            j.put(f"/rest/api/3/dashboard/{DASHBOARD}/gadget/{gadget['id']}", {"title": title})
        except RuntimeError:
            pass  # title is cosmetic; binding is what matters
        log(f"  bound gadget {gadget['id']} -> {title} (filter {fid})")
        bound += 1
    return bound


def fetch_unresolved(j, F):
    """Done tickets with no resolution, plus their Resolution Code."""
    out, token = [], None
    while True:
        body = {"jql": f"project = {C.PROJECT_KEY} AND statusCategory = Done "
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
            target = RESOLUTION_MAP.get(code, DEFAULT_RESOLUTION)
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
    state = json.loads(STATE.read_text())

    if args.only != "resolution":
        log("== dashboard gadgets ==")
        n = repair_dashboard(j, state["filters"], args.dry_run)
        log(f"  {n} gadgets bound")

    if args.only != "dashboard":
        log("\n== resolutions ==")
        ok, fail = repair_resolutions(j, state["fields"], args.dry_run, args.workers)
        log(f"  set {ok}, failed {fail}")

    if not args.dry_run:
        log("\n== verify ==")
        def c(q):
            return j.post("/rest/api/3/search/approximate-count", {"jql": q}).get("count")
        unresolved = c("project=OPS AND statusCategory=Done AND resolution=Unresolved")
        total = c("project=OPS")
        tier2 = c('project=OPS AND "Support Tier"=L2')
        gate = c('project=OPS AND "Troubleshooting Performed" is not EMPTY')
        log(f"  Done without resolution: {unresolved}  (target 0)")
        log(f"  total issues:            {total}  (must stay 420)")
        log(f"  tier L2:                 {tier2}  (must stay 171)")
        log(f"  gate evidence:           {gate}  (must stay 171)")
        gl = j.get(f"/rest/api/3/dashboard/{DASHBOARD}/gadget").get("gadgets", [])
        wired = 0
        for g in gl:
            p = j.try_get(f"/rest/api/3/dashboard/{DASHBOARD}/items/{g['id']}/properties/config")
            if p and p.get("value", {}).get("filterId"):
                wired += 1
        log(f"  gadgets bound to a filter: {wired}/{len(gl)}")


if __name__ == "__main__":
    main()
