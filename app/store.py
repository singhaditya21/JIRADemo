#!/usr/bin/env python3
"""Fetch-once issue store: one paginated read of Jira, then pure functions.

WHY THIS MODULE EXISTS
----------------------
app/metrics.py asks Jira a question per metric. That is a dozen `approximate-count`
calls for one report, and it is the right shape for a report: cheap, obviously
correct, one number per line. It is the wrong shape the moment a number has to be
trended. Six metrics x 13 weeks x 7 tower cuts is 546 round-trips for one HTML
file, every one of them rate-limitable, and the totals would not even reconcile
with each other because each count is evaluated at a slightly different instant.

So the control tower reads every issue in the project ONCE - 420 issues, 5 pages,
~4s - holds them in memory, and computes every panel locally. Every panel is then
a pure function of a tuple of `Issue` records, which means the metrics can be unit
tested with hand-built records and no Jira at all. See app/analytics.py.

app/sla_engine.py has the same problem in a worse form: it issues one GET per
issue (420 round-trips) purely to obtain fields plus changelog. `fetch(...,
with_changelog=True)` returns exactly that payload in 5 requests. See
"SEAM FOR sla_engine" at the foot of this file - this module does not import
sla_engine and never should; the dependency runs the other way.

WHAT THIS MODULE IS NOT
-----------------------
It computes no metric. Ratios, targets, sigma bands and week series belong to
app/analytics.py. What it does own is the *semantics of the data*: what
"escalated" means, which issues count as closed, which timestamp is the time
axis. Those live here as derived booleans on the record so that the tower and
`app.cli metrics` cannot quietly disagree about a denominator on stage.

THE TIME AXIS
-------------
`Reported At` (customfield_10057 on this instance - resolved by NAME, never
hardcoded). Jira's own `created` is 2026-07-20 for all 420 seeded issues because
`created` is read-only over REST; `resolutiondate` is likewise today for all Done
issues. Both are fetched, both are stored as `jira_created` /
`jira_resolutiondate`, and both exist ONLY so a panel can display them as the
counterexample. They are banned from every time axis. Use `reported_at`.

LAYER RULES
-----------
Imports shared/ only - never jira_config, never fixtures. Reads no build artifact.
READ-ONLY against Jira: the only verbs are a POST to /rest/api/3/search/jql (which
is Jira's *read* endpoint - it takes a body, so it cannot be a GET) and a GET of
the per-issue changelog.

Python 3.9. No f-strings containing backslashes.
"""

import json
import re
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from shared import domain as D
from shared import fields as FIELDS

# ---------------------------------------------------------------------------
# What we ask Jira for
# ---------------------------------------------------------------------------

# Jira caps a page by RESPONSE SIZE, not by the maxResults you send: asking for
# 1000 with this field list still returns 100 (measured). So send 100, and loop.
PAGE_SIZE = 100

# Guard against a nextPageToken that never clears. 500 pages x 100 = 50k issues,
# far past anything this tool is for, so tripping it means the loop is broken.
MAX_PAGES = 500

# Select fields arrive as {"self":..., "value": "L1", "id":...} and are unwrapped.
SELECT_READS = (
    "Tower", "Support Tier", "Intake Channel", "KB Article Checked",
    "Escalation Reason", "Root Cause", "Resolution Code",
    "Response SLA", "Resolution SLA", "Reopened", "Impact", "Urgency",
)

# Plain strings.
TEXT_READS = ("L1 Analyst", "L2 Analyst", "Affected Service")

# Strings like "2026-06-25T19:30:00.000+0530", parsed to aware datetimes.
DATE_READS = ("Reported At", "First Response At", "Escalated At", "Resolved At")

STORE_FIELD_NAMES = DATE_READS + SELECT_READS + TEXT_READS

