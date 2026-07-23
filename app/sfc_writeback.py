#!/usr/bin/env python3
"""DeliveryIQ writeback: maintain the modelled per-org deploy state + config health.

There is NO live Salesforce in this deployment — by design, DeliveryIQ tracks Salesforce
config requests as Jira issues (that was the agreed scope). So per-org deploy state and
config health are MODELLED, not real Salesforce telemetry. This job is the mechanism
that maintains them: it runs in CI (holding the Jira token), enumerates the "Org Deploy"
sub-tasks under each Salesforce Config Request, computes each org's modelled deploy state
+ config health, and WRITES them back to Jira — Deploy State, Config Health, a fresh
Health Checked At, and Deploy Source = "Modelled".

What is real vs. modelled, stated plainly (the lens says the same):
  - REAL: the writeback itself (real Jira mutations), and the Health Checked At timestamp
    it stamps each run — so the health board's freshness/staleness signal is genuine.
  - MODELLED: the deploy-state and config-health VALUES (deploy_health_model()). There is
    no Salesforce to observe; these are illustrative. The Source = "Modelled" badge and
    the lens note make that explicit — it is never dressed up as a live read.

If a real Salesforce org is ever connected, deploy_health_model() is the single seam to
replace with real Tooling/Metadata API calls; write Deploy Source = "CI writeback" then
so the board can distinguish observed data from the model. Nothing else changes.

Run modes (the workflow decides): a MANUAL dispatch defaults to a dry rehearsal
(dry_run=true); the 6-hourly SCHEDULED run APPLIES. To keep that unattended cadence from
churning Jira, a cell is only written when its modelled deploy state or health actually
CHANGED, or when its Health Checked At has gone stale (older than STALE_HOURS) and needs
re-stamping — an unchanged, freshly-checked cell is skipped.

    python3 -m app.sfc_writeback [--dry-run]

Writes SFC only. Reuses app.sfc_export for the fetch + field resolution so there is one
definition of the SFC schema. Imports shared/ + app.sfc_export only.

Python 3.9. %-formatting, no f-strings with backslashes.
"""

import argparse
import hashlib
from datetime import datetime, timezone

from shared.jira_client import Jira, log, require_env
from app.store import parse_dt
from app.sfc_export import (resolve_fields, _fetch_all, _org_from_summary,
                            STALE_HOURS, REQUEST_TYPE, SUBTASK_TYPE)

WRITEBACK_SOURCE = "Modelled"   # no live Salesforce -> values are modelled, labelled so

# Deploy states that mean a deployment has occurred, so there is a health to model.
# "Not started" orgs are left untouched (Source = Seeded) — nothing has shipped there.
DEPLOYED_STATES = {"Validated", "Deploying", "Deployed", "Failed", "Rolled back"}


def deploy_health_model(parent_status, current_state, org, key):
    """Return (deploy_state, config_health) for one org — MODELLED, not observed.

    Deterministic (hash of key|org, no RNG) so a re-run is stable. There is no
    Salesforce to read; this is the illustrative model behind the demo. If a real org
    is ever wired, replace this body with the Salesforce Tooling/Metadata API calls.
    """
    h = int(hashlib.sha1(("%s|%s" % (key, org)).encode()).hexdigest()[:8], 16) / float(0xFFFFFFFF)
    state = current_state
    # A request that has reached Deployed/Audit/Done means every in-flight org landed.
    if parent_status in ("Deployed", "Audit", "Done") and current_state in ("Validated", "Deploying"):
        state = "Deployed"
    # Health only means something once deployed.
    if state == "Deployed":
        health = "Healthy" if h < 0.72 else "Degraded" if h < 0.92 else "Failing"
    elif state in ("Failed", "Rolled back"):
        health = "Failing"
    else:
        health = "Unknown"
    return state, health


def jira_dt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _cur_state(f, F):
    v = f.get(F["Deploy State"])
    return v.get("value") if isinstance(v, dict) else None


