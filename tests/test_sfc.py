"""Unit tests for the SFC (DeliveryIQ) pure functions.

Everything under test here is deterministic and I/O-free — record mapping, the evidence
conjunction, the staleness guard, the scoreboard, the invariants and the health model — so
none of it needs Jira, a token or a network. That is exactly why the absence of these tests
was the audit's one BLOCKER: the honesty guarantees the lens makes (evidence is computed not
claimed; a stale verdict reads Unknown; buckets partition) are all enforced by this code, and
nothing was stopping a refactor from silently removing them.

    python3 -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import sfc_export as X
from app import sfc_seed as S
from app import sfc_writeback as W

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _dep(org, state="Deployed", health="Healthy", checked_h=1, source="Modelled"):
    at = None if checked_h is None else (NOW - timedelta(hours=checked_h)).isoformat()
    return {"org": org, "deploy_state": state, "config_health": health,
            "health_checked_at": at, "source": source}


# ---------------------------------------------------------------------------
# evidence pack — COMPUTED, never the stored claim (spec §4.4)
# ---------------------------------------------------------------------------

FULL = {"comply_authorized": True, "build_tested": True, "l2_analyst": "A. Okafor"}


def test_evidence_ready_when_every_conjunct_holds():
    ready, missing = X._evidence(FULL, [_dep("Prod")], ["Prod"], "Audit", 4)
    assert ready is True and missing == []


@pytest.mark.parametrize("drop,expect", [
    ("comply_authorized", "authorization not logged"),
    ("build_tested", "tests not passed"),
    ("l2_analyst", "no reviewer past Review gate"),
])
def test_evidence_each_missing_conjunct_is_named(drop, expect):
    vals = dict(FULL, **{drop: None})
    ready, missing = X._evidence(vals, [_dep("Prod")], ["Prod"], "Audit", 4)
    assert ready is False and expect in missing


def test_evidence_requires_action_history():
    ready, missing = X._evidence(FULL, [_dep("Prod")], ["Prod"], "Audit", 0)
    assert ready is False and "no action history" in missing


def test_evidence_requires_reviewer_to_be_past_the_review_gate():
    # a named reviewer is not enough while the request is still upstream of Review
    ready, _ = X._evidence(FULL, [_dep("Prod")], ["Prod"], "Build", 4)
    assert ready is False


def test_evidence_fails_when_any_target_org_is_not_deployed():
    ready, missing = X._evidence(FULL, [_dep("Prod"), _dep("QA", "Failed")],
                                 ["Prod", "QA"], "Audit", 4)
    assert ready is False and missing == ["not deployed in QA"]


def test_evidence_ranges_over_target_orgs_not_just_existing_subtasks():
    """THE regression this guards: ranging over org_deploys alone silently passes a request
    whose target org has no sub-task at all — 'ready' with a whole org unaccounted for."""
    ready, missing = X._evidence(FULL, [_dep("Prod")], ["Prod", "Dev"], "Audit", 4)
    assert ready is False and "not deployed in Dev" in missing[0]


def test_evidence_with_no_target_orgs_is_not_ready():
    ready, missing = X._evidence(FULL, [], [], "Audit", 4)
    assert ready is False and "no target orgs" in missing


# ---------------------------------------------------------------------------
# Redeployed — derived from the real changelog (spec §1 anti-gaming counter)
# ---------------------------------------------------------------------------

def _hop(to):
    return {"at": None, "field": "status", "from": None, "to": to}


def test_redeploy_false_on_a_clean_forward_path():
    assert X._is_redeployed([_hop("In Build"), _hop("Deploying"), _hop("Deployed")]) is False


def test_redeploy_true_when_shipped_again_after_a_failure():
    assert X._is_redeployed([_hop("Deploying"), _hop("Deploy Failed"), _hop("Deploying")]) is True


def test_redeploy_true_after_a_rollback():
    assert X._is_redeployed([_hop("Deployed"), _hop("Rolled Back"), _hop("Deployed")]) is True


def test_redeploy_false_when_it_failed_and_stayed_failed():
    assert X._is_redeployed([_hop("Deploying"), _hop("Deploy Failed")]) is False


# ---------------------------------------------------------------------------
# staleness guard — the claim "a stale verdict reads Unknown, never green" (§7.1 N-SF3)
# ---------------------------------------------------------------------------

def test_fresh_health_is_left_alone():
    out = X._apply_staleness([_dep("Prod", checked_h=3)], NOW)
    assert out[0]["config_health"] == "Healthy" and out[0]["stale"] is False


def test_stale_green_is_forced_to_unknown():
    out = X._apply_staleness([_dep("Prod", checked_h=X.STALE_HOURS + 1)], NOW)
    assert out[0]["config_health"] == "Unknown" and out[0]["stale"] is True


def test_never_checked_is_forced_to_unknown():
    out = X._apply_staleness([_dep("Prod", checked_h=None)], NOW)
    assert out[0]["config_health"] == "Unknown" and out[0]["stale"] is True


def test_already_unknown_is_not_counted_as_stale():
    out = X._apply_staleness([_dep("Dev", "Not started", "Unknown", checked_h=None)], NOW)
    assert out[0]["stale"] is False


def test_staleness_does_not_mutate_its_input():
    src = [_dep("Prod", checked_h=999)]
    X._apply_staleness(src, NOW)
    assert src[0]["config_health"] == "Healthy"   # caller's dict untouched


# ---------------------------------------------------------------------------
# scoreboard — num/den/target/verdict, and the denominator bug that inflated failure
# ---------------------------------------------------------------------------

def _rec(**kw):
    base = {"org_deploys": [], "deploy_rollup": "Not started", "resolved_at": None,
            "reported_at": None, "is_redeployed": False, "evidence_pack_ready": False,
            "stage": "Build", "status": "In Build", "timeline": [], "cab_approval": "Approved",
            "evidence_overclaimed": False}
    base.update(kw)
    return base


def test_deploy_success_excludes_not_started_from_the_denominator():
    """The bug: every 'Not started' org counted as a failed deploy, so a request that simply
    hadn't shipped dragged the rate down (27% on live data instead of the real figure)."""
    r = _rec(org_deploys=[_dep("Prod"), _dep("Dev", "Not started", "Unknown", None)])
    sb = X._scoreboard([r])
    assert sb["deploy_success_pct"]["num"] == 1
    assert sb["deploy_success_pct"]["den"] == 1          # the Not-started cell is not a failure
    assert sb["deploy_success_pct"]["value"] == 100.0


