#!/usr/bin/env python3
"""Seed the ITSM (Jira Service Management) project with realistic L1/L2 tower traffic.

This is fixtures/seed.py's model re-targeted at JSM. The ticket *content* and the whole
derivation chain (tower -> archetype -> impact/urgency -> priority -> SLA target ->
timeline) are reused verbatim from fixtures/catalog.py and shared/domain.py, so ITSM tells the same
operational story as OPS. What changes is the shape of the container:

  * OPS has one bespoke workflow with eleven statuses shared by all four types.
    ITSM has FIVE stock ITIL workflows, one per issue type, with disjoint status
    sets and no shared vocabulary. So the lifecycle is drawn once as an abstract
    STAGE and then mapped per issue type (STATUS_FOR), and the transition path is
    walked over each workflow's real edge list (EDGES).
  * OPS's "Escalated to L2" is a status. In JSM only the two request-fulfilment
    workflows have an Escalated status; incidents and problems carry escalation in
    the fields alone. Both are honoured - an escalated request really transitions
    through Escalated, so the audit trail shows it.
  * Changes go through the real ITIL approval chain (peer review -> CAB ->
    awaiting implementation -> implementing -> resolved), which is why Change maps
    to the approvals-capable Change type rather than a plain task.
  * Service requests that need sign-off use "Service Request with Approvals" and
    are driven through its approval gate.

Everything else that fixtures/seed.py learned the hard way still applies and is kept:
  * Jira's `created` is read-only, so the real timeline lives in `Reported At`
    and every view keys off it, not `created`.
  * Textarea custom fields need ADF, not a bare string.
  * {"value": None} is an invalid select payload - omit the field instead, and
    test for the KEY not the value, because an ADF doc is also a dict.
  * Problems carry no SLA; they are investigations.
  * Priority lands on the real priority field, not just the description.

New for JSM: `Request Type` (customfield_10010) takes a bare id STRING - not
{"id": ...}, not {"requestType": {...}} - and is what makes an issue show up as a
real customer request rather than a bare Jira issue.

SAFETY: writes only to ITSM. A guard asserts OPS is untouched before and after.

Usage:  python3 -m fixtures.jsm_seed [--count 420] [--dry-run] [--pilot 6]
"""

import argparse
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.jira_client import Jira, adf, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as OPS_STATE, JSM_STATE as STATE
from fixtures import catalog as K

# The resume cursor is a fixture artifact, not build state, so it sits beside the
# seeder rather than in jira_config/state/.
DONE = Path(__file__).resolve().parent / ".jsm_seed_done.json"
SEED = 20260721
PROJECT = S.JSM_PROJECT_KEY
SEED_LABEL = "tower-seed"

# Target mix for the JSM tower (incidents dominate a little harder than in OPS).
TYPE_MIX = [("Incident", 65), ("Service Request", 26), ("Change", 7), ("Problem", 3)]

# catalog.TYPE_BEHAVIOUR plus the forced-escalation lifecycle stage already lands on
# the tower's stated 40%; the hook stays so the rate is tunable without editing catalog.
ESC_UPLIFT = 1.00

NOTES_FOR = {
    "Incident": K.TROUBLESHOOTING,
    "Service Request": K.REQUEST_NOTES,
    "Change": K.CHANGE_NOTES,
    "Problem": K.PROBLEM_NOTES,
}

APPROVER_ID = [None]  # filled from /myself at run time

# ---------------------------------------------------------------------------
# The five ITIL workflows, as their real edge lists.
#
# Read off /rest/api/3/workflow/search?expand=transitions rather than guessed.
# Keyed (from_status, transition_name) -> to_status because the Change workflow
# reuses the names "Approve" and "Cancel" from different statuses with different
# destinations - matching on name alone would land the ticket in the wrong place.
# ---------------------------------------------------------------------------
PEER = "Peer review / change manager approval"