# System fields. `summary` is here because every panel that shows a count wants a
# drill-down list behind it and a key alone is unreadable. `description` and
# `Troubleshooting Performed` are deliberately NOT here - they are long text, they
# would multiply the page count, and no panel reads them.
SYSTEM_READS = ("issuetype", "status", "priority", "created", "resolutiondate",
                "summary", "issuelinks")


def jql_for(project, extra=""):
    """Every issue in the project. The window is applied locally, not in JQL.

    Two reasons the window is not pushed into JQL:

      1. app/metrics.py deliberately does NOT window two of its numbers - `open`
         and `aged_14d` are project-wide, because a 90-day filter would hide the
         very backlog they exist to expose. A store that only held the window
         could not reproduce them, and the tower would then disagree with
         `python3 -m app.cli metrics` on stage.
      2. --days becomes a display control. Changing 90 to 30 re-renders from the
         same fetch instead of hitting the API again.

    ORDER BY is `created ASC, key ASC` rather than bare `created ASC`: `created`
    is identical (2026-07-20) on all 420 seeded issues, so on its own it is not a
    total order. Token pagination held anyway when measured, but a sort key with
    420 ties is not something to rely on. The tiebreak costs nothing.
    """
    return "project = " + project + extra + " ORDER BY created ASC, key ASC"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Jira Cloud emits "+0530"; some endpoints emit "+05:30". datetime.fromisoformat
# on Python 3.9 rejects the first form (it only became lenient in 3.11), so
# normalise the offset and use strptime. Do not "simplify" this to fromisoformat.
_TZ_COLON = re.compile(r"([+-]\d{2}):(\d{2})$")


def parse_dt(ts):
    """Jira timestamp -> aware datetime, or None.

    The offset is PRESERVED, not normalised to UTC: week buckets are cut on the
    wall clock a Jira user sees, and shifting +05:30 to UTC first would move a
    Monday 02:00 ticket into the previous Sunday. Two of the 420 live rows
    (OPS-2358, OPS-2534) sit in exactly that window.
    """
    if not ts:
        return None
    text = _TZ_COLON.sub(r"\1\2", ts.strip())
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        # Some Jira endpoints omit the milliseconds. Not seen on this instance,
        # but a timestamp that fails to parse would silently become "no Reported
        # At" and drop the issue off every time axis, so try the short form too.
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")


def week_start(when):
    """The Monday of the week containing `when`, as a date, in `when`'s own offset."""
    day = when.date()
    return day - timedelta(days=day.weekday())


def _opt(value):
    """Unwrap a Jira select option. {"value": "L1"} -> "L1"; None stays None."""
    if isinstance(value, dict):
        return value.get("value")
    return value


def _parse_links(raw):
    """`fields.issuelinks` -> a flat list of {key, rel, dir, issue_type, status}.

    Each Jira link names the OTHER issue as inwardIssue or outwardIssue plus a type with
    directional labels ("causes"/"is caused by"). We flatten to the neighbour's key, the
    directional phrase, and the neighbour's type/status (Jira returns a small fields subset
    on the linked issue) so the record layer can render "this problem causes N incidents".
    """
    out = []
    for l in raw or []:
        t = l.get("type") or {}
        if l.get("outwardIssue"):
            oi, direction, rel = l["outwardIssue"], "outward", t.get("outward")
        elif l.get("inwardIssue"):
            oi, direction, rel = l["inwardIssue"], "inward", t.get("inward")
        else:
            continue
        of = oi.get("fields") or {}
        out.append({"key": oi.get("key"), "rel": rel, "dir": direction,
                    "type": t.get("name"),
                    "issue_type": (of.get("issuetype") or {}).get("name"),
                    "status": (of.get("status") or {}).get("name")})
    return out


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

Change = namedtuple("Change", "at field frm to")