def _sel(f, F, name):
    v = f.get(F[name]) if name in F else None
    return v.get("value") if isinstance(v, dict) else None


def _stamp_age_h(f, F, now):
    """Hours since Health Checked At, or None if never stamped."""
    raw = f.get(F["Health Checked At"]) if "Health Checked At" in F else None
    if not raw:
        return None
    try:
        return (now - parse_dt(raw)).total_seconds() / 3600.0
    except (TypeError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="app.sfc_writeback")
    ap.add_argument("--dry-run", action="store_true",
                    help="log every write without issuing it")
    args = ap.parse_args(argv)

    require_env()
    j = Jira()
    F = resolve_fields(j)
    need = ["Deploy State", "Config Health", "Health Checked At", "Deploy Source"]
    missing = [n for n in need if n not in F]
    if missing:
        raise SystemExit("SFC not provisioned — missing fields: %s. Run "
                         "jira_config.sfc_build first." % ", ".join(missing))

    log("no live Salesforce — deploy state & config health are MODELLED (the writeback "
        "to Jira and the Health Checked At timestamp are real; the values are illustrative)")

    raw = _fetch_all(j, F)
    parent_status, subtasks = {}, []
    for it in raw:
        f = it.get("fields") or {}
        itype = (f.get("issuetype") or {}).get("name")
        if itype == REQUEST_TYPE:
            parent_status[it["key"]] = (f.get("status") or {}).get("name")
        elif itype == SUBTASK_TYPE:
            subtasks.append(it)
    log("SFC: %d requests, %d Org Deploy sub-tasks" % (len(parent_status), len(subtasks)))

    now = datetime.now(timezone.utc)
    checked = jira_dt(now)
    written = skipped = unchanged = failed = 0
    for it in subtasks:
        f = it.get("fields") or {}
        key = it["key"]
        parent = (f.get("parent") or {}).get("key")
        org = _org_from_summary(f.get("summary")) or "?"
        cur = _cur_state(f, F)
        if cur not in DEPLOYED_STATES:
            skipped += 1                 # nothing shipped to this org yet -> nothing to model
            continue
        state, health = deploy_health_model(parent_status.get(parent), cur, org, parent or key)

        # Only write when something actually MOVED, or when the stamp has gone stale and
        # needs refreshing. Without this the 6-hourly cron rewrote every cell 4x a day —
        # pure churn in each issue's history for an identical value.
        age_h = _stamp_age_h(f, F, now)
        same = (state == cur and health == _sel(f, F, "Config Health")
                and _sel(f, F, "Deploy Source") == WRITEBACK_SOURCE)
        fresh = age_h is not None and age_h <= STALE_HOURS
        if same and fresh:
            unchanged += 1
            continue

        fields = {
            F["Deploy State"]: {"value": state},
            F["Config Health"]: {"value": health},
            F["Health Checked At"]: checked,
            F["Deploy Source"]: {"value": WRITEBACK_SOURCE},
        }
        if args.dry_run:
            log("  [dry] %s (%s): %s / %s @ %s" % (key, org, state, health, checked))
            written += 1
            continue
        try:
            j.put("/rest/api/3/issue/%s" % key, {"fields": fields})
            written += 1
        except RuntimeError as e:
            failed += 1
            log("  ! %s: %s" % (key, str(e)[:140]))

    log("  %d unchanged & fresh (skipped to avoid churn; re-stamped only past %dh)"
        % (unchanged, STALE_HOURS))
    verb = ("would be written [DRY RUN]" if args.dry_run
            else "written (Source=%s)" % WRITEBACK_SOURCE)
    log("\n%d org-deploy sub-task(s) %s, %d skipped (not deployed), %d failed"
        % (written, verb, skipped, failed))
    log("NOTE: deploy state & config health are MODELLED (no live Salesforce). The Health "
        "Checked At stamp is real, so the health board's staleness signal is genuine.")


if __name__ == "__main__":
    main()
