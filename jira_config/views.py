#!/usr/bin/env python3
"""Reconcile the OPS saved filters and the OPS dashboard.

These filters stand in for JSM agent queues. Every one keys off `Reported At`
rather than `created`, because the seeded history lives there.

DECLARATIVE AND IDEMPOTENT. Re-running against an unchanged plan issues ZERO
writes. The predecessor of this file blind-appended three unconfigured gadgets on
every run - it never listed what was already there and never sent a filter id -
which is how dashboard 10001 accumulated twelve blank ones over four runs. All
the reconciliation logic now lives in jira_config/reconcile.py; this file is the
declared plan and nothing else.

The gadget plan is the twelve-view plan that jira_config/repair.py bound by hand,
with the SAME titles, the SAME config and the SAME rows the live dashboard ended
up with. That is deliberate on all three counts: it makes this script a verified
no-op against the live dashboard, and it retires the second, divergent copy of
the dashboard definition that used to sit in repair.py (which now imports the
plan from here).

Usage:  python3 -m jira_config.views [--dry-run] [--extras keep|delete] [--relayout]
"""

import argparse
import json
import sys

from shared.jira_client import Jira, log, require_env
from shared import domain as D
from jira_config import jira_schema as S
from jira_config import BUILD_STATE as STATE
from jira_config.reconcile import (
    Writer, ensure_dashboard, gadget, reconcile_filters, reconcile_gadgets)

P = S.PROJECT_KEY
DASH_NAME = "OPS - L1/L2 Tower"
DASH_DESC = "L1/L2 tower operating view. All dates key off Reported At."

# Column set every OPS gadget uses. Matches what is live on the dashboard.
COLUMNS = "issuetype|issuekey|summary|priority|status|updated"
BASE_CFG = {"num": "10", "columnNames": COLUMNS, "refresh": "false"}

# Rendered once so the paused-status list has a single source (domain), and so
# the two JQL sites below cannot drift apart.
_PAUSED = ", ".join('"%s"' % s for s in D.SLA_PAUSED_STATUSES)

# ---------------------------------------------------------------------------
# The dashboard plan: (filter name, gadget title, row).
#
# ONE definition, imported by repair.py rather than copied into it - two copies
# of this list is how the dashboard drifted in the first place.
#
# Rows are the order Jira ACTUALLY laid these out, not the order they were asked
# for. Jira reflows position.row when a POST collides, so the twelve live gadgets
# do not sit in the order they were created (L1 queue is row 9). Encoding reality
# as intent keeps even a --relayout run a no-op. Reordering them into something
# more readable is a separate, deliberate change against a dashboard nobody is
# about to demo.
#
# The list order itself is creation/id order, which is what repair.py's
# positional zip needs. Do not sort it.
# ---------------------------------------------------------------------------
GADGET_PLAN = [
    ("OPS - L1 queue (open)", "L1 queue", 9),
    ("OPS - L2 queue (open)", "L2 queue", 10),
    ("OPS - Major incidents (Impact High + Urgency High)", "Major incidents", 11),
    ("OPS - SLA breached (resolution)", "SLA breached", 6),
    ("OPS - SLA paused (waiting on customer or vendor)",
     "SLA paused - clock stopped", 7),
    ("OPS - Aged backlog over 14 days", "Aged over 14 days", 8),
    ("OPS - Reopened tickets", "Reopened - paired with FTR", 3),
    ("OPS - Escalated in last 30 days", "Escalated last 30 days", 4),
    ("OPS - Escalated with no KB article found", "KB gap - the biggest lever", 5),
    ("OPS - Intake via chat (shadow support pulled in)",
     "Shadow support via chat", 0),
    ("OPS - P1 at risk (past 75% of target)", "P1 at risk", 1),
    ("OPS - P2 at risk (past 75% of target)", "P2 at risk", 2),
]


