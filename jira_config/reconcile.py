#!/usr/bin/env python3
"""Idempotent reconciliation primitives for Jira filters, dashboards and queues.

Every function here is a RECONCILER, not a builder: it reads live state, diffs it
against a declared plan, and issues the minimum writes that close the gap. Running
twice against an unchanged plan must produce ZERO writes the second time. That is
a stronger property than "ends up correct", and it is the one that was missing.

Three rules hold throughout:

  1. Never blind-append. Enumerate first, match, create only the remainder. The
     predecessor of views.py appended three unconfigured gadgets per run with no
     lookup at all; four runs is how OPS dashboard 10001 reached twelve blank ones.
  2. Never delete unless the caller explicitly asked. Jira has no undo, and JSM
     queues have no REST delete at all (GET on the internal endpoint answers 405).
  3. Never bind a gadget to a filter id that was not confirmed present. A gadget
     with no filterId renders as a blank "select a filter" prompt - exactly the
     defect this module exists to stop recurring.

Facts established by probing the live instance, so nobody re-derives them:

  * GET /dashboard/{id}/gadget is UNPAGINATED - it returns {"gadgets": [...]} and
    no paging keys. Its `id` is an int; cast at the boundary.
  * A gadget with no config property makes the config GET answer 404, which
    Jira.try_get turns into the default. That is the unbound signal.
  * Jira REFLOWS position.row on POST collision. Position therefore carries no
    identity and must never be used for matching.
  * Titles round-trip in both directions, so title is the natural key.
  * Jira REWRITES stored JQL (`Tower = "Database"` comes back `Tower = Database`).
    Comparing raw strings reports drift forever; hence normalize_jql.
  * Filter sharePermissions SURVIVE a PUT that omits them, and the value changes
    name in transit ("authenticated" in, "loggedin" out) so it cannot be diffed.
    Send them on create only.

Python 3.9. No f-strings with backslashes, no match statements.
"""

import re
import sys

from shared.jira_client import log

_WS = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# write gate
# ---------------------------------------------------------------------------

class Writer:
    """Wraps Jira so every mutating call is skippable, countable and logged.

    --dry-run is a first-class mode rather than an afterthought: the rule in this
    repo is that nothing runs against live OPS/ITSM without a dry pass first, and
    a dry pass is only trustworthy if the write path is the thing being gated.
    """

    def __init__(self, jira, dry=False):
        self.j = jira
        self.dry = dry
        self.writes = 0
        self.planned = []

    def _note(self, method, path):
        self.planned.append((method, path))
        if self.dry:
            log("      [dry] " + method + " " + path)

    def post(self, path, body):
        self._note("POST", path)
        if self.dry:
            return {"id": "DRY-%d" % len(self.planned)}
        self.writes += 1
        return self.j.post(path, body)

    def put(self, path, body):
        self._note("PUT", path)
        if self.dry:
            return {}
        self.writes += 1
        return self.j.put(path, body)

    def delete(self, path):
        self._note("DELETE", path)
        if self.dry:
            return {}
        self.writes += 1
        return self.j.delete(path)


# ---------------------------------------------------------------------------
# comparison helpers
# ---------------------------------------------------------------------------

def normalize_jql(jql):
    """Collapse a JQL string to a comparable form.

    Jira rewrites the JQL it stores, dropping quotes wherever they are not
    syntactically required. Comparing raw strings therefore reports drift on
    every run forever - which is why the JSM views script gave up on diffing and
    simply PUT unconditionally.

    Dropping every quote and lowercasing is safe HERE because the result is used
    only for the equality test; the DECLARED jql is always what gets written. Do
    not reuse this function to compare JQL for any other purpose - it would treat
    two genuinely different plan entries as identical.
    """
    if not jql:
        return ""
    flat = jql.replace('"', "").replace("'", "")
    return _WS.sub(" ", flat).strip().lower()


def strip_project_prefix(jql, project_key):
    """The queue endpoint auto-prepends `project = KEY AND ` to what it stores."""
    prefix = "project = %s AND " % project_key
    if jql.startswith(prefix):
        return jql[len(prefix):]
    return jql


def norm_text(s):
    if not s:
        return ""
    return _WS.sub(" ", s).strip()


