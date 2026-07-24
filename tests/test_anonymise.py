"""What must never survive a public bake.

The site is world-readable and presented internally, so the artifact must not name whose Jira
tenant it is or who worked each ticket. Two vectors leaked in practice and both are pinned
here: the per-record `url` (tenant hostname) and — caught only by the CI gate, after the
analyst masking was already believed complete — person-valued CHANGELOG entries, where an
assignee hop carries a display name the l1/l2 alias map never covered.

These tests exist because the masking looked done and wasn't. They assert the property
(no real name reaches the output), not the implementation.
"""

from datetime import datetime, timezone

import pytest

from app import export_pages as E
from app.store import Change


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)
REAL = "Ada Lovelace"          # stands in for any real display name


class FakeIssue:
    """Only the attributes the alias map and _mask_change actually read."""

    def __init__(self, l1=None, l2=None, changelog=()):
        self.l1_analyst = l1
        self.l2_analyst = l2
        self.changelog = changelog


def ch(field, frm=None, to=None):
    return Change(at=NOW, field=field, frm=frm, to=to)


# --- the alias map has to see the changelog, not just the analyst slots -----------------

def test_map_covers_the_l1_l2_analysts():
    m = E._pseudonymise_map([FakeIssue(l1="Grace Hopper", l2=REAL)])
    assert set(m) == {"Grace Hopper", REAL}
    assert all(v.startswith("Analyst ") for v in m.values())


def test_map_covers_a_name_that_only_ever_appears_in_the_changelog():
    # The exact shape of the leak: the account that seeded the instance holds no l1/l2 slot,
    # so the old map never learned its name and the timeline shipped it verbatim.
    m = E._pseudonymise_map([FakeIssue(changelog=(ch("assignee", frm=REAL),))])
    assert REAL in m


def test_map_ignores_enum_valued_changes():
    m = E._pseudonymise_map([FakeIssue(changelog=(ch("status", "Open", "Done"),
                                                  ch("resolution", None, "Fixed")))])
    assert m == {}


def test_alias_is_stable_across_records():
    issues = [FakeIssue(l1=REAL), FakeIssue(changelog=(ch("assignee", to=REAL),))]
    m = E._pseudonymise_map(issues)
    assert m[REAL] == m[REAL]                      # same key -> one alias, by construction
    assert len(set(m.values())) == len(m)          # and aliases are not reused across people


# --- masking one changelog entry -------------------------------------------------------

def test_status_hops_pass_through_untouched():
    m = {REAL: "Analyst 01"}
    assert E._mask_change(ch("status", "Open", "Done"), m)["from"] == "Open"
    assert E._mask_change(ch("status", "Open", "Done"), m)["to"] == "Done"


def test_assignee_hop_is_replaced_by_the_alias():
    out = E._mask_change(ch("assignee", frm=REAL, to=None), {REAL: "Analyst 01"})
    assert out["from"] == "Analyst 01"
    assert out["to"] is None                       # unassigned stays unassigned, not "Analyst"


def test_an_unmapped_person_becomes_a_constant_rather_than_leaking():
    # Fail closed: losing WHICH person it was beats publishing WHO they are.
    out = E._mask_change(ch("assignee", frm=REAL), {})
    assert REAL not in str(out)
    assert out["from"] == "Analyst"


@pytest.mark.parametrize("field", ["assignee", "Assignee", "ASSIGNEE", "Request participants"])
def test_person_fields_are_matched_case_insensitively(field):
    # Jira renders custom person fields with their display label, so the comparison cannot
    # assume a stable lowercase id.
    assert E._mask_change(ch(field, frm=REAL), {})["from"] == "Analyst"


def test_masking_is_off_when_no_alias_map_is_in_play():
    # A local, non-published bake keeps the real changelog — pseudonymisation is a choice,
    # and the exporter should not quietly rewrite data nobody asked it to rewrite.
    assert E._mask_change(ch("assignee", frm=REAL), None)["from"] == REAL


def test_the_timestamp_and_field_survive_masking():
    out = E._mask_change(ch("assignee", frm=REAL), {REAL: "Analyst 01"})
    assert out["field"] == "assignee"
    assert out["at"] == NOW.isoformat()


# --- the flags -------------------------------------------------------------------------

def test_anonymise_reads_the_env_flag(monkeypatch):
    monkeypatch.setenv("DEMO_ANONYMISE", "1")
    assert E.anonymised() is True
    monkeypatch.setenv("DEMO_ANONYMISE", "")
    assert E.anonymised() is False


def test_strip_tenant_drops_the_site_and_every_record_url():
    payload = {"site": "https://acme.atlassian.net", "totals": {"open": 3}}
    records = [{"key": "ITSM-1", "url": "https://acme.atlassian.net/browse/ITSM-1"}]
    E.strip_tenant(payload, records)
    assert "site" not in payload
    assert records[0]["url"] is None
    assert payload["totals"] == {"open": 3}        # only identity goes, not the data


# --- end to end: a whole record, as it would be published ------------------------------

def test_no_real_name_survives_a_pseudonymised_record():
    issue = FakeIssue(l1=REAL, changelog=(ch("assignee", frm=REAL, to=None),
                                          ch("status", "Open", "Done")))
    alias = E._pseudonymise_map([issue])
    timeline = [E._mask_change(c, alias) for c in issue.changelog]
    assert REAL not in str(timeline)
    assert str(timeline).count("Analyst") == 1     # only the person hop was rewritten
