#!/usr/bin/env python3
"""Single source of truth for the OPS project schema.

The four previously-open decisions are resolved here as working defaults. Each is
marked DECISION with its rationale — override any of them and re-run the build.
"""

PROJECT_KEY = "OPS"
PROJECT_NAME = "IT Operations - L1 L2 Support"

# ---------------------------------------------------------------------------
# DECISION 1 — Licensing.
# Build on Jira Software now; provision JSM in parallel.
# Rationale: JSM is not provisioned (servicedeskapi 403) and waiting on a
# licensing call blocks everything. Every mechanism in the design except the
# SLA engine, queues and portal works on Jira Software today. SLA state is
# carried in the fields below so the model is identical; when JSM lands, the
# native engine replaces the fields and nothing else changes.
# ---------------------------------------------------------------------------
SLA_BACKEND = "fields"  # "fields" until JSM is provisioned, then "jsm"

# ---------------------------------------------------------------------------
# DECISION 2 — Towers. Six, not eight.
# Rationale: each tower needs enough volume to make its dashboards legible.
# Eight towers across a realistic monthly volume leaves several with too few
# tickets to chart. Six is the largest number that still looks like an
# operating tower rather than a spreadsheet. REPLACE WITH THE REAL DOMAINS.
# Weights approximate real enterprise IT demand: EUC and Apps dominate.
# ---------------------------------------------------------------------------
TOWERS = [
    ("End User Computing", 30),
    ("Enterprise Applications", 24),
    ("Network & Connectivity", 15),
    ("Database", 11),
    ("Compute & Storage", 11),
    ("Cloud & Security", 9),
]

# ---------------------------------------------------------------------------
# DECISION 3 — Team size and shift pattern.
# 12 L1 across three shifts (24x7), 10 L2 on business hours plus on-call,
# 3 tower leads, 1 major incident manager. ~26 people.
# Rationale: 24x7 L1 is what justifies P1/P2 round-the-clock targets; L2 on
# business hours plus on-call is the standard economical pattern and is why
# P3/P4 targets are stated in business days rather than hours.
# ---------------------------------------------------------------------------
SHIFTS = ["Shift A (06:00-14:00)", "Shift B (14:00-22:00)", "Shift C (22:00-06:00)"]

L1_ANALYSTS = [
    ("A. Okafor", "Shift A"), ("R. Mehta", "Shift A"), ("S. Lindqvist", "Shift A"),
    ("D. Fernandes", "Shift A"), ("K. Yamamoto", "Shift B"), ("T. Abara", "Shift B"),
    ("M. Delacroix", "Shift B"), ("P. Novak", "Shift B"), ("J. Whitfield", "Shift C"),
    ("N. Haddad", "Shift C"), ("L. Petrov", "Shift C"), ("C. Nkemelu", "Shift C"),
]

L2_ANALYSTS = {
    "End User Computing": ["B. Sorensen", "V. Ramaswamy"],
    "Enterprise Applications": ["G. Achebe", "H. Lindgren"],
    "Network & Connectivity": ["F. Costa", "W. Njoroge"],
    "Database": ["E. Vasileiou", "Y. Trung"],
    "Compute & Storage": ["I. Marchetti", "O. Sandoval"],
    "Cloud & Security": ["Z. Adeyemi"],
}

MAJOR_INCIDENT_MANAGER = "Q. Bergström"

# 24x7 for majors, business hours for the rest — follows directly from the shift model.
SLA_CALENDAR = {"P1": "24x7", "P2": "24x7", "P3": "Business hours", "P4": "Business hours"}

# ---------------------------------------------------------------------------
# DECISION 4 — Intake channels.
# Four, with monitoring wired to skew high-priority.
# Rationale: portal and email are the baseline; monitoring intake is what makes
# P1 detection faster than a human noticing; chat captures the shadow-support
# demand named in PROBLEM.md 3.6 and drags it back into the ticket record.
# Portal requires JSM — until then portal-equivalent intake is the REST API.
# ---------------------------------------------------------------------------
INTAKE_CHANNELS = [("Portal", 42), ("Email", 28), ("Monitoring", 18), ("Chat", 12)]

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SELECT_FIELDS = {
    "Tower": [t for t, _ in TOWERS],
    "Support Tier": ["L1", "L2", "L3 - Vendor"],
    "Impact": ["High", "Medium", "Low"],
    "Urgency": ["High", "Medium", "Low"],
    "Intake Channel": [c for c, _ in INTAKE_CHANNELS],
    "Escalation Reason": [
        "Requires elevated access",
        "Beyond documented runbook",
        "Suspected platform defect",
        "Vendor engagement required",
        "Root cause unclear after triage",
        "Change required to resolve",
    ],
    "KB Article Checked": ["Yes - article applied", "Yes - none found", "No"],
    "Root Cause": [
        "Configuration error", "Capacity / resource exhaustion", "Software defect",
        "Hardware failure", "Human error", "Third-party outage",
        "Access / permission misconfiguration", "Unknown - monitoring added",
    ],
    "Resolution Code": [
        "Fixed", "Workaround applied", "No fault found",
        "Duplicate", "Withdrawn by requester", "Referred to vendor",
    ],
    "Response SLA": ["Met", "Breached", "In progress"],
    "Resolution SLA": ["Met", "Breached", "In progress", "Paused"],
    "Reopened": ["Yes", "No"],
}

TEXT_FIELDS = {
    "L1 Analyst": "short",
    "L2 Analyst": "short",
    "Troubleshooting Performed": "long",
    "Affected Service": "short",
}

# Backdating workaround: Jira's `created` is read-only over REST, so a seeder run
# today stamps every ticket with today's date and every trend chart becomes a single
# vertical spike. These seeder-controlled datetime fields carry the real timeline,
# and every filter, chart and SLA calculation keys off `Reported At` rather than
# `created`. This is what makes seeded history chartable.
DATE_FIELDS = ["Reported At", "First Response At", "Escalated At", "Resolved At"]

ISSUE_TYPES = [
    ("Incident", "Something is broken or degraded", "standard"),
    ("Service Request", "A standard, pre-approved ask", "standard"),
    ("Change", "A modification requiring approval", "standard"),
    ("Problem", "Root cause behind recurring incidents", "standard"),
]

# Impact x Urgency -> Priority. The mechanism matters; the cells are tunable.
PRIORITY_MATRIX = {
    ("High", "High"): "P1", ("High", "Medium"): "P2", ("High", "Low"): "P3",
    ("Medium", "High"): "P2", ("Medium", "Medium"): "P3", ("Medium", "Low"): "P3",
    ("Low", "High"): "P3", ("Low", "Medium"): "P3", ("Low", "Low"): "P4",
}

# PLACEHOLDER targets (CLAIMS.md #14). Response / resolution in hours.
SLA_TARGETS = {
    "P1": (0.25, 4), "P2": (0.5, 8), "P3": (4, 72), "P4": (8, 120),
}

STATUSES = [
    ("New", "new"), ("Triage", "indeterminate"), ("In Progress L1", "indeterminate"),
    ("Escalated to L2", "indeterminate"), ("In Progress L2", "indeterminate"),
    ("L3 / Vendor", "indeterminate"), ("Pending Customer", "indeterminate"),
    ("Pending Vendor", "indeterminate"), ("Resolved", "done"),
    ("Closed", "done"), ("Cancelled", "done"),
]

SLA_PAUSED_STATUSES = ["Pending Customer", "Pending Vendor"]