_ISSUE_ATTRS = [
    # identity
    "key", "url", "summary", "issue_type", "status", "status_category", "priority",
    # unwrapped selects
    "tower", "tier", "intake", "kb_checked", "escalation_reason", "root_cause",
    "resolution_code", "response_sla", "resolution_sla", "reopened",
    "impact", "urgency",
    # text
    "l1_analyst", "l2_analyst", "affected_service",
    # the real timeline
    "reported_at", "first_response_at", "escalated_at", "resolved_at",
    # Jira's own timestamps - counterexamples only, never a time axis
    "jira_created", "jira_resolutiondate",
    # derived: bucketing and durations
    "week", "age_days", "lifetime_days", "response_hours",
    # derived: the shared denominators
    "is_done", "is_open", "is_problem", "is_escalated", "is_reopened",
    "counts_as_closed", "counts_as_ftr", "kb_gap",
    # issue links (Problem/Incident etc.) — record-layer only; analytics ignores them
    "links",
    # optional
    "changelog", "changelog_truncated",
]

Issue = namedtuple("Issue", _ISSUE_ATTRS)
Issue.__new__.__defaults__ = (None,) * len(_ISSUE_ATTRS)

Issue.__doc__ = """One Jira issue, flattened and parsed.

The derived booleans are the point of this record. They encode the denominator
decisions that app/metrics.py makes in JQL, in one place, so a panel physically
cannot pick a different one:

  is_done          status_category == "done"        (Jira's category, not a name.
                                                     NOTE this includes Cancelled,
                                                     matching metrics.py.)
  is_open          not is_done                      (covers "new" AND
                                                     "indeterminate" - 5 + 57 = 62
                                                     on OPS today)
  is_problem       issue_type == "Problem"
  counts_as_closed is_done and not is_problem       <- FTR and reopen DENOMINATOR.
                                                     Problems are investigations by
                                                     definition; counting them
                                                     punishes doing the right thing.
                                                     metrics.py excludes them:
                                                     `statusCategory = Done AND
                                                     issuetype != Problem`.
  counts_as_ftr    counts_as_closed and tier == "L1"
  is_escalated     tier == "L2"                     <- numerator of escalation rate;
                                                     the DENOMINATOR is every issue
                                                     in the window, problems
                                                     included, matching metrics.py.
  is_reopened      reopened == "Yes"
  kb_gap           is_escalated and
                   kb_checked == "Yes - none found"

`kb_gap` is the only derived boolean that is NOT a faithful transcription of
metrics.py: the JQL numerator carries no tier clause. It is a subset flag, and
0 of 420 live rows have the KB value without tier L2, so the two agree. The
analytics layer counts the JQL form and asserts the containment - see
analytics.kb_gap.

Durations, all in the caller-supplied `now` frame so they are deterministic:

  age_days         reported_at -> now, elapsed days as a float. Meaningful for
                   open work; still computed for closed so the ageing histogram
                   can be re-cut without a refetch.
  lifetime_days    reported_at -> (resolved_at or now).
  response_hours   reported_at -> first_response_at, elapsed hours, or None.
                   ELAPSED, not business hours - business-calendar arithmetic is
                   sla_engine.business_hours_between and stays there.
"""


