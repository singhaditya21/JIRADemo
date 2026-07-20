#!/usr/bin/env python3
"""The control tower's metric core. Pure functions, no Jira, no network.

WHAT THIS IS
------------
Every number the control tower page shows is computed here, from a plain list of
`app.store.Issue` records. Nothing in this module opens a socket, reads a file,
or imports shared.jira_client. That is deliberate and it is the whole reason the
feature is testable: `compute_all(rows, now, 90)` against a frozen snapshot is a
complete regression test of the page, runnable offline in milliseconds.

Records are duck-typed. Anything with the attributes app.store.Issue carries will
work, which means a unit test can hand-build three records and assert a rate
without a fixture file.

FIDELITY IS THE POINT
---------------------
app/metrics.py is the reference implementation. It asks Jira one
`approximate-count` per metric, which is slow and untrendable but obviously
correct. Every headline figure here reproduces its JQL answer EXACTLY - verified
field by field at both 90 and 30 days against live OPS and ITSM.

Where metrics.py's JQL has a quirk, this module reproduces the quirk rather than
improving on it, and says so in a comment. Three of those are load-bearing:

  * FTR excludes Problems; escalation rate does NOT.       (see escalation)
  * The reopen numerator ranges over the window while its
    denominator is the closed set.                        (see reopen)
  * `Cancelled` has statusCategory Done, so a withdrawn
    ticket counts as a closed one.                        (see closed_set)

If any of these is ever "fixed", it must be fixed in app/metrics.py FIRST and
both must move together. A tower that silently disagrees with the CLI baseline is
worse than one that reproduces a known wart, because the disagreement is only
discovered in the room.

TIME
----
`Reported At` is the only time axis. Jira's `created` and `resolutiondate` are
uniformly today on this dataset (the seeder cannot backdate them over REST) and
are carried on the record purely so a panel can display them as the
counterexample. Nothing here reads them.

`now` is an ARGUMENT everywhere, never `datetime.now()` inside a function. Three
panels key off it - the window cut, the 14-day aged cut, the ageing histogram -
and if they each read the clock, a generation that straddles midnight produces a
page that disagrees with itself.

Python 3.9. Standard library only.
"""

import math
from datetime import datetime, timedelta

from shared import domain as D

# ---------------------------------------------------------------------------
# Placeholder thresholds
# ---------------------------------------------------------------------------
#
# PLACEHOLDERS (CLAIMS.md #14/#15), same status as domain.SCORECARD_TARGETS:
# invented, defensible, and to be replaced from a real baseline.
#
# They live here rather than in shared/domain.py on purpose. SCORECARD_TARGETS
# are business targets the organisation would agree to. These three are the
# TOWER'S OWN presentation thresholds - how few tickets is too few to state a
# rate, how few tickets is too few to judge a person. Promoting them to the
# shared model would imply an agreement that does not exist.

# Below this many tickets in a week, a weekly rate is not stated at all.
# See rate_point() for why this is a hard requirement rather than a nicety.
MIN_WEEK_DENOM = 10

# Below this many tickets, an analyst's escalation rate is shown but excluded
# from the mean and sigma band. See analyst_escalation() for the measured
# justification - one new starter's first three tickets otherwise doubles the sd.
MIN_ANALYST_N = 20

# Targets for the two scoreboard metrics domain.SCORECARD_TARGETS does not carry.
TOWER_TARGETS = {"escalation_pct": (35, "le"), "aged_14d": (0, "le")}

# Aged-backlog threshold, in days. Matches metrics.py's `"Reported At" <= -14d`.
AGED_DAYS = 14

# Half-open [lo, hi) day buckets for the ageing histogram. hi=None is the tail.
AGE_BUCKETS = [(0, 3, "0-3d"), (3, 7, "3-7d"), (7, 14, "7-14d"),
               (14, 30, "14-30d"), (30, 60, "30-60d"), (60, None, "60d+")]

# The exact option string that means "the analyst looked and there was no
# article". "No" means NOT CHECKED, which is a process failure rather than a
# content gap; conflating the two overstates the KB backlog.
KB_NONE_FOUND = "Yes - none found"


def target_for(key):
    """(target, direction) for a scoreboard key, or None.

    Business targets win; the tower's own placeholders fill the gaps.
    """
    if key in D.SCORECARD_TARGETS:
        return D.SCORECARD_TARGETS[key]
    return TOWER_TARGETS.get(key)


def verdict(key, value):
    """"PASS" / "GAP" / None, using the same comparison metrics.py.verdict does."""
    t = target_for(key)
    if t is None:
        return None
    target, direction = t
    ok = value >= target if direction == "ge" else value <= target
    return "PASS" if ok else "GAP"


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def pct(n, d):
    """Identical to app.metrics.pct - 0.0 on an empty denominator, so headline
    numbers match metrics.py exactly.

    Deliberately DIFFERENT from rate_point(), which returns None. A headline
    figure always renders; a trend point may abstain.
    """
    return (100.0 * n / d) if d else 0.0


