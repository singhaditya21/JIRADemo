#!/usr/bin/env python3
"""Seed the OPS project with realistic support-tower traffic.

Not filler. Every ticket carries a coherent story: a plausible title for its tower,
an impact/urgency pair that derives its priority, an intake channel, a timeline, and
- where it escalated - a genuine reason and a record of what L1 tried.

The timeline lives in the seeder-controlled `Reported At` / `Resolved At` fields rather
than Jira's read-only `created`, so trend charts show 90 days of history instead of one
vertical spike on the day the seeder ran. Every filter and dashboard keys off those.

Usage:  python3 scripts/03_seed.py [--count 420] [--dry-run]
"""

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import Jira, adf, log, require_env  # noqa: E402
import config as C  # noqa: E402

STATE = Path(__file__).parent / ".build_state.json"
SEED = 20260720  # fixed so re-runs are reproducible

# --- realistic ticket content, per tower -----------------------------------
CATALOG = {
    "End User Computing": [
        ("Laptop will not join corporate VPN after OS update", "VPN client 7.2 fails handshake post-update", "Low", "Medium"),
        ("Outlook repeatedly prompting for credentials", "Modern auth token not refreshing", "Low", "Medium"),
        ("Shared drive mapping missing after profile rebuild", "Login script not applying drive map", "Low", "Low"),
        ("Laptop battery drains within 90 minutes", "Hardware degradation suspected", "Low", "Low"),
        ("Cannot print to floor-3 multifunction device", "Print queue stalled on server", "Low", "Medium"),
        ("Teams audio device not detected on docking station", "Dock firmware mismatch", "Low", "Low"),
        ("Full disk encryption recovery key required", "User locked out after BIOS change", "Medium", "High"),
        ("New starter equipment build not delivered", "Provisioning request incomplete", "Medium", "Medium"),
        ("Screen flicker on external monitor via USB-C", "Display driver or cable fault", "Low", "Low"),
        ("Software install request - statistical package", "License allocation needed", "Low", "Low"),
    ],
    "Enterprise Applications": [
        ("Payroll export failing at month-end close", "Batch job aborts on record 4,812", "High", "High"),
        ("ERP purchase requisition stuck in approval", "Workflow engine not advancing", "Medium", "High"),
        ("CRM reports timing out for regional managers", "Query plan regression after release", "Medium", "Medium"),
        ("Invoice PDF generation producing blank pages", "Template rendering fault", "Medium", "Medium"),
        ("SSO redirect loop on finance portal", "SAML assertion clock skew", "High", "High"),
        ("Bulk upload rejects valid supplier records", "Validation rule too strict after change", "Medium", "Medium"),
        ("Scheduled nightly reconciliation did not run", "Scheduler missed trigger window", "High", "Medium"),
        ("User cannot access cost centre 4400", "Role mapping missing post-reorg", "Low", "Medium"),
        ("Expense approval notifications not sending", "Mail connector queue backed up", "Medium", "Medium"),
        ("Duplicate journal entries after integration retry", "Idempotency key not honoured", "High", "High"),
    ],
    "Network & Connectivity": [
        ("Branch office link down - 40 users affected", "Primary circuit loss, failover not engaged", "High", "High"),
        ("Intermittent packet loss on data centre uplink", "Approx 4% loss on core switch port", "High", "High"),
        ("Wi-Fi authentication failing in west wing", "RADIUS timeout under load", "Medium", "High"),
        ("VPN concentrator at session capacity", "Licence ceiling reached during peak", "High", "High"),
        ("DNS resolution slow for internal zone", "Forwarder responding above 800ms", "Medium", "Medium"),
        ("Firewall rule change request for vendor access", "Standard change, needs approval", "Low", "Low"),
        ("Guest network captive portal not loading", "Portal certificate expired", "Low", "Medium"),
        ("Latency spike between regions", "Carrier-side routing change suspected", "Medium", "High"),
    ],
    "Database": [
        ("Replication lag exceeding 15 minutes", "Secondary falling behind under write load", "High", "High"),
        ("Deadlocks on order processing table", "Lock contention during batch window", "High", "High"),
        ("Tablespace approaching capacity", "92% used, growth trend steep", "Medium", "High"),
        ("Slow query on customer search endpoint", "Missing index after schema change", "Medium", "Medium"),
        ("Backup job failed verification step", "Checksum mismatch on archive", "High", "Medium"),
        ("Read-only user requires reporting access", "Standard access request", "Low", "Low"),
        ("Connection pool exhaustion during peak", "Application not releasing connections", "High", "High"),
    ],
    "Compute & Storage": [
        ("Virtual host memory pressure - workloads ballooning", "Cluster above 90% memory", "High", "High"),
        ("File share quota exceeded for engineering", "Growth outpacing allocation", "Medium", "Medium"),
        ("Backup window overrunning into business hours", "Job duration doubled since retention change", "Medium", "Medium"),
        ("Server unresponsive after patch cycle", "Host requires manual intervention", "High", "High"),
        ("Storage array reporting predictive disk failure", "Drive flagged, RAID still healthy", "Medium", "High"),
        ("Capacity request for new application tier", "Standard provisioning request", "Low", "Low"),
        ("Snapshot retention consuming excess capacity", "Policy misconfigured after migration", "Medium", "Low"),
    ],
    "Cloud & Security": [
        ("Suspicious sign-in from unrecognised location", "Impossible-travel alert raised", "High", "High"),
        ("Cloud spend anomaly - compute up 40% week on week", "Untagged resources in dev subscription", "Medium", "High"),
        ("Certificate expiring in 5 days on public endpoint", "Renewal not automated", "High", "High"),
        ("Privileged access review overdue", "Quarterly attestation outstanding", "Medium", "Medium"),
        ("Phishing report from finance team", "User reported, no click confirmed", "Medium", "High"),
        ("Storage bucket permissions wider than policy", "Public read detected by scanner", "High", "High"),
        ("MFA enrolment failing for contractor accounts", "Directory sync attribute missing", "Medium", "Medium"),
    ],
}