def build_issue(raw, F, now):
    """One search/jql `issues[]` element -> Issue. Pure; no I/O."""
    f = raw.get("fields") or {}

    def sel(name):
        return _opt(f.get(F[name]))

    def dt(name):
        return parse_dt(f.get(F[name]))

    itype = (f.get("issuetype") or {}).get("name")
    status = f.get("status") or {}
    category = (status.get("statusCategory") or {}).get("key")

    reported = dt("Reported At")
    resolved = dt("Resolved At")
    first = dt("First Response At")

    is_done = category == "done"
    is_problem = itype == "Problem"
    tier = sel("Support Tier")
    kb = sel("KB Article Checked")
    reopened = sel("Reopened")
    escalated = tier == "L2"
    closed = is_done and not is_problem

    age = lifetime = None
    if reported is not None:
        age = (now - reported).total_seconds() / 86400.0
        lifetime = ((resolved or now) - reported).total_seconds() / 86400.0
    resp_h = None
    if reported is not None and first is not None:
        resp_h = (first - reported).total_seconds() / 3600.0

    changelog, truncated = None, False
    if "changelog" in raw:
        changelog, truncated = build_changelog(raw["changelog"])

    return Issue(
        key=raw.get("key"),
        url=None,                          # filled by fetch(), which knows the site
        summary=f.get("summary"),
        issue_type=itype,
        status=status.get("name"),
        status_category=category,
        priority=(f.get("priority") or {}).get("name"),
        tower=sel("Tower"), tier=tier, intake=sel("Intake Channel"),
        kb_checked=kb, escalation_reason=sel("Escalation Reason"),
        root_cause=sel("Root Cause"), resolution_code=sel("Resolution Code"),
        response_sla=sel("Response SLA"), resolution_sla=sel("Resolution SLA"),
        reopened=reopened, impact=sel("Impact"), urgency=sel("Urgency"),
        l1_analyst=f.get(F["L1 Analyst"]), l2_analyst=f.get(F["L2 Analyst"]),
        affected_service=f.get(F["Affected Service"]),
        reported_at=reported, first_response_at=first,
        escalated_at=dt("Escalated At"), resolved_at=resolved,
        jira_created=parse_dt(f.get("created")),
        jira_resolutiondate=parse_dt(f.get("resolutiondate")),
        week=week_start(reported) if reported is not None else None,
        age_days=age, lifetime_days=lifetime, response_hours=resp_h,
        is_done=is_done, is_open=not is_done, is_problem=is_problem,
        is_escalated=escalated, is_reopened=reopened == "Yes",
        counts_as_closed=closed, counts_as_ftr=closed and tier == "L1",
        kb_gap=escalated and kb == "Yes - none found",
        links=_parse_links(f.get("issuelinks")),
        changelog=changelog, changelog_truncated=truncated,
    )


def build_changelog(block):
    """`changelog` block -> (tuple of Change sorted by time, truncated?).

    search/jql returns changelog inline but does NOT paginate it. On OPS the
    longest history is 9 entries and nothing is cut, but on real traffic it will
    be, so `total` is compared against what arrived and the shortfall is reported
    rather than silently averaged away.
    """
    histories = block.get("histories") or []
    total = block.get("total")
    changes = []
    for h in histories:
        when = parse_dt(h.get("created"))
        for item in h.get("items") or []:
            changes.append(Change(at=when, field=item.get("field"),
                                  frm=item.get("fromString"), to=item.get("toString")))
    changes.sort(key=lambda c: (c.at is None, c.at))
    truncated = total is not None and len(histories) < total
    return tuple(changes), truncated


# ---------------------------------------------------------------------------
# The fetch
# ---------------------------------------------------------------------------

class StoreError(RuntimeError):
    pass


def field_ids(F, names=STORE_FIELD_NAMES):
    """The exact `fields` list to send: system fields, then the custom ids
    resolved by NAME through shared/fields.py.

    Ids are never hardcoded and never read from jira_config/state/*.json - see
    shared/fields.py for why. Note "key" is NOT in this list: the issue key is a
    top-level property of the response, and asking for it under `fields` is a
    no-op that quietly does nothing.
    """
    return list(SYSTEM_READS) + [F.id(n) for n in names]


def fetch_page(j, jql, ids, token=None, with_changelog=False):
    body = {"jql": jql, "maxResults": PAGE_SIZE, "fields": list(ids)}
    if token:
        body["nextPageToken"] = token
    if with_changelog:
        # A STRING. {"expand": ["changelog"]} is a 400 "Invalid request payload"
        # on this endpoint - measured. The GET form takes a list; this one does not.
        body["expand"] = "changelog"
    # POST, but a READ: search/jql takes a JQL body, so Jira exposes it as POST.
    # This module writes nothing. Do not "fix" this into a mutation.
    return j.post("/rest/api/3/search/jql", body)


