#!/usr/bin/env python3
"""Ticket content per tower and issue type.

Each entry is (summary, detail, impact, urgency) describing the archetype at its
worst; the seeder damps most instances downward so the queue is not all P1.
"""

# Roughly how a real tower's demand splits. Incidents dominate, requests are the
# steady background, changes are comparatively rare, problems rarer still because
# each one represents a cluster of incidents rather than a single report.
TYPE_MIX = [("Incident", 62), ("Service Request", 28), ("Change", 7), ("Problem", 3)]

INCIDENT = {
    "End User Computing": [
        ("Laptop will not join corporate VPN after OS update", "VPN client 7.2 fails handshake post-update", "Low", "Medium"),
        ("Outlook repeatedly prompting for credentials", "Modern auth token not refreshing", "Low", "Medium"),
        ("Shared drive mapping missing after profile rebuild", "Login script not applying drive map", "Low", "Low"),
        ("Cannot print to floor-3 multifunction device", "Print queue stalled on server", "Low", "Medium"),
        ("Teams audio device not detected on docking station", "Dock firmware mismatch", "Low", "Low"),
        ("Full disk encryption recovery key required", "User locked out after BIOS change", "Medium", "High"),
        ("Screen flicker on external monitor via USB-C", "Display driver or cable fault", "Low", "Low"),
        ("Laptop battery drains within 90 minutes", "Hardware degradation suspected", "Low", "Low"),
    ],
    "Enterprise Applications": [
        ("Payroll export failing at month-end close", "Batch job aborts on record 4,812", "High", "High"),
        ("ERP purchase requisition stuck in approval", "Workflow engine not advancing", "Medium", "High"),
        ("CRM reports timing out for regional managers", "Query plan regression after release", "Medium", "Medium"),
        ("Invoice PDF generation producing blank pages", "Template rendering fault", "Medium", "Medium"),
        ("SSO redirect loop on finance portal", "SAML assertion clock skew", "High", "High"),
        ("Scheduled nightly reconciliation did not run", "Scheduler missed trigger window", "High", "Medium"),
        ("Duplicate journal entries after integration retry", "Idempotency key not honoured", "High", "High"),
        ("Expense approval notifications not sending", "Mail connector queue backed up", "Medium", "Medium"),
    ],
    "Network & Connectivity": [
        ("Branch office link down - 40 users affected", "Primary circuit loss, failover not engaged", "High", "High"),
        ("Intermittent packet loss on data centre uplink", "Approx 4% loss on core switch port", "High", "High"),
        ("Wi-Fi authentication failing in west wing", "RADIUS timeout under load", "Medium", "High"),
        ("VPN concentrator at session capacity", "Licence ceiling reached during peak", "High", "High"),
        ("DNS resolution slow for internal zone", "Forwarder responding above 800ms", "Medium", "Medium"),
        ("Guest network captive portal not loading", "Portal certificate expired", "Low", "Medium"),
        ("Latency spike between regions", "Carrier-side routing change suspected", "Medium", "High"),
    ],
    "Database": [
        ("Replication lag exceeding 15 minutes", "Secondary falling behind under write load", "High", "High"),
        ("Deadlocks on order processing table", "Lock contention during batch window", "High", "High"),
        ("Tablespace approaching capacity", "92% used, growth trend steep", "Medium", "High"),
        ("Slow query on customer search endpoint", "Missing index after schema change", "Medium", "Medium"),
        ("Backup job failed verification step", "Checksum mismatch on archive", "High", "Medium"),
        ("Connection pool exhaustion during peak", "Application not releasing connections", "High", "High"),
    ],
    "Compute & Storage": [
        ("Virtual host memory pressure - workloads ballooning", "Cluster above 90% memory", "High", "High"),
        ("File share quota exceeded for engineering", "Growth outpacing allocation", "Medium", "Medium"),
        ("Backup window overrunning into business hours", "Job duration doubled since retention change", "Medium", "Medium"),
        ("Server unresponsive after patch cycle", "Host requires manual intervention", "High", "High"),
        ("Storage array reporting predictive disk failure", "Drive flagged, RAID still healthy", "Medium", "High"),
        ("Snapshot retention consuming excess capacity", "Policy misconfigured after migration", "Medium", "Low"),
    ],
    "Cloud & Security": [
        ("Suspicious sign-in from unrecognised location", "Impossible-travel alert raised", "High", "High"),
        ("Cloud spend anomaly - compute up 40% week on week", "Untagged resources in dev subscription", "Medium", "High"),
        ("Certificate expiring in 5 days on public endpoint", "Renewal not automated", "High", "High"),
        ("Phishing report from finance team", "User reported, no click confirmed", "Medium", "High"),
        ("Storage bucket permissions wider than policy", "Public read detected by scanner", "High", "High"),
        ("MFA enrolment failing for contractor accounts", "Directory sync attribute missing", "Medium", "Medium"),
    ],
}

