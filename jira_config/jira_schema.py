#!/usr/bin/env python3
"""Everything that is true about Jira rather than about the support tower.

Custom-field type keys, searcher keys, project and issue-type template keys,
scheme names, priority colours, the domain-slug -> Jira-constant bridges, and the
project keys themselves. These were previously scattered as module-level literals
across seven build scripts; collecting them here is what lets shared/domain.py be
genuinely vendor-neutral.

Import direction is one-way: this module may import shared.domain. shared/ may
never import this module, and neither may app/ - if app/ needs something from
here, the boundary is wrong and the symbol belongs in domain.py.
"""

from shared import domain as D

# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------

PROJECT_KEY = "OPS"
PROJECT_NAME = "IT Operations - L1 L2 Support"

# ---------------------------------------------------------------------------
# DECISION 1 — Licensing.
# Build on Jira Software now; provision JSM in parallel.
# Rationale: JSM is not provisioned (servicedeskapi 403) and waiting on a
# licensing call blocks everything. Every mechanism in the design except the
# SLA engine, queues and portal works on Jira Software today. SLA state is
# carried in the tower's own fields so the model is identical; when JSM lands,
# the native engine replaces the fields and nothing else changes.
#
# This lives here rather than in domain.py because "jsm" names a Jira product:
# it selects which Jira mechanism carries SLA state, not what an SLA is.
# ---------------------------------------------------------------------------
SLA_BACKEND = "fields"  # "fields" until JSM is provisioned, then "jsm"

PROJECT_TYPE_KEY = "software"
# classic == company-managed; required for shared schemes and workflow rules
PROJECT_TEMPLATE_KEY = "com.pyxis.greenhopper.jira:gh-simplified-kanban-classic"

# ---------------------------------------------------------------------------
# Custom-field wire formats
# ---------------------------------------------------------------------------

# Re-exported, not re-declared. shared/fields.py owns these because it is the
# module that reads /rest/api/3/field and narrows a duplicate field NAME by type.
# If that copy and this one ever drifted, the builder would create a field of one
# type while the resolver looked for another, and the duplicate-name tie-break
# would quietly stop working. One definition, imported downhill (jira_config may
# import shared; never the reverse).
from shared.fields import (  # noqa: E402  - re-export, deliberately not at top
    AREA_TYPE, DATE_TYPE, SELECT_TYPE, TEXT_TYPE)

SEARCHER = {
    SELECT_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:multiselectsearcher",
    TEXT_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
    AREA_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:textsearcher",
    DATE_TYPE: "com.atlassian.jira.plugin.system.customfieldtypes:datetimerange",
}

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

# domain.STATUSES carries generic slugs ("new" / "indeterminate" / "done").
# This is the bridge to Jira's own status-category constants.
STATUS_CATEGORY = {"new": "TODO", "indeterminate": "IN_PROGRESS", "done": "DONE"}

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

ISSUE_TYPE_SCHEME_NAME = "OPS Issue Type Scheme"
PRIORITY_SCHEME_NAME = "OPS Priority Scheme"

# Colour and icon are how Jira paints a priority. The label itself is contractual
# and lives in domain.PRIORITY_LABELS, so it is referenced here, not re-typed.
PRIORITY_SPECS = [
    (D.PRIORITY_LABELS["P1"], "Business stopped or major incident", "#B3352A", "highest"),
    (D.PRIORITY_LABELS["P2"], "Severe degradation, workaround limited", "#96610C", "high"),
    (D.PRIORITY_LABELS["P3"], "Standard fault or request", "#3B5057", "medium"),
    (D.PRIORITY_LABELS["P4"], "Minor, no business impact", "#64787E", "low"),
]

# ---------------------------------------------------------------------------
# Resolutions
# ---------------------------------------------------------------------------

# Resolution Code (our field) -> Jira's native resolution. "Won't Do" and
# "Cannot Reproduce" are Jira built-ins, which is what makes this mapping
# Jira-specific. Blanket-setting everything to "Done" would make the closure
# data say something untrue.
RESOLUTION_MAP = {
    "Fixed": "Done",
    "Workaround applied": "Done",
    "Implemented": "Done",
    "Fulfilled": "Done",
    "Referred to vendor": "Done",
    "Known error documented": "Done",
    "No fault found": "Cannot Reproduce",
    "Duplicate": "Duplicate",
    "Withdrawn by requester": "Won't Do",
    "Rolled back": "Won't Do",
}
DEFAULT_RESOLUTION = "Done"

# ---------------------------------------------------------------------------
# Jira Service Management (the ITSM project)
# ---------------------------------------------------------------------------

JSM_PROJECT_KEY = "ITSM"
JSM_PROJECT_NAME = "IT Service Management - L1/L2 Tower"

# Verified by probe: the only service_desk template on this site that ships
# Incident / Service Request / Change / Problem out of the box.
JSM_TEMPLATE = "com.atlassian.servicedesk:itil-v2-service-desk-project"

# [System] Post-incident review. No template on this site ships it; it is added to
# ITSM's own (dedicated) issue type scheme afterwards.
PIR_ISSUE_TYPE_ID = "10025"

SERVICE_DESK_ID = "8"

# ITSM runs the stock ITIL workflows, so its paused-status names differ from OPS's
# own (domain.SLA_PAUSED_STATUSES). These are template statuses shipped by Jira,
# not part of our model. The two lists look similar and are NOT interchangeable:
# merging them would silently change which tickets are excluded from attainment
# on both projects.
JSM_PAUSED_STATUSES = ["Pending", "Waiting for customer", "Waiting for approval"]

# The tower schema in the order it should read on a Jira screen. The names are
# domain field names; the ordering is a Jira rendering concern, which is why it
# lives here. Ids are looked up from state, never guessed.
SCREEN_FIELD_ORDER = [
    "Tower", "Support Tier", "Impact", "Urgency", "Intake Channel",
    "Escalation Reason", "Troubleshooting Performed", "KB Article Checked",
    "Root Cause", "Resolution Code", "Response SLA", "Resolution SLA", "Reopened",
    "L1 Analyst", "L2 Analyst", "Affected Service",
    "Reported At", "First Response At", "Escalated At", "Resolved At",
]

# The screen order must stay a subset of the fields the model actually declares.
# Asserted at import so a rename in domain.py cannot silently strand a field off
# every ITSM screen.
_DOMAIN_FIELD_NAMES = (set(D.SELECT_FIELDS) | set(D.TEXT_FIELDS) | set(D.DATE_FIELDS))
_UNKNOWN = sorted(set(SCREEN_FIELD_ORDER) - _DOMAIN_FIELD_NAMES)
if _UNKNOWN:
    raise RuntimeError(
        "SCREEN_FIELD_ORDER names %d field(s) that shared/domain.py does not "
        "declare: %s" % (len(_UNKNOWN), ", ".join(_UNKNOWN)))