# ---------------------------------------------------------------------------
# gadget vocabulary
# ---------------------------------------------------------------------------

_G = "rest/gadgets/1.0/g/com.atlassian.jira.gadgets:"

GADGET_URI = {
    "filter-results": _G + "filter-results-gadget/gadgets/filter-results-gadget.xml",
    "pie": _G + "pie-chart-gadget/gadgets/piechart-gadget.xml",
    "two-dim": _G + "two-dimensional-stats-gadget/gadgets/"
                    "two-dimensional-stats-gadget.xml",
    "stats": _G + "stats-gadget/gadgets/stats-gadget.xml",
    "heat-map": _G + "heat-map-gadget/gadgets/heatmap-gadget.xml",
}

# JSM dashboard items are addressed by moduleKey rather than uri.
GADGET_MODULE = {
    "filter-count": "com.atlassian.servicedesk.dashboard-items-plugin:"
                    "filter-count-dashboard-item",
}


def gadget(title, kind, filter_name, config, row, column, color="blue"):
    """One declared gadget. `title` is the identity key - it MUST be unique."""
    return {"title": title, "kind": kind, "filter": filter_name,
            "config": dict(config), "row": row, "column": column, "color": color}


def _plan_type_key(p):
    kind = p["kind"]
    if kind in GADGET_URI:
        return ("uri", GADGET_URI[kind])
    if kind in GADGET_MODULE:
        return ("moduleKey", GADGET_MODULE[kind])
    raise RuntimeError("unknown gadget kind: %s" % kind)


def _live_type_key(g):
    if g.get("uri"):
        return ("uri", g["uri"])
    return ("moduleKey", g.get("moduleKey") or "")


def validate_stat_types(j, plan):
    """Assert every statType we use is one Jira actually accepts.

    A wrong value is NOT rejected by the config PUT - the property round-trips
    happily and the gadget then renders broken, which is the worst kind of
    failure because the run looks green. The live vocabulary is plural for system
    fields ("priorities", never "priority") and does not match JQL field names.
    """
    live = j.try_get("/rest/gadget/1.0/statTypes")
    if not live:
        log("  ~ /rest/gadget/1.0/statTypes unavailable - statTypes NOT validated")
        return
    stats = live.get("stats") if isinstance(live, dict) else live
    valid = set(str(v.get("value")) for v in stats)
    bad = []
    for p in plan:
        for key in ("statType", "xstattype", "ystattype"):
            val = p["config"].get(key)
            if val is not None and val not in valid:
                bad.append("%s: %s=%r is not a valid stat type"
                           % (p["title"], key, val))
    if bad:
        for b in bad:
            log("  !! " + b)
        sys.exit("ABORTING - a gadget would have rendered broken. Fix the plan.")
    log("  statTypes validated against %d live values" % len(valid))


# ---------------------------------------------------------------------------
# live reads
# ---------------------------------------------------------------------------

def read_gadget_config(j, did, gid):
    """{} when the gadget has no config property (that endpoint 404s - verified)."""
    prop = j.try_get("/rest/api/3/dashboard/%s/items/%s/properties/config"
                     % (did, gid))
    if not prop:
        return {}
    value = prop.get("value")
    return value if isinstance(value, dict) else {}


def list_gadgets(j, did):
    """Live gadgets, oldest id first. Unpaginated by the API's own design."""
    raw = j.try_get("/rest/api/3/dashboard/%s/gadget" % did, {}) or {}
    out = []
    for g in raw.get("gadgets", []):
        gid = str(g["id"])           # the API hands back an int here
        pos = g.get("position") or {}
        out.append({
            "id": gid,
            "uri": g.get("uri"),
            "moduleKey": g.get("moduleKey"),
            "color": g.get("color"),
            "title": g.get("title"),
            "row": pos.get("row"),
            "column": pos.get("column"),
            "config": read_gadget_config(j, did, gid),
        })
    out.sort(key=lambda x: int(x["id"]))
    return out


