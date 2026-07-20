#!/usr/bin/env python3
"""Recompute SLA state from the timeline. The JSM SLA engine, hand-rolled.

Why this exists: the Response/Resolution SLA fields were written once by the seeder,
so they were decoration. A ticket could blow through its target and still read "Met"
forever. That made the attainment figure unquotable.

This computes them properly:

  elapsed = (resolved_at or now) - reported_at  -  time spent in a paused status
  breached if elapsed > the target for that priority

Pause intervals come from the issue changelog, which is what JSM does natively. On
seeded data the changelog is compressed into the seeding run, so historical pause
time reads as ~0 and the result is driven by the Reported At -> Resolved At timeline;
on real traffic the changelog is the real thing. Tickets sitting in a Pending status
right now are marked Paused and excluded from attainment either way.

Problems are skipped - they are investigations, not SLA-bound work.

Usage:  python3 scripts/08_sla.py [--dry-run] [--workers 4]
"""

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
PAUSED = set(C.SLA_PAUSED_STATUSES)
PRIORITY_CODE = {"P1 - Critical": "P1", "P2 - High": "P2",
                 "P3 - Medium": "P3", "P4 - Low": "P4"}


def parse(ts):
    if not ts:
        return None
    return datetime.strptime(ts[:23] + ts[23:].replace(":", ""), "%Y-%m-%dT%H:%M:%S.%f%z")


def business_hours_between(start, end):
    """Elapsed business hours, Mon-Fri within the working window.

    This is what a JSM SLA calendar does. Without it a P3 raised on Friday
    afternoon is 'late' by Monday morning purely because the weekend elapsed,
    and the whole attainment report becomes indefensible.
    """
    if end <= start:
        return 0.0
    lo, hi = C.BUSINESS_DAY
    total = 0.0
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        if day.weekday() in C.BUSINESS_DAYS:
            win_start = day.replace(hour=lo)
            win_end = day.replace(hour=hi)
            lo_b = max(win_start, start)
            hi_b = min(win_end, end)
            if hi_b > lo_b:
                total += (hi_b - lo_b).total_seconds() / 3600.0
        day += timedelta(days=1)
    return total


def paused_seconds(changelog, until):
    """Time the issue spent in a paused status, from its status-change history."""
    total, entered = 0.0, None
    events = []
    for h in changelog:
        when = parse(h["created"])
        for item in h.get("items", []):
            if item.get("field") == "status":
                events.append((when, item.get("toString")))
    for when, status in sorted(events, key=lambda e: e[0]):
        if status in PAUSED and entered is None:
            entered = when
        elif status not in PAUSED and entered is not None:
            total += (when - entered).total_seconds()
            entered = None
    if entered is not None:                    # still paused
        total += (until - entered).total_seconds()
    return total


def evaluate(j, key, F, now):
    issue = j.get(f"/rest/api/3/issue/{key}?expand=changelog"
                  f"&fields=status,priority,issuetype,{F['Reported At']},"
                  f"{F['Resolved At']},{F['First Response At']}")
    f = issue["fields"]
    itype = f["issuetype"]["name"]
    if itype == "Problem":
        return key, None, None, "problem-skipped"

    status = f["status"]["name"]
    reported = parse(f.get(F["Reported At"]))
    if not reported:
        return key, None, None, "no-reported-at"

    pname = (f.get("priority") or {}).get("name", "")
    code = PRIORITY_CODE.get(pname)
    if not code:
        return key, None, None, f"unknown-priority:{pname}"
    resp_target, res_target = C.SLA_TARGETS[code]

    resolved = parse(f.get(F["Resolved At"]))
    endpoint = resolved or now
    paused = paused_seconds(issue.get("changelog", {}).get("histories", []), endpoint)

    # Measure on the calendar this priority is actually governed by.
    if C.SLA_CLOCK[code] == "business":
        elapsed_h = business_hours_between(reported, endpoint) - (paused / 3600.0)
    else:
        elapsed_h = ((endpoint - reported).total_seconds() - paused) / 3600.0
    elapsed_h = max(0.0, elapsed_h)

    # Response
    first = parse(f.get(F["First Response At"]))
    if first:
        resp_h = (business_hours_between(reported, first)
                  if C.SLA_CLOCK[code] == "business"
                  else (first - reported).total_seconds() / 3600.0)
        resp = "Met" if resp_h <= resp_target else "Breached"
    else:
        resp = "In progress"

    # Resolution
    if status in PAUSED:
        res = "Paused"
    elif resolved:
        res = "Met" if elapsed_h <= res_target else "Breached"
    else:
        res = "Breached" if elapsed_h > res_target else "In progress"

    return key, resp, res, f"{elapsed_h:.1f}h/{res_target}h"


def apply(j, key, F, resp, res):
    fields = {}
    if resp:
        fields[F["Response SLA"]] = {"value": resp}
    if res:
        fields[F["Resolution SLA"]] = {"value": res}
    if fields:
        j.put(f"/rest/api/3/issue/{key}", {"fields": fields})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    require_env()
    j = Jira()
    F = json.loads(STATE.read_text())["fields"]
    now = datetime.now(timezone.utc)

    keys, token = [], None
    while True:
        body = {"jql": f"project = {C.PROJECT_KEY} ORDER BY created ASC",
                "maxResults": 100, "fields": ["key"]}
        if token:
            body["nextPageToken"] = token
        r = j.post("/rest/api/3/search/jql", body)
        keys += [i["key"] for i in r.get("issues", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    log(f"  {len(keys)} issues to evaluate")

    results, tallies = [], defaultdict(int)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(evaluate, j, k, F, now) for k in keys]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                key, resp, res, note = fut.result()
                results.append((key, resp, res))
                tallies[f"resolution:{res}"] += 1
                tallies[f"response:{resp}"] += 1
            except Exception as e:
                tallies["error"] += 1
                if tallies["error"] <= 2:
                    log(f"    ! {str(e)[:130]}")
            if n % 100 == 0:
                log(f"  evaluated {n}/{len(keys)}")

    log("\n  computed:")
    for k in sorted(tallies):
        log(f"    {k:<26} {tallies[k]}")

    met = tallies["resolution:Met"]
    br = tallies["resolution:Breached"]
    if met + br:
        log(f"\n  resolution SLA attainment (computed, paused excluded): "
            f"{100.0*met/(met+br):.1f}%")

    if args.dry_run:
        log("\n  dry run - nothing written")
        return

    log(f"\n  writing back ({args.workers} workers)")
    wrote, failed = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(apply, j, k, F, resp, res)
                for k, resp, res in results if resp or res]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                fut.result()
                wrote += 1
            except Exception:
                failed += 1
            if n % 100 == 0:
                log(f"  wrote {n}")
    log(f"  updated {wrote}, failed {failed}")


if __name__ == "__main__":
    main()