TROUBLESHOOTING = [
    "Confirmed the fault reproduces from a second account and a clean device profile. Checked the runbook entry and applied the documented restart sequence with no change. Collected client logs and attached them.",
    "Verified service health and recent change records; nothing scheduled in the window. Reproduced on two clients on different subnets, which rules out a local cause. Escalating with logs attached.",
    "Ran the standard diagnostic script and reviewed the last 200 log lines. Error is consistent and matches no existing KB article. Cleared cache and re-authenticated without effect.",
    "Checked connectivity, credentials and permissions in that order. Permissions look correct against the role matrix. Restarted the client service twice; fault persists across both.",
    "Compared configuration against a working peer and found no difference. Confirmed the issue began after the release on the date noted. Rolled back the local change with no improvement.",
    "Followed the KB article end to end. The documented fix does not apply because the underlying setting is now managed centrally. Needs someone with elevated access.",
]

COMMENTS = [
    "Acknowledged and triaging. Will update within the hour.",
    "Confirmed with the user that the issue is still occurring as described.",
    "Applied the documented workaround; monitoring before closing.",
    "Reproduced in the test environment - behaves identically.",
    "Awaiting confirmation from the requester that service is restored.",
    "Change record raised to cover the permanent fix.",
]


def weighted(rng, pairs):
    vals, wts = zip(*pairs)
    return rng.choices(vals, weights=wts, k=1)[0]


def business_hours_offset(rng, dt, hours):
    """Approximate a business-hours clock by stretching elapsed time over weekends."""
    end = dt + timedelta(hours=hours)
    if end.weekday() >= 5:
        end += timedelta(days=2)
    return end