def list_owned_filters(j, account_id):
    """(owned, foreign); owned is name -> {id, jql, description}.

    Paginated properly - the predecessor read a single 100-row page and never
    checked isLast, which is latent at 51 filters and breaks silently past 100.

    Scoped to filters this account OWNS on purpose. filter/search returns every
    filter the account can SEE. Keying a name -> id map off that set lets a
    same-named filter owned by somebody else win the key, after which the run
    either 403s on the PUT (and the old code swallowed that) or succeeds and
    silently rewrites a colleague's saved search.
    """
    owned, foreign = {}, {}
    start, guard = 0, 0
    while True:
        guard += 1
        if guard > 100:
            raise RuntimeError("filter/search did not terminate after 100 pages")
        page = j.try_get("/rest/api/3/filter/search?maxResults=100&startAt=%d"
                         "&expand=jql,description,owner" % start, {}) or {}
        values = page.get("values", [])
        for f in values:
            owner = (f.get("owner") or {}).get("accountId")
            if owner == account_id:
                owned[f["name"]] = {"id": str(f["id"]),
                                    "jql": f.get("jql") or "",
                                    "description": f.get("description") or ""}
            else:
                foreign[f["name"]] = owner
        if page.get("isLast", True) or not values:
            break
        start += len(values)
    return owned, foreign


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------

def reconcile_filters(w, plan, account_id, share=True):
    """plan: [(name, jql, description)] -> (name -> id, [failure strings]).

    The caller MUST treat a non-empty failure list as fatal before touching the
    dashboard. Binding gadgets against a partial filter map is precisely how a
    blank gadget gets created.
    """
    names = [p[0] for p in plan]
    dupes = sorted(set(n for n in names if names.count(n) > 1))
    if dupes:
        raise RuntimeError("plan has duplicate filter names: " + ", ".join(dupes))

    owned, foreign = list_owned_filters(w.j, account_id)
    ids, failures = {}, []
    created = updated = unchanged = 0

    for name, jql, desc in plan:
        if name in owned:
            cur = owned[name]
            ids[name] = cur["id"]
            drift = []
            if normalize_jql(cur["jql"]) != normalize_jql(jql):
                drift.append("jql")
            if norm_text(cur["description"]) != norm_text(desc):
                drift.append("description")
            if not drift:
                unchanged += 1
                log("  = %s" % name)
                continue
            try:
                # sharePermissions deliberately OMITTED on update: verified that a
                # name/jql/description PUT preserves them, re-sending risks
                # stacking duplicate grants, and the value round-trips under a
                # different name so it cannot be diffed reliably anyway.
                w.put("/rest/api/3/filter/" + cur["id"],
                      {"name": name, "jql": jql, "description": desc})
                updated += 1
                log("  ~ %s (changed: %s)" % (name, ", ".join(drift)))
            except RuntimeError as e:
                # NEVER swallow this. The predecessor's bare `except: pass` is why
                # stale JQL could sit on a filter indefinitely while the run
                # printed a reassuring "=".
                failures.append("%s: update failed - %s" % (name, str(e)[:200]))
                log("  ! %s: %s" % (name, str(e)[:200]))
            continue

        if name in foreign:
            failures.append(
                "%s: a filter with this name is owned by account %s; refusing to "
                "create a duplicate or edit theirs" % (name, foreign[name]))
            log("  ! %s: name taken by another account" % name)
            continue

        body = {"name": name, "jql": jql, "description": desc, "favourite": True}
        if share:
            body["sharePermissions"] = [{"type": "authenticated"}]
        try:
            res = w.post("/rest/api/3/filter", body)
            ids[name] = str(res["id"])
            created += 1
            log("  + %s" % name)
        except RuntimeError as e:
            failures.append("%s: create failed - %s" % (name, str(e)[:200]))
            log("  ! %s: %s" % (name, str(e)[:200]))

    log("  filters: %d created, %d updated, %d unchanged, %d failed"
        % (created, updated, unchanged, len(failures)))
    return ids, failures


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

