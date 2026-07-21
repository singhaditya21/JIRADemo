# Field schema, permission scheme and automation rules

Live reference for the `OPS` project on `singhaditya21.atlassian.net`. Field IDs are
real — built by `jira_config/build.py` and verified against the instance on 2026-07-20.

---

## 1. Field schema

Twenty custom fields. Each earns its place: it either drives routing, gates a
transition, or is required to compute a metric on the scoreboard.

### Routing and classification

| Field | ID | Type | Purpose |
|---|---|---|---|
| Tower | `customfield_10042` | Select (6) | Owning technical domain. Drives every queue and dashboard cut. **Not** a project. |
| Support Tier | `customfield_10043` | Select (3) | L1 / L2 / L3-Vendor. Set by workflow post-function, read-only to agents. |
| Affected Service | `customfield_10056` | Text | Service catalogue reference. |
| Intake Channel | `customfield_10045` | Select (4) | Portal / Email / Monitoring / Chat. Chat exists to drag shadow support into the record. |

### Priority derivation

| Field | ID | Type | Purpose |
|---|---|---|---|
| Impact | `customfield_10004` | Select (3) | Agent-set. How much of the business is affected. |
| Urgency | `customfield_10044` | Select (3) | Agent-set. How fast it must move. |

Priority is **computed** from these two, never chosen. Agents answer two defensible
questions; automation does the rest.

### The escalation gate — the three fields that make it enforceable

| Field | ID | Type | Purpose |
|---|---|---|---|
| Escalation Reason | `customfield_10046` | Select (6) | Required to escalate. Becomes the category axis of the escalation report. |
| Troubleshooting Performed | `customfield_10055` | Textarea | Required to escalate. Stops one-word escalations. **Takes ADF, not a bare string.** |
| KB Article Checked | `customfield_10047` | Select (3) | Required to escalate. "Yes - none found" is the KB backlog. |

### Closure and cause

| Field | ID | Type | Purpose |
|---|---|---|---|
| Root Cause | `customfield_10048` | Select (8) | Set at resolution. Feeds problem management. |
| Resolution Code | `customfield_10049` | Select (6) | Fixed / Workaround / No fault found / Duplicate / Withdrawn / Vendor. |
| Reopened | `customfield_10052` | Select (2) | Paired with FTR so neither can be gamed alone. |

### SLA state

Carried in fields because Service Management is not provisioned. When JSM lands, the
native engine replaces these four and nothing else in the model changes.

| Field | ID | Type | Purpose |
|---|---|---|---|
| Response SLA | `customfield_10050` | Select (3) | Met / Breached / In progress. |
| Resolution SLA | `customfield_10051` | Select (4) | Met / Breached / In progress / **Paused**. |
| L1 Analyst | `customfield_10053` | Text | Named analyst. Text rather than a user picker because the instance has one licensed user. |
| L2 Analyst | `customfield_10054` | Text | As above. |

### Timeline — the fields that make seeded history chartable

| Field | ID | Type |
|---|---|---|
| Reported At | `customfield_10057` | DateTime |
| First Response At | `customfield_10058` | DateTime |
| Escalated At | `customfield_10059` | DateTime |
| Resolved At | `customfield_10060` | DateTime |

**Why these exist.** Jira's `created` is read-only over REST, so a seeder run today
stamps every ticket with today's date and every trend chart collapses into one vertical
spike. These four carry the real timeline instead, and **every filter, gadget and SLA
calculation keys off `Reported At` rather than `created`**. Seeded data currently spans
2026-04-24 to 2026-07-15 while `created` is uniformly 2026-07-20 — the charts work
because nothing reads `created`.

This is also correct beyond the demo: `Reported At` is when the *user* hit the problem,
which is rarely when the ticket got raised.

---

## 2. Permission scheme

Scheme `10034` on project `OPS`. Roles: `Administrators` (10002),
`atlassian-addons-project-access`, `jira-guest-member`.

**The single most important grant is a negative one:** L1 agents hold
`TRANSITION_ISSUES` but **not** the major-incident transition, which is restricted to
the Major Incident Manager role. That restriction is what makes the fast path
accountable rather than a free choice under pressure.

| Role | Grants | Deliberately withheld |
|---|---|---|
| **L1 Agent** | Browse, Create, Edit, Comment, Transition (standard paths), Assign | Major-incident transition · Delete · Set Root Cause · Close P1 |
| **L2 Agent** | All L1 grants, plus Root Cause and Resolution Code, transitions within own tower | Cross-tower reassignment · Delete |
| **Tower Lead** | All L2 grants, plus cross-tower reassign, priority override, close P1 | Project admin |
| **Major Incident Manager** | **`Escalate - major incident` transition** · declare/stand down majors | — |
| **Service Desk Manager** | Project admin, workflow and SLA configuration | Site admin |
| **Customer** | Create and comment on own tickets; view own only | Everything else |

