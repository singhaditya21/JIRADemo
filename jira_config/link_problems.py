#!/usr/bin/env python3
"""Link ITSM Problems to the Incidents they explain — the ITIL Problem/Incident relationship.

This creates REAL Jira issue links (not a fabricated field, not an invented column in the
bake): each Problem is linked, via Jira's causal link type, to a handful of Incidents in its
own tower — preferring incidents whose root cause matches the problem's. The pairings are
synthetic (this is a seeded demo), but the LINK is a genuine Jira object, so the control
tower reads it back through the same `issuelinks` field a real instance would expose.

Idempotent and safe to re-run: an existing Problem→Incident link is never duplicated, and
--dry-run rehearses every mutation through Writer without issuing one. Deterministic: the
same Problems get the same Incidents on every run (no RNG), so the demo is reproducible.

    python3 -m jira_config.link_problems [--dry-run] [--per-problem N] [--limit N]

Run it once (locally with your token, or via the "Link ITSM problems to incidents" GitHub
Action which uses the CI secret). The next bake then surfaces the links in the tower's
Problem-management panel; before it runs, the panel simply says "no links yet".
"""

import argparse
import hashlib

from shared.jira_client import Jira, log, require_env
from shared import fields as FIELDS
from app import store as S
from jira_config.reconcile import Writer

PROJECT = "ITSM"
CAUSAL_HINTS = ("problem/incident", "causers", "caused")   # names/labels that mean "causes"


def pick_link_type(j):
    """Choose the causal link type, falling back to Relates, then the first available."""
    types = (j.get("/rest/api/3/issueLinkType") or {}).get("issueLinkTypes") or []
    for t in types:                                    # a real Problem/Incident / causes type
        blob = " ".join([t.get("name", ""), t.get("inward", ""), t.get("outward", "")]).lower()
        if any(h in blob for h in CAUSAL_HINTS) or "cause" in blob:
            return t
    for t in types:
        if t.get("name") == "Relates":
            return t
    return types[0] if types else None


def per_problem_count(problem_key, base):
    """Deterministic 4..(base+3)-ish spread so problems differ but reproducibly."""
    h = int(hashlib.sha1(problem_key.encode()).hexdigest()[:6], 16)
    return base + (h % 5)                              # base .. base+4


def plan_links(issues, per_base):
    """Return [(problem, incident)] pairs to link, deterministically, no incident reused."""
    problems = sorted((i for i in issues if i.issue_type == "Problem"), key=lambda i: i.key)
    incidents = sorted((i for i in issues if i.issue_type == "Incident"), key=lambda i: i.key)
    by_tower = {}
    for inc in incidents:
        by_tower.setdefault(inc.tower, []).append(inc)

    used = set()
    pairs = []
    for p in problems:
        pool = by_tower.get(p.tower, [])
        # root-cause matches first, then the rest of the tower — both key-sorted (deterministic)
        ordered = ([i for i in pool if i.root_cause and i.root_cause == p.root_cause]
                   + [i for i in pool if not (i.root_cause and i.root_cause == p.root_cause)])
        want = per_problem_count(p.key, per_base)
        picked = 0
        for inc in ordered:
            if picked >= want:
                break
            if inc.key in used:
                continue
            used.add(inc.key)
            pairs.append((p, inc))
            picked += 1
    return pairs


def already_linked(problem, incident_key):
    return any((l.get("key") == incident_key) for l in (problem.links or []))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--per-problem", type=int, default=4, help="base links per problem (4..8)")
    ap.add_argument("--limit", type=int, default=0, help="cap total links created (0 = no cap)")
    args = ap.parse_args(argv)

    require_env()
    j = Jira()
    w = Writer(j, dry=args.dry_run)

    lt = pick_link_type(j)
    if not lt:
        raise SystemExit("no issue link types available on this instance")
    log(f"link type: {lt['name']}  (outward: '{lt.get('outward')}', inward: '{lt.get('inward')}')")

    F = FIELDS.resolve(j)
    st = S.fetch(j, PROJECT, F)                        # reads issuelinks -> idempotency check
    pairs = plan_links(st.issues, args.per_problem)
    log(f"planned {len(pairs)} problem->incident pairs across "
        f"{len({p.key for p, _ in pairs})} problems")

    created = skipped = 0
    for problem, incident in pairs:
        if args.limit and created >= args.limit:
            break
        if already_linked(problem, incident.key):
            skipped += 1
            continue
        # outwardIssue "causes" inwardIssue: the Problem is the cause, the Incident the effect.
        w.post("/rest/api/3/issueLink", {
            "type": {"name": lt["name"]},
            "outwardIssue": {"key": problem.key},
            "inwardIssue": {"key": incident.key},
        })
        created += 1
        log(f"  {problem.key} --{lt.get('outward','causes')}--> {incident.key}"
            f"  ({problem.tower} · {problem.root_cause or 'n/a'})")

    log(f"done: {created} link(s) created, {skipped} already present"
        + (" [dry-run]" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