def ensure_dashboard(w, name, description):
    """Find-by-name or create. Paginated, unlike the single 50-row page before."""
    start, guard = 0, 0
    while True:
        guard += 1
        if guard > 100:
            raise RuntimeError("dashboard/search did not terminate")
        page = w.j.try_get("/rest/api/3/dashboard/search?maxResults=50&startAt=%d"
                           % start, {}) or {}
        values = page.get("values", [])
        for d in values:
            if d["name"] == name:
                log("  = dashboard exists (%s)" % d["id"])
                return str(d["id"]), False
        if page.get("isLast", True) or not values:
            break
        start += len(values)
    d = w.post("/rest/api/3/dashboard",
               {"name": name, "description": description,
                "sharePermissions": [{"type": "authenticated"}]})
    log("  + dashboard created (%s)" % d["id"])
    return str(d["id"]), True


# ---------------------------------------------------------------------------
# the matcher
# ---------------------------------------------------------------------------

def match_gadgets(plan, live):
    """Three-pass matcher -> (pairs, to_create, extras).

    `plan` entries must already carry `_want_filter_id` ("filter-NNNNN").

    Pass A - EXACT TITLE. Titles are the declared identity of a gadget: we set
             them on POST and they come back on GET. On any dashboard this module
             has built before, every gadget matches here and the run is a no-op.
    Pass B - SAME TYPE + SAME BOUND filterId. Adopts gadgets built by an older
             plan whose title has since been reworded, so a rename re-labels the
             existing gadget instead of stacking a duplicate beside it.
    Pass C - SAME TYPE + NO filterId AT ALL. Adopts the blank gadgets a
             blind-append run left behind, rather than adding a fresh one next to
             each corpse. `live` is sorted oldest-id-first, so this is
             deterministic across runs.

    Anything unmatched on either side is REPORTED, never silently changed.
    Position is deliberately not a matching signal: Jira reflows rows on POST
    collision, so position carries no identity.
    """
    pairs = []
    remaining = list(live)

    def take(candidates, pred):
        leftover = []
        for item in candidates:
            hit = None
            for g in remaining:
                if pred(item, g):
                    hit = g
                    break
            if hit is None:
                leftover.append(item)
            else:
                remaining.remove(hit)
                pairs.append((item, hit))
        return leftover

    unplaced = take(list(plan),
                    lambda p, g: g.get("title") is not None
                    and g["title"] == p["title"])
    unplaced = take(unplaced,
                    lambda p, g: _live_type_key(g) == _plan_type_key(p)
                    and g["config"].get("filterId") == p["_want_filter_id"])
    unplaced = take(unplaced,
                    lambda p, g: _live_type_key(g) == _plan_type_key(p)
                    and not g["config"].get("filterId"))
    return pairs, unplaced, remaining


# ---------------------------------------------------------------------------
# the gadget reconciler
# ---------------------------------------------------------------------------

