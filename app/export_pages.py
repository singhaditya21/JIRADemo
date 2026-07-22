#!/usr/bin/env python3
"""Bake the control-tower model to static JSON for the GitHub Pages React app.

GitHub Pages is a *static* host: there is no server to hold the Jira token, and a browser
on a public `github.io` page cannot call Jira Cloud anyway (CORS + the token must never
reach the browser). So the token stays in CI: a GitHub Actions job runs THIS script with
the token as a repo secret, fetches through the exact same `app/store` + `app/control_tower`
pipeline the local `app.server` uses, and writes the computed models to
`webapp/public/data/*.json`. Vite bundles `public/` into `dist/`, which is deployed to
Pages. The React app then reads those static files — no token, no live Jira call, no CORS.

Two kinds of file are written:
  - `{project}-{days}.json`   the AGGREGATE model (one per window) the panels render.
  - `{project}-records.json`  the RECORD-LEVEL dataset (one per project): every issue as a
                              flat row plus the derived population booleans and a compact
                              changelog timeline. The drill-down drawer lazy-loads this to
                              show the actual Jira rows behind a mark and each record's
                              tier/SLA history (roadmap Part III). Each aggregate model
                              carries `window_start_ts`/`now_ts` so the client can filter
                              records to the exact same window and reconcile counts.

"Real time" therefore means "refreshed every time this runs" (the Actions schedule), not
live-on-load. `index.json` carries the `generated_at` stamp the UI shows.

    python3 -m app.export_pages [--out webapp/public/data] [--days 30 90 180]
    PSEUDONYMISE_ANALYSTS=1 python3 -m app.export_pages   # mask analyst names (see below)

Read-only against Jira. Same numbers as the static HTML tower and the metrics CLI, because
all of them consume `app.control_tower.build_model`.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.jira_client import Jira, require_env
from shared import fields as FIELDS
from app import store as S
from app.control_tower import build_model

PROJECTS = ("OPS", "ITSM")
DEFAULT_DAYS = (30, 90, 180)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "webapp" / "public" / "data"

# Per-record fields the drill list/detail render. Booleans (is_*, counts_as_*, kb_gap)
# encode the exact population rules app/analytics uses, so a client-side filter on them
# reconciles with the aggregate's numerator/denominator.
RECORD_FIELDS = (
    "key", "url", "summary", "issue_type", "status", "status_category", "priority",
    "tower", "tier", "intake", "kb_checked", "escalation_reason", "root_cause",
    "resolution_code", "response_sla", "resolution_sla", "reopened", "impact", "urgency",
    "l1_analyst", "l2_analyst", "affected_service", "age_days", "response_hours",
    "is_open", "is_done", "is_problem", "is_escalated", "is_reopened",
    "counts_as_closed", "counts_as_ftr", "kb_gap",
)


def _jsonable(model):
    return json.loads(json.dumps(model, default=str))  # datetimes -> str, once


# --- Modelled CSAT proxy -----------------------------------------------------
# This instance has NO satisfaction survey — there is no CSAT field on any ticket.
# Rather than fabricate a Jira field and pass invented numbers off as real customer
# responses, the proxy is computed HERE, transparently, and labelled a model (never a
# survey) everywhere it surfaces. It answers a narrow, honest question: "if satisfaction
# tracked service outcomes, what would it look like?" — nothing more.
#
# It is deliberately NOT a pure re-encoding of the SLA verdict (which would make the panel
# redundant with the SLA panel). A base is set from the outcomes that actually move
# satisfaction (resolution SLA, reopening, response speed), then a deterministic per-key
# jitter adds the independent spread a real survey has — so a met-SLA ticket can still score
# a 3 and a breached one a 4, and the distribution is not two spikes. Deterministic (hash of
# the issue key, no RNG) so every bake reproduces the same scores.
def _csat_rating(issue):
    """Modelled 1–5 CSAT for a resolved, customer-facing ticket, or None.

    Only Incidents and Service Requests that are actually resolved get a score — you
    cannot survey satisfaction on a Problem investigation, a Change, or still-open work.
    """
    if issue.issue_type not in ("Incident", "Service Request"):
        return None
    if not issue.is_done or issue.is_problem:
        return None

    score = 4.4                                        # a resolved ticket starts satisfied
    if issue.resolution_sla == "Breached":
        score -= 1.7                                   # missing the promised time hurts most
    if issue.response_sla == "Breached":
        score -= 0.5                                   # a slow first response stings too
    elif issue.response_sla == "Met":
        score += 0.15
    if issue.is_reopened:
        score -= 1.3                                   # "you said it was fixed and it wasn't"
    if issue.priority in ("Highest", "P1", "High", "P2"):
        score -= 0.2                                   # higher stakes, less forgiving

    # Independent per-ticket spread (±0.85) so CSAT is not just SLA wearing a hat.
    h = int(hashlib.sha1((issue.key or "").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    score += (h - 0.5) * 1.7

    return max(1, min(5, round(score)))


def _ts(dt):
    return dt.timestamp() if dt is not None else None


def _pseudonymise_map(issues):
    """Stable Analyst NN alias per real name — for a public host where the model would
    otherwise expose named individuals' escalation rates (roadmap: privacy). Off by default
    because this instance's seed names are synthetic; flip PSEUDONYMISE_ANALYSTS for real data."""
    names = sorted({n for i in issues for n in (i.l1_analyst, i.l2_analyst) if n})
    return {n: f"Analyst {k + 1:02d}" for k, n in enumerate(names)}