SERVICE_REQUEST = {
    "End User Computing": [
        ("New starter equipment build - Engineering", "Laptop, dock and peripherals for 03 Aug start", "Low", "Medium"),
        ("Software install request - statistical package", "Licence allocation and install", "Low", "Low"),
        ("Replacement laptop for departing-to-new-role user", "Standard refresh, data migration needed", "Low", "Low"),
        ("Mobile device enrolment for new contractor", "MDM profile and app assignment", "Low", "Medium"),
        ("Additional monitor request - accessibility need", "Occupational health recommendation attached", "Low", "Medium"),
    ],
    "Enterprise Applications": [
        ("Access request - cost centre 4400 reporting", "Role mapping for new finance analyst", "Low", "Medium"),
        ("Add approver to procurement workflow", "Delegation during team lead absence", "Low", "Medium"),
        ("New report - supplier spend by quarter", "Standard report build request", "Low", "Low"),
        ("CRM licence assignment for regional team", "Six seats, existing licence pool", "Low", "Low"),
        ("Sandbox refresh from production", "Quarterly refresh for UAT cycle", "Medium", "Low"),
    ],
    "Network & Connectivity": [
        ("Firewall rule request - vendor support access", "Time-bounded access, standard change", "Low", "Low"),
        ("Static IP allocation for lab equipment", "Two addresses on the lab VLAN", "Low", "Low"),
        ("Guest Wi-Fi voucher batch for conference", "200 vouchers, one-week validity", "Low", "Medium"),
        ("Site-to-site VPN for new partner", "Standard tunnel build with agreed subnets", "Medium", "Low"),
    ],
    "Database": [
        ("Read-only reporting access for analytics team", "Standard access request", "Low", "Low"),
        ("Schema export for migration testing", "Structure only, no production data", "Low", "Low"),
        ("Additional index request from application team", "Supporting a new query pattern", "Low", "Medium"),
        ("Restore to test from last night's backup", "UAT dataset refresh", "Medium", "Low"),
    ],
    "Compute & Storage": [
        ("Capacity request for new application tier", "Four hosts, standard specification", "Low", "Low"),
        ("File share creation for new department", "With quota and access group", "Low", "Low"),
        ("Extend quota for engineering share", "Additional 2TB, approved by lead", "Low", "Medium"),
        ("Archive restore from cold storage", "Records requested for audit", "Medium", "Low"),
    ],
    "Cloud & Security": [
        ("Privileged access request - 4 hour window", "Break-glass access for planned work", "Medium", "High"),
        ("New service principal for CI pipeline", "Scoped to build resource group", "Low", "Medium"),
        ("Security exception request - legacy protocol", "Time-bounded, compensating controls noted", "Medium", "Medium"),
        ("Add user to security distribution list", "Standard onboarding step", "Low", "Low"),
    ],
}

CHANGE = {
    "End User Computing": [
        ("Deploy OS patch ring 2 to 400 devices", "Standard monthly patch cycle", "Medium", "Low"),
        ("Update baseline image with new security agent", "Requires CAB approval", "Medium", "Low"),
    ],
    "Enterprise Applications": [
        ("Apply vendor patch to ERP - release 24.3", "Scheduled weekend window", "High", "Low"),
        ("Change approval matrix for procurement", "Reorg-driven workflow update", "Medium", "Low"),
        ("Enable new integration endpoint for CRM", "Partner data feed go-live", "Medium", "Medium"),
    ],
    "Network & Connectivity": [
        ("Core switch firmware upgrade - DC1", "Maintenance window, failover tested", "High", "Low"),
        ("Migrate branch circuit to new carrier", "Cutover with rollback plan", "High", "Medium"),
    ],
    "Database": [
        ("Add partitioning to order history table", "Performance remediation from problem record", "High", "Low"),
        ("Upgrade minor version on reporting replica", "Vendor-recommended patch level", "Medium", "Low"),
    ],
    "Compute & Storage": [
        ("Expand cluster by two hypervisor hosts", "Capacity uplift, approved in planning", "Medium", "Low"),
        ("Change backup retention policy to 35 days", "Compliance-driven change", "Medium", "Low"),
    ],
    "Cloud & Security": [
        ("Tighten storage bucket policy across dev", "Remediation of scanner findings", "High", "Medium"),
        ("Roll out conditional access policy phase 2", "Staged, with break-glass exclusions", "High", "Medium"),
    ],
}