def reconcile_gadgets(w, did, plan, filter_ids, extras="keep", relayout=False):
    """Reconcile the gadgets on dashboard `did` against `plan`.

    extras: what to do with live gadgets the plan does not claim.
      "keep"   - report only. THE DEFAULT. Never destructive.
      "delete" - remove them. Opt-in cleanup for a dashboard polluted by an older
                 blind-append run. Requires an explicit flag.
    relayout: also PUT position. Off by default because position writes are not
      verified on this instance (only title writes are), and a wrong guess would
      scramble a dashboard that currently renders correctly.

    Returns a summary dict. Never raises for a single gadget failure; the caller
    decides what a non-empty `failed` list means.
    """
    titles = [p["title"] for p in plan]
    dupes = sorted(set(t for t in titles if titles.count(t) > 1))
    if dupes:
        raise RuntimeError("gadget plan has duplicate titles (title is the "
                           "identity key): " + ", ".join(dupes))

    # RULE 3: resolve every filter BEFORE any write. A plan referencing a filter
    # we do not have is a plan that would produce blank gadgets, so refuse the
    # whole run rather than build a partly-dead dashboard.
    missing = [p["title"] + " -> " + p["filter"]
               for p in plan if not filter_ids.get(p["filter"])]
    if missing:
        for m in missing:
            log("  !! unresolved filter for gadget: " + m)
        return {"aborted": "unresolved filters", "missing": missing,
                "created": [], "updated": [], "unchanged": [],
                "failed": missing, "extras": [], "gadget_ids": {}}

    for p in plan:
        p["_want_filter_id"] = "filter-" + str(filter_ids[p["filter"]])

    validate_stat_types(w.j, plan)

    live = list_gadgets(w.j, did)
    log("  %d gadget(s) live on dashboard %s" % (len(live), did))

    pairs, to_create, extra_gadgets = match_gadgets(plan, live)
    log("  matched %d, to create %d, unclaimed %d"
        % (len(pairs), len(to_create), len(extra_gadgets)))

    created, updated, unchanged, failed = [], [], [], []

    # --- create only the remainder -----------------------------------------
    for p in to_create:
        payload = {"color": p["color"], "title": p["title"],
                   "position": {"row": p["row"], "column": p["column"]}}
        kind_key, kind_val = _plan_type_key(p)
        payload[kind_key] = kind_val
        try:
            res = w.post("/rest/api/3/dashboard/%s/gadget" % did, payload)
            new = {"id": str(res["id"]), "uri": payload.get("uri"),
                   "moduleKey": payload.get("moduleKey"), "color": p["color"],
                   "title": p["title"], "row": None, "column": None, "config": {}}
            pairs.append((p, new))
            created.append(p["title"])
            log("  + %s [%s] (gadget %s)" % (p["title"], p["kind"], new["id"]))
        except RuntimeError as e:
            failed.append("%s: add failed - %s" % (p["title"], str(e)[:200]))
            log("  ! add %s: %s" % (p["title"], str(e)[:200]))

    # --- reconcile config + title on everything we own ----------------------
    for p, g in pairs:
        gid = g["id"]
        want_cfg = dict(p["config"])
        want_cfg["filterId"] = p["_want_filter_id"]

        # Compare only the keys we declare. A key the browser UI added on its own
        # is left alone rather than stomped - we own our keys, not the whole blob.
        have = g["config"] or {}
        cfg_drift = [k for k, v in want_cfg.items() if str(have.get(k)) != str(v)]

        if cfg_drift:
            merged = dict(have)
            merged.update(want_cfg)
            try:
                w.put("/rest/api/3/dashboard/%s/items/%s/properties/config"
                      % (did, gid), merged)
                if not w.dry:
                    back = read_gadget_config(w.j, did, gid)
                    if back.get("filterId") != want_cfg["filterId"]:
                        raise RuntimeError("config did not round-trip")
                updated.append("%s (config: %s)" % (p["title"], ", ".join(cfg_drift)))
                log("  ~ %s config -> %s" % (p["title"], want_cfg["filterId"]))
            except RuntimeError as e:
                failed.append("%s: config failed - %s" % (p["title"], str(e)[:200]))
                log("  ! %s config: %s" % (p["title"], str(e)[:200]))
        elif p["title"] not in created:
            unchanged.append(p["title"])
            log("  = %s" % p["title"])

        meta = {}
        if g.get("title") != p["title"]:
            meta["title"] = p["title"]
        if g.get("color") != p["color"]:
            meta["color"] = p["color"]
        if relayout:
            meta["position"] = {"row": p["row"], "column": p["column"]}
        if meta:
            try:
                w.put("/rest/api/3/dashboard/%s/gadget/%s" % (did, gid), meta)
                log("  ~ %s meta %s" % (p["title"], sorted(meta.keys())))
            except RuntimeError as e:
                # Cosmetic. Binding is what matters, so never fail the run here.
                log("  ~ %s meta not applied: %s" % (p["title"], str(e)[:150]))

    # --- extras -------------------------------------------------------------
    extra_desc = ["%s (id %s, title %r, filter %s)"
                  % (_live_type_key(g)[1][-42:], g["id"], g.get("title"),
                     g["config"].get("filterId")) for g in extra_gadgets]
    if extra_gadgets:
        log("  %d gadget(s) on this dashboard are not in the plan:"
            % len(extra_gadgets))
        for d in extra_desc:
            log("      " + d)
        if extras == "delete":
            for g in extra_gadgets:
                try:
                    w.delete("/rest/api/3/dashboard/%s/gadget/%s" % (did, g["id"]))
                    log("  - removed unclaimed gadget %s" % g["id"])
                except RuntimeError as e:
                    log("  ! remove %s: %s" % (g["id"], str(e)[:150]))
        else:
            log("  left in place (--extras=delete to remove them)")

    return {"created": created, "updated": updated, "unchanged": unchanged,
            "failed": failed, "extras": extra_desc,
            "gadget_ids": dict((p["title"], g["id"]) for p, g in pairs)}