def build_ticket(rng, idx, now):
    tower = weighted(rng, C.TOWERS)
    title, detail, base_impact, base_urgency = rng.choice(CATALOG[tower])
    channel = weighted(rng, C.INTAKE_CHANNELS)

    # Catalog entries describe the archetype at its worst. Most real instances are
    # milder, so damp both axes downward - without this, a third of the queue is P1,
    # which is exactly the priority inflation the design exists to prevent.
    DOWN = {"High": "Medium", "Medium": "Low", "Low": "Low"}
    impact, urgency = base_impact, base_urgency
    if channel == "Monitoring" and rng.random() < 0.40:
        impact, urgency = "High", "High"          # detection precedes complaint
    else:
        if rng.random() < 0.62:
            urgency = DOWN[urgency]
        if rng.random() < 0.55:
            impact = DOWN[impact]
    if rng.random() < 0.08:                        # natural variance either way
        impact = rng.choice(["High", "Medium", "Low"])

    priority = C.PRIORITY_MATRIX[(impact, urgency)]
    resp_h, res_h = C.SLA_TARGETS[priority]

    # 90 days of history, weekday-heavy, with a mild business-hours bias
    age_days = rng.triangular(0, 90, 55)
    reported = now - timedelta(days=age_days)
    if reported.weekday() >= 5 and rng.random() < 0.7:
        reported -= timedelta(days=2)
    reported = reported.replace(hour=rng.choices(range(24),
                                weights=[1,1,1,1,1,2,4,7,9,10,10,9,8,9,10,9,7,5,3,2,2,1,1,1])[0],
                                minute=rng.randrange(60))

    # First response: usually inside target, sometimes not
    resp_actual = resp_h * rng.triangular(0.1, 1.5, 0.35)
    first_response = reported + timedelta(hours=resp_actual)
    response_met = "Met" if resp_actual <= resp_h else "Breached"

    escalated = rng.random() < 0.38
    tier = "L2" if escalated else "L1"

    # Resolution: escalated work takes materially longer
    factor = rng.triangular(0.1, 1.3, 0.35) * (1.35 if escalated else 1.0)
    res_actual = res_h * factor
    resolved_at = business_hours_offset(rng, reported, res_actual) if priority in ("P3", "P4") \
        else reported + timedelta(hours=res_actual)
    escalated_at = first_response + timedelta(hours=resp_actual * rng.uniform(0.5, 3)) if escalated else None

    # Lifecycle position. Most traffic is finished; a live tail sits in flight.
    r = rng.random()
    if r < 0.74:
        status, done = "Closed", True
    elif r < 0.82:
        status, done = "Resolved", True
    elif r < 0.86:
        status, done = ("In Progress L2" if escalated else "In Progress L1"), False
    elif r < 0.90:
        status, done = "Escalated to L2", False
        escalated = True; tier = "L2"
    elif r < 0.935:
        status, done = "Pending Customer", False
    elif r < 0.955:
        status, done = "Pending Vendor", False
    elif r < 0.97:
        status, done = "Triage", False
    elif r < 0.985:
        status, done = "New", False
    else:
        status, done = "Cancelled", True

    # A ticket cannot be resolved in the future
    if done and resolved_at > now:
        resolved_at = now - timedelta(hours=rng.uniform(1, 48))

    if not done:
        resolved_at = None
        resolution_sla = "Paused" if status.startswith("Pending") else "In progress"
    else:
        resolution_sla = "Met" if res_actual <= res_h else "Breached"

    l1 = rng.choice(C.L1_ANALYSTS)[0]
    l2 = rng.choice(C.L2_ANALYSTS[tower]) if escalated else None
    reopened = "Yes" if (done and rng.random() < 0.042) else "No"

    return {
        "idx": idx, "tower": tower, "title": title, "detail": detail,
        "impact": impact, "urgency": urgency, "priority": priority, "channel": channel,
        "tier": tier, "escalated": escalated, "status": status, "done": done,
        "reported": reported, "first_response": first_response,
        "escalated_at": escalated_at, "resolved_at": resolved_at,
        "response_sla": response_met, "resolution_sla": resolution_sla,
        "l1": l1, "l2": l2, "reopened": reopened,
        "escalation_reason": rng.choice(C.SELECT_FIELDS["Escalation Reason"]) if escalated else None,
        "troubleshooting": rng.choice(TROUBLESHOOTING) if escalated else None,
        "kb": rng.choice(["Yes - article applied", "Yes - none found", "Yes - none found", "No"]) if escalated else None,
        "root_cause": rng.choice(C.SELECT_FIELDS["Root Cause"]) if done and status != "Cancelled" else None,
        "resolution_code": (rng.choice(C.SELECT_FIELDS["Resolution Code"])
                            if done and status != "Cancelled" else
                            ("Withdrawn by requester" if status == "Cancelled" else None)),
        "comment": rng.choice(COMMENTS) if rng.random() < 0.45 else None,
    }


def jira_dt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def fields_payload(t, F, settable):
    f = {
        "project": {"key": C.PROJECT_KEY},
        "issuetype": {"name": "Task"},
        "summary": f"[{t['tower'].split(' ')[0]}] {t['title']}",
        "description": adf(
            f"{t['detail']}\n\n"
            f"Reported via {t['channel']} at {t['reported'].strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"Impact {t['impact']} / Urgency {t['urgency']} -> {t['priority']} "
            f"(derived, not agent-selected)."
        ),
    }
    def put(name, value):
        if value is not None and name in F and F[name] in settable:
            f[F[name]] = value

    put("Tower", {"value": t["tower"]})
    put("Support Tier", {"value": t["tier"]})
    put("Impact", {"value": t["impact"]})
    put("Urgency", {"value": t["urgency"]})
    put("Intake Channel", {"value": t["channel"]})
    put("Response SLA", {"value": t["response_sla"]})
    put("Resolution SLA", {"value": t["resolution_sla"]})
    put("Reopened", {"value": t["reopened"]})
    put("L1 Analyst", t["l1"])
    put("L2 Analyst", t["l2"])
    put("Affected Service", t["tower"])
    put("Reported At", jira_dt(t["reported"]))
    put("First Response At", jira_dt(t["first_response"]))
    if t["escalated"]:
        put("Escalation Reason", {"value": t["escalation_reason"]})
        # textarea custom fields take ADF, not a bare string
        put("Troubleshooting Performed", adf(t["troubleshooting"]))
        put("KB Article Checked", {"value": t["kb"]})
        if t["escalated_at"]:
            put("Escalated At", jira_dt(t["escalated_at"]))
    if t["resolved_at"]:
        put("Resolved At", jira_dt(t["resolved_at"]))
    if t["root_cause"]:
        put("Root Cause", {"value": t["root_cause"]})
    if t["resolution_code"]:
        put("Resolution Code", {"value": t["resolution_code"]})
    return f


