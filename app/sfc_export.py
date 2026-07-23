#!/usr/bin/env python3
"""Bake the REAL SFC (DeliveryIQ / Salesforce Config) project to the lens's JSON.

The "Delivery / SF Config" lens was first shipped on a deterministic PREVIEW seed
(app/sfc_seed.py). Once the SFC Jira project is provisioned and seeded (jira_config/
sfc_build.py + fixtures/sfc_seed.py), this reads that project READ-ONLY and emits the
IDENTICAL schema — so the panels render unchanged, now on live Jira data. Every record
and model carries `preview: false`, so the lens drops its "preview — not live" banner.

What is real vs. not, stated honestly (the lens shows this too):
  - the request, its stage/status, squad, priority, dates, CAB, agent-action ledger,
    and the five-stage funnel are REAL Jira data;
  - per-org deploy state + config health are MODELLED — there is no live Salesforce,
    so these are illustrative values maintained on the Org Deploy sub-tasks by the
    writeback job (app/sfc_writeback), Source = "Modelled" with a real Health Checked
    At; the staleness guard is real (a stale cell reads Unknown, never green).

Schema parity with app/sfc_seed.py is the contract; if you change one, change both.

Read-only against Jira: the only verb is POST /rest/api/3/search/jql (Jira's read
endpoint — it takes a JQL body, so it cannot be a GET). Imports shared/ + app.store
(for the battle-tested timestamp parser) only; never jira_config or fixtures.

Python 3.9. %-formatting, no f-strings with backslashes.
"""

import json
from datetime import datetime, timedelta, timezone

from app.store import parse_dt   # Jira "+0530"/"+05:30" timestamp parser, 3.9-safe

PROJECT_KEY = "SFC"
REQUEST_TYPE = "Salesforce Config Request"
SUBTASK_TYPE = "Org Deploy"

PAGE_SIZE = 100
MAX_PAGES = 500

SF_STAGES = ["Intake", "Build", "Review", "Deploy", "Audit"]
# Jira status -> DeliveryIQ stage (stage is derived, never stored). Matches the
# preview's STAGE_STATUS: Deployed/Deploy Failed sit in Deploy; Done in Audit.
STAGE_OF_STATUS = {
    "Intake": "Intake",
    "In Build": "Build",
    "In Review": "Review",
    "Awaiting CAB": "Deploy", "Deploying": "Deploy", "Deployed": "Deploy",
    "Deploy Failed": "Deploy", "Rolled Back": "Deploy",
    "Audit": "Audit", "Done": "Audit", "Cancelled": "Audit",
}

# System fields every request/sub-task needs, plus `parent` so sub-tasks group.
SYSTEM_READS = ("issuetype", "status", "priority", "summary", "created",
                "resolutiondate", "parent")

