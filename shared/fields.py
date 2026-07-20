#!/usr/bin/env python3
"""Resolve tower field NAMES to Jira customfield ids at runtime.

WHY THIS MODULE EXISTS
----------------------
The application layer has to run against ANY correctly-configured instance - OPS,
ITSM, or a fresh one - with no build artifact on disk. Before this module, the SLA
engine opened jira_config/state/.build_state.json to learn its customfield ids,
which meant it only ran on a machine that happened to have the configurator's
output sitting next to it. The contract between the configurator and the app is
the field NAME. Ids are an implementation detail of one instance.

The trade this makes explicit: renaming a field in the Jira UI now breaks the app
loudly at startup instead of silently returning zeros. That is the point. Do not
"fix" it by reintroducing the state file.

DUPLICATE NAMES ARE REAL, NOT HYPOTHETICAL
------------------------------------------
This site carries two custom fields called "Urgency":

    customfield_10044  select, description "OPS tower schema - Urgency"  <- ours
    customfield_10071  select, description ""                            <- JSM ITIL

The obvious one-liner

    {f["name"]: f["id"] for f in jira.get("/rest/api/3/field") if f.get("custom")}

is last-one-wins over a response with no defined ordering. On this instance it
happens to land on the right one. That is luck. A resolver that guesses here
writes tower data into a template field nobody reads. So: ambiguity is resolved
deliberately, or it is an error - never a silent pick.

Two endpoints are involved, deliberately:

  GET /rest/api/3/field          one unpaginated call, every custom field, but it
                                 returns description: null for ALL of them
                                 (verified - do not build a tie-break on it)
  GET /rest/api/3/field/search   paginated, and DOES carry descriptions. Called
                                 ONLY for a name that turned out ambiguous, so
                                 the common path stays at a single HTTP call.

Project-scoped disambiguation was tried and rejected: both Urgency fields have a
global context, so contexts cannot separate them. Do not reintroduce it.

Python 3.9. %-formatting throughout, no f-strings with backslashes.
"""

import os
import re
import threading
import urllib.parse

from shared import domain

# Jira custom-field type keys.
#
# These sit in shared/ rather than jira_config/jira_schema.py because shared/ may
# not import jira_config, and this module is the one place in shared/ that has to
# know Jira wire formats - it is talking to /rest/api/3/field. jira_schema.py
# imports them FROM here so there is exactly one definition and no drift.
SELECT_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:select"
TEXT_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:textfield"
AREA_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:textarea"
DATE_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:datetime"

# RLock, not Lock: _pick() runs inside the lock and issues further HTTP calls.
# The SLA engine fans out over a ThreadPoolExecutor; resolve() is called once on
# the main thread before the pool starts, and the lock makes a stray concurrent
# call safe rather than merely unlikely.
_LOCK = threading.RLock()
_CACHE = {}          # site url -> FieldMap


class FieldResolutionError(RuntimeError):
    """A field could not be resolved to exactly one customfield id."""


def _expected_types():
    """Field name -> the Jira custom type key the model says it should have."""
    exp = {}
    for name in domain.SELECT_FIELDS:
        exp[name] = SELECT_TYPE
    for name, kind in domain.TEXT_FIELDS.items():
        exp[name] = AREA_TYPE if kind == "long" else TEXT_TYPE
    for name in domain.DATE_FIELDS:
        exp[name] = DATE_TYPE
    return exp


EXPECTED_TYPES = _expected_types()
ALL_FIELD_NAMES = tuple(sorted(EXPECTED_TYPES))


def env_key(name):
    """Env var that pins one field: Urgency -> JIRA_FIELD_ID__URGENCY."""
    slug = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return "JIRA_FIELD_ID__" + slug


class FieldMap(dict):
    """name -> customfield id, plus JQL rendering that is safe under ambiguity.

    Subclasses dict on purpose: call sites written as F["Reported At"] against the
    old state-file dict keep working with no edit at all.
    """

    def __init__(self, mapping, ambiguous=None, site=""):
        dict.__init__(self, mapping)
        # name -> [rejected candidate ids], for names that had duplicates
        self.ambiguous = dict(ambiguous or {})
        self.site = site

    def id(self, name):
        if name not in self:
            raise FieldResolutionError(
                "field %r was not resolved on %s; resolved names: %s"
                % (name, self.site or "this instance", ", ".join(sorted(self))))
        return self[name]

    def cf(self, name):
        """cf[10057] form - unambiguous whatever the display name says."""
        return "cf[" + self.id(name).split("_")[-1] + "]"

    def jql(self, name):
        """How to name this field inside JQL.

        Unambiguous -> the quoted name, because a human reads these filters.
        Ambiguous    -> cf[id], because Jira's tie-break between two identically
                        named fields is undocumented and not portable across
                        instances even if it happens to work here.
        """
        if name in self.ambiguous:
            return self.cf(name)
        return '"' + name + '"'

    def warnings(self):
        out = []
        for name in sorted(self.ambiguous):
            out.append(
                "field %r is ambiguous on this instance: using %s, ignoring %s "
                "(its JQL will use the cf[] form). Pin it with %s=<id> to be explicit."
                % (name, self[name], ", ".join(self.ambiguous[name]), env_key(name)))
        return out