def rate_point(num, den, floor=MIN_WEEK_DENOM):
    """A weekly rate point, or None.

    None means "not enough denominator to state a rate", which is a different
    fact from 0% and MUST render differently: break the line, do not plot a zero.

    The first and last buckets of any window are partial by construction. On live
    OPS at 90 days the edge weeks hold 3 and 4 tickets, and their unqualified
    rates are 0.0% and 100.0% - the two most eye-catching points on the chart and
    both pure noise. This is the single most likely way for this page to tell a
    lie on stage, so the floor is a hard requirement.

    den == 0 is subsumed: 0 < MIN_WEEK_DENOM, so it returns None. There is no
    division by zero anywhere in this module.
    """
    if den < floor:
        return None
    return 100.0 * num / den


def monday(when):
    """The Monday of the week containing `when` (a datetime), as a date.

    Cut on the LOCAL date the timestamp carries, not on its UTC equivalent. A
    ticket reported Monday 00:02 +05:30 belongs to that Monday; converting to UTC
    first would file it under the previous Sunday. Measured on live OPS: exactly
    2 of 420 rows bucket differently, OPS-2358 and OPS-2534, and both are
    genuinely Monday-morning tickets.
    """
    d = when.date()
    return d - timedelta(days=d.weekday())


def in_window(row, now, days):
    """The in-memory form of JQL `"Reported At" >= -Nd`.

    Both sides are timezone-aware, so Python normalises the +05:30 offset itself.
    Do NOT convert to UTC and compare naive dates first - that reintroduces a
    rounding difference exactly at the boundary.

    Accepted boundary risk: a ticket whose Reported At sits within seconds of the
    cutoff could fall either side of a JQL cross-check run moments later. Seeded
    data is minute-granular across three months, so nothing is near the boundary.
    """
    return row.reported_at is not None and row.reported_at >= now - timedelta(days=days)


def windowed(rows, now, days):
    return [r for r in rows if in_window(r, now, days)]


def closed_set(rows):
    """The FTR and reopen denominator: finished, non-Problem.

    `counts_as_closed` is computed once, in app/store.py, precisely so that no
    panel can pick a different denominator. Getting this wrong turns 61.8% into
    60.0% and nobody notices until someone reconciles the tower against the CLI
    in the room.

    NOTE this includes `Cancelled`, whose statusCategory is Done. A ticket
    withdrawn by the requester and resolved by nobody therefore scores as a
    first-time resolution if it never left L1 - 6 of them on OPS today, 3 at L1.
    Known wart, inherited from metrics.py's `statusCategory = Done`, and
    reproducing 61.8% requires it.
    """
    return [r for r in rows if r.counts_as_closed]


def data_tz(rows):
    """The offset the data is stamped in, from the most recent Reported At.

    Week boundaries in the backlog reconstruction are cut in this frame so the
    newest point cannot land a day out from what a Jira user sees.
    """
    stamped = [r.reported_at for r in rows if r.reported_at is not None]
    if not stamped:
        return None
    return max(stamped).tzinfo


def week_axis(now, days, rows=None):
    """Contiguous Mondays covering the window, oldest first.

    Built from the WINDOW, not from the rows, so a zero-volume week is a visible
    gap rather than a silently missing point. On OPS at 90 days this is 14 weeks,
    2026-04-20 .. 2026-07-20, the last of which is the in-progress current week.

    `rows` (the windowed rows) only ever EXTENDS the axis. It exists because the
    axis ends are cut from `now`, which is UTC, while a row's week is cut from
    its own +05:30 stamp: a row reported 00:30 local on the Monday `now` has not
    yet reached in UTC would otherwise fall off the end of the axis and vanish
    from every weekly bucket while still counting in the window totals. The union
    is what makes "weekly buckets sum to the window" true by construction rather
    than by luck.
    """
    first, last = monday(now - timedelta(days=days)), monday(now)
    if rows:
        weeks = [r.week for r in rows if r.week is not None]
        if weeks:
            first, last = min(first, min(weeks)), max(last, max(weeks))
    out, d = [], first
    while d <= last:
        out.append(d)
        d = d + timedelta(days=7)
    return out


def bucket_weeks(rows, now, days):
    """(axis, {monday: [rows]}) over the window. Every axis week is a key.

    One helper rather than four copies of the same loop, so the sparklines cannot
    disagree with each other about which week a ticket is in.
    """
    W = windowed(rows, now, days)
    axis = week_axis(now, days, W)
    buckets = dict((w, []) for w in axis)
    for r in W:
        if r.week in buckets:
            buckets[r.week].append(r)
    return axis, buckets


# ---------------------------------------------------------------------------
# Panel 1 - the six scoreboard metrics
# ---------------------------------------------------------------------------

def ftr(rows):
    """First-time resolution at L1. Live OPS 90d: 215/348 = 61.78%.

    Problems are excluded from BOTH numerator and denominator. A Problem is an
    investigation - it is supposed to sit with L2 for weeks, and counting it as a
    failed first-time resolution penalises the tower for doing root-cause work.
    metrics.py: `statusCategory = Done AND issuetype != Problem`.
    """
    c = closed_set(rows)
    n = sum(1 for r in c if r.tier == "L1")
    return n, len(c), pct(n, len(c))