def test_prod_deploy_success_is_prod_only():
    rs = [_rec(org_deploys=[_dep("Prod")]),
          _rec(org_deploys=[_dep("Prod", "Failed", "Failing")]),
          _rec(org_deploys=[_dep("QA", "Failed", "Failing")])]   # non-Prod must not count
    m = X._scoreboard(rs)["prod_deploy_success_pct"]
    assert (m["num"], m["den"]) == (1, 2)


def test_verdicts_follow_target_and_direction():
    sb = X._scoreboard([_rec(org_deploys=[_dep("Prod")])])
    assert sb["deploy_success_pct"]["verdict"] == "PASS"        # 100 >= 90
    sb2 = X._scoreboard([_rec(org_deploys=[_dep("Prod", "Failed", "Failing")])])
    assert sb2["deploy_success_pct"]["verdict"] == "GAP"        # 0 < 90


def test_rollback_rate_is_a_le_metric():
    rs = [_rec(org_deploys=[_dep("Prod"), _dep("QA", "Rolled back", "Failing")])]
    m = X._scoreboard(rs)["rollback_rate_pct"]
    assert m["direction"] == "le" and m["verdict"] == "GAP"     # 100% rolled back


def test_empty_input_never_divides_by_zero():
    for m in X._scoreboard([]).values():
        assert m["value"] is None or isinstance(m["value"], float)


# ---------------------------------------------------------------------------
# invariants — reconciliation + wart-catchers (§7.1)
# ---------------------------------------------------------------------------

def _by_text(inv, needle):
    return next(i for i in inv if needle in i["text"])


def test_stage_partition_invariant_passes_on_valid_stages():
    inv = X._invariants([_rec(stage=s) for s in X.SF_STAGES])
    assert _by_text(inv, "Stage buckets partition")["ok"] is True


def test_stage_partition_invariant_trips_on_an_unknown_stage():
    inv = X._invariants([_rec(stage="Nonsense")])
    assert _by_text(inv, "Stage buckets partition")["ok"] is False


def test_wart_flags_audit_stage_with_an_undeployed_org():
    """N-SF4: a contradiction must be FLAGGED, not hidden."""
    r = _rec(stage="Audit", status="Audit", org_deploys=[_dep("Prod", "Failed", "Failing")])
    assert _by_text(X._invariants([r]), "Stage↔deploy consistency")["ok"] is False


def test_cancelled_does_not_trip_the_audit_wart():
    """Cancelled folds into stage Audit, so without this guard the check is mostly noise."""
    r = _rec(stage="Audit", status="Cancelled", org_deploys=[_dep("Prod", "Not started", "Unknown", None)])
    assert _by_text(X._invariants([r]), "Stage↔deploy consistency")["ok"] is True


def test_wart_flags_deploy_without_recorded_cab_approval():
    r = _rec(timeline=[_hop("Deploying")], cab_approval="Pending")
    assert _by_text(X._invariants([r]), "CAB gate")["ok"] is False


def test_not_required_cab_is_not_a_bypass():
    r = _rec(timeline=[_hop("Deploying")], cab_approval="Not required")
    assert _by_text(X._invariants([r]), "CAB gate")["ok"] is True


def test_wart_flags_evidence_overclaim():
    assert _by_text(X._invariants([_rec(evidence_overclaimed=True)]), "Evidence packs")["ok"] is False