# Transition path to each target status, walking the real workflow graph so the
# issue history shows every hand that touched the ticket.
PATHS = {
    "New": [],
    "Triage": ["Begin triage"],
    "In Progress L1": ["Begin triage", "Start L1 work"],
    "Escalated to L2": ["Begin triage", "Start L1 work", "Escalate to L2"],
    "In Progress L2": ["Begin triage", "Start L1 work", "Escalate to L2", "Accept at L2"],
    "Pending Customer": ["Begin triage", "Start L1 work", "Await customer"],
    "Pending Vendor": ["Begin triage", "Start L1 work", "Await vendor"],
    "Resolved": ["Begin triage", "Start L1 work", "Resolve"],
    "Closed": ["Begin triage", "Start L1 work", "Resolve", "Close"],
    "Cancelled": ["Begin triage", "Cancel"],
}


def path_for(t):
    p = list(PATHS[t["status"]])
    if t["escalated"] and t["status"] in ("Resolved", "Closed"):
        p = ["Begin triage", "Start L1 work", "Escalate to L2", "Accept at L2", "Resolve"]
        if t["status"] == "Closed":
            p.append("Close")
    return p


def create_one(j, t, F, settable):
    issue = j.post("/rest/api/3/issue", {"fields": fields_payload(t, F, settable)})
    key = issue["key"]
    for step in path_for(t):
        avail = j.get(f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
        match = next((x for x in avail if x["name"].lower() == step.lower()), None)
        if match:
            j.post(f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": match["id"]}})
    if t["comment"]:
        j.post(f"/rest/api/3/issue/{key}/comment", {"body": adf(t["comment"])})
    return key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=420)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    require_env()
    j = Jira()
    state = json.loads(STATE.read_text())
    F = state["fields"]
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc)

    # Only send fields the create screen actually accepts, or every issue 400s.
    meta = j.get(f"/rest/api/3/issue/createmeta?projectKeys={C.PROJECT_KEY}"
                 f"&issuetypeNames=Task&expand=projects.issuetypes.fields")
    settable = set()
    for p in meta.get("projects", []):
        for it in p.get("issuetypes", []):
            settable |= set(it.get("fields", {}).keys())
    usable = [n for n, fid in F.items() if fid in settable]
    log(f"  {len(usable)}/{len(F)} schema fields settable on create")
    missing = [n for n, fid in F.items() if fid not in settable]
    if missing:
        log(f"  not on create screen (will be skipped): {', '.join(missing)}")

    tickets = [build_ticket(rng, i, now) for i in range(args.count)]

    log(f"\n== distribution across {len(tickets)} tickets ==")
    for label, key in (("tower", "tower"), ("priority", "priority"),
                       ("channel", "channel"), ("status", "status")):
        counts = {}
        for t in tickets:
            counts[t[key]] = counts.get(t[key], 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        log(f"  {label:<9} " + "  ".join(f"{k}:{v}" for k, v in top))
    esc = sum(1 for t in tickets if t["escalated"])
    log(f"  escalated {esc} ({esc/len(tickets):.0%})  |  "
        f"L1-resolved {len(tickets)-esc} ({1-esc/len(tickets):.0%})")
    log(f"  reopened  {sum(1 for t in tickets if t['reopened']=='Yes')}")
    log(f"  SLA breached (resolution) {sum(1 for t in tickets if t['resolution_sla']=='Breached')}")

    if args.dry_run:
        log("\ndry run - nothing written")
        return

    log(f"\n== creating in Jira ({args.workers} workers) ==")
    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(create_one, j, t, F, settable): t for t in tickets}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                ok.append(fut.result())
            except Exception as e:
                failed.append(str(e)[:160])
            if n % 40 == 0:
                log(f"  {n}/{len(tickets)}  ok={len(ok)} failed={len(failed)}")

    log(f"\n  created {len(ok)}, failed {len(failed)}")
    for f in failed[:3]:
        log(f"    ! {f}")
    state["seeded"] = len(ok)
    STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
