#!/usr/bin/env python3
"""Delete every issue in the OPS project so the seed can be re-run clean.

Rehearsing a demo means seeding several times. Without a reset the project
accumulates half-written runs and the dashboards stop meaning anything.

Leaves the project, fields, statuses and workflow intact - only issues go.
Pass --project to delete the project itself as well.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, log, require_env  # noqa: E402
import config as C  # noqa: E402


def all_issue_keys(j):
    keys, start = [], 0
    while True:
        r = j.post("/rest/api/3/search/jql", {
            "jql": f"project = {C.PROJECT_KEY} ORDER BY created ASC",
            "maxResults": 100, "fields": ["key"],
            **({"nextPageToken": start} if isinstance(start, str) else {}),
        })
        batch = [i["key"] for i in r.get("issues", [])]
        keys.extend(batch)
        token = r.get("nextPageToken")
        if not token or not batch:
            break
        start = token
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", action="store_true", help="also delete the project")
    ap.add_argument("--yes", action="store_true", help="skip confirmation")
    args = ap.parse_args()

    require_env()
    j = Jira()
    keys = all_issue_keys(j)
    log(f"  {len(keys)} issues in {C.PROJECT_KEY}")
    if not keys and not args.project:
        return
    if not args.yes:
        if input(f"  delete all {len(keys)} issues? [y/N] ").strip().lower() != "y":
            log("  aborted")
            return

    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(j.delete, f"/rest/api/3/issue/{k}?deleteSubtasks=true") for k in keys]
        for n, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
                done += 1
            except Exception:
                pass
            if n % 100 == 0:
                log(f"  {n}/{len(keys)}")
    log(f"  deleted {done} issues")

    if args.project:
        j.delete(f"/rest/api/3/project/{C.PROJECT_KEY}")
        log(f"  deleted project {C.PROJECT_KEY}")


if __name__ == "__main__":
    main()