def fetch(j, project, F=None, now=None, with_changelog=False, extra_jql=""):
    """Read the whole project once and return an IssueStore.

    5 requests / ~4s for OPS's 420 issues; ~6-9s with changelog.
    """
    if F is None:
        F = FIELDS.resolve(j)
    if now is None:
        now = datetime.now(timezone.utc)

    warnings = list(F.warnings())
    ids = field_ids(F)
    jql = jql_for(project, extra_jql)

    raw, token, pages, seen = [], None, 0, set()
    while True:
        page = fetch_page(j, jql, ids, token, with_changelog)
        batch = page.get("issues") or []

        # An unknown customfield id is DROPPED SILENTLY by this endpoint - the
        # issue comes back with no `fields` key at all rather than an error
        # (measured). Resolution already failed loudly upstream if a field is
        # missing, so this is the belt to that braces; without it, a schema drift
        # renders a control tower full of confident zeroes.
        if pages == 0 and batch and "fields" not in batch[0]:
            raise StoreError(
                "search/jql returned issues with no `fields` for %s. Every id in "
                "the request was rejected; requested: %s"
                % (project, ", ".join(ids)))

        for issue in batch:
            if issue.get("key") not in seen:
                seen.add(issue.get("key"))
                raw.append(issue)
        pages += 1
        token = page.get("nextPageToken")
        if page.get("isLast") or not token or not batch:
            break
        if pages >= MAX_PAGES:
            raise StoreError("pagination did not terminate after %d pages (%d issues)"
                             % (pages, len(raw)))

    issues = []
    no_reported = []
    for r in raw:
        rec = build_issue(r, F, now)
        rec = rec._replace(url=j.site + "/browse/" + (rec.key or ""))
        if rec.reported_at is None:
            # Not dropped - counted and named. An issue with no Reported At cannot
            # be placed on the time axis, and silently discarding it would make
            # every rate quietly optimistic.
            no_reported.append(rec.key)
        issues.append(rec)

    if no_reported:
        warnings.append(
            "%d issue(s) have no 'Reported At' and are excluded from every "
            "time-bucketed panel: %s"
            % (len(no_reported), ", ".join(no_reported[:10])))
    cut = [i.key for i in issues if i.changelog_truncated]
    if cut:
        warnings.append(
            "%d issue(s) returned a truncated changelog; call top_up_changelog() "
            "before using pause time: %s" % (len(cut), ", ".join(cut[:10])))

    return IssueStore(project=project, issues=tuple(issues), fieldmap=F,
                      now=now, pages=pages, warnings=warnings, site=j.site)


def top_up_changelog(j, store):
    """Refetch full changelogs for the issues whose inline one was cut.

    Only the truncated ones, so on OPS today this is zero requests. The per-issue
    endpoint /rest/api/3/issue/{key}/changelog IS paginated properly.
    """
    fixed = {}
    for issue in store.issues:
        if not issue.changelog_truncated:
            continue
        histories, start = [], 0
        while True:
            page = j.get("/rest/api/3/issue/%s/changelog?startAt=%d&maxResults=100"
                         % (issue.key, start))
            values = page.get("values") or []
            histories.extend(values)
            start += len(values)
            if page.get("isLast", True) or not values:
                break
        changes, _ = build_changelog({"histories": histories,
                                      "total": len(histories)})
        fixed[issue.key] = changes
    if not fixed:
        return store
    issues = tuple(i._replace(changelog=fixed[i.key], changelog_truncated=False)
                   if i.key in fixed else i for i in store.issues)
    return store._with(issues)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