WORKFLOWS = {
    "Incident": {
        "initial": "Open",
        "edges": {
            ("Open", "Investigate"): "Work in progress",
            ("Pending", "Investigate"): "Work in progress",
            ("Open", "Pending"): "Pending",
            ("Work in progress", "Pending"): "Pending",
            ("Open", "Resolve"): "Completed",
            ("Work in progress", "Resolve"): "Completed",
            ("Open", "Cancel"): "Canceled",
            ("Work in progress", "Cancel"): "Canceled",
            ("Pending", "Cancel"): "Canceled",
            ("Completed", "Close"): "Closed",
            ("Canceled", "Close"): "Closed",
            # escalation path added by jira_config.jsm_workflow
            ("Work in progress", "Escalate to L2"): "Escalated to L2",
            ("Escalated to L2", "Accept at L2"): "Work in progress",
            ("Escalated to L2", "Resolve"): "Completed",
        },
    },
    "Service Request": {
        "initial": "Waiting for support",
        "edges": {
            ("Waiting for support", "In progress"): "In Progress",
            ("Pending", "In progress"): "In Progress",
            ("Escalated", "In progress"): "In Progress",
            ("Waiting for support", "Escalate"): "Escalated",
            ("Waiting for customer", "Escalate this issue"): "Escalated",
            ("Waiting for support", "Respond to customer"): "Waiting for customer",
            ("Pending", "Respond to customer"): "Waiting for customer",
            ("Waiting for customer", "Respond to support"): "Waiting for support",
            ("Waiting for support", "Pending"): "Pending",
            ("In Progress", "Pending"): "Pending",
            ("Waiting for support", "Resolve this issue"): "Resolved",
            ("Waiting for customer", "Resolve this issue"): "Resolved",
            ("Pending", "Resolve this issue"): "Resolved",
            ("In Progress", "Resolve this issue"): "Resolved",
            ("Waiting for support", "Cancel request"): "Canceled",
            ("Waiting for customer", "Cancel request"): "Canceled",
            ("Pending", "Cancel request"): "Canceled",
            ("In Progress", "Cancel request"): "Canceled",
            ("Resolved", "Close"): "Closed",
            ("Canceled", "Close"): "Closed",
        },
    },
    "Change": {
        "initial": PEER,
        "edges": {
            (PEER, "Approve"): "Planning",
            (PEER, "Decline"): "Declined",
            (PEER, "Cancel"): "Canceled",
            (PEER, "Emergency override"): "Awaiting implementation",
            ("Planning", "Ready for CAB approval"): "Awaiting CAB approval",
            ("Planning", "Ready for implementation"): "Awaiting implementation",
            ("Planning", "Pending"): "Pending",
            ("Planning", "Cancel"): "Canceled",
            ("Awaiting CAB approval", "Approve"): "Awaiting implementation",
            ("Awaiting CAB approval", "Decline"): "Declined",
            ("Awaiting CAB approval", "Emergency override"): "Awaiting implementation",
            ("Awaiting implementation", "Start implementation"): "Implementing",
            ("Awaiting implementation", "Pending"): "Pending",
            ("Awaiting implementation", "Cancel"): "Canceled",
            ("Implementing", "Change completed"): "Resolved",
            ("Pending", "Back to planning"): "Planning",
            ("Pending", "Ready for implementation"): "Awaiting implementation",
            ("Pending", "Cancel"): "Canceled",
            ("Declined", "Cancel"): "Canceled",
            ("Resolved", "Close"): "Closed",
            ("Declined", "Close"): "Closed",
            ("Canceled", "Close"): "Closed",
        },
    },
    "Problem": {
        "initial": "Open",
        "edges": {
            ("Open", "Review"): "Under review",
            ("Open", "Complete"): "Completed",
            ("Open", "Cancel"): "Canceled",
            ("Under review", "Investigate"): "Under investigation",
            ("Under review", "Pending"): "Pending",
            ("Under review", "Cancel"): "Canceled",
            ("Under investigation", "Complete"): "Completed",
            ("Under investigation", "Pending"): "Pending",
            ("Under investigation", "Cancel"): "Canceled",
            ("Pending", "Investigate"): "Under investigation",
            ("Pending", "Back to under review"): "Under review",
            ("Completed", "Close"): "Closed",
            ("Canceled", "Close"): "Closed",
            # escalation path added by jira_config.jsm_workflow
            ("Under investigation", "Escalate to L2"): "Escalated to L2",
            ("Escalated to L2", "Accept at L2"): "Under investigation",
        },
    },
}

# The approvals variant is the request workflow with an approval gate bolted on the front.
#
# THE APPROVAL GATE CANNOT BE PASSED OVER REST ON THIS INSTANCE. Proven, not assumed:
# the "Waiting for approval" status carries approval.field.id=customfield_10003 and
# approval.exclude=reporter,assignee. The seeder is the reporter of every issue it
# creates, so it is excluded from answering its own approval - the approval object
# comes back canAnswerApproval=false with an empty approvers list, and
# POST /rest/servicedeskapi/request/{k}/approval/{id} 403s "You don't have approve
# permission." Posting the hidden approved-transition id (901, read off the status
# property) directly 400s on the same condition. The only fix is a second account to
# act as reporter or approver, and creating accounts is out of scope here.
#
# So this type is used ONLY for requests that legitimately SIT at the gate - a
# pending-approval backlog is a real and demo-worthy queue state - and never as a
# waypoint to a downstream status it cannot reach. Change, whose ITIL approval chain
# runs on ordinary transitions (Approve -> CAB -> Approve), carries the approval story.
WORKFLOWS["Service Request with Approvals"] = {
    "initial": "Waiting for approval",
    "edges": {**WORKFLOWS["Service Request"]["edges"], **{
        ("Waiting for approval", "Cancel request"): "Canceled",
    }},
}

DONE_STATUSES = {"Closed", "Completed", "Resolved", "Canceled", "Declined"}

# Abstract lifecycle stage -> the concrete status in each workflow.
STATUS_FOR = {
    "Incident": {
        "NEW": "Open", "TRIAGE": "Open", "WORKING": "Work in progress",
        "ESCALATED": "Escalated to L2", "PENDING_CUST": "Pending",
        "PENDING_VENDOR": "Pending", "RESOLVED": "Completed",
        "CLOSED": "Closed", "CANCELLED": "Canceled",
    },
    "Service Request": {
        "NEW": "Waiting for support", "TRIAGE": "Waiting for support",
        "WORKING": "In Progress", "ESCALATED": "Escalated",
        "PENDING_CUST": "Waiting for customer", "PENDING_VENDOR": "Pending",
        "RESOLVED": "Resolved", "CLOSED": "Closed", "CANCELLED": "Canceled",
    },
    "Change": {
        "NEW": PEER, "TRIAGE": "Planning", "WORKING": "Implementing",
        "ESCALATED": "Awaiting CAB approval", "PENDING_CUST": "Pending",
        "PENDING_VENDOR": "Pending", "RESOLVED": "Resolved",
        "CLOSED": "Closed", "CANCELLED": "Canceled",
    },
    "Problem": {
        "NEW": "Open", "TRIAGE": "Under review", "WORKING": "Under investigation",
        "ESCALATED": "Escalated to L2", "PENDING_CUST": "Pending",
        "PENDING_VENDOR": "Pending", "RESOLVED": "Completed",
        "CLOSED": "Closed", "CANCELLED": "Canceled",
    },
}
STATUS_FOR["Service Request with Approvals"] = dict(
    STATUS_FOR["Service Request"], NEW="Waiting for approval",
    AWAITING_APPROVAL="Waiting for approval")