> **Live-instance note.** `DELETE_ISSUES` is granted to the `Administrators` *role*, and
> being project **lead** does not put you in that role. Seed reset failed with 403 until
> the account was explicitly added to the role. Worth knowing before a rehearsal.

---

## 3. The seven automation rules

**All seven are live on OPS and ENABLED** (verified 2026-07-21). There is no *public* Cloud
REST API for automation (`/rest/api/3/automation/rules` → 404), but the Automation
**internal** API takes create + enable, so they are built and reconciled in code by
`automation/build_rules.py` — not hand-built in the UI. The recipes below are the design;
`automation/README.md` records what is actually on the instance, including the two places a
rule uses a verified substitute for a sub-shape that stayed UI-only (rule 1 fires on
**create** rather than on field-change; rule 3 posts a **comment** rather than an email).

### Rule 1 — Derive priority (the anti-inflation rule)
- **Trigger:** Field value changed → `Impact` or `Urgency`
- **Condition:** both fields present
- **Action:** Edit issue → `Priority` from the Impact × Urgency matrix
- **Why:** priority becomes a derivation, not a negotiation.

### Rule 2 — Route on escalation
- **Trigger:** Issue transitioned → `Escalated to L2`
- **Action:** Edit `Support Tier` = L2; clear assignee; add issue to the tower's queue
- **Why:** the ticket lands in a tower queue, not on one named person.

### Rule 3 — Major incident alert
- **Trigger:** Field value changed → `Priority` = P1, or issue created as P1
- **Action:** Notify tower lead + Major Incident Manager; post to the incident channel
- **Why:** a P1 that waits in a queue is not a P1.

### Rule 4 — SLA breach warning at 75%
- **Trigger:** Scheduled, every 15 minutes
- **Condition:** JQL — not done, elapsed since `Reported At` ≥ 75% of target for priority
- **Action:** Comment on issue; notify assignee and tower lead
- **Why:** warn while it can still be saved, not after the fact.

### Rule 5 — SLA pause and resume
- **Trigger:** Issue transitioned → to or from `Pending Customer` / `Pending Vendor`
- **Action:** Set `Resolution SLA` = Paused on entry; recompute on exit
- **Why:** **this is the rule that makes the SLA report trustworthy.** Without it every
  ticket waiting on a user reads as a failure and leadership stops opening the report.

### Rule 6 — Reopen handling
- **Trigger:** Issue transitioned → `Resolved` to `Triage`
- **Condition:** within 7 days of resolution
- **Action:** Set `Reopened` = Yes; notify the original resolver; return to L1 queue
- **Why:** without the flag, a premature close reappears as a fresh ticket and flatters FTR.

### Rule 7 — Auto-close after resolution
- **Trigger:** Scheduled, daily
- **Condition:** JQL — status `Resolved` and no customer response for 5 days
- **Action:** Transition to `Closed`; comment explaining why
- **Why:** stops the Resolved column becoming a second backlog.

> Rules 5 and 6 are the two that carry the design. Rule 5 makes the SLA report
> defensible; rule 6 makes first-time resolution honest. Build those first.

---

## 4. What is scripted vs what is UI — verified on this instance

| Item | Route | Verified |
|---|---|---|
| Project, custom fields, contexts, options | REST | ✅ built by `jira_config/build.py` |
| Screens and field associations | REST | ✅ 40 associations added |
| Statuses (all 11) | REST | ✅ built by `jira_config/workflow.py` |
| Workflow with 13 transitions | REST | ✅ created and bound via workflow scheme |
| **Escalation-gate validator** | **UI only** | ❌ `system:field-required` rejected by `workflows/create` with "Rule cannot be applied to this type or is unsupported" — three payload variants tried |
| Issues, transitions, comments | REST | ✅ 420 seeded, 0 failures |
| Filters and dashboard | REST | ✅ 10 filters, 1 dashboard |
| Automation rules | UI + JSON export | ❌ no public REST API (404) |
| SLA targets, agent queues, portal | JSM UI | ⛔ blocked — JSM not provisioned |

**The honest sentence for the demo:** *structure is scripted end to end; the escalation
gate validator and the automation rules are UI, and version-controlled as exported JSON.*