def escalation(rows):
    """Escalation rate. Live OPS 90d: 171/420 = 40.71%.

    Denominator is EVERY issue in the window, Problems INCLUDED.

    Do not "fix" the asymmetry with ftr(). FTR excludes Problems; this does not.
    That is what metrics.py does and it is why 40.7% reproduces. Excluding the 9
    escalated Problems would give 162/409 = 39.6%, and the page would contradict
    the baseline report on the same screen.
    """
    n = sum(1 for r in rows if r.tier == "L2")
    return n, len(rows), pct(n, len(rows))


def reopen(rows):
    """Reopen rate. Live OPS 90d: 15/348 = 4.31%.

    FIDELITY RULE - READ BEFORE TIDYING. The numerator ranges over the whole
    window; the denominator is the closed set. That is a mismatched pair, and it
    is metrics.py's existing shape, so it is reproduced exactly.

    Verified harmless today: all 15 reopened rows are already inside the closed
    set (10 done Incidents, 5 done Service Requests), and 0 of the 11 Problems
    carry Reopened=Yes. It would diverge only for a ticket reopened and currently
    open, or for a reopened Problem. Do NOT rewrite this as
    `sum(... for r in c ...)`; it would silently move the number.
    """
    c = closed_set(rows)
    n = sum(1 for r in rows if r.is_reopened)
    return n, len(c), pct(n, len(c))


def _sla(rows, attr):
    """Met / Breached / attainment for one of the two SLA fields.

    Only Met and Breached enter the denominator. Three states are excluded and
    each exclusion is deliberate:

      Paused        21 live. The clock is stopped in Pending Customer / Pending
                    Vendor. Counting a paused ticket as breached bills the tower
                    for the customer's silence.
      In progress   0 live today, non-zero on real traffic. Not yet adjudicated -
                    counting it met inflates, counting it breached defames.
      None          11 live, and they are EXACTLY the 11 Problems.
                    sla_engine.evaluate returns problem-skipped before writing,
                    so Problems have never had these fields written.

    That last one is why there is no `issue_type != "Problem"` guard here: the
    data already enforces it, because the SLA engine did. Adding the guard would
    change nothing today and would MASK a real regression - a Problem that
    somehow acquired an SLA verdict. The invariant is asserted in invariants()
    instead.
    """
    met = sum(1 for r in rows if getattr(r, attr) == "Met")
    br = sum(1 for r in rows if getattr(r, attr) == "Breached")
    return met, br, pct(met, met + br)


def resolution_sla(rows):
    """Live OPS 90d: 306 met / 82 breached = 78.87%."""
    return _sla(rows, "resolution_sla")


def response_sla(rows):
    """Live OPS 90d: 96.58%. No Paused state - response has no pause concept."""
    return _sla(rows, "response_sla")


def open_count(rows):
    """Open work across the WHOLE project. Pass unwindowed rows."""
    return sum(1 for r in rows if r.is_open)


def aged_backlog(rows, now, threshold_days=AGED_DAYS):
    """Open and reported at least `threshold_days` ago. Live OPS: 60.

    NOT WINDOWED. This is a point-in-time snapshot of the whole project.
    metrics.py builds it from `statusCategory != Done AND "Reported At" <= -14d`
    with no window clause, which is why it reads 60 at both --days 90 and 30.

    Passing the windowed rows here is the single easiest bug to introduce in this
    file: at 90 days it happens to give the same answer, at 30 days it does not.
    """
    cut = now - timedelta(days=threshold_days)
    return sum(1 for r in rows
               if r.is_open and r.reported_at is not None and r.reported_at <= cut)


def shadow_chat(rows):
    """Tickets that arrived over chat - shadow support pulled into the record.
    Live OPS 90d: 43."""
    return sum(1 for r in rows if r.intake == "Chat")


# ---------------------------------------------------------------------------
# Panel 1g - the weekly trend behind the scoreboard
# ---------------------------------------------------------------------------

def weekly_series(rows, now, days):
    """One pass, all five reported-week metrics.

    TREND SEMANTICS - state this on the page. A week's point is a COHORT rate: of
    the tickets REPORTED that week, how many ended up meeting SLA / escalating /
    reopening. It is not "SLA attainment observed during that week". The cohort
    reading is the correct one for a reported-at axis, and it is why the most
    recent weeks are thin - their tickets are still open. Label the axis
    "week reported" and dim the final bucket.

    Aged backlog is absent from this series on purpose: it is a stock, not a
    flow, and bucketing it by reported-week is meaningless. See backlog_series.
    """
    axis, buckets = bucket_weeks(rows, now, days)
    out = []
    for w in axis:
        b = buckets[w]
        c = closed_set(b)
        met, brc, _ = resolution_sla(b)
        rmet, rbr, _ = response_sla(b)
        out.append({
            "week": w.isoformat(),
            "n": len(b),
            "closed": len(c),
            "ftr_pct": rate_point(sum(1 for r in c if r.tier == "L1"), len(c)),
            "escalation_pct": rate_point(sum(1 for r in b if r.tier == "L2"), len(b)),
            "reopen_pct": rate_point(sum(1 for r in b if r.is_reopened), len(c)),
            "sla_pct": rate_point(met, met + brc),
            "response_pct": rate_point(rmet, rmet + rbr),
        })
    return out