def route(jtype, target, escalated, emergency=False):
    """Breadth-first walk of the real workflow graph to `target`.

    Preferring the longest sensible route rather than the shortest is deliberate:
    a change that jumps straight from peer review to closed has no audit trail.
    Escalated requests are forced through the Escalated status, and emergency
    changes are forced through the override edge, so the history reads correctly.
    """
    wf = WORKFLOWS[jtype]
    start = wf["initial"]
    if target == start:
        return []

    # Forced intermediate hops that make the story true rather than merely legal.
    via = []
    if jtype in ("Service Request", "Service Request with Approvals"):
        if escalated and target in ("Resolved", "Closed", "In Progress"):
            via.append("Escalated")
        if target in ("Resolved", "Closed"):
            via.append("In Progress")
    elif jtype == "Change" and target in ("Implementing", "Resolved", "Closed"):
        via = ["Awaiting implementation"] if emergency else \
              ["Planning", "Awaiting CAB approval", "Awaiting implementation"]
        via.append("Implementing")
    elif jtype == "Problem" and target in ("Completed", "Closed", "Pending"):
        via = ["Under review", "Under investigation"]
        if escalated:
            via.append("Escalated to L2")   # workflow now carries the path (jsm_workflow)
    elif jtype == "Incident" and target in ("Completed", "Closed", "Pending"):
        via = ["Work in progress"]
        if escalated:
            via.append("Escalated to L2")

    hops, cur = [], start
    for waypoint in via + [target]:
        if waypoint == cur:
            continue
        leg = _shortest(wf["edges"], cur, waypoint, emergency)
        if leg is None:
            return _shortest(wf["edges"], start, target, emergency) or []
        hops += leg
        cur = waypoint
    return hops


def _shortest(edges, src, dst, emergency=False):
    seen, queue = {src}, [(src, [])]
    while queue:
        node, path = queue.pop(0)
        for (frm, name), to in edges.items():
            if frm != node or to in seen:
                continue
            # Never route through the override unless this is an emergency change.
            if name == "Emergency override" and not emergency:
                continue
            if to == dst:
                return path + [(name, to)]
            seen.add(to)
            queue.append((to, path + [(name, to)]))
    return None


# ---------------------------------------------------------------------------
# Request types. Setting one is what turns a Jira issue into a customer request
# that the portal, the SLA engine and the queues all recognise. Matched on
# content so the label on the ticket is not a lie; left unset when nothing fits
# (Problem has no portal request type at all, by design).
# ---------------------------------------------------------------------------
REQUEST_TYPES = {"Incident": "129", "Change": "130",
                 "Service Request": "115", "Service Request with Approvals": "128"}

RT_KEYWORDS = [
    ("mobile", "128"), ("contractor", "121"), ("new starter", "121"),
    ("vpn", "118"), ("wi-fi", "117"), ("wifi", "117"), ("guest", "117"),
    ("software", "124"), ("licence", "124"), ("install", "124"),
    ("laptop", "125"), ("monitor", "125"), ("equipment", "125"), ("hardware", "125"),
    ("phone", "126"), ("desk phone", "126"),
    ("privileged", "119"), ("admin access", "119"), ("break-glass", "119"),
    ("access", "120"), ("account", "120"), ("licence assignment", "120"),
    ("server", "130"), ("cluster", "130"), ("host", "130"),
]

# Requests whose content plainly implies a sign-off go through the approvals type.
APPROVAL_WORDS = ("access", "privileged", "exception", "approver", "quota",
                  "licence", "mobile device", "break-glass", "service principal")


def request_type_for(jtype, title):
    low = title.lower()
    if jtype == "Problem":
        return None
    if jtype == "Change":
        return "130" if any(w in low for w in ("server", "host", "cluster", "database",
                                               "switch", "circuit")) else "131"
    if jtype == "Incident":
        return "129"
    for word, rid in RT_KEYWORDS:
        if word in low:
            # A request type must belong to this issue type or the create 400s.
            if jtype == "Service Request with Approvals" and rid != "128":
                continue
            if jtype == "Service Request" and rid == "128":
                continue
            return rid
    return REQUEST_TYPES[jtype]


# ---------------------------------------------------------------------------
# Ticket model - the derivation chain is fixtures/seed.py's, unchanged.
# ---------------------------------------------------------------------------
def weighted(rng, pairs):
    vals, wts = zip(*pairs)
    return rng.choices(vals, weights=wts, k=1)[0]


def business_hours_offset(rng, dt, hours):
    end = dt + timedelta(hours=hours)
    if end.weekday() >= 5:
        end += timedelta(days=2)
    return end