# Request custom fields: name -> how to unwrap.
#   "select" -> option value      "multi" -> list of option values
#   "date" -> aware datetime      "number" -> float        "text" -> str
#   "yesno" -> bool (== "Yes")
REQUEST_FIELDS = [
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

# Org Deploy sub-task custom fields.
SUBTASK_FIELDS = [
    ("deploy_state", "Deploy State", "select"),
    ("config_health", "Config Health", "select"),
    ("health_checked_at", "Health Checked At", "date"),
    ("source", "Deploy Source", "select"),
]

ALL_FIELD_NAMES = ([n for _, n, _ in REQUEST_FIELDS]
                   + [n for _, n, _ in SUBTASK_FIELDS])


# ---------------------------------------------------------------------------
# field resolution + value unwrapping
# ---------------------------------------------------------------------------

def resolve_fields(j):
    """SFC field NAME -> customfield id, from the live instance (never a state file).

    SFC-owned names are unique on the instance, so a plain name->id map is safe; the
    OPS-shared names (Impact/Urgency/L2 Analyst/the four dates) are disambiguated
    through shared.fields (this instance carries two "Urgency" fields). Same contract
    as fixtures/sfc_seed.resolve_fields — the field NAME, not a per-instance id.
    """
    from shared import fields as SF
    allcf = {}
    for f in j.get("/rest/api/3/field"):
        if f.get("custom"):
            allcf.setdefault(f["name"], f["id"])
    try:
        shared = SF.resolve(j)
    except SF.FieldResolutionError:
        shared = {}
    F = {}
    for name in ALL_FIELD_NAMES:
        if name in shared:
            F[name] = shared[name]
        elif name in allcf:
            F[name] = allcf[name]
    return F


def _opt(v):
    return v.get("value") if isinstance(v, dict) else v


def _unwrap(kind, raw):
    if raw is None:
        return [] if kind == "multi" else None
    if kind == "select":
        return _opt(raw)
    if kind == "multi":
        return [_opt(x) for x in raw if _opt(x) is not None]
    if kind == "yesno":
        return _opt(raw) == "Yes"
    if kind == "date":
        return parse_dt(raw)
    if kind == "number":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return raw  # text


def _iso(dt):
    return dt.isoformat() if dt else None


def _org_from_summary(summary):
    """Org Deploy sub-tasks are titled 'Deploy to {org} — {parentKey}'. The org is not
    stored in a field on the sub-tasks, so recover it from the summary (the summary is
    the only carrier of which org a sub-task targets)."""
    if summary and summary.startswith("Deploy to "):
        return summary[len("Deploy to "):].rsplit(" — ", 1)[0].strip()
    return None


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def _fetch_all(j, F):
    """Every SFC issue (requests + Org Deploy sub-tasks), one paginated read, with
    changelog for the status timeline. Returns the raw issues[] list."""
    ids = list(SYSTEM_READS) + sorted({fid for fid in F.values()})
    jql = "project = %s ORDER BY created ASC, key ASC" % PROJECT_KEY
    raw, token, pages, seen = [], None, 0, set()
    while True:
        body = {"jql": jql, "maxResults": PAGE_SIZE, "fields": ids, "expand": "changelog"}
        if token:
            body["nextPageToken"] = token
        page = j.post("/rest/api/3/search/jql", body)
        batch = page.get("issues") or []
        for it in batch:
            if it.get("key") not in seen:
                seen.add(it.get("key"))
                raw.append(it)
        pages += 1
        token = page.get("nextPageToken")
        if page.get("isLast") or not token or not batch:
            break
        if pages >= MAX_PAGES:
            raise RuntimeError("SFC pagination did not terminate after %d pages" % pages)
    return raw


def _timeline(raw):
    """status-change timeline [{at, field, from, to}] from the inline changelog."""
    out = []
    for h in (raw.get("changelog") or {}).get("histories") or []:
        at = parse_dt(h.get("created"))
        for item in h.get("items") or []:
            if item.get("field") == "status":
                out.append({"at": _iso(at), "field": "status",
                            "from": item.get("fromString"), "to": item.get("toString")})
    out.sort(key=lambda c: (c["at"] is None, c["at"]))
    return out


# ---------------------------------------------------------------------------
# mapping
# ---------------------------------------------------------------------------

def _subtask_record(raw, F):
    f = raw.get("fields") or {}
    dep = {"org": _org_from_summary(f.get("summary"))}
    for key, name, kind in SUBTASK_FIELDS:
        val = _unwrap(kind, f.get(F[name])) if name in F else None
        dep[key] = _iso(val) if kind == "date" else val
    parent = (f.get("parent") or {}).get("key")
    return parent, dep


# The staleness guard, for real. Every doc + the lens banner promise "a verdict with no
# fresh check reads Unknown, never green" — that was previously an unbacked claim: nothing
# compared Health Checked At to the clock, so an aged "Healthy" stayed green forever. The
# writeback re-stamps every 6h, so anything unchecked for more than STALE_HOURS means the
# probe has stopped and the verdict is no longer evidence of anything.
STALE_HOURS = 24


def _apply_staleness(deploys, now):
    """Force a stale (or never-checked) health verdict to Unknown, and flag it.

    Returns NEW dicts — the raw verdict is replaced on purpose: a green cell nobody has
    re-checked is exactly the false comfort the guard exists to prevent. `stale` is kept so
    the health board can report how many cells went Unknown for staleness rather than
    because nothing was deployed.
    """
    out = []
    for d in deploys:
        dep = dict(d)
        checked = dep.get("health_checked_at")
        age_h = None
        if checked:
            try:
                age_h = (now - datetime.fromisoformat(checked)).total_seconds() / 3600.0
            except (TypeError, ValueError):
                age_h = None
        stale = (dep.get("config_health") not in (None, "Unknown")
                 and (age_h is None or age_h > STALE_HOURS))
        dep["stale"] = bool(stale)
        dep["health_age_h"] = round(age_h, 2) if age_h is not None else None
        if stale:
            dep["config_health"] = "Unknown"
        out.append(dep)
    return out


def _request_record(raw, F, site, deploys_by_parent, now):
    f = raw.get("fields") or {}
    key = raw.get("key")
    status = (f.get("status") or {}).get("name")
    category = ((f.get("status") or {}).get("statusCategory") or {}).get("key")
    stage = STAGE_OF_STATUS.get(status, "Intake")

    rec = {"key": key, "url": site + "/browse/" + (key or ""),
           "summary": f.get("summary"), "issue_type": REQUEST_TYPE,
           "status": status, "stage": stage, "status_category": category,
           "priority": (f.get("priority") or {}).get("name"), "intake": None}
    vals = {}
    for attr, name, kind in REQUEST_FIELDS:
        vals[attr] = _unwrap(kind, f.get(F[name])) if name in F else (
            [] if kind == "multi" else None)

    reported = vals["reported_at"]
    first = vals["first_response_at"]
    resolved = vals["resolved_at"]
    is_done = category == "done"
    # A request in "Deploy Failed" is NOT finished — it needs rework, and it is the most
    # urgent thing an agent is holding. It previously fell into a gap (neither open nor
    # done) and silently vanished from every open-work / WIP / agent-workload view.
    is_open = not is_done
    age_days = (now - reported).total_seconds() / 86400.0 if reported else None
    resp_h = ((first - reported).total_seconds() / 3600.0
              if (reported and first) else None)

    org_deploys = _apply_staleness(deploys_by_parent.get(key, []), now)
    states = [d.get("deploy_state") for d in org_deploys]
    deploy_rollup = ("Deployed" if states and all(s == "Deployed" for s in states)
                     else "Failed" if any(s in ("Failed", "Rolled back") for s in states)
                     else "Deploying" if any(s in ("Deploying", "Validated") for s in states)
                     else "Not started")

    tl = _timeline(raw)
    rec.update({
        "tower": vals["tower"], "impact": vals["impact"], "urgency": vals["urgency"],
        "change_risk": vals["change_risk"], "config_component_type": vals["config_component_type"],
        "target_orgs": vals["target_orgs"], "package_ref": vals["package_ref"],
        "cab_approval": vals["cab_approval"], "l2_analyst": vals["l2_analyst"],
        "reported_at": _iso(reported), "reported_ts": reported.timestamp() if reported else None,
        "first_response_at": _iso(first), "escalated_at": _iso(vals["escalated_at"]),
        "resolved_at": _iso(resolved),
        "age_days": round(age_days, 2) if age_days is not None else None,
        "response_hours": round(resp_h, 3) if resp_h is not None else None,
        "is_open": is_open, "is_done": is_done,
        "org_deploys": org_deploys, "deploy_rollup": deploy_rollup,
        "build_tested": bool(vals["build_tested"]),
        "comply_authorized": bool(vals["comply_authorized"]),
        "comply_evidence": bool(vals["comply_evidence"]),
        "coord_conflicts": int(vals["coord_conflicts"]) if vals["coord_conflicts"] is not None else 0,
        "coord_dependencies": int(vals["coord_dependencies"]) if vals["coord_dependencies"] is not None else 0,
        "evidence_pack_ready": bool(vals["evidence_pack_ready"]),
        "timeline": tl, "changelog_hops": len(tl),
        "preview": False,
    })
    return rec


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

def _scoreboard(records):
    deployed = sum(1 for r in records for d in r["org_deploys"]
                   if d.get("deploy_state") == "Deployed")
    total = sum(len(r["org_deploys"]) for r in records) or 1
    lead = sorted(
        (datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["reported_at"]))
        .total_seconds() / 86400.0
        for r in records if r["resolved_at"] and r["reported_at"])
    sb = {
        "deploy_success_pct": {"value": deployed / total * 100, "num": deployed,
                               "den": total, "target": 90, "direction": "ge", "verdict": None},
        "lead_time_d": {"value": (lead[len(lead) // 2] if lead else None),
                        "num": None, "den": None, "target": None, "direction": None, "verdict": None},
    }
    m = sb["deploy_success_pct"]
    if m["value"] is not None:
        m["verdict"] = "PASS" if m["value"] >= m["target"] else "GAP"
    return sb


def _model(records, days, now, generated_at):
    window_start = now - timedelta(days=days)
    in_window = [r for r in records
                 if r["reported_ts"] and r["reported_ts"] >= window_start.timestamp()]
    return {
        "project": PROJECT_KEY, "preview": False, "window_days": days,
        "generated_at": generated_at, "now_ts": now.timestamp(),
        "window_start_ts": window_start.timestamp(),
        "window_label": "%s – %s" % (window_start.strftime("%d %b"),
                                          now.strftime("%d %b %Y")),
        "volume": len(in_window), "scoreboard": _scoreboard(in_window), "warnings": [],
        "note": ("Live SFC Jira data. The stage/funnel, squad, CAB and agent-action "
                 "ledger are real Jira data. Per-org deploy state & config health are "
                 "MODELLED — DeliveryIQ tracks Salesforce config requests as Jira issues "
                 "and there is no live Salesforce connection; the writeback job "
                 "(app/sfc_writeback) maintains them on the Org Deploy sub-tasks with a "
                 "real Health Checked At (Source = Modelled). The staleness guard is "
                 "real, so a lapsed cell reads Unknown, never green."),
    }


# ---------------------------------------------------------------------------
# snapshot history + frozen baseline (parity with app.export_pages for OPS/ITSM)
# ---------------------------------------------------------------------------

HISTORY_WINDOW = 90     # the canonical window the trend tracks
HISTORY_CAP = 180       # keep ~6 months of daily points


def _sfc_point(records, now, generated_at):
    """A dated snapshot of the headline SFC KPIs over the 90-day window. Date-keyed and
    rounded, so two bakes on one day produce a byte-identical point (no CI churn)."""
    cut = (now - timedelta(days=HISTORY_WINDOW)).timestamp()
    win = [r for r in records if r["reported_ts"] and r["reported_ts"] >= cut]
    ods = [d for r in win for d in r["org_deploys"]]
    total = len(ods) or 1
    deployed = sum(1 for d in ods if d.get("deploy_state") == "Deployed")
    healthy = sum(1 for d in ods if d.get("config_health") == "Healthy")
    lead = sorted(
        (datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["reported_at"]))
        .total_seconds() / 86400.0
        for r in win if r["resolved_at"] and r["reported_at"])
    return {"date": generated_at[:10], "volume": len(win),
            "deploy_success_pct": round(deployed / total * 100, 2),
            "healthy_pct": round(healthy / total * 100, 2),
            "lead_time_d": round(lead[len(lead) // 2], 2) if lead else None}


def _append_history(out_dir, point):
    path = out_dir / "SFC-history.json"
    hist = []
    if path.exists():
        try:
            doc = json.loads(path.read_text())
            hist = doc.get("points", []) if isinstance(doc, dict) else (doc or [])
        except (ValueError, OSError):
            hist = []
    hist = [p for p in hist if p.get("date") != point["date"]]
    hist.append(point)
    hist.sort(key=lambda p: p.get("date") or "")
    hist = hist[-HISTORY_CAP:]
    path.write_text(json.dumps({"project": PROJECT_KEY, "window_days": HISTORY_WINDOW,
                                "points": hist}, separators=(",", ":"), default=str))
    return len(hist)


def _freeze_baseline(out_dir, point, generated_at):
    """Write the first full bake as the pilot baseline, once, never overwritten."""
    path = out_dir / "SFC-baseline.json"
    if path.exists():
        return False
    base = {"frozen_at": generated_at, **{k: point.get(k) for k in
            ("deploy_success_pct", "healthy_pct", "lead_time_d", "volume")}}
    path.write_text(json.dumps({"project": PROJECT_KEY, "baseline": base},
                               separators=(",", ":"), default=str))
    return True


# ---------------------------------------------------------------------------
# fetch (reused by app.export_pages AND app.server) + entry point
# ---------------------------------------------------------------------------

def fetch_sfc_records(j, now=None):
    """Read the SFC project once and map it to the lens's record schema. Pure of file
    I/O so the near-real-time backend (app.server) can serve the same rows. Returns
    (records, now)."""
    now = now or datetime.now(timezone.utc)
    F = resolve_fields(j)
    raw = _fetch_all(j, F)
    deploys_by_parent, requests = {}, []
    for it in raw:
        itype = ((it.get("fields") or {}).get("issuetype") or {}).get("name")
        if itype == SUBTASK_TYPE:
            parent, dep = _subtask_record(it, F)
            if parent:
                deploys_by_parent.setdefault(parent, []).append(dep)
        elif itype == REQUEST_TYPE:
            requests.append(it)
    records = [_request_record(it, F, j.site, deploys_by_parent, now) for it in requests]
    return records, now


def sfc_model(records, days, now, generated_at):
    """Public wrapper so app.server can build one window's model from fetched records."""
    return _model(records, days, now, generated_at)


def export_sfc(j, out_dir, day_windows, generated_at, now=None):
    """Bake SFC-{days}.json + SFC-records.json + SFC-history.json + SFC-baseline.json
    from the live SFC project.

    Returns (record_count, [window_file_names]). Raises if the project is absent so
    the caller can record the error and fall back (e.g. keep the preview seed).
    """
    records, now = fetch_sfc_records(j, now)

    written = []
    for days in day_windows:
        model = _model(records, days, now, generated_at)
        name = "SFC-%d.json" % days
        (out_dir / name).write_text(json.dumps(model, separators=(",", ":"), default=str))
        written.append(name)
        print("  + %s  (%d in window)" % (name, model["volume"]))
    (out_dir / "SFC-records.json").write_text(json.dumps(
        {"project": PROJECT_KEY, "preview": False, "generated_at": generated_at,
         "count": len(records), "records": records}, separators=(",", ":"), default=str))
    print("  + SFC-records.json  (%d requests, %d org-deploys)"
          % (len(records), sum(len(r["org_deploys"]) for r in records)))

    # snapshot history + frozen baseline (same discipline as OPS/ITSM)
    point = _sfc_point(records, now, generated_at)
    n = _append_history(out_dir, point)
    print("  + SFC-history.json  (%d point(s))" % n)
    if _freeze_baseline(out_dir, point, generated_at):
        print("  + SFC-baseline.json  (pilot baseline frozen)")
    return len(records), written