# ---------------------------------------------------------------------------
# Panel 1h - aged backlog, reconstructed rather than bucketed
# ---------------------------------------------------------------------------

def backlog_as_of(rows, t, threshold_days=AGED_DAYS):
    """(open, aged) as they stood at instant `t`, from the timeline alone.

    A row was open at t iff it had been reported by then and was not yet
    resolved. This is the panel Jira structurally cannot draw: it has no stored
    history of a custom datetime field, so it cannot rewind a backlog.

    Soundness rests on one invariant - `Resolved At is None` iff
    `statusCategory != Done` - which holds with 0 mismatches across all 420 live
    rows. invariants() asserts it; if it ever breaks, this panel is lying and
    must be suppressed rather than shown.
    """
    cut = t - timedelta(days=threshold_days)
    op = aged = 0
    for r in rows:
        if r.reported_at is None or r.reported_at > t:
            continue
        if r.resolved_at is not None and r.resolved_at <= t:
            continue
        op += 1
        if r.reported_at <= cut:
            aged += 1
    return op, aged


def backlog_series(rows, now, days):
    """Open and aged counts at each week boundary, then at `now`.

    Live OPS: open is flat at ~65 across the window while aged climbs 0 -> 60.
    The backlog is not growing, it is STALING - the same queue, ageing in place.

    Week boundaries are instants, and they are cut in the DATA's timezone rather
    than UTC for the same reason monday() is: +05:30 shifts the boundary by five
    and a half hours, which moves tickets between adjacent points.
    """
    W = windowed(rows, now, days)
    axis = week_axis(now, days, W)
    tz = data_tz(rows) or now.tzinfo
    pts = []
    for w in axis[1:]:                 # skip the ragged first partial week
        t = datetime(w.year, w.month, w.day, tzinfo=tz) + timedelta(days=7)
        if t > now:
            continue                   # future boundary; the "now" point covers it
        op, aged = backlog_as_of(rows, t)
        pts.append({"week": w.isoformat(), "open": op, "aged": aged})
    pts.append({"week": "now", "open": open_count(rows),
                "aged": aged_backlog(rows, now)})
    return pts


# ---------------------------------------------------------------------------
# Panel 2 - FTR against reopen, explicitly paired
# ---------------------------------------------------------------------------

def ftr_vs_reopen(rows, now, days):
    """Both series on one chart, shared week axis, SHARED DENOMINATOR.

    The shared denominator is the honesty mechanism and the reason this panel
    exists. Closing a ticket early moves a row from open into the closed set,
    which lifts FTR *and* enlarges the reopen denominator; if the close was
    premature, the reopen numerator follows a week later. Neither metric can be
    moved on its own without the other one answering.

    Rendering requirement: FTR on a 0-100 left axis, reopen on a 0-20 right axis
    (reopen lives at 0-9% and would be a flat line against 0-100), and BOTH axes
    labelled with their range. A dual-axis chart with an unlabelled right scale
    is the classic way to make two unrelated series look correlated.
    """
    axis, buckets = bucket_weeks(rows, now, days)
    out = []
    for w in axis:
        b = buckets[w]
        c = closed_set(b)
        out.append({
            "week": w.isoformat(),
            "closed": len(c),                       # the shared denominator
            "ftr_pct": rate_point(sum(1 for r in c if r.tier == "L1"), len(c)),
            "reopen_pct": rate_point(sum(1 for r in b if r.is_reopened), len(c)),
        })
    return out


def pairing_note(series):
    """Pearson r across the weeks where BOTH rates are stateable, or None.

    Ship it as "r = -0.42 over 11 weeks", with the n visible, and NEVER as a
    claim of causation. With about a dozen points this is weak-evidence
    statistics. The panel's argument is structural - the two metrics are defined
    so that neither can be gamed alone - not empirical.
    """
    pts = [(p["ftr_pct"], p["reopen_pct"]) for p in series
           if p["ftr_pct"] is not None and p["reopen_pct"] is not None]
    if len(pts) < 4:
        return None
    n = len(pts)
    mx = sum(a for a, _ in pts) / n
    my = sum(b for _, b in pts) / n
    sxy = sum((a - mx) * (b - my) for a, b in pts)
    sxx = sum((a - mx) ** 2 for a, _ in pts)
    syy = sum((b - my) ** 2 for _, b in pts)
    if sxx <= 0 or syy <= 0:
        return None
    return {"r": sxy / math.sqrt(sxx * syy), "weeks": n}


# ---------------------------------------------------------------------------
# Panel 3 - escalation rate per L1 analyst
# ---------------------------------------------------------------------------

def binomial_z(n, d, pooled_pct):
    """z of this analyst's rate against the pooled tower rate, at their own n.

    Complements the population sigma. Sigma asks "is this person unlike their
    peers"; z asks "is this person's own sample big enough to say so". The
    population sd treats a 46-ticket analyst and a 20-ticket analyst as equally
    precise, and they are not.
    """
    if d <= 0:
        return None
    p = pooled_pct / 100.0
    se = math.sqrt(p * (1 - p) / d)
    if se <= 0:
        return None
    return ((n / float(d)) - p) / se