def allocate(pairs, n, rng):
    """Exact largest-remainder allocation, then shuffled.

    Drawing the type and tower mix at random gives a headline number that misses
    its target by a couple of points for no reason - at n=406 a 65% incident share
    lands anywhere from 61% to 69%. The mix is a specification of the tower's
    demand, so it is allocated exactly and only the ORDER is random.
    """
    total = sum(w for _, w in pairs)
    exact = [(v, n * w / total) for v, w in pairs]
    counts = {v: int(x) for v, x in exact}
    short = n - sum(counts.values())
    for v, x in sorted(exact, key=lambda p: -(p[1] - int(p[1])))[:short]:
        counts[v] += 1
    out = [v for v, c in counts.items() for _ in range(c)]
    rng.shuffle(out)
    return out


def build_ticket(idx, now, itype, tower):
    # Per-ticket stream, not one shared stream. Ticket i must be identical on every
    # run regardless of how many tickets ran before it or what the wall clock said,
    # because .jsm_seed_done.json resumes BY INDEX - a shared stream that forks on a
    # `resolved_at > now` comparison would silently re-map every index on a re-run.
    rng = random.Random(SEED * 1_000_003 + idx)
    pool = K.BY_TYPE[itype].get(tower) or K.BY_TYPE["Incident"][tower]
    title, detail, base_impact, base_urgency = rng.choice(pool)
    esc_odds, time_mult, res_codes = K.TYPE_BEHAVIOUR[itype]
    esc_odds = min(esc_odds * ESC_UPLIFT, 0.95)
    channel = weighted(rng, D.INTAKE_CHANNELS)
    if itype in ("Change", "Problem"):
        channel = "Portal"

    # The Jira issue type is not the same thing as the ITIL type. A service request
    # whose content plainly implies a sign-off can be raised on the approvals type -
    # but only if it is going to sit at the gate, because the gate cannot be passed
    # over REST here (see WORKFLOWS above). So the draw happens with the lifecycle.
    jtype = itype
    needs_approval = itype == "Service Request" and \
        any(w in title.lower() for w in APPROVAL_WORDS)

    DOWN = {"High": "Medium", "Medium": "Low", "Low": "Low"}
    impact, urgency = base_impact, base_urgency
    if channel == "Monitoring" and rng.random() < 0.40:
        impact, urgency = "High", "High"
    else:
        if rng.random() < 0.62:
            urgency = DOWN[urgency]
        if rng.random() < 0.55:
            impact = DOWN[impact]
    if rng.random() < 0.08:
        impact = rng.choice(["High", "Medium", "Low"])

    priority = D.PRIORITY_MATRIX[(impact, urgency)]
    resp_h, res_h = D.SLA_TARGETS[priority]

    age_days = rng.triangular(0, 90, 55)
    reported = now - timedelta(days=age_days)
    if reported.weekday() >= 5 and rng.random() < 0.7:
        reported -= timedelta(days=2)
    reported = reported.replace(hour=rng.choices(range(24),
                                weights=[1,1,1,1,1,2,4,7,9,10,10,9,8,9,10,9,7,5,3,2,2,1,1,1])[0],
                                minute=rng.randrange(60))

    resp_actual = resp_h * rng.triangular(0.1, 1.5, 0.35)
    first_response = reported + timedelta(hours=resp_actual)
    response_met = "Met" if resp_actual <= resp_h else "Breached"

    escalated = rng.random() < esc_odds
    tier = "L2" if escalated else "L1"

    factor = rng.triangular(0.1, 1.3, 0.35) * (1.35 if escalated else 1.0) * time_mult
    res_actual = res_h * factor
    resolved_at = business_hours_offset(rng, reported, res_actual) if priority in ("P3", "P4") \
        else reported + timedelta(hours=res_actual)
    escalated_at = first_response + timedelta(hours=resp_actual * rng.uniform(0.5, 3)) if escalated else None

    # Lifecycle position, drawn abstractly then mapped onto this type's workflow.
    r = rng.random()
    if r < 0.74:
        stage = "CLOSED"
    elif r < 0.82:
        stage = "RESOLVED"
    elif r < 0.86:
        stage = "WORKING"
    elif r < 0.90:
        stage = "ESCALATED"
    elif r < 0.935:
        stage = "PENDING_CUST"
    elif r < 0.955:
        stage = "PENDING_VENDOR"
    elif r < 0.97:
        stage = "TRIAGE"
    elif r < 0.985:
        stage = "NEW"
    else:
        stage = "CANCELLED"

    # A real approval backlog: requests that need sign-off and have not had it yet.
    # These are the only tickets raised on the approvals type, and they stop at the
    # gate by design rather than by failure.
    if needs_approval and rng.random() < 0.42:
        jtype = "Service Request with Approvals"
        stage = "AWAITING_APPROVAL"

    if stage == "ESCALATED":
        escalated = True
        tier = "L2"
    # An escalated ticket sitting at a pre-escalation status (NEW/TRIAGE/WORKING) would
    # carry Support Tier = L2 with no Escalated-to-L2 hop in its history - the exact
    # incoherence this whole fix exists to remove. Promote it to the escalated stage so
    # its current status matches its tier.
    if escalated and stage in ("NEW", "TRIAGE", "WORKING"):
        stage = "ESCALATED"
    if stage == "AWAITING_APPROVAL":
        # Nobody has worked it yet, so it cannot have been escalated.
        escalated = False
        tier = "L1"

    status = STATUS_FOR[jtype][stage]

    # A small share of changes are declined at the gate, and a share of those that
    # get built are emergencies that bypass CAB. Both are real ITIL outcomes and
    # both leave a distinct, verifiable trail in the history.
    emergency = False
    if jtype == "Change":
        if stage in ("CLOSED", "RESOLVED") and rng.random() < 0.10:
            status = "Declined"
        elif rng.random() < 0.18:
            emergency = True

    done = status in DONE_STATUSES
    cancelled = status in ("Canceled", "Declined")

    if done and resolved_at > now:
        resolved_at = now - timedelta(hours=rng.uniform(1, 48))

    if not done:
        resolved_at = None
        resolution_sla = "Paused" if status in ("Pending", "Waiting for customer",
                                                "Waiting for approval") else "In progress"
    else:
        resolution_sla = "Met" if res_actual <= res_h else "Breached"

    # Problems are investigations, not SLA-bound work.
    if itype == "Problem":
        response_met = None
        resolution_sla = None

    l1 = rng.choice(D.L1_ANALYSTS)[0]
    l2 = rng.choice(D.L2_ANALYSTS[tower]) if escalated else None
    reopened = "Yes" if (done and rng.random() < 0.042) else "No"

    return {
        "idx": idx, "tower": tower, "itype": itype, "jtype": jtype,
        "title": title, "detail": detail,
        "impact": impact, "urgency": urgency, "priority": priority, "channel": channel,
        "tier": tier, "escalated": escalated, "status": status, "stage": stage,
        "done": done, "emergency": emergency,
        "request_type": request_type_for(jtype, title),
        "reported": reported, "first_response": first_response,
        "escalated_at": escalated_at, "resolved_at": resolved_at,
        "response_sla": response_met, "resolution_sla": resolution_sla,
        "l1": l1, "l2": l2, "reopened": reopened,
        # The escalation gate: all three of these must be present on every
        # escalated ticket, which is the whole point of the gate.
        "escalation_reason": rng.choice(D.SELECT_FIELDS["Escalation Reason"]) if escalated else None,
        "troubleshooting": rng.choice(NOTES_FOR[itype]) if escalated else None,
        "kb": rng.choice(["Yes - article applied", "Yes - none found",
                          "Yes - none found", "No"]) if escalated else None,
        "root_cause": rng.choice(D.SELECT_FIELDS["Root Cause"]) if done and not cancelled else None,
        "resolution_code": (rng.choice(res_codes) if done and not cancelled
                            else ("Withdrawn by requester" if cancelled else None)),
        "comment": rng.choice(K.COMMENTS) if rng.random() < 0.45 else None,
    }