class IssueStore(object):
    """Every issue in one project, parsed, plus the selectors panels share.

    Deliberately contains NO metric. `window()` and `week_starts()` are here
    because getting either subtly wrong silently changes every panel at once;
    ratios are app/analytics.py's business.
    """

    def __init__(self, project, issues, fieldmap, now, pages=0, warnings=(), site=""):
        self.project = project
        self.issues = tuple(issues)
        self.fields = fieldmap
        self.now = now
        self.pages = pages
        self.warnings = list(warnings)
        self.site = site

    def _with(self, issues):
        return IssueStore(self.project, issues, self.fields, self.now,
                          self.pages, self.warnings, self.site)

    def __len__(self):
        return len(self.issues)

    # -- the display timezone ------------------------------------------------
    @property
    def tz(self):
        """The offset the data is stamped in (+05:30 here), taken from the most
        recent Reported At. Week edges and "today" are cut in this frame so the
        newest bucket cannot land a day out from what Jira shows."""
        stamped = [i.reported_at for i in self.issues if i.reported_at is not None]
        if not stamped:
            return timezone.utc
        return max(stamped).tzinfo

    @property
    def today(self):
        return self.now.astimezone(self.tz).date()

    # -- selection -----------------------------------------------------------
    def window(self, days):
        """Issues whose Reported At falls in the last `days`.

        Exactly `"Reported At" >= -Nd` as metrics.py writes it in JQL - Jira
        evaluates that against now, so an aware comparison against
        now - timedelta(days=N) is the faithful in-memory form. Issues with no
        Reported At are excluded; fetch() has already counted them into
        store.warnings so they are visible rather than lost.
        """
        cut = self.now - timedelta(days=days)
        return tuple(i for i in self.issues
                     if i.reported_at is not None and i.reported_at >= cut)

    def open_issues(self):
        """NOT windowed - matches metrics.py, which asks for open work across the
        whole project. Windowing it would hide the backlog it exists to show."""
        return tuple(i for i in self.issues if i.is_open)

    def aged(self, days=14):
        """Open and reported at least `days` ago. 60 on OPS today, which is what
        `statusCategory != Done AND "Reported At" <= -14d` returns."""
        cut = self.now - timedelta(days=days)
        return tuple(i for i in self.open_issues()
                     if i.reported_at is not None and i.reported_at <= cut)

    # -- bucketing -----------------------------------------------------------
    def week_starts(self, days=None):
        """Contiguous Mondays covering the window, INCLUDING empty weeks.

        Contiguity is not a detail. Deriving the axis from the weeks that happen
        to contain tickets makes a sparkline skip a quiet week, which reads as
        continuity across a gap - the chart says nothing happened when in fact
        nothing was recorded.

        NOTE this is the DATA-derived axis (first ticket to last ticket). The
        analytics layer builds its axis from the WINDOW instead - see
        analytics.week_axis - so that a trailing week with no tickets at all
        still appears. Both are contiguous; they differ only at the ends.
        """
        pool = self.window(days) if days else self.issues
        weeks = [i.week for i in pool if i.week is not None]
        if not weeks:
            return ()
        out, cur, last = [], min(weeks), max(weeks)
        while cur <= last:
            out.append(cur)
            cur = cur + timedelta(days=7)
        return tuple(out)

    def by_week(self, days=None):
        """[(week_start, issues)], every week present, in order."""
        pool = self.window(days) if days else self.issues
        axis = self.week_starts(days)
        buckets = dict((w, []) for w in axis)
        for i in pool:
            if i.week in buckets:
                buckets[i.week].append(i)
        return [(w, tuple(buckets[w])) for w in axis]

    def by_tower(self, days=None):
        """[(tower, issues)] in domain.TOWERS order, every tower present even at
        zero volume - a tower that vanishes from the comparison table because it
        had a quiet quarter is a tower nobody reviews."""
        pool = self.window(days) if days else self.issues
        buckets = dict((t, []) for t, _ in D.TOWERS)
        for i in pool:
            buckets.setdefault(i.tower, []).append(i)
        ordered = [(t, tuple(buckets.pop(t, ()))) for t, _ in D.TOWERS]
        # anything the model does not know about is surfaced, not swallowed
        for t in sorted(k for k in buckets if k is not None):
            ordered.append((t, tuple(buckets[t])))
        return ordered

    def by_l1_analyst(self, days=None):
        """[(analyst, issues)]. Keyed on the L1 Analyst FIELD, not the Jira
        assignee: the seeded assignee is the API account on all 420 issues, and
        on a real instance the assignee moves to L2 on escalation, which would
        credit the escalation to the wrong person - the exact bias the analyst
        panel exists to detect. 12 analysts, no nulls, on OPS today."""
        pool = self.window(days) if days else self.issues
        buckets = {}
        for i in pool:
            if i.l1_analyst:
                buckets.setdefault(i.l1_analyst, []).append(i)
        return [(a, tuple(buckets[a])) for a in sorted(buckets)]

    # -- snapshot ------------------------------------------------------------
    def dump(self, path):
        """Freeze the fetch to JSON so the panels can be developed, diffed and
        unit tested with the API unplugged."""
        payload = {
            "project": self.project, "site": self.site,
            "now": self.now.isoformat(), "pages": self.pages,
            "warnings": self.warnings,
            "issues": [_jsonable(i) for i in self.issues],
        }
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=1)

    @classmethod
    def load(cls, path, fieldmap=None):
        with open(path) as fh:
            payload = json.load(fh)
        issues = tuple(_from_jsonable(d) for d in payload["issues"])
        return cls(payload["project"], issues, fieldmap,
                   datetime.fromisoformat(payload["now"]),
                   payload.get("pages", 0), payload.get("warnings", []),
                   payload.get("site", ""))


