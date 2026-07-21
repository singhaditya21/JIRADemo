#!/usr/bin/env python3
"""Bake the control-tower model to static JSON for the GitHub Pages React app.

GitHub Pages is a *static* host: there is no server to hold the Jira token, and a browser
on a public `github.io` page cannot call Jira Cloud anyway (CORS + the token must never
reach the browser). So the token stays in CI: a GitHub Actions job runs THIS script with
the token as a repo secret, fetches through the exact same `app/store` + `app/control_tower`
pipeline the local `app.server` uses, and writes the computed models to
`webapp/public/data/*.json`. Vite bundles `public/` into `dist/`, which is deployed to
Pages. The React app then reads those static files — no token, no live Jira call, no CORS.

"Real time" therefore means "refreshed every time this runs" (the Actions schedule), not
live-on-load. `index.json` carries the `generated_at` stamp the UI shows so a viewer always
knows how fresh the data is.

    python3 -m app.export_pages [--out webapp/public/data] [--days 30 90 180]

Read-only against Jira. Same numbers as the static HTML tower and the metrics CLI, because
all of them consume `app.control_tower.build_model`.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from shared.jira_client import Jira, require_env
from shared import fields as FIELDS
from app import store as S
from app.control_tower import build_model

PROJECTS = ("OPS", "ITSM")
DEFAULT_DAYS = (30, 90, 180)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "webapp" / "public" / "data"


def _jsonable(model):
    return json.loads(json.dumps(model, default=str))  # datetimes -> str, once


def export(out_dir, day_windows):
    require_env()                                     # clear message if a secret is missing
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    j = Jira()
    F = FIELDS.resolve(j)

    index = {"generated_at": generated_at, "projects": [], "windows": list(day_windows),
             "files": {}, "errors": {}}
    ok_any = False

    for project in PROJECTS:
        try:                                          # whole per-project body: one bad project
            st = S.fetch(j, project, F)               # (missing/unreadable) records + continues
            for days in day_windows:
                model = build_model(st.issues, st.now, days, project,
                                    site=st.site, pages=st.pages, warnings=list(st.warnings))
                model["generated_at"] = generated_at
                payload = _jsonable(model)
                name = f"{project}-{days}.json"
                (out_dir / name).write_text(json.dumps(payload, separators=(",", ":")))
                index["files"][f"{project}-{days}"] = name
                print(f"  + {name}  ({payload.get('volume')} in window, {st.pages} page(s))")
                ok_any = True
            index["projects"].append(project)
        except Exception as e:
            index["errors"][project] = f"{type(e).__name__}: {e}"
            print(f"  ! {project}: export failed - {e}", file=sys.stderr)
            continue

    # index.json is always written, even if a project failed, so the site still deploys.
    (out_dir / "index.json").write_text(json.dumps(index, indent=1))
    print(f"  + index.json  (generated_at {generated_at})")
    if not ok_any:
        sys.exit("no project exported - check JIRA_SITE / JIRA_EMAIL / JIRA_TOKEN")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--days", type=int, nargs="+", default=list(DEFAULT_DAYS))
    args = ap.parse_args()
    print(f"exporting control-tower data -> {args.out}")
    export(args.out, args.days)


if __name__ == "__main__":
    main()