def _record(issue, alias):
    r = {f: getattr(issue, f) for f in RECORD_FIELDS}
    if alias:
        r["l1_analyst"] = alias.get(r["l1_analyst"], r["l1_analyst"])
        r["l2_analyst"] = alias.get(r["l2_analyst"], r["l2_analyst"])
    r["reported_at"] = issue.reported_at.isoformat() if issue.reported_at else None
    r["reported_ts"] = _ts(issue.reported_at)
    r["resolved_at"] = issue.resolved_at.isoformat() if issue.resolved_at else None
    # REAL seeded lifecycle timestamps (not the collapsed changelog) — these unlock genuine
    # timing metrics: escalation latency, L1/L2 dwell, OLA handoff, MTTA-by-priority, RCA cycle.
    r["first_response_at"] = issue.first_response_at.isoformat() if issue.first_response_at else None
    r["escalated_at"] = issue.escalated_at.isoformat() if issue.escalated_at else None
    _h = lambda a, b: round((b - a).total_seconds() / 3600.0, 3) if a and b else None
    r["escalation_latency_h"] = _h(issue.reported_at, issue.escalated_at)   # reported -> escalated
    r["l2_dwell_h"] = _h(issue.escalated_at, issue.resolved_at)             # L2 time after handoff
    r["ola_handoff_h"] = _h(issue.first_response_at, issue.escalated_at)    # first response -> escalation
    r["ttr_h"] = _h(issue.reported_at, issue.resolved_at)                   # end-to-end resolution
    r["csat"] = _csat_rating(issue)                    # modelled proxy (see _csat_rating)
    r["links"] = issue.links or []                      # issue links (Problem/Incident etc.)
    cl = issue.changelog or ()
    r["changelog_hops"] = len(cl)
    r["timeline"] = [{"at": c.at.isoformat() if c.at else None,
                      "field": c.field, "from": c.frm, "to": c.to} for c in cl]
    return r


# --- Snapshot history --------------------------------------------------------
# The per-week sparklines show trend WITHIN one window; they cannot show how a headline KPI
# moved deploy-over-deploy (was FTR 64% last week, 61% today?). That needs a point appended
# each run and persisted. This bake appends one dated point per project per run to
# `{project}-history.json`; the CI job commits it back (see pages.yml) so it accumulates. The
# point is keyed by UTC day, so many runs on one day collapse to one point (last write wins) —
# no fabricated past, just the real scoreboard captured as each bake sees it.
HISTORY_WINDOW = 90     # the canonical window the trend tracks (matches the dashboard default)
HISTORY_CAP = 180       # keep ~6 months of daily points, then roll off the oldest


def _history_point(model, generated_at):
    # NOTE: no run timestamp here on purpose — the point carries only the UTC `date` and the
    # KPI values, so two bakes on the same day produce a byte-identical file and the CI
    # commit-back is skipped (no churn). Rounded to 2 dp for the same reason.
    sb = model.get("scoreboard") or {}
    val = lambda k: (lambda v: round(v, 2) if isinstance(v, (int, float)) else v)((sb.get(k) or {}).get("value"))
    return {"date": generated_at[:10], "volume": model.get("volume"),
            "ftr_pct": val("ftr_pct"), "escalation_pct": val("escalation_pct"),
            "reopen_pct": val("reopen_pct"), "sla_pct": val("sla_pct"),
            "response_pct": val("response_pct"), "aged_14d": val("aged_14d")}


def _append_history(out_dir, project, point):
    """Append/replace today's point in {project}-history.json; return the point count."""
    path = out_dir / f"{project}-history.json"
    hist = []
    if path.exists():
        try:
            doc = json.loads(path.read_text())
            hist = doc.get("points", []) if isinstance(doc, dict) else (doc or [])
        except (ValueError, OSError):
            hist = []                                 # a corrupt history never breaks a bake
    hist = [p for p in hist if p.get("date") != point["date"]]   # replace same UTC day
    hist.append(point)
    hist.sort(key=lambda p: p.get("date") or "")
    hist = hist[-HISTORY_CAP:]
    path.write_text(json.dumps({"project": project, "window_days": HISTORY_WINDOW,
                                "points": hist}, separators=(",", ":"), default=str))
    return len(hist)


