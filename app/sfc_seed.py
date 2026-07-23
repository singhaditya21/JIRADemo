#!/usr/bin/env python3
"""Preview seed for the DeliveryIQ "Delivery / SF Config" (SFC) lens.

The real SFC data will come from a Jira project (see DELIVERYIQ-SF-CONFIG.md, P0) via the
same bake as OPS/ITSM. Until that project is provisioned, this generates a DETERMINISTIC,
clearly-labelled **preview** dataset so the new lens is demonstrable — every record and model
it writes carries `preview: true`, and the lens shows a "preview — not the live SF Config
project" banner. It never claims to be live Jira/Salesforce data.

Schema mirrors exactly what the P0 bake will emit for a Salesforce Config Request, so the
same panels render unchanged once real data flows:
  - the request: key, stage, status, squad (tower), priority/impact/urgency, dates, change
    risk, config component types, target orgs, CAB approval, agent-action fields, evidence.
  - per-org deploys (Model A sub-tasks, flattened): org_deploys[] with deploy_state,
    config_health, health_checked_at, source.

    python3 -m app.sfc_seed [--out webapp/public/data] [--n 64] [--days 90]
"""

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The evidence conjunction and the redeploy derivation are defined ONCE, in the real bake —
# schema parity between preview and live is the contract, so the preview imports them rather
# than restating them (a second copy is how the two silently drift).
from app.sfc_export import (_evidence, _is_redeployed, _scoreboard as _sfc_scoreboard,
                            _invariants as _sfc_invariants, STALE_HOURS)

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "webapp" / "public" / "data"

SQUADS = ["Sales Cloud", "Service Cloud", "Platform / Core", "Revenue / CPQ", "Data & Integrations", "Experience Cloud"]
ORGS = ["Prod", "Full-copy UAT", "QA", "Staging", "Dev"]
COMPONENTS = ["Field", "Flow", "Validation Rule", "Permission Set", "Page Layout", "Custom Object", "Apex-adjacent", "LWC-adjacent"]
CHANNELS = ["Backlog grooming", "Portal", "Monitoring", "Chat"]
RISK = ["Low", "Medium", "High"]
PRIORITIES = ["P1 - Critical", "P2 - High", "P3 - Medium", "P4 - Low"]
IMPACT = ["High", "Medium", "Low"]
URGENCY = ["High", "Medium", "Low"]
REVIEWERS = ["A. Okafor", "R. Mehta", "N. Haddad", "P. Novak", "K. Yamamoto", "S. Lindqvist", "L. Petrov", "M. Delacroix"]

# The five DeliveryIQ stages as ordered statuses (stage is DERIVED from status).
STAGE_STATUS = [
    ("Intake", "Intake"),
    ("Build", "In Build"),
    ("Review", "In Review"),
    ("Deploy", "Awaiting CAB"),
    ("Deploy", "Deploying"),
    ("Deploy", "Deployed"),
    ("Audit", "Audit"),
    ("Audit", "Done"),
]
DEPLOY_STATES = ["Not started", "Validated", "Deploying", "Deployed", "Failed", "Rolled back"]
HEALTH = ["Healthy", "Degraded", "Failing", "Unknown"]


def _iso(dt):
    return dt.isoformat() if dt else None