def jira_dt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def fields_payload(t, F, settable):
    f = {
        "project": {"key": PROJECT},
        "issuetype": {"name": t["jtype"]},
        "summary": f"[{t['tower'].split(' ')[0]}] {t['title']}",
        "priority": {"name": D.PRIORITY_LABELS[t["priority"]]},
        "description": adf(
            f"{t['detail']}\n\n"
            f"Reported via {t['channel']} at {t['reported'].strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"Impact {t['impact']} / Urgency {t['urgency']} -> {t['priority']} "
            f"(derived, not agent-selected)."
        ),
    }
    if "labels" in settable:
        f["labels"] = [SEED_LABEL, t["tower"].split(" ")[0].lower().replace("&", "and")]
    # Request Type takes a BARE ID STRING. {"id": ...} and {"requestType": {...}}
    # are both rejected; the plain string is what the vp-origin field accepts.
    if t["request_type"] and "customfield_10010" in settable:
        f["customfield_10010"] = t["request_type"]
    # Populate the approver so the gate is visibly configured rather than empty,
    # even though this account cannot answer it (it is the reporter, and the status
    # property approval.exclude names reporter,assignee).
    if t["jtype"] == "Service Request with Approvals" and APPROVER_ID[0]:
        f["customfield_10003"] = [{"accountId": APPROVER_ID[0]}]

    def put(name, value):
        # {"value": None} is not None but is still an invalid select payload.
        # Test for the KEY - an ADF doc is a dict too and has no "value" key.
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
        put("Troubleshooting Performed", adf(t["troubleshooting"]))  # textarea needs ADF
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


# Transition ids are a property of (issue type, current status), not of the issue,
# so they are cached. 420 tickets x ~4 hops would otherwise be ~1,700 extra GETs.
_TRANS_CACHE = {}
_CACHE_LOCK = threading.Lock()