def _fetch_all(jira):
    return [f for f in jira.get("/rest/api/3/field") if f.get("custom")]


def _descriptions_for(jira, name):
    """id -> description, for custom fields named exactly `name`.

    GET /rest/api/3/field does NOT return descriptions - verified, every tower
    field comes back with description null. /field/search does. This is only
    called for an ambiguous name, so the common path stays at one HTTP call.

    The `query` parameter is fuzzy and matches descriptions too, so results are
    filtered to an exact name match. Unlike /field, this endpoint IS paginated.
    """
    out = {}
    start, guard = 0, 0
    while True:
        guard += 1
        if guard > 100:
            raise FieldResolutionError("field/search did not terminate for %r" % name)
        page = jira.try_get(
            "/rest/api/3/field/search?type=custom&maxResults=50&startAt=%d&query=%s"
            % (start, urllib.parse.quote(name)), {}) or {}
        values = page.get("values", [])
        for f in values:
            if f.get("name") == name:
                out[f["id"]] = f.get("description") or ""
        if page.get("isLast", True) or not values:
            break
        start += len(values)
    return out


def _pick(jira, name, candidates, expected):
    """Choose one field dict from `candidates`, all sharing this exact name.

    Returns (chosen_id, [rejected_ids]).
    """
    # 1. An explicit operator override always wins. This is the escape hatch when
    #    two fields are genuinely indistinguishable.
    override = os.environ.get(env_key(name))
    if override:
        ids = [c["id"] for c in candidates]
        if override not in ids:
            raise FieldResolutionError(
                "%s=%s but no custom field with that id is named %r (candidates: %s)"
                % (env_key(name), override, name, ", ".join(ids) or "none"))
        return override, [i for i in ids if i != override]

    if len(candidates) == 1:
        return candidates[0]["id"], []

    # 2. Narrow by the type the model says this field has - but only when that
    #    leaves something behind. "Impact" is a Jira built-in here with a type we
    #    did not choose, and it must still resolve because its name is unique.
    typed = [c for c in candidates
             if (c.get("schema") or {}).get("custom") == expected]
    pool = typed if typed else candidates

    if len(pool) == 1:
        return pool[0]["id"], [c["id"] for c in candidates if c["id"] != pool[0]["id"]]

    # 3. Still tied. Fetch descriptions and prefer the field this schema owns.
    #    jira_config/build.py stamps every field it creates with a description
    #    containing domain.FIELD_DESCRIPTION_TAG. TIE-BREAK ONLY - never a filter.
    descs = _descriptions_for(jira, name)
    tag = domain.FIELD_DESCRIPTION_TAG.lower()
    owned = [c for c in pool if tag in (descs.get(c["id"], "")).lower()]
    if len(owned) == 1:
        return owned[0]["id"], [c["id"] for c in candidates
                                if c["id"] != owned[0]["id"]]

    detail = ", ".join(
        "%s (type=%s, description=%r)"
        % (c["id"], (c.get("schema") or {}).get("custom", "?"),
           descs.get(c["id"], ""))
        for c in sorted(pool, key=lambda c: c["id"]))
    raise FieldResolutionError(
        "field name %r matches %d custom fields on this instance and none of them "
        "can be told apart: %s. Pin the right one with %s=<customfield_id>."
        % (name, len(pool), detail, env_key(name)))


def resolve(jira, names=None, refresh=False):
    """{name: customfield_id}. Cached per process, keyed on the site url.

    Every field the model declares is resolved, even when the caller asked for
    five of them. That is deliberate: it is a preflight. An instance that is
    half-configured should fail on the first line of output, not at ticket 300.

    Raises FieldResolutionError naming EVERY field it could not resolve, not the
    first one - fixing these one error message at a time is miserable.
    """
    site = getattr(jira, "site", "")
    with _LOCK:
        full = None if refresh else _CACHE.get(site)
        if full is None:
            by_name = {}
            for f in _fetch_all(jira):
                by_name.setdefault(f["name"], []).append(f)

            mapping, ambiguous, missing = {}, {}, []
            for name in ALL_FIELD_NAMES:
                cands = by_name.get(name, [])
                if not cands:
                    missing.append(name)
                    continue
                fid, rejected = _pick(jira, name, cands, EXPECTED_TYPES[name])
                mapping[name] = fid
                if rejected:
                    ambiguous[name] = rejected

            if missing:
                raise FieldResolutionError(
                    "%d tower field(s) do not exist on %s: %s. This instance is not "
                    "configured for the tower schema - run the configurator "
                    "(python3 -m jira_config.apply) against it first."
                    % (len(missing), site or "this instance",
                       "; ".join("%s (expected %s)"
                                 % (n, EXPECTED_TYPES[n].rsplit(":", 1)[-1])
                                 for n in missing)))

            full = FieldMap(mapping, ambiguous, site)
            _CACHE[site] = full

    if names is None:
        return full

    subset = {}
    for n in names:
        subset[n] = full.id(n)          # .id() raises a named error if absent
    return FieldMap(subset,
                    dict((k, v) for k, v in full.ambiguous.items() if k in subset),
                    site)


def clear_cache():
    with _LOCK:
        _CACHE.clear()