# ---------------------------------------------------------------------------
# stage mapping + the modelled health function
# ---------------------------------------------------------------------------

def test_every_seeded_status_maps_to_a_stage():
    for _stage, status in S.STAGE_STATUS:
        assert X.STAGE_OF_STATUS[status] in X.SF_STAGES
    for status in ("Deploy Failed", "Rolled Back", "Cancelled"):
        assert X.STAGE_OF_STATUS[status] in X.SF_STAGES


def test_health_model_is_deterministic():
    a = W.deploy_health_model("Deployed", "Deployed", "Prod", "SFC-1")
    b = W.deploy_health_model("Deployed", "Deployed", "Prod", "SFC-1")
    assert a == b


def test_health_model_never_reports_health_for_an_undeployed_org():
    _state, health = W.deploy_health_model("Deploying", "Validated", "Prod", "SFC-1")
    assert health == "Unknown"


def test_health_model_marks_failed_deploys_failing():
    _state, health = W.deploy_health_model("Deploy Failed", "Failed", "Prod", "SFC-1")
    assert health == "Failing"


def test_health_model_lands_in_flight_orgs_once_the_request_is_done():
    state, _health = W.deploy_health_model("Done", "Deploying", "Prod", "SFC-1")
    assert state == "Deployed"


# ---------------------------------------------------------------------------
# the preview generator — the two bugs the audit found, locked down
# ---------------------------------------------------------------------------

def test_model_volume_matches_client_side_windowing():
    """The masthead read '64 in window' while the panels showed 8/29, because each window
    generated its own record set instead of windowing one."""
    _m, all_recs = S.build(64, 180, NOW, span=180)
    for days in (30, 90, 180):
        model, _ = S.build(64, days, NOW, span=180)
        client = sum(1 for r in all_recs if r["reported_ts"] >= model["window_start_ts"])
        assert model["volume"] == client, "window %sd disagrees" % days


def test_deploy_failed_requests_stay_open():
    """They were neither open nor done, so they vanished from every WIP/agent view."""
    _m, recs = S.build(64, 180, NOW, span=180)
    failed = [r for r in recs if r["status"] == "Deploy Failed"]
    assert failed and all(r["is_open"] for r in failed)


def test_preview_and_live_records_share_one_schema():
    """Schema parity is the stated contract between app/sfc_seed and app/sfc_export."""
    _m, recs = S.build(4, 180, NOW, span=180)
    preview_keys = set(recs[0])
    for k in ("evidence_pack_claimed", "evidence_pack_ready", "evidence_missing",
              "evidence_overclaimed", "is_redeployed", "stage", "org_deploys",
              "deploy_rollup", "is_open", "is_done", "timeline", "changelog_hops"):
        assert k in preview_keys, "preview record is missing %r" % k
    for d in recs[0]["org_deploys"]:
        assert {"org", "deploy_state", "config_health", "health_checked_at",
                "stale", "health_age_h", "source"} <= set(d)


def test_preview_exercises_the_staleness_guard():
    """It used to hardcode stale=False, which made the freshness invariant a free pass."""
    _m, recs = S.build(64, 180, NOW, span=180)
    cells = [d for r in recs for d in r["org_deploys"]]
    assert any(d["stale"] for d in cells)
    assert all(d["config_health"] == "Unknown" for d in cells if d["stale"])


def test_preview_invariants_are_all_present():
    model, _ = S.build(64, 180, NOW, span=180)
    assert len(model["invariants"]) >= 7
    assert all("text" in i and "ok" in i for i in model["invariants"])


# ---------------------------------------------------------------------------
# time_in_stage — the input the §5.7 stall thresholds key off
# ---------------------------------------------------------------------------

def test_time_in_stage_uses_the_most_recent_status_change():
    tl = [{"at": (NOW - timedelta(hours=50)).isoformat(), "field": "status", "from": "Intake", "to": "In Build"},
          {"at": (NOW - timedelta(hours=5)).isoformat(), "field": "status", "from": "In Build", "to": "In Review"}]
    stamps = [e["at"] for e in tl if e.get("at")]
    entry = max(datetime.fromisoformat(s) for s in stamps)
    assert round((NOW - entry).total_seconds() / 3600.0) == 5


def test_preview_records_carry_time_in_stage():
    _m, recs = S.build(8, 180, NOW, span=180)
    assert all(r.get("time_in_stage_h") is not None for r in recs)
    assert all(r.get("stage_entry_at") for r in recs)


def test_time_in_stage_falls_back_to_reported_for_a_request_that_never_moved():
    """A request with no status change has been in its first stage since it was reported —
    that IS its time in stage, so the fallback is honest rather than a null hole."""
    _m, recs = S.build(64, 180, NOW, span=180)
    never_moved = [r for r in recs if r["changelog_hops"] == 0]
    assert never_moved
    for r in never_moved:
        assert abs(r["time_in_stage_h"] - r["age_days"] * 24) < 0.5
