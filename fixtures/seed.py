#!/usr/bin/env python3
"""Seed the OPS project with realistic support-tower traffic.

Not filler. Every ticket carries a coherent story: a plausible title for its tower,
an impact/urgency pair that derives its priority, an intake channel, a timeline, and
- where it escalated - a genuine reason and a record of what L1 tried.

The timeline lives in the seeder-controlled `Reported At` / `Resolved At` fields rather
than Jira's read-only `created`, so trend charts show 90 days of history instead of one
vertical spike on the day the seeder ran. Every filter and dashboard keys off those.

Usage:  python3 -m fixtures.seed [--count 420] [--dry-run]
"""

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from shared.jira_client import Jira, adf, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config import merge_state
from fixtures import catalog as K

SEED = 20260720  # fixed so re-runs are reproducible


NOTES_FOR = {
    "Incident": K.TROUBLESHOOTING,
    "Service Request": K.REQUEST_NOTES,
    "Change": K.CHANGE_NOTES,
    "Problem": K.PROBLEM_NOTES,
}


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
    tower = weighted(rng, D.TOWERS)
    itype = weighted(rng, K.TYPE_MIX)
    pool = K.BY_TYPE[itype].get(tower) or K.BY_TYPE["Incident"][tower]
    title, detail, base_impact, base_urgency = rng.choice(pool)
    esc_odds, time_mult, res_codes = K.TYPE_BEHAVIOUR[itype]
    channel = weighted(rng, D.INTAKE_CHANNELS)
    # Changes and problems are planned work - they do not arrive by phone.
    if itype in ("Change", "Problem"):
        channel = "Portal"


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

    priority = D.PRIORITY_MATRIX[(impact, urgency)]
    resp_h, res_h = D.SLA_TARGETS[priority]

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

    escalated = rng.random() < esc_odds
    tier = "L2" if escalated else "L1"

    # Resolution: escalated work takes materially longer
    factor = rng.triangular(0.1, 1.3, 0.35) * (1.35 if escalated else 1.0) * time_mult
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

    # Problems are investigations, not SLA-bound work. Leaving them in the
    # attainment figures would penalise the tower for doing root-cause analysis -
    # exactly the behaviour the design is trying to encourage.
    if itype == "Problem":
        response_met = None
        resolution_sla = None

    l1 = rng.choice(D.L1_ANALYSTS)[0]
    l2 = rng.choice(D.L2_ANALYSTS[tower]) if escalated else None
    reopened = "Yes" if (done and rng.random() < 0.042) else "No"

    return {
        "idx": idx, "tower": tower, "itype": itype, "title": title, "detail": detail,
        "impact": impact, "urgency": urgency, "priority": priority, "channel": channel,
        "tier": tier, "escalated": escalated, "status": status, "done": done,
        "reported": reported, "first_response": first_response,
        "escalated_at": escalated_at, "resolved_at": resolved_at,
        "response_sla": response_met, "resolution_sla": resolution_sla,
        "l1": l1, "l2": l2, "reopened": reopened,
        "escalation_reason": rng.choice(D.SELECT_FIELDS["Escalation Reason"]) if escalated else None,
        "troubleshooting": rng.choice(NOTES_FOR[itype]) if escalated else None,
        "kb": rng.choice(["Yes - article applied", "Yes - none found", "Yes - none found", "No"]) if escalated else None,
        "root_cause": rng.choice(D.SELECT_FIELDS["Root Cause"]) if done and status != "Cancelled" else None,
        "resolution_code": (rng.choice(res_codes) if done and status != "Cancelled"
                            else ("Withdrawn by requester" if status == "Cancelled" else None)),
        "comment": rng.choice(K.COMMENTS) if rng.random() < 0.45 else None,
    }


PRIORITY_NAME = {"P1": "P1 - Critical", "P2": "P2 - High",
                 "P3": "P3 - Medium", "P4": "P4 - Low"}


def jira_dt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def fields_payload(t, F, settable):
    f = {
        "project": {"key": S.PROJECT_KEY},
        "issuetype": {"name": t["itype"]},
        "summary": f"[{t['tower'].split(' ')[0]}] {t['title']}",
        # The derived priority must land on the real field, not just the description,
        # or every priority-based queue and SLA view is blind to it.
        "priority": {"name": PRIORITY_NAME[t["priority"]]},
        "description": adf(
            f"{t['detail']}\n\n"
            f"Reported via {t['channel']} at {t['reported'].strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"Impact {t['impact']} / Urgency {t['urgency']} -> {t['priority']} "
            f"(derived, not agent-selected)."
        ),
    }
    def put(name, value):
        # A select payload of {"value": None} is not None but is still invalid.
        # Check for the *key* - an ADF document is also a dict and has no "value"
        # key, and testing .get("value") silently dropped every textarea field.
        if isinstance(value, dict) and "value" in value and value["value"] is None:
            return
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
    # Every other state reader guards this; seed used to not, so a fresh clone
    # or an unbuilt instance got a bare pathlib traceback instead of the one
    # instruction that fixes it.
    if not STATE.exists():
        sys.exit("%s not found - run python3 -m jira_config.build first." % STATE)
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError) as e:
        sys.exit("cannot read %s: %s" % (STATE, e))
    if "fields" not in state:
        sys.exit("%s has no 'fields' - re-run python3 -m jira_config.build." % STATE)
    F = state["fields"]
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc)

    # Only send fields the create screen actually accepts, or every issue 400s.
    meta = j.get(f"/rest/api/3/issue/createmeta?projectKeys={S.PROJECT_KEY}"
                 f"&expand=projects.issuetypes.fields")
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
    for label, key in (("type", "itype"), ("tower", "tower"), ("priority", "priority"),
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
    merge_state(STATE, state, ("seeded",), dry=args.dry_run)


if __name__ == "__main__":
    main()