def analyst_escalation(rows, now, days, floor=MIN_ANALYST_N):
    """Per-L1-analyst escalation rate, with the tower mean and a 2-sigma band.

    PILOT.md exit criterion 6 is "no analyst diverges > 2 sigma". This is how it
    gets judged, so the verdict must be COMPUTED and rendered as a line - "12
    analysts, 0 outside 2 sigma - criterion 6 met" - never a hardcoded string.

    Keyed on the L1 Analyst FIELD, never the Jira assignee. The seeded assignee
    is the API account on all 420 rows, and on a real instance the assignee moves
    to L2 on escalation, which would credit the escalation to the person who
    RECEIVED it. Escalation rate is a property of the L1 who passed it on.
    Verified clean: 0 rows carry an L2 Analyst while tier is L1, and 0 tier-L2
    rows lack one.

    Denominator per analyst is every windowed row bearing their name - Problems
    included, closed or not - the same population as the tower headline, so the
    pooled rate reconciles to 40.71% by construction.

    THE SMALL-SAMPLE FLOOR, and why it is not optional. On today's data excluding
    n < 20 is nearly free: mean 40.01 -> 40.44, sd 8.85 -> 9.15, same verdict.
    Its value is the failure it prevents. Simulated, adding one new starter with
    3 tickets and 3 escalations:

        without the floor:  mean 44.63  sd 18.67  band [ 7.29, 81.97]
        with the floor:     mean 40.44  sd  9.15  band [22.15, 58.73]

    One person's first three tickets more than doubles the sd and widens the band
    to [7%, 82%], inside which NO real outlier can ever be detected. The
    criterion silently stops working - passing not because the tower is uniform
    but because the yardstick went slack.
    """
    W = windowed(rows, now, days)
    den, num = {}, {}
    for r in W:
        a = r.l1_analyst
        if not a:
            continue
        den[a] = den.get(a, 0) + 1
        if r.tier == "L2":
            num[a] = num.get(a, 0) + 1

    people = []
    for a in sorted(den):
        d = den[a]
        n = num.get(a, 0)
        people.append({"analyst": a, "escalated": n, "handled": d,
                       "rate": pct(n, d), "rateable": d >= floor})

    # Reference line: the POOLED rate - same numerator over the same denominator
    # as the tower headline, so the two agree by construction.
    pooled = pct(sum(num.values()), sum(den.values()))

    # The band is the mean and sd ACROSS ANALYSTS, each analyst one unweighted
    # observation. "No analyst diverges > 2 sigma" is a statement about the
    # spread of the analyst population, so the analyst is the unit of
    # observation, not the ticket.
    vals = [p["rate"] for p in people if p["rateable"]]
    if len(vals) >= 3:
        mean = sum(vals) / len(vals)
        # n-1: these analysts are a sample of the tower's staffing over time, not
        # a fixed population. It is also the conservative choice here - it widens
        # the band slightly and so flags FEWER people.
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    else:
        mean, sd = pooled, None

    for p in people:
        if sd is None or not p["rateable"]:
            # Shown in the table, greyed, rate displayed, not rated. Hiding them
            # would look like concealment; rating them would break the band.
            p["sigma"], p["outlier"] = None, False
        else:
            # sd == 0 (every rateable analyst identical) -> sigma 0.0 for all,
            # no outliers, no division by zero.
            p["sigma"] = (p["rate"] - mean) / sd if sd > 0 else 0.0
            p["outlier"] = abs(p["sigma"]) > 2.0
        p["z"] = binomial_z(p["escalated"], p["handled"], pooled)

    people.sort(key=lambda p: -p["rate"])
    rated = [p for p in people if p["rateable"]]
    outliers = [p["analyst"] for p in people if p["outlier"]]
    return {
        "people": people,
        "pooled": pooled,
        "mean": mean,
        "sd": sd,
        "lo": (mean - 2 * sd) if sd is not None else None,
        "hi": (mean + 2 * sd) if sd is not None else None,
        "floor": floor,
        "rated": len(rated),
        "excluded": [p["analyst"] for p in people if not p["rateable"]],
        "outliers": outliers,
        # The PILOT.md criterion-6 verdict, computed. Suppressed entirely when
        # there are too few rateable analysts to compute a band at all.
        "criterion_6": (None if sd is None
                        else ("met" if not outliers else "gap")),
    }


# ---------------------------------------------------------------------------
# Panel 4 - the KB gap
# ---------------------------------------------------------------------------

def kb_gap(rows):
    """Escalations that found no article. Live OPS 90d: 79/171 = 46.20%.

    The numerator is counted on the KB field ALONE, with no tier clause, because
    that is literally what metrics.py's JQL asks. store.Issue also carries a
    `kb_gap` boolean that ANDs in tier == "L2"; the two agree because 0 live rows
    have the KB value outside an escalation, and invariants() asserts exactly
    that. If the assertion ever fires, the denominator is wrong, not the
    numerator.

    Denominator is the same 171 escalations as the escalation-rate panel,
    Problems included.
    """
    esc = sum(1 for r in rows if r.tier == "L2")
    gap = sum(1 for r in rows if r.kb_checked == KB_NONE_FOUND)
    return gap, esc, pct(gap, esc)


