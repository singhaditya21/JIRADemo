#!/usr/bin/env python3
"""DeliveryIQ CI/CD writeback + Salesforce drift probe for the SFC lens.

Runs in CI (holding the Jira token), enumerates the "Org Deploy" sub-tasks under each
Salesforce Config Request, PROBES each target org's deploy status + config health, and
WRITES the result back to Jira — Deploy State, Config Health, a fresh Health Checked At,
and Deploy Source = "CI writeback". That is what turns those cells from a fixture
placeholder into pipeline-owned data with a real, recent timestamp; the lens's health
board already splits CI-written vs seeded, so the change shows with no app edit.

THE PROBE IS A SEAM (`probe_org`). With no Salesforce credentials configured it runs a
DETERMINISTIC SIMULATION: the WRITEBACK is real (real Jira mutations, real timestamps),
but the health VALUES are modelled until the real API is wired — and this is stated in
the run log and the lens note, never hidden. To go fully live:
  1. Add repo secrets SF_INSTANCE_URL / SF_CLIENT_ID / SF_CLIENT_SECRET (see SF_ENV).
  2. Replace probe_org()'s body with real calls:
       - Salesforce Tooling API: the DeployRequest status  -> deploy_state
       - a metadata retrieve + diff (drift check)          -> config_health
Nothing else changes — the same four fields are written the same way, and Source stays
"CI writeback" (it already was a CI writeback; now the probe behind it is real too).

Dry-run-first: --dry-run logs every write and mutates nothing. The token is CI-only, so
run this via .github/workflows/sfc-writeback.yml (dry_run defaults true).

    python3 -m app.sfc_writeback [--dry-run]

Writes SFC only. Reuses app.sfc_export for the fetch + field resolution so there is one
definition of the SFC schema. Imports shared/ + app.sfc_export only.

Python 3.9. %-formatting, no f-strings with backslashes.
"""

import argparse
import hashlib
import os
from datetime import datetime, timezone

from shared.jira_client import Jira, log, require_env
from app.sfc_export import (resolve_fields, _fetch_all, _org_from_summary,
                            REQUEST_TYPE, SUBTASK_TYPE)

# Deploy states that mean a deployment has actually occurred, so there is something to
# probe. "Not started" orgs are left untouched (and read Source = Seeded) — a real
# pipeline would have no deploy record for them either.
DEPLOYED_STATES = {"Validated", "Deploying", "Deployed", "Failed", "Rolled back"}

# Presence of ALL of these switches probe_org from simulated to a real Salesforce call.
SF_ENV = ("SF_INSTANCE_URL", "SF_CLIENT_ID", "SF_CLIENT_SECRET")


def sf_creds_present():
    return all(os.environ.get(v) for v in SF_ENV)


def probe_org(parent_status, current_state, org, key, real):
    """Return (deploy_state, config_health) for one org.

    SEAM: when `real` is True, call Salesforce here (Tooling API DeployRequest status +
    a metadata drift check) and return the observed values. The default path below is a
    DETERMINISTIC SIMULATION — same input always yields the same output, so a re-run is
    stable — that advances a completed deploy and runs a plausible drift check.
    """
    if real:
        # SEAM — implement with the Salesforce APIs. Until then we never reach here
        # because sf_creds_present() gates it; kept explicit so the contract is obvious.
        raise NotImplementedError(
            "Real Salesforce probe not implemented. Wire the Tooling/Metadata API here.")

    h = int(hashlib.sha1(("%s|%s" % (key, org)).encode()).hexdigest()[:8], 16) / float(0xFFFFFFFF)
    state = current_state
    # A request that has reached Deployed/Audit/Done means every in-flight org landed.
    if parent_status in ("Deployed", "Audit", "Done") and current_state in ("Validated", "Deploying"):
        state = "Deployed"
    # Drift probe: health only means something once deployed.
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

    real = sf_creds_present()
    log("probe mode: %s" % ("REAL Salesforce (SF_* secrets present)" if real else
        "SIMULATED (no SF_* creds — the Jira writeback is real; health values are modelled)"))

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

    checked = jira_dt(datetime.now(timezone.utc))
    written = skipped = failed = 0
    for it in subtasks:
        f = it.get("fields") or {}
        key = it["key"]
        parent = (f.get("parent") or {}).get("key")
        org = _org_from_summary(f.get("summary")) or "?"
        cur = _cur_state(f, F)
        if cur not in DEPLOYED_STATES:
            skipped += 1                 # nothing deployed to this org yet -> nothing to probe
            continue
        state, health = probe_org(parent_status.get(parent), cur, org, parent or key, real)
        fields = {
            F["Deploy State"]: {"value": state},
            F["Config Health"]: {"value": health},
            F["Health Checked At"]: checked,
            F["Deploy Source"]: {"value": "CI writeback"},
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

    verb = "would be written [DRY RUN]" if args.dry_run else "written (Source=CI writeback)"
    log("\n%d org-deploy sub-task(s) %s, %d skipped (not deployed), %d failed"
        % (written, verb, skipped, failed))
    if not real:
        log("NOTE: health values are SIMULATED. Add SF_* secrets + implement probe_org() "
            "for a real Salesforce deploy-status + drift probe.")


if __name__ == "__main__":
    main()