_DT_ATTRS = ("reported_at", "first_response_at", "escalated_at", "resolved_at",
             "jira_created", "jira_resolutiondate")


def _jsonable(issue):
    d = issue._asdict()
    for a in _DT_ATTRS:
        d[a] = d[a].isoformat() if d[a] else None
    d["week"] = d["week"].isoformat() if d["week"] else None
    if d["changelog"]:
        d["changelog"] = [[c.at.isoformat() if c.at else None, c.field, c.frm, c.to]
                          for c in d["changelog"]]
    return d


def _from_jsonable(d):
    d = dict(d)
    for a in _DT_ATTRS:
        d[a] = parse_iso(d[a])
    d["week"] = (datetime.strptime(d["week"], "%Y-%m-%d").date()
                 if d["week"] else None)
    if d["changelog"]:
        d["changelog"] = tuple(Change(parse_iso(c[0]), c[1], c[2], c[3])
                               for c in d["changelog"])
    return Issue(**d)


def parse_iso(text):
    """Reverse of datetime.isoformat(). 3.9's fromisoformat handles the "+05:30"
    form it emits itself, which is exactly what dump() writes."""
    return datetime.fromisoformat(text) if text else None


# ---------------------------------------------------------------------------
# SEAM FOR sla_engine (documented, not wired in this change)
# ---------------------------------------------------------------------------
#
# app/sla_engine.py today does one paginated key search plus ONE GET PER ISSUE
# with expand=changelog, fanned over a ThreadPoolExecutor to hide the cost. The
# same payload is 5 requests through this module:
#
#     store = fetch(j, args.project, with_changelog=True)
#     store = top_up_changelog(j, store)      # no-op unless something was cut
#     for issue in store.issues:
#         if issue.is_problem or issue.reported_at is None:
#             continue
#         code = D.PRIORITY_CODES.get(issue.priority)
#         ...  # evaluate() unchanged from here, reading issue.* instead of f[...]
#
# What sla_engine KEEPS (business-calendar arithmetic, not data access):
# business_hours_between(), the SLA_TARGETS/SLA_CLOCK lookup, the Met/Breached/
# Paused decision, write_back(). What it DELETES: the per-issue GET, its own
# parse() (superseded by parse_dt, which also handles the "+05:30" form), and the
# field-name string building. paused_seconds() changes shape only - it takes
# Change tuples instead of raw histories and no longer has to sort, because
# build_changelog already did.
#
# DEPENDENCY DIRECTION IS FIXED: sla_engine imports store. This module imports
# shared/ only, and must never import sla_engine, metrics, analytics or
# control_tower.