def build_filters():
    """[(name, jql, description)].

    A function rather than a module-level list so that importing this module -
    which jira_config/apply.py and repair.py both do - executes nothing but
    definitions.
    """
    f = [
        ("OPS - L1 queue (open)",
         'project = %s AND "Support Tier" = L1 AND statusCategory != Done '
         'ORDER BY priority DESC' % P,
         "Everything sitting at L1 and not finished."),
        ("OPS - L2 queue (open)",
         'project = %s AND "Support Tier" = L2 AND statusCategory != Done '
         'ORDER BY priority DESC' % P,
         "Escalated work in flight, across all towers."),
        ("OPS - Major incidents (Impact High + Urgency High)",
         'project = %s AND Impact = High AND Urgency = High '
         'ORDER BY "Reported At" DESC' % P,
         "The P1 war-room view. Priority is derived, so this is the real definition."),
        ("OPS - SLA breached (resolution)",
         'project = %s AND "Resolution SLA" = Breached '
         'ORDER BY "Reported At" DESC' % P,
         "Resolution target missed. Attainment reporting starts here."),
        ("OPS - SLA paused (waiting on customer or vendor)",
         'project = %s AND status IN (%s) ORDER BY "Reported At" ASC' % (P, _PAUSED),
         "Ball is not in our court. Excluded from attainment - this is what makes "
         "the report trustworthy."),
        ("OPS - Aged backlog over 14 days",
         'project = %s AND statusCategory != Done AND "Reported At" <= -14d '
         'ORDER BY "Reported At" ASC' % P,
         "What is quietly rotting."),
        ("OPS - Reopened tickets",
         'project = %s AND Reopened = Yes ORDER BY "Reported At" DESC' % P,
         "Paired with first-time resolution - closing early to flatter FTR shows "
         "up here."),
        ("OPS - Escalated in last 30 days",
         'project = %s AND "Support Tier" = L2 AND "Reported At" >= -30d '
         'ORDER BY "Reported At" DESC' % P,
         "Feeds escalation rate per analyst and per tower."),
        ("OPS - Escalated with no KB article found",
         'project = %s AND "KB Article Checked" = "Yes - none found" '
         'ORDER BY "Reported At" DESC' % P,
         "Every row is a candidate knowledge-base article. This is the loop that "
         "lifts L1's ceiling."),
        ("OPS - Intake via chat (shadow support pulled in)",
         'project = %s AND "Intake Channel" = Chat ORDER BY "Reported At" DESC' % P,
         "Demand that would otherwise be invisible. See PROBLEM.md 3.6."),
    ]

    # One L2 queue per tower. This is the JSM agent-queue equivalent: escalated
    # work lands in the tower's pool rather than on a named person, which is what
    # the escalation post-function is for.
    for tower, _ in D.TOWERS:
        f.append((
            "OPS - L2 queue: %s" % tower,
            'project = %s AND "Support Tier" = L2 AND Tower = "%s" '
            'AND statusCategory != Done '
            'ORDER BY priority DESC, "Reported At" ASC' % (P, tower),
            "Escalated %s work awaiting or in progress at L2." % tower))

    # SLA at-risk: past 75% of the resolution target and still not done.
    # Approximated against Reported At because the native SLA engine needs JSM.
    #
    # UNIT CONVERSION, and it is the whole subtlety of this block. domain.SLA_TARGETS
    # states P3/P4 in BUSINESS hours (domain.SLA_CLOCK says so) while the JQL below
    # compares against `"Reported At" <= -Nh`, which Jira evaluates in ELAPSED
    # calendar hours. Feeding a business-hour number straight into that clause
    # silently shrinks the window by the ratio of the two clocks: a 24-business-hour
    # P3 target is 72 calendar hours, so 75% of it is 54h, not 18h. Emitting -18h
    # would flag work as at-risk three times too early.
    #
    # P1/P2 run on the 24x7 clock, so their factor is 1 and they are unaffected -
    # which is exactly why only the P3/P4 filters ever looked wrong. This is the
    # error recorded and retracted as CLAIMS #55: the live -54h/-90h filters were
    # right all along and the generator was wrong.
    hours_per_business_day = D.BUSINESS_DAY[1] - D.BUSINESS_DAY[0]
    for p, (_resp, res) in D.SLA_TARGETS.items():
        factor = (24.0 / hours_per_business_day
                  if D.SLA_CLOCK[p] == "business" else 1.0)
        elapsed_target = int(res * factor)
        threshold = int(res * 0.75 * factor)
        f.append((
            "OPS - %s at risk (past 75%% of target)" % p,
            'project = %s AND priority = "%s" AND statusCategory != Done '
            'AND status NOT IN (%s) AND "Reported At" <= -%dh '
            'ORDER BY "Reported At" ASC'
            % (P, D.PRIORITY_LABELS[p], _PAUSED, threshold),
            "%s tickets past %dh of a %sh resolution target, clock still running."
            % (p, threshold, elapsed_target)))
    return f


def build_gadgets():
    return [gadget(title, "filter-results", fname, BASE_CFG, row, 0)
            for fname, title, row in GADGET_PLAN]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jira_config.views")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change and write nothing")
    ap.add_argument("--extras", choices=["keep", "delete"], default="keep",
                    help="what to do with dashboard gadgets the plan does not claim")
    ap.add_argument("--relayout", action="store_true",
                    help="also rewrite gadget positions (off by default: position "
                         "writes are not verified on this instance)")
    args = ap.parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)
    account_id = j.get("/rest/api/3/myself")["accountId"]

    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    log("== filters ==")
    filter_ids, filter_failures = reconcile_filters(w, build_filters(), account_id)
    state["filters"] = filter_ids

    if filter_failures:
        # Do NOT proceed. Binding gadgets against a partial filter map is exactly
        # how a blank gadget gets created, and blank gadgets were the whole bug.
        for f in filter_failures:
            log("  FILTER FAILURE: " + f)
        if not args.dry_run:
            STATE.write_text(json.dumps(state, indent=2))
        sys.exit("ABORTING - filters incomplete, refusing to touch the dashboard.")

    log("\n== dashboard ==")
    did, _ = ensure_dashboard(w, DASH_NAME, DASH_DESC)
    state["dashboard_id"] = did

    log("\n== gadgets ==")
    result = reconcile_gadgets(w, did, build_gadgets(), filter_ids,
                               extras=args.extras, relayout=args.relayout)
    state["gadgets"] = result.get("gadget_ids", {})

    if not args.dry_run:
        STATE.write_text(json.dumps(state, indent=2))

    log("\n== summary ==")
    log("  %d filters; gadgets: %d created / %d updated / %d unchanged"
        % (len(filter_ids), len(result["created"]), len(result["updated"]),
           len(result["unchanged"])))
    log("  %d write(s) issued%s"
        % (w.writes, " [DRY RUN - none applied]" if args.dry_run else ""))
    for f in result["failed"]:
        log("  GADGET FAILURE: " + f)

    log("\n  Project:   %s/browse/%s" % (j.site, P))
    log("  Dashboard: %s/jira/dashboards/%s" % (j.site, did))

    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