# ---------------------------------------------------------------------------
# JSM agent queues
# ---------------------------------------------------------------------------

# Stock queues shipped by the ITIL template. Never write to these.
STOCK_QUEUE_NAMES = frozenset([
    "All open", "Assigned to me", "Unassigned work items",
])


def list_queues(j, service_desk_id):
    """name -> {id, jql, fields}. Reads go through servicedeskapi because the
    internal endpoint used for writes answers 405 on GET."""
    out = {}
    start, guard = 0, 0
    while True:
        guard += 1
        if guard > 100:
            raise RuntimeError("queue listing did not terminate")
        page = j.try_get("/rest/servicedeskapi/servicedesk/%s/queue?start=%d&limit=50"
                         % (service_desk_id, start), {}) or {}
        values = page.get("values", [])
        for q in values:
            out[q["name"]] = {"id": str(q["id"]), "jql": q.get("jql") or "",
                              "fields": list(q.get("fields") or [])}
        if page.get("isLastPage", True) or not values:
            break
        start += len(values)
    return out


def reconcile_queues(w, project_key, service_desk_id, plan, columns):
    """plan: [(name, jql)] -> (name -> id, [failures]).

    NO DELETE EXISTS over REST on this instance, so a botched name is PERMANENT.
    Everything here is check-then-PUT, never create-then-fix, and any queue that
    is not in the plan is reported as an orphan for a human to deal with.
    """
    names = [p[0] for p in plan]
    dupes = sorted(set(n for n in names if names.count(n) > 1))
    if dupes:
        raise RuntimeError("queue plan has duplicate names: " + ", ".join(dupes))
    clash = sorted(set(names) & STOCK_QUEUE_NAMES)
    if clash:
        raise RuntimeError("queue plan collides with template queues (refusing to "
                           "overwrite): " + ", ".join(clash))

    live = list_queues(w.j, service_desk_id)
    log("  %d queue(s) on service desk %s" % (len(live), service_desk_id))

    ids, failures = {}, []
    created = updated = unchanged = 0

    for name, jql in plan:
        body = {"name": name, "jql": jql, "columns": list(columns)}
        if name in live:
            cur = live[name]
            ids[name] = cur["id"]
            have_jql = strip_project_prefix(cur["jql"], project_key)
            drift = []
            if normalize_jql(have_jql) != normalize_jql(jql):
                drift.append("jql")
            if list(cur["fields"]) != list(columns):
                drift.append("columns")
            if not drift:
                unchanged += 1
                log("  = %s" % name)
                continue
            try:
                w.put("/rest/servicedesk/1/servicedesk/%s/queues/%s"
                      % (project_key, cur["id"]), body)
                updated += 1
                log("  ~ %s (changed: %s)" % (name, ", ".join(drift)))
            except RuntimeError as e:
                failures.append("%s: update failed - %s" % (name, str(e)[:200]))
                log("  ! %s: %s" % (name, str(e)[:200]))
            continue
        try:
            res = w.post("/rest/servicedesk/1/servicedesk/%s/queues" % project_key,
                         body)
            ids[name] = str(res["id"])
            created += 1
            log("  + %s (id %s) - PERMANENT, no REST delete exists"
                % (name, res["id"]))
        except RuntimeError as e:
            failures.append("%s: create failed - %s" % (name, str(e)[:200]))
            log("  ! %s: %s" % (name, str(e)[:200]))

    # Orphans cannot be deleted, so the only honest thing is to say so, loudly.
    planned = set(names)
    orphans = sorted(n for n in live
                     if n not in planned and n not in STOCK_QUEUE_NAMES)
    if orphans:
        log("  %d unclaimed queue(s) - NOT in the plan and NOT deletable over "
            "REST; rename or hide them in the UI:" % len(orphans))
        for n in orphans:
            log("      %s (id %s)" % (n, live[n]["id"]))

    log("  queues: %d created, %d updated, %d unchanged, %d failed, %d orphaned"
        % (created, updated, unchanged, len(failures), len(orphans)))
    return ids, failures