def kb_gap_series(rows, now, days):
    """Weekly KB gap, as a COUNT and as a share.

    The weekly denominator is escalations in that week - typically 8 to 25 - so
    MIN_WEEK_DENOM gaps several buckets. That is correct. Plot the raw COUNT as
    bars, which is always stateable, and the SHARE as a line that breaks. The
    count is what carries the message - 79 tickets went to L2 with no article to
    hand - and it never abstains.
    """
    axis, buckets = bucket_weeks(rows, now, days)
    out = []
    for w in axis:
        b = buckets[w]
        esc = sum(1 for r in b if r.tier == "L2")
        gap = sum(1 for r in b if r.kb_checked == KB_NONE_FOUND)
        out.append({"week": w.isoformat(), "gap": gap, "escalated": esc,
                    "gap_pct": rate_point(gap, esc)})
    return out


def kb_gap_breakdown(rows, attr):
    """Gap counts by `tower` or `escalation_reason`, biggest first.

    This is the actionable output of the panel: the KB backlog in priority order,
    i.e. which articles to write next.
    """
    agg = {}
    for r in rows:
        if r.kb_checked != KB_NONE_FOUND:
            continue
        k = getattr(r, attr) or "(unset)"
        agg[k] = agg.get(k, 0) + 1
    return sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------------------------------------------------------------------
# Panel 5 - the tower comparison table
# ---------------------------------------------------------------------------

def tower_table(rows, now, days):
    """One row per tower in domain.TOWERS order, plus any tower the model does
    not know about, plus "(unset)" if any row lacks a tower.

    Model order, not data order: a tower with zero volume must still appear as a
    zero row, which is itself information. A tower that vanishes from the
    comparison because it had a quiet quarter is a tower nobody reviews.

    `pilot_score` is volume x headroom - enough volume to be significant, worst
    FTR to improve - the same key metrics.py ranks on:
        sorted(..., key=lambda kv: -volume * (100 - ftr_pct))
    It MUST be computed with ftr_pct as a float PERCENTAGE, not a fraction, to
    reproduce that ranking. The score is emitted so the ranking is auditable
    rather than asserted: a reviewer must be able to see that a tower ranked
    first because it is big AND weak, not merely weak. volume 0 -> score 0.0,
    which correctly ranks an empty tower last.
    """
    W = windowed(rows, now, days)
    by = {}
    for r in W:
        by.setdefault(r.tower or "(unset)", []).append(r)

    known = [t for t, _ in D.TOWERS]
    extra = sorted(k for k in by if k not in known and k != "(unset)")
    names = known + extra + (["(unset)"] if "(unset)" in by else [])

    out = []
    for tower in names:
        b = by.get(tower, [])
        c = closed_set(b)
        _fn, _fd, ftr_pct = ftr(b)
        _en, _ed, esc_pct = escalation(b)
        _m, _br, sla_pct = resolution_sla(b)
        # Aged is a SNAPSHOT over all rows for this tower, not the window -
        # matching metrics.py, which drops the window clause for aged_14d.
        scope = [r for r in rows
                 if (r.tower or "(unset)") == tower]
        out.append({
            "tower": tower,
            "volume": len(b),
            "closed": len(c),
            "ftr_pct": ftr_pct,
            "escalation_pct": esc_pct,
            "sla_pct": sla_pct,
            "aged": aged_backlog(scope, now),
            "open": open_count(scope),
            "known": tower in known,
            "pilot_score": len(b) * (100.0 - ftr_pct),
        })

    for i, t in enumerate(sorted(out, key=lambda t: -t["pilot_score"]), 1):
        t["pilot_rank"] = i
    return out


# ---------------------------------------------------------------------------
# Panel 6 - intake mix
# ---------------------------------------------------------------------------

def intake_mix(rows):
    """Volume by channel, in domain.INTAKE_CHANNELS order.

    Model order rather than count order, so Chat sits in a stable position across
    regenerations and the eye can find it. Live OPS 90d: Chat 43 of 420 = 10.2%,
    and the four observed channels are exactly the four the model declares.

    Chat is flagged `shadow`: those 43 are shadow support that previously never
    reached a ticket at all.
    """
    counts = {}
    for r in rows:
        k = r.intake or "(unset)"
        counts[k] = counts.get(k, 0) + 1
    total = len(rows)
    known = [c for c, _ in D.INTAKE_CHANNELS]
    names = known + sorted(k for k in counts if k not in known)
    return [{"channel": ch, "n": counts.get(ch, 0),
             "pct": pct(counts.get(ch, 0), total),
             "shadow": ch == "Chat"} for ch in names]


def channel_quality(rows):
    """FTR and escalation per channel.

    Pairs with intake_mix so the shadow-support claim is measurable rather than
    rhetorical: if chat tickets escalate far more than portal ones, that is a
    finding, not a talking point.
    """
    known = [c for c, _ in D.INTAKE_CHANNELS]
    out = []
    for ch in known:
        b = [r for r in rows if r.intake == ch]
        _n, _d, ftr_pct = ftr(b)
        _en, _ed, esc_pct = escalation(b)
        out.append({"channel": ch, "n": len(b),
                    "ftr_pct": ftr_pct, "escalation_pct": esc_pct})
    return out