def _freeze_baseline(out_dir, project, snapshot, generated_at):
    """Freeze the FIRST full-window bake as the pilot baseline (roadmap 6.3). Written once and
    never overwritten, so 'baseline → current → target' framing has a fixed reference point."""
    path = out_dir / f"{project}-baseline.json"
    if path.exists():
        return False
    sb = snapshot.get("scoreboard") or {}
    keys = ("ftr_pct", "escalation_pct", "reopen_pct", "sla_pct", "response_pct", "aged_14d")
    point = {"frozen_at": generated_at, **{k: (sb.get(k) or {}).get("value") for k in keys}}
    path.write_text(json.dumps({"project": project, "baseline": point}, separators=(",", ":"), default=str))
    return True


def export(out_dir, day_windows):
    require_env()                                     # clear message if a secret is missing
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    pseudo = os.environ.get("PSEUDONYMISE_ANALYSTS", "").lower() in ("1", "true", "yes")
    j = Jira()
    F = FIELDS.resolve(j)

    index = {"generated_at": generated_at, "projects": [], "windows": list(day_windows),
             "files": {}, "record_files": {}, "errors": {}, "pseudonymised": pseudo}
    ok_any = False

    for project in PROJECTS:
        try:                                          # whole per-project body: one bad project
            st = S.fetch(j, project, F, with_changelog=True)   # changelog -> record timelines
            alias = _pseudonymise_map(st.issues) if pseudo else None
            snapshot = None                           # the canonical-window model for history
            for days in day_windows:
                model = build_model(st.issues, st.now, days, project,
                                    site=st.site, pages=st.pages, warnings=list(st.warnings))
                model["generated_at"] = generated_at
                model["now_ts"] = _ts(st.now)
                model["window_start_ts"] = _ts(st.now - timedelta(days=days))
                if alias:                             # mask names in the analyst band too
                    for p in (model.get("analysts", {}) or {}).get("people", []):
                        p["analyst"] = alias.get(p.get("analyst"), p.get("analyst"))
                payload = _jsonable(model)
                name = f"{project}-{days}.json"
                (out_dir / name).write_text(json.dumps(payload, separators=(",", ":")))
                index["files"][f"{project}-{days}"] = name
                print(f"  + {name}  ({payload.get('volume')} in window, {st.pages} page(s))")
                if days == HISTORY_WINDOW or snapshot is None:
                    snapshot = payload                # prefer the 90d window, else the first
                ok_any = True
            # one dated snapshot point per project per run (accumulates via CI commit-back)
            hn = _append_history(out_dir, project, _history_point(snapshot, generated_at))
            index.setdefault("history_files", {})[project] = f"{project}-history.json"
            print(f"  + {project}-history.json  ({hn} point(s))")
            if _freeze_baseline(out_dir, project, snapshot, generated_at):
                print(f"  + {project}-baseline.json  (pilot baseline frozen)")
            index.setdefault("baseline_files", {})[project] = f"{project}-baseline.json"
            # one record file per project (all issues); the client windows it per view
            records = [_record(i, alias) for i in st.issues]
            rname = f"{project}-records.json"
            (out_dir / rname).write_text(json.dumps(
                {"project": project, "generated_at": generated_at, "count": len(records),
                 "pseudonymised": pseudo, "records": records}, separators=(",", ":"), default=str))
            index["record_files"][project] = rname
            print(f"  + {rname}  ({len(records)} records, changelog)")
            index["projects"].append(project)
        except Exception as e:
            index["errors"][project] = f"{type(e).__name__}: {e}"
            print(f"  ! {project}: export failed - {e}", file=sys.stderr)
            continue

    # SFC (DeliveryIQ) is a separate lens with its own schema (stages/deploys/health,
    # not the SLA engine), so it bakes through its own module rather than build_model.
    # If the SFC project is not provisioned yet, this fails softly and the CI step that
    # writes the preview seed (app.sfc_seed) still covers the lens.
    try:
        from app.sfc_export import export_sfc
        count, sfc_files = export_sfc(j, out_dir, day_windows, generated_at)
        for days, name in zip(day_windows, sfc_files):
            index["files"]["SFC-%d" % days] = name
        index["record_files"]["SFC"] = "SFC-records.json"
        index.setdefault("history_files", {})["SFC"] = "SFC-history.json"
        index.setdefault("baseline_files", {})["SFC"] = "SFC-baseline.json"
        index["projects"].append("SFC")
        ok_any = True
        print("  + SFC live bake (%d requests)" % count)
    except Exception as e:
        index["errors"]["SFC"] = "%s: %s" % (type(e).__name__, e)
        print("  ! SFC: live bake skipped - %s (preview seed still covers the lens)" % e,
              file=sys.stderr)

    # index.json is always written, even if a project failed, so the site still deploys.
    (out_dir / "index.json").write_text(json.dumps(index, indent=1))
    print(f"  + index.json  (generated_at {generated_at}, pseudonymised={pseudo})")
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