def transitions_for(j, key, jtype, status):
    ck = (jtype, status)
    with _CACHE_LOCK:
        hit = _TRANS_CACHE.get(ck)
    if hit is not None:
        return hit
    avail = j.get(f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
    table = {x["name"].lower(): x["id"] for x in avail}
    with _CACHE_LOCK:
        _TRANS_CACHE[ck] = table
    return table


# ---------------------------------------------------------------------------
# Resolution. The stock ITIL workflows move an issue into a done-category status
# WITHOUT setting the resolution field - there is no "set resolution" post-function
# on Resolve/Close/Change completed. Left alone, every one of the 420 tickets reads
# as unresolved, and all seven agent queues (which all filter
# `resolution = Unresolved`) show the entire project as open. So the seeder sets it
# explicitly, mapping the tower's own Resolution Code onto Jira's resolution list.
# ---------------------------------------------------------------------------
RESOLUTION_MAP = {
    "Fixed": "Done", "Workaround applied": "Done", "Fulfilled": "Done",
    "Implemented": "Done", "Rolled back": "Done", "Referred to vendor": "Done",
    "Known error documented": "Done", "No fault found": "Cannot Reproduce",
    "Duplicate": "Duplicate", "Withdrawn by requester": "Won't Do",
}


def resolution_for(status, resolution_code):
    if status == "Declined":
        return "Declined"
    if status == "Canceled":
        return "Won't Do"
    return RESOLUTION_MAP.get(resolution_code, "Done")


# Statuses at which nobody has picked the work up yet. The project's default
# assignee is the project lead, so without this every one of the 420 tickets is
# assigned and the "Unassigned work items" queue - one of the seven the demo
# shows - is permanently empty.
INTAKE_STATUSES = {"Open", "Waiting for support", "Waiting for approval",
                   PEER, "Under review"}


def set_resolution(j, key, status, resolution_code):
    j.put(f"/rest/api/3/issue/{key}",
          {"fields": {"resolution": {"name": resolution_for(status, resolution_code)}}})


def post_state(j, key, status, resolution_code, resolution_done):
    """Set what the stock workflows leave unset: resolution, and intake ownership."""
    fields = {}
    if status in DONE_STATUSES and not resolution_done:
        fields["resolution"] = {"name": resolution_for(status, resolution_code)}
    if status in INTAKE_STATUSES:
        fields["assignee"] = None
    if fields:
        j.put(f"/rest/api/3/issue/{key}", {"fields": fields})


def create_one(j, t, F, settable):
    issue = j.post("/rest/api/3/issue", {"fields": fields_payload(t, F, settable)})
    key = issue["key"]
    cur = WORKFLOWS[t["jtype"]]["initial"]
    resolution_done = False
    for name, dest in route(t["jtype"], t["status"], t["escalated"], t["emergency"]):
        # Closed is TERMINAL and carries jira.issue.editable=false in the Incident and
        # Problem workflows, so once the ticket is closed nothing can be written to it
        # and there is no transition back out. The resolution therefore has to be set
        # on the last editable status, immediately BEFORE the close hop.
        if dest == "Closed" and not resolution_done:
            set_resolution(j, key, "Closed", t["resolution_code"])
            resolution_done = True
        table = transitions_for(j, key, t["jtype"], cur)
        tid = table.get(name.lower())
        if tid is None:
            break  # can't get further; leave it where it legitimately stands
        j.post(f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": tid}})
        cur = dest
    post_state(j, key, cur, t["resolution_code"], resolution_done)
    if t["comment"]:
        j.post(f"/rest/api/3/issue/{key}/comment", {"body": adf(t["comment"])})
    return key, cur


# ---------------------------------------------------------------------------
# OPS guard. OPS is live and demoed; this script must not be able to touch it.
# ---------------------------------------------------------------------------
def reset_itsm(j, workers):
    """Delete every issue in ITSM (never OPS). Guarded by the project key assertion."""
    assert PROJECT != "OPS"
    keys, token = [], None
    while True:
        body = {"jql": f"project = {PROJECT} ORDER BY created ASC",
                "maxResults": 100, "fields": ["key"]}
        if token:
            body["nextPageToken"] = token
        r = j.post("/rest/api/3/search/jql", body)
        keys += [i["key"] for i in r.get("issues", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    log(f"  reset: deleting {len(keys)} {PROJECT} issues")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(j.delete, f"/rest/api/3/issue/{k}?deleteSubtasks=true") for k in keys]
        for f in as_completed(futs):
            try:
                f.result()
                done += 1
            except Exception:
                pass
    log(f"  reset: deleted {done}")


def guard_ops(j, label):
    ops = json.loads(OPS_STATE.read_text())
    n = j.post("/rest/api/3/search/approximate-count", {"jql": "project = OPS"})["count"]
    types = {it["name"] for it in j.get("/rest/api/3/project/OPS/statuses")}
    wf = j.get("/rest/api/3/workflowscheme/project?projectId=" + str(ops["project_id"]))
    wf_name = wf["values"][0]["workflowScheme"]["name"]
    log(f"  OPS guard [{label}]: {n} issues, {len(types)} issue types, scheme '{wf_name}'")
    assert n == 420, f"OPS issue count changed: {n}"
    assert len(types) == 4, f"OPS issue types changed: {types}"
    return n


def count(j, jql):
    return j.post("/rest/api/3/search/approximate-count", {"jql": jql})["count"]


def ensure_resolution_on_screens(j, state):
    """Put `resolution` on ITSM's screens so the seeder can set it.

    Needed because the stock ITIL workflows never set a resolution and the field is
    not on the ITSM screens, so a plain PUT comes back
    "Field 'resolution' cannot be set. It is not on the appropriate screen".

    OPS SAFETY: ITSM's screen set is computed from state/.jsm_state.json and OPS's is
    resolved live from its own issue type screen scheme; the two are asserted
    disjoint before a single write. At the time of writing ITSM owns 10195-10203
    and OPS owns 10013-10014, so nothing here can reach OPS.
    """
    itsm = {int(s) for s in state["screens"]}
    ops = json.loads(OPS_STATE.read_text())
    ops_screens = set()
    for v in j.get("/rest/api/3/issuetypescreenscheme/project?projectId="
                   + str(ops["project_id"])).get("values", []):
        sid = v["issueTypeScreenScheme"]["id"]
        for mm in j.get("/rest/api/3/issuetypescreenscheme/mapping"
                        f"?issueTypeScreenSchemeId={sid}").get("values", []):
            for s in j.get(f"/rest/api/3/screenscheme?id={mm['screenSchemeId']}").get("values", []):
                ops_screens |= {int(x) for x in s["screens"].values()}
    overlap = itsm & ops_screens
    assert not overlap, f"REFUSING: ITSM/OPS screen overlap {overlap}"
    log(f"  screens: ITSM {sorted(itsm)} vs OPS {sorted(ops_screens)} - disjoint")

    added = 0
    for sid in sorted(itsm):
        tabs = j.get(f"/rest/api/3/screens/{sid}/tabs")
        if any(f["id"] == "resolution"
               for t in tabs
               for f in j.get(f"/rest/api/3/screens/{sid}/tabs/{t['id']}/fields")):
            continue
        j.post(f"/rest/api/3/screens/{sid}/tabs/{tabs[0]['id']}/fields",
               {"fieldId": "resolution"})
        added += 1
    log(f"  screens: resolution added to {added} screen(s), {len(itsm) - added} already had it")
    return added


CLOSED_LOCKED_WORKFLOWS = [
    "ITSM: Incident Management workflow for Jira Service Management",
    "ITSM: Problem Management workflow for Jira Service Management",
]


def set_closed_editable(j, want):
    """Temporarily unlock the terminal Closed status so a repair pass can write to it.

    The Incident and Problem workflows ship Closed with jira.issue.editable=false and
    no outgoing transition, so a ticket that reached Closed without a resolution can
    never be fixed in place. Flipping the status property is the only non-destructive
    remedy; the caller flips it straight back, so stock ITIL semantics survive.

    OPS SAFETY: each workflow is asserted to be used by the ITSM workflow scheme and
    nothing else before it is touched. OPS runs "OPS L1-L2 Support Workflow", which
    is not in this list and is never read or written here.
    """
    import copy
    import urllib.parse
    for name in CLOSED_LOCKED_WORKFLOWS:
        s = j.get("/rest/api/3/workflow/search?workflowName=" + urllib.parse.quote(name)
                  + "&expand=schemes&maxResults=1")
        schemes = [x["name"] for v in s["values"] for x in v.get("schemes", [])]
        assert schemes and all("ITSM" in x for x in schemes), \
            f"REFUSING: {name} is used outside ITSM: {schemes}"
        r = j.post("/rest/api/3/workflows", {"workflowNames": [name]})
        w = copy.deepcopy(r["workflows"][0])
        for st in w["statuses"]:
            if st["statusReference"] == "6":  # Closed
                st.setdefault("properties", {})["jira.issue.editable"] = want
        payload = {"statuses": r["statuses"], "workflows": [w]}
        v = j.post("/rest/api/3/workflows/update/validation", {"payload": payload})
        errs = [e for e in v.get("errors", []) if e.get("level") == "ERROR"]
        assert not errs, f"workflow update rejected: {errs}"
        j.post("/rest/api/3/workflows/update", payload)
    log(f"  workflows: Closed jira.issue.editable = {want}")


def backfill(j, F, workers):
    """Repair pass, idempotent: reads the state off Jira rather than off the plan,
    so it fixes tickets created by any earlier run of this script."""
    code_fid = F["Resolution Code"]
    todo = []
    for jql, want in (
        (f'project = {PROJECT} AND labels = "{SEED_LABEL}" AND statusCategory = Done '
         f'AND resolution IS EMPTY', "resolution"),
        (f'project = {PROJECT} AND labels = "{SEED_LABEL}" AND assignee IS NOT EMPTY '
         f'AND status IN ({", ".join(chr(34) + s + chr(34) for s in INTAKE_STATUSES)})',
         "assignee"),
    ):
        # /search/jql is token-paginated, not offset-paginated - it rejects startAt.
        token = None
        while True:
            body = {"jql": jql, "fields": ["status", code_fid], "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = j.post("/rest/api/3/search/jql", body)
            for i in page.get("issues", []):
                todo.append((i["key"], i["fields"]["status"]["name"],
                             (i["fields"].get(code_fid) or {}).get("value"), want))
            token = page.get("nextPageToken")
            if not token or page.get("isLast"):
                break

    log(f"  backfill: {len(todo)} field repairs queued")
    if not todo:
        return 0, []

    def fix(item):
        key, status, code, want = item
        if want == "resolution":
            set_resolution(j, key, status, code)
        else:
            j.put(f"/rest/api/3/issue/{key}", {"fields": {"assignee": None}})
        return key

    # Closed is frozen in two of the five workflows, so unlock it for the duration
    # of the repair and restore it afterwards even if the repair blows up.
    unlock = any(st == "Closed" and w == "resolution" for _, st, _, w in todo)
    ok, bad = 0, []
    if unlock:
        set_closed_editable(j, "true")
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(fix, it) for it in todo]
            for n, fut in enumerate(as_completed(futs), 1):
                try:
                    fut.result()
                    ok += 1
                except Exception as e:
                    bad.append(str(e)[:160])
                if n % 100 == 0:
                    log(f"    {n}/{len(todo)}")
    finally:
        if unlock:
            set_closed_editable(j, "false")
    log(f"  backfill: {ok} repaired, {len(bad)} failed")
    for b in bad[:3]:
        log(f"    ! {b}")
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=420)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot", type=int, default=0, help="create only the first N")
    ap.add_argument("--workers", type=int, default=4)  # single-writer phase: max 4
    ap.add_argument("--backfill-only", action="store_true",
                    help="repair resolution/assignee on already-created tickets")
    ap.add_argument("--reset", action="store_true",
                    help="delete all ITSM issues before seeding (never touches OPS)")
    args = ap.parse_args()

    require_env()
    assert PROJECT != "OPS"
    j = Jira()
    APPROVER_ID[0] = j.get("/rest/api/3/myself")["accountId"]
    state = json.loads(STATE.read_text())
    F = state["fields"]
    now = datetime.now(timezone.utc)

    # Only send fields the create screen accepts, per issue type, or creates 400.
    meta = j.get(f"/rest/api/3/issue/createmeta?projectKeys={PROJECT}"
                 f"&expand=projects.issuetypes.fields")
    per_type, settable = {}, set()
    for p in meta.get("projects", []):
        for it in p.get("issuetypes", []):
            per_type[it["name"]] = set(it.get("fields", {}).keys())
            settable |= per_type[it["name"]]
    log(f"  {sum(1 for fid in F.values() if fid in settable)}/{len(F)} tower fields settable")

    if args.backfill_only:
        guard_ops(j, "before")
        ensure_resolution_on_screens(j, state)
        backfill(j, F, args.workers)
        guard_ops(j, "after")
        return

    if args.reset and not args.dry_run:
        guard_ops(j, "before reset")
        reset_itsm(j, args.workers)
        if DONE.exists():
            DONE.unlink()   # clear the resume cursor so reseed starts fresh
            log("  reset: cleared resume cursor")
        guard_ops(j, "after reset")

    # The plan is a pure function of (SEED, count) - which is why the resume file
    # records the count and refuses to continue against a different one.
    prng = random.Random(SEED ^ (args.count * 7919))
    types = allocate(TYPE_MIX, args.count, prng)
    towers = allocate(D.TOWERS, args.count, prng)
    tickets = [build_ticket(i, now, types[i], towers[i]) for i in range(args.count)]

    log(f"\n== modelled distribution across {len(tickets)} tickets ==")
    for label, key in (("itil type", "itype"), ("jira type", "jtype"), ("tower", "tower"),
                       ("priority", "priority"), ("channel", "channel"), ("status", "status")):
        counts = {}
        for t in tickets:
            counts[t[key]] = counts.get(t[key], 0) + 1
        log(f"  {label:<10} " + "  ".join(f"{k}:{v}" for k, v in
                                          sorted(counts.items(), key=lambda kv: -kv[1])))
    esc = sum(1 for t in tickets if t["escalated"])
    log(f"  escalated {esc} ({esc/len(tickets):.0%})  |  L1-only {len(tickets)-esc}")
    gate_ok = sum(1 for t in tickets if t["escalated"] and t["escalation_reason"]
                  and t["troubleshooting"] and t["kb"])
    log(f"  gate evidence complete on {gate_ok}/{esc} escalated")
    assert gate_ok == esc, "escalated ticket missing gate evidence"

    if args.dry_run:
        log("\ndry run - nothing written")
        return

    guard_ops(j, "before")

    # Resumable: every index that has actually been created is recorded, so a
    # pilot run and the main run never create the same ticket twice and a
    # half-finished run can be continued rather than restarted.
    done_idx = set()
    if DONE.exists():
        rec = json.loads(DONE.read_text())
        assert rec["count"] == args.count, (
            f"resume file was written for --count {rec['count']}, not {args.count}; "
            "index i would refer to a different ticket")
        done_idx = set(rec["idx"])
    remaining = [t for t in tickets if t["idx"] not in done_idx]
    if done_idx:
        log(f"  resuming: {len(done_idx)} already created, {len(remaining)} remaining")

    if args.pilot:
        # A diverse pilot: one ticket per jira type and per interesting landing
        # status, so the approval gate and the change chain are proven before
        # 400-odd tickets are committed to them.
        picked, seen = [], set()
        for t in remaining:
            k = (t["jtype"], t["status"], t["emergency"])
            if k in seen:
                continue
            seen.add(k)
            picked.append(t)
            if len(picked) >= args.pilot:
                break
        todo = picked
    else:
        todo = remaining
    log(f"\n== creating {len(todo)} in {PROJECT} ({args.workers} workers) ==")
    ok, failed, landed = [], [], {}
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(create_one, j, t, F, settable): t for t in todo}
            for n, fut in enumerate(as_completed(futs), 1):
                t = futs[fut]
                try:
                    key, cur = fut.result()
                    ok.append(key)
                    done_idx.add(t["idx"])
                    landed[key] = (t["status"], cur)
                except Exception as e:
                    failed.append(f"{t['jtype']}/{t['status']}: {str(e)[:200]}")
                if n % 40 == 0:
                    log(f"  {n}/{len(todo)}  ok={len(ok)} failed={len(failed)}")
    finally:
        DONE.write_text(json.dumps({"count": args.count, "idx": sorted(done_idx)}))

    log(f"\n  created {len(ok)}, failed {len(failed)}")
    for f in failed[:5]:
        log(f"    ! {f}")
    drift = {k: v for k, v in landed.items() if v[0] != v[1]}
    log(f"  landed off-target: {len(drift)}")
    for k, v in list(drift.items())[:5]:
        log(f"    ~ {k}: wanted {v[0]}, reached {v[1]}")

    ensure_resolution_on_screens(j, state)
    backfill(j, F, args.workers)
    guard_ops(j, "after")

    if not args.pilot:
        state["seeded"] = len(done_idx)
        state["seed_label"] = SEED_LABEL
        STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