# ---------------------------------------------------------------------------
# Panel 7 - ageing distribution of open work
# ---------------------------------------------------------------------------

def _median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def ageing(rows, now):
    """Age histogram of OPEN work, over ALL rows - deliberately not windowed.

    An 84-day-old ticket is exactly what this panel is for, and a 30-day window
    would hide it.

    Buckets are half-open [lo, hi) so no ticket is double-counted and the bucket
    sum equals open_count. invariants() asserts that.

    Live OPS: 62 open, min age 7.4d, max 84.1d, and 54 of 62 are over 30 days
    old. The distribution is bimodal-degenerate - nothing new is sitting. Shade
    the >= 14d buckets and annotate the 54.
    """
    op = [r for r in rows if r.is_open and r.reported_at is not None]
    ages = [(now - r.reported_at).total_seconds() / 86400.0 for r in op]
    buckets = []
    for lo, hi, label in AGE_BUCKETS:
        n = sum(1 for a in ages if a >= lo and (hi is None or a < hi))
        buckets.append({"label": label, "lo": lo, "hi": hi, "n": n,
                        "breach": lo >= AGED_DAYS})
    return {"buckets": buckets, "total": len(op),
            "oldest": max(ages) if ages else 0.0,
            "median": _median(ages),
            "over_30": sum(1 for a in ages if a >= 30)}


def ageing_by_status(rows, now):
    """The same buckets, split into work the tower is HOLDING versus work whose
    SLA clock is legitimately paused.

    Without this split the panel accuses the tower of 21 tickets it is not
    currently holding: on OPS today 14 sit in Pending Customer and 7 in Pending
    Vendor, waiting on someone else. The other 41 - Escalated to L2, In Progress
    L1/L2, Triage, New - are the tower's own queue.
    """
    paused_names = set(D.SLA_PAUSED_STATUSES)
    op = [r for r in rows if r.is_open and r.reported_at is not None]
    out = []
    for lo, hi, label in AGE_BUCKETS:
        cell = {"label": label, "owned": 0, "paused": 0}
        for r in op:
            a = (now - r.reported_at).total_seconds() / 86400.0
            if a >= lo and (hi is None or a < hi):
                cell["paused" if r.status in paused_names else "owned"] += 1
        out.append(cell)
    by_status = {}
    for r in op:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"buckets": out,
            "paused_total": sum(1 for r in op if r.status in paused_names),
            "owned_total": sum(1 for r in op if r.status not in paused_names),
            "by_status": sorted(by_status.items(), key=lambda kv: (-kv[1], kv[0]))}


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def invariants(rows, now):
    """Every assumption a panel silently rests on, checked against the data.

    Returns a list of human-readable violations; empty means all hold. Render
    them in the page footer. A panel whose invariant has failed is not "slightly
    off" - it is asserting something the data no longer supports - so
    backlog_series in particular must be SUPPRESSED rather than shown if its
    invariant fires.
    """
    bad = []

    # No Problem carries an SLA verdict - because sla_engine returns
    # problem-skipped before writing one. This is why _sla() has no
    # `issue_type != "Problem"` guard: the data enforces the exclusion, and a
    # guard would MASK the drift instead of reporting it.
    #
    # This one is live on ITSM today: ITSM-265 is a Problem carrying
    # Response SLA = "Met", so it sits in ITSM's response denominator. Note the
    # tower still reconciles with app/metrics.py, whose JQL has no issuetype
    # clause on the SLA counts either - both include it, and this line is how
    # anyone finds out.
    offenders = [r.key for r in rows if r.is_problem
                 and (r.resolution_sla in ("Met", "Breached")
                      or r.response_sla in ("Met", "Breached"))]
    if offenders:
        bad.append("%d Problem(s) carry an SLA verdict and so sit inside an SLA "
                   "denominator: %s" % (len(offenders), ", ".join(offenders[:10])))

    # The KB gap numerator is a subset of the escalation denominator, so the
    # ratio cannot exceed 100%.
    n = sum(1 for r in rows if r.kb_checked == KB_NONE_FOUND and r.tier != "L2")
    if n:
        bad.append("%d row(s) have KB '%s' without tier L2; the KB gap "
                   "denominator is wrong" % (n, KB_NONE_FOUND))

    # Resolved At is set iff the issue is Done. backlog_as_of() depends on this.
    n = sum(1 for r in rows if (r.resolved_at is None) != r.is_open)
    if n:
        bad.append("%d row(s) disagree between 'Resolved At' and statusCategory; "
                   "the backlog reconstruction cannot be trusted" % n)

    # Age buckets partition the open set.
    ag = ageing(rows, now)
    got = sum(b["n"] for b in ag["buckets"])
    if got != ag["total"]:
        bad.append("age buckets hold %d of %d open issues" % (got, ag["total"]))

    # The reconstruction agrees with the snapshot at t = now.
    if backlog_as_of(rows, now) != (open_count(rows), aged_backlog(rows, now)):
        bad.append("backlog reconstruction disagrees with the live snapshot at now")

    # Unbucketable tickets. A data-quality defect, not a rounding error.
    n = sum(1 for r in rows if r.reported_at is None)
    if n:
        bad.append("%d issue(s) have no 'Reported At' and are absent from every "
                   "time-bucketed panel" % n)
    return bad


