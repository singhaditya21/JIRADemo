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


def build(n, days, now):
    rnd = random.Random(20260722)
    window_start = now - timedelta(days=days)
    records = []
    for i in range(n):
        key = f"SFC-{1000 + i}"
        squad = rnd.choice(SQUADS)
        reported = now - timedelta(days=rnd.uniform(1, days), hours=rnd.uniform(0, 24))
        age_days = (now - reported).total_seconds() / 86400.0
        # stage is distributed independently of age (weighted toward mid/late so every window
        # shows real deploys), so a status filter and the funnel agree but any window has a mix
        si = rnd.choices(range(len(STAGE_STATUS)), weights=[8, 9, 12, 6, 6, 12, 8, 12])[0]
        stage, status = STAGE_STATUS[si]
        # a few fail / roll back
        if status in ("Deploying", "Deployed") and rnd.random() < 0.12:
            stage, status = "Deploy", "Deploy Failed"
        is_done = status == "Done"
        is_open = not is_done and status not in ("Deploy Failed",)

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
            org_deploys.append({"org": org, "deploy_state": dstate, "config_health": health,
                                "health_checked_at": _iso(checked), "source": ("Modelled" if dstate not in ("Not started",) else "Seeded")})

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
        evidence_pack_ready = is_done or (si >= 6 and rnd.random() < 0.7)

        records.append({
            "key": key, "url": f"https://singhaditya21.atlassian.net/browse/{key}",
            "summary": f"{rnd.choice(['Add', 'Update', 'Refactor', 'Retire', 'Extend'])} {rnd.choice(comps).lower()} — {squad}",
            "issue_type": "Salesforce Config Request", "status": status, "stage": stage,
            "status_category": "done" if is_done else "indeterminate" if not is_open else "new" if stage == "Intake" else "indeterminate",
            "tower": squad, "priority": rnd.choices(PRIORITIES, weights=[2, 4, 6, 4])[0],
            "impact": rnd.choice(IMPACT), "urgency": rnd.choice(URGENCY), "intake": rnd.choice(CHANNELS),
            "change_risk": risk, "config_component_type": comps, "target_orgs": target, "package_ref": f"sfdx/{key.lower()}",
            "cab_approval": cab, "l2_analyst": rnd.choice(REVIEWERS) if si >= 2 else None,
            "reported_at": _iso(reported), "reported_ts": reported.timestamp(),
            "first_response_at": _iso(first_response), "escalated_at": _iso(escalated),
            "resolved_at": _iso(resolved), "age_days": round(age_days, 2), "response_hours": round(response_hours, 3) if response_hours else None,
            "is_open": is_open, "is_done": is_done,
            "org_deploys": org_deploys, "deploy_rollup": deploy_rollup,
            "build_tested": build_tested, "comply_authorized": comply_authorized, "comply_evidence": comply_evidence,
            "coord_conflicts": coord_conflicts, "coord_dependencies": coord_deps, "evidence_pack_ready": evidence_pack_ready,
            "timeline": [{"at": None, "field": "status", "from": STAGE_STATUS[j][1], "to": STAGE_STATUS[j + 1][1]} for j in range(si)],
            "changelog_hops": si,
            "preview": True,
        })

    # minimal delivery model for the KPI strip + window filtering
    deployed_orgs = sum(1 for r in records for d in r["org_deploys"] if d["deploy_state"] == "Deployed")
    total_org_targets = sum(len(r["org_deploys"]) for r in records) or 1
    lead = [((datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["reported_at"])).total_seconds() / 86400.0)
            for r in records if r["resolved_at"]]
    lead.sort()
    sb = {
        "deploy_success_pct": {"value": deployed_orgs / total_org_targets * 100, "num": deployed_orgs, "den": total_org_targets, "target": 90, "direction": "ge", "verdict": None},
        "lead_time_d": {"value": (lead[len(lead) // 2] if lead else None), "num": None, "den": None, "target": None, "direction": None, "verdict": None},
    }
    for k, m in sb.items():
        if m.get("target") is not None and m.get("value") is not None:
            m["verdict"] = "PASS" if (m["value"] >= m["target"] if m["direction"] == "ge" else m["value"] <= m["target"]) else "GAP"
    model = {
        "project": "SFC", "preview": True, "window_days": days,
        "generated_at": now.isoformat(), "now_ts": now.timestamp(), "window_start_ts": window_start.timestamp(),
        "window_label": f"{window_start:%d %b} – {now:%d %b %Y}", "volume": len(records),
        "scoreboard": sb, "warnings": [],
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
    for days in (30, 90, 180):
        model, records = build(args.n, days, now)
        (args.out / f"SFC-{days}.json").write_text(json.dumps(model, separators=(",", ":"), default=str))
    # records file is window-agnostic (client windows it), built at the widest span
    _, records = build(args.n, 180, now)
    (args.out / "SFC-records.json").write_text(json.dumps(
        {"project": "SFC", "preview": True, "generated_at": now.isoformat(), "count": len(records), "records": records},
        separators=(",", ":"), default=str))
    print(f"  + SFC preview seed: {len(records)} requests, {sum(len(r['org_deploys']) for r in records)} org-deploys -> {args.out}")


if __name__ == "__main__":
    main()