PROBLEM = {
    "End User Computing": [
        ("Recurring VPN handshake failures after OS updates", "14 incidents in 60 days, same signature", "Medium", "Low"),
        ("Docking station disconnects across one hardware batch", "Cluster suggests firmware defect", "Medium", "Low"),
    ],
    "Enterprise Applications": [
        ("Month-end batch failures recurring each cycle", "Same abort point three months running", "High", "Medium"),
        ("Intermittent SSO failures on finance portal", "Correlates with clock drift on one node", "High", "Medium"),
    ],
    "Network & Connectivity": [
        ("Repeated Wi-Fi auth timeouts in west wing", "RADIUS capacity suspected, 21 incidents", "Medium", "Medium"),
    ],
    "Database": [
        ("Deadlock pattern on order processing recurring", "Nine incidents traced to one batch job", "High", "Medium"),
    ],
    "Compute & Storage": [
        ("Backup window overruns recurring since migration", "Root cause not yet established", "Medium", "Low"),
    ],
    "Cloud & Security": [
        ("MFA enrolment failures for contractor cohort", "Directory attribute gap, 11 incidents", "Medium", "Medium"),
    ],
}

BY_TYPE = {
    "Incident": INCIDENT,
    "Service Request": SERVICE_REQUEST,
    "Change": CHANGE,
    "Problem": PROBLEM,
}

# How each type behaves, which is what stops the four types being cosmetic.
TYPE_BEHAVIOUR = {
    # escalation odds, resolution-time multiplier, allowed resolution codes
    "Incident": (0.42, 1.0, ["Fixed", "Workaround applied", "No fault found", "Duplicate"]),
    "Service Request": (0.16, 0.7, ["Fulfilled", "Withdrawn by requester", "Duplicate"]),
    "Change": (0.30, 2.2, ["Implemented", "Rolled back", "Withdrawn by requester"]),
    "Problem": (0.85, 5.0, ["Known error documented", "Fixed", "Referred to vendor"]),
}

TROUBLESHOOTING = [
    "Confirmed the fault reproduces from a second account and a clean device profile. Checked the runbook entry and applied the documented restart sequence with no change. Collected client logs and attached them.",
    "Verified service health and recent change records; nothing scheduled in the window. Reproduced on two clients on different subnets, which rules out a local cause. Escalating with logs attached.",
    "Ran the standard diagnostic script and reviewed the last 200 log lines. Error is consistent and matches no existing KB article. Cleared cache and re-authenticated without effect.",
    "Checked connectivity, credentials and permissions in that order. Permissions look correct against the role matrix. Restarted the client service twice; fault persists across both.",
    "Compared configuration against a working peer and found no difference. Confirmed the issue began after the release on the date noted. Rolled back the local change with no improvement.",
    "Followed the KB article end to end. The documented fix does not apply because the underlying setting is now managed centrally. Needs someone with elevated access.",
]

REQUEST_NOTES = [
    "Requester confirmed line-manager approval is attached. Checked entitlement against the standard catalogue - within policy, no exception needed.",
    "Verified the requester's role grants this entitlement. Checked stock and lead time before committing to a fulfilment date.",
    "Approval recorded. This is above the standard allocation, so it needs the tower lead to authorise before fulfilment.",
]

CHANGE_NOTES = [
    "Change record raised with rollback plan and test evidence. Scheduled inside the agreed maintenance window. CAB approval recorded.",
    "Implementation plan reviewed with the application owner. Backout tested in the staging environment. Requires an implementer with elevated access.",
]

PROBLEM_NOTES = [
    "Linked the contributing incidents and confirmed the shared signature. Initial hypothesis does not survive the timeline. Needs platform-level diagnosis beyond L1 scope.",
    "Trend analysis across 60 days shows the cluster is real, not coincidental. Workaround is documented and holding; underlying cause still unknown.",
]

COMMENTS = [
    "Acknowledged and triaging. Will update within the hour.",
    "Confirmed with the requester that the issue is still occurring as described.",
    "Applied the documented workaround; monitoring before closing.",
    "Reproduced in the test environment - behaves identically.",
    "Awaiting confirmation from the requester that service is restored.",
    "Linked to the related problem record for trend analysis.",
]