def check_weekly_sums(rows, now, days):
    """The weekly buckets must partition the window. Returns violations.

    This is the acceptance check for the trend panels. If a row falls outside the
    axis it silently vanishes from every sparkline while still counting in the
    headline, and the page then contradicts itself with no visible symptom.
    """
    W = windowed(rows, now, days)
    weekly = weekly_series(rows, now, days)
    pair = ftr_vs_reopen(rows, now, days)
    kb = kb_gap_series(rows, now, days)

    bad = []
    checks = [
        ("volume", sum(w["n"] for w in weekly), len(W)),
        ("closed", sum(w["closed"] for w in weekly), len(closed_set(W))),
        ("closed (paired panel)", sum(p["closed"] for p in pair),
         len(closed_set(W))),
        ("escalated (kb panel)", sum(k["escalated"] for k in kb),
         sum(1 for r in W if r.tier == "L2")),
        ("kb gap (kb panel)", sum(k["gap"] for k in kb),
         sum(1 for r in W if r.kb_checked == KB_NONE_FOUND)),
    ]
    for label, got, want in checks:
        if got != want:
            bad.append("weekly %s sums to %d, window holds %d" % (label, got, want))
    if len(weekly) != len(pair):
        bad.append("weekly axis (%d) and paired axis (%d) differ"
                   % (len(weekly), len(pair)))
    return bad


# ---------------------------------------------------------------------------
# The assembled result
# ---------------------------------------------------------------------------

def compute_all(rows, now, days):
    """Everything the page needs, from one list of records.

    EVERY RATE CARRIES ITS num AND den. The renderer must show them - "61.8%
    215/348" - on every scoreboard tile and in every tooltip. A percentage
    without its denominator is the thing this whole page exists to argue against:
    78.9% over 388 adjudicated tickets is a different claim from 78.9% over 12.

    `rows` must be the UNWINDOWED project. Two figures - open and aged - are
    project-wide snapshots by design, and the ageing and backlog panels need
    tickets reported before the window in order to reconstruct history.
    """
    rows = list(rows)
    W = windowed(rows, now, days)

    ftr_n, ftr_d, ftr_p = ftr(W)
    esc_n, esc_d, esc_p = escalation(W)
    ro_n, ro_d, ro_p = reopen(W)
    sm, sb, sp = resolution_sla(W)
    rm, rb, rp = response_sla(W)
    kg, ke, kp = kb_gap(W)
    aged = aged_backlog(rows, now)

    def tile(key, value, num, den):
        t = target_for(key)
        return {"value": value, "num": num, "den": den,
                "target": None if t is None else t[0],
                "direction": None if t is None else t[1],
                "verdict": verdict(key, value)}

    pair = ftr_vs_reopen(rows, now, days)

    return {
        "generated": now.isoformat(),
        "window_days": days,
        "total_issues": len(rows),
        "volume": len(W),
        "open": open_count(rows),
        "closed": len(closed_set(W)),
        "shadow_chat": shadow_chat(W),
        "scoreboard": {
            "ftr_pct": tile("ftr_pct", ftr_p, ftr_n, ftr_d),
            "escalation_pct": tile("escalation_pct", esc_p, esc_n, esc_d),
            "reopen_pct": tile("reopen_pct", ro_p, ro_n, ro_d),
            "sla_pct": tile("sla_pct", sp, sm, sm + sb),
            "response_pct": tile("response_pct", rp, rm, rm + rb),
            # A count, not a rate: num/den are None and the renderer must not
            # print a percent sign next to it.
            "aged_14d": tile("aged_14d", aged, None, None),
        },
        "sla_detail": {"resolution_met": sm, "resolution_breached": sb,
                       "response_met": rm, "response_breached": rb},
        "weekly": weekly_series(rows, now, days),
        "backlog": backlog_series(rows, now, days),
        "ftr_vs_reopen": pair,
        "pairing": pairing_note(pair),
        "analysts": analyst_escalation(rows, now, days),
        "kb": {"gap": kg, "escalated": ke, "pct": kp,
               "series": kb_gap_series(rows, now, days),
               "by_tower": kb_gap_breakdown(W, "tower"),
               "by_reason": kb_gap_breakdown(W, "escalation_reason")},
        "towers": tower_table(rows, now, days),
        "intake": intake_mix(W),
        "channel_quality": channel_quality(W),
        "ageing": ageing(rows, now),
        "ageing_by_status": ageing_by_status(rows, now),
        "invariants": invariants(rows, now),
        "weekly_sums": check_weekly_sums(rows, now, days),
        # Jira's own timestamps, shown as the counterexample: one distinct date
        # each across the whole project, which is why nothing here uses them.
        "jira_time_counterexample": {
            "created_distinct_dates": len(set(
                r.jira_created.date() for r in rows if r.jira_created)),
            "resolutiondate_distinct_dates": len(set(
                r.jira_resolutiondate.date() for r in rows
                if r.jira_resolutiondate)),
        },
    }