def build(n, days, now, span=None):
    """`days` is the MODEL window; `span` is how far back records are generated.

    They are separate on purpose: every window model must be computed over ONE record set
    (generated across `span`, the widest window) and then filtered to `days` — the same way
    the client re-windows the records file. Generating a fresh set per window made each
    window claim the full volume while the panels showed the windowed subset.
    """
    span = span or days
    rnd = random.Random(20260722)
    window_start = now - timedelta(days=days)
    records = []
    for i in range(n):
        key = f"SFC-{1000 + i}"
        squad = rnd.choice(SQUADS)
        reported = now - timedelta(days=rnd.uniform(1, span), hours=rnd.uniform(0, 24))
        age_days = (now - reported).total_seconds() / 86400.0
        # stage is distributed independently of age (weighted toward mid/late so every window
        # shows real deploys), so a status filter and the funnel agree but any window has a mix
        si = rnd.choices(range(len(STAGE_STATUS)), weights=[8, 9, 12, 6, 6, 12, 8, 12])[0]
        stage, status = STAGE_STATUS[si]
        # a few fail / roll back
        if status in ("Deploying", "Deployed") and rnd.random() < 0.12:
            stage, status = "Deploy", "Deploy Failed"
        is_done = status == "Done"
        # "Deploy Failed" is unfinished work needing rework — it must stay OPEN, or it
        # vanishes from every WIP / agent-workload view (matches app/sfc_export).
        is_open = not is_done

        risk = rnd.choices(RISK, weights=[5, 3, 2])[0]
        comps = rnd.sample(COMPONENTS, rnd.randint(1, 3))
        target = rnd.sample(ORGS, rnd.randint(1, 4))
        # ensure Prod is often a target for later-stage work
        if si >= 3 and "Prod" not in target and rnd.random() < 0.6:
            target = target + ["Prod"]

        # lifecycle timestamps (real-shaped)
        first_response = reported + timedelta(hours=rnd.uniform(2, 40)) if si >= 1 else None
        escalated = first_response + timedelta(hours=rnd.uniform(4, 60)) if (si >= 3 and rnd.random() < 0.5) else None
        resolved = reported + timedelta(days=rnd.uniform(1, max(1.5, age_days))) if is_done else None
        response_hours = ((first_response - reported).total_seconds() / 3600.0) if first_response else None

        cab = "Not required" if risk == "Low" else rnd.choice(["Pending", "Approved", "Approved", "Rejected"]) if si >= 3 else "Pending"

        # per-org deploy sub-tasks (Model A, flattened for the bake)
        org_deploys = []
        for org in target:
            if si < 4:
                dstate = "Not started"
            elif status == "Deploy Failed":
                dstate = rnd.choices(["Failed", "Deployed", "Validated"], weights=[5, 3, 2])[0]
            elif si == 4:
                dstate = rnd.choice(["Validated", "Deploying"])
            else:
                dstate = rnd.choices(["Deployed", "Deployed", "Failed", "Rolled back"], weights=[7, 6, 2, 1])[0]
            # Health only meaningful once deployed. No live Salesforce: deploy/health are
            # MODELLED — a deployed org's cell reads Source "Modelled" (maintained by the
            # writeback job), a not-started org stays "Seeded" (raw fixture).
            if dstate == "Deployed":
                health = rnd.choices(["Healthy", "Healthy", "Degraded", "Failing"], weights=[7, 6, 3, 1])[0]
                checked = (resolved or now) - timedelta(hours=rnd.uniform(0, 30))
            elif dstate in ("Failed", "Rolled back"):
                health = "Failing"
                checked = now - timedelta(hours=rnd.uniform(0, 48))
            else:
                health, checked = "Unknown", None
            # Apply the SAME staleness guard as the real bake (app/sfc_export._apply_staleness)
            # rather than hardcoding stale=False — otherwise the freshness invariant would pass
            # trivially on preview data while the guard was never exercised.
            age_h = round((now - checked).total_seconds() / 3600.0, 2) if checked else None
            stale = health != "Unknown" and (age_h is None or age_h > STALE_HOURS)
            if stale:
                health = "Unknown"
            org_deploys.append({"org": org, "deploy_state": dstate, "config_health": health,
                                "health_checked_at": _iso(checked), "stale": bool(stale), "health_age_h": age_h,
                                "source": ("Modelled" if dstate not in ("Not started",) else "Seeded")})

        # roll-ups
        states = [d["deploy_state"] for d in org_deploys]
        deploy_rollup = ("Deployed" if states and all(s == "Deployed" for s in states)
                         else "Failed" if any(s in ("Failed", "Rolled back") for s in states)
                         else "Deploying" if any(s in ("Deploying", "Validated") for s in states)
                         else "Not started")

        # agent-action ledger (what Build/Comply/Coord produced by this stage)
        build_tested = si >= 1
        comply_authorized = si >= 1
        comply_evidence = si >= 5 or is_done
        coord_conflicts = rnd.randint(0, 2) if si >= 1 else 0
        coord_deps = rnd.randint(0, 4)
        # What Jira would CLAIM (a free-set flag), kept only so the lens can contrast it with
        # the computed truth — see app/sfc_export._evidence and spec §4.4.
        evidence_claimed = is_done or (si >= 6 and rnd.random() < 0.7)
        l2_analyst = rnd.choice(REVIEWERS) if si >= 2 else None
        timeline = [{"at": None, "field": "status", "from": STAGE_STATUS[j][1],
                     "to": STAGE_STATUS[j + 1][1]} for j in range(si)]
        ev_ready, ev_missing = _evidence(
            {"comply_authorized": comply_authorized, "build_tested": build_tested,
             "l2_analyst": l2_analyst},
            org_deploys, target, stage, si)

        records.append({
            "key": key, "url": f"https://singhaditya21.atlassian.net/browse/{key}",
            "summary": f"{rnd.choice(['Add', 'Update', 'Refactor', 'Retire', 'Extend'])} {rnd.choice(comps).lower()} — {squad}",
            "issue_type": "Salesforce Config Request", "status": status, "stage": stage,
            "status_category": "done" if is_done else "indeterminate" if not is_open else "new" if stage == "Intake" else "indeterminate",
            "tower": squad, "priority": rnd.choices(PRIORITIES, weights=[2, 4, 6, 4])[0],
            "impact": rnd.choice(IMPACT), "urgency": rnd.choice(URGENCY), "intake": rnd.choice(CHANNELS),
            "change_risk": risk, "config_component_type": comps, "target_orgs": target, "package_ref": f"sfdx/{key.lower()}",
            "cab_approval": cab, "l2_analyst": l2_analyst,
            "reported_at": _iso(reported), "reported_ts": reported.timestamp(),
            "first_response_at": _iso(first_response), "escalated_at": _iso(escalated),
            "resolved_at": _iso(resolved), "age_days": round(age_days, 2), "response_hours": round(response_hours, 3) if response_hours else None,
            "is_open": is_open, "is_done": is_done,
            "org_deploys": org_deploys, "deploy_rollup": deploy_rollup,
            "build_tested": build_tested, "comply_authorized": comply_authorized, "comply_evidence": comply_evidence,
            "coord_conflicts": coord_conflicts, "coord_dependencies": coord_deps,
            "evidence_pack_claimed": evidence_claimed, "evidence_pack_ready": ev_ready,
            "evidence_missing": ev_missing, "evidence_overclaimed": bool(evidence_claimed and not ev_ready),
            "is_redeployed": _is_redeployed(timeline),
            "timeline": timeline,
            "changelog_hops": si,
            # parity with app/sfc_export: clock since the last status change. The preview's
            # timeline carries no timestamps, so this falls back to Reported At.
            "stage_entry_at": _iso(reported),
            "time_in_stage_h": round(age_days * 24, 2),
            "preview": True,
        })

    # Model KPIs are computed over the records IN THIS WINDOW, exactly as the client
    # re-windows the (window-agnostic) records file — otherwise the masthead's "N in
    # window" disagrees with every panel on the 30/90-day tabs.
    in_window = [r for r in records if r["reported_ts"] >= window_start.timestamp()]
    # ONE scoreboard implementation, shared with the live bake — so a preview tile and a live
    # tile can never be computed differently (num/den/target/verdict all come from there).
    sb = _sfc_scoreboard(in_window)
    model = {
        "project": "SFC", "preview": True, "window_days": days,
        "generated_at": now.isoformat(), "now_ts": now.timestamp(), "window_start_ts": window_start.timestamp(),
        "window_label": f"{window_start:%d %b} – {now:%d %b %Y}", "volume": len(in_window),
        "scoreboard": sb, "warnings": [], "invariants": _sfc_invariants(in_window),
        "note": "PREVIEW dataset — the SFC Jira project is not yet provisioned (see DELIVERYIQ-SF-CONFIG.md P0). Deterministic seed; not live Jira/Salesforce.",
    }
    return model, records


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    args.out.mkdir(parents=True, exist_ok=True)
    # ONE record set, built at the widest span, windowed per model — the same discipline the
    # real bake uses. Generating a fresh 64 records per window made every window file claim
    # volume=64 while the (180-day) records file windowed down to 8/29 on the 30/90 tabs.
    WIDEST = 180
    for days in (30, 90, WIDEST):
        model, _ = build(args.n, days, now, span=WIDEST)
        (args.out / f"SFC-{days}.json").write_text(json.dumps(model, separators=(",", ":"), default=str))
    # records file is window-agnostic (client windows it), built at the widest span
    _, records = build(args.n, WIDEST, now, span=WIDEST)
    (args.out / "SFC-records.json").write_text(json.dumps(
        {"project": "SFC", "preview": True, "generated_at": now.isoformat(), "count": len(records), "records": records},
        separators=(",", ":"), default=str))
    print(f"  + SFC preview seed: {len(records)} requests, {sum(len(r['org_deploys']) for r in records)} org-deploys -> {args.out}")


if __name__ == "__main__":
    main()
