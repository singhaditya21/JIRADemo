# L1/L2 Tower Ticket Management System — Build Plan

**Instance:** `singhaditya21.atlassian.net`
**Account:** Aditya Singh (site admin — `ADMINISTER`, `CREATE_PROJECT` all true)
**Date:** 2026-07-20

---

## 1. What's in the instance today

| Item | State |
|---|---|
| Licensed products | `jira-software` only (100,000 seats, 1 used) |
| Existing projects | `KAN` — "Demo with Claude" (team-managed, software)<br>`SAM1` — "(Example) Billing System Dev" (team-managed, software) |
| Jira Service Management | **Not provisioned** — `/rest/servicedeskapi/*` returns 403 |
| Issue types available | Bug, Epic, Feature, Request, Story, Subtask, Task |
| Company-managed projects | None yet (both existing are team-managed / next-gen) |

Nothing here conflicts with the build. We start clean.

---

## 2. The one decision that changes everything: JSM vs Jira Software

An L1/L2 support tower is the exact workload Jira Service Management is built for. Four capabilities matter, and **three of them do not exist in Jira Software**:

| Capability | JSM | Jira Software |
|---|---|---|
| SLA engine (targets, pause conditions, breach clocks) | Native | ✗ — must be faked with automation + date fields |
| Agent queues (shared, filter-driven work lists) | Native | ✗ — approximated with boards/filters |
| Customer portal + email intake → ticket | Native | ✗ — no portal; email intake is limited |
| Approvals (for access/change requests) | Native | ✗ — workflow hack |
| Request types (portal-facing forms) | Native | ✗ — issue types only |

**Recommendation: provision JSM.** The free tier covers 3 agents and includes the full SLA engine — enough to build and demo the entire design. Building this on Jira Software means hand-rolling an SLA clock in automation rules, which is the part that will be brittle and the part a demo audience will poke at.

If this must stay on Jira Software, the design below still holds — Sections 4–7 change from "configure" to "simulate," and Section 8 (SLA) degrades to best-effort. Flagged inline as **[JSM]** where a step requires it.

---

## 3. Core model: tier is a state, tower is a dimension

The most common way these builds fail is treating L1→L2 escalation as *handing off to a different project*, which breaks the ticket ID, splits the SLA clock, and destroys end-to-end MTTR reporting.

**Design: one project. Tier and tower are both fields on the ticket.**

- **Tower** = which technical domain owns it (custom field, single-select)
- **Support Tier** = L1 / L2 / L3-Vendor (custom field, driven by workflow)
- Escalation = a **workflow transition** that flips Support Tier and reassigns — same issue key, same SLA clock, one audit trail

```
                    ┌─────────── ONE PROJECT: OPS ───────────┐
   Intake  ──────►  │  Tower: [Network|DB|Apps|EUC|Cloud|Sec] │
 (portal/email)     │  Tier:  [L1] ──escalate──► [L2] ──► [L3]│  ──► Resolved
                    │  SLA clock: runs continuously across all│
                    └─────────────────────────────────────────┘
```

Alternative considered — a project per tower — is worth it only if towers are separate vendors with separate contracts and must not see each other's tickets. Note that as an open question in §11.

---

## 4. Project setup

| Setting | Value |
|---|---|
| Project type | **Company-managed** (not team-managed) — needed for shared workflows, screens, and field configs across towers |
| Key | `OPS` |
| Name | IT Operations — L1/L2 Support |
| Template | **[JSM]** IT Service Management |

Company-managed is non-negotiable: team-managed projects can't share a workflow scheme or use company-wide custom field contexts, both of which this design depends on.

---

## 5. Towers

Proposed starting set — **needs confirmation, see §11**:

1. Network & Connectivity
2. Server / Compute
3. Database
4. Storage & Backup
5. End User Computing (EUC)
6. Applications
7. Cloud & Platform
8. Security & IAM

Each tower gets: a queue, a Jira group (`ops-l2-<tower>`), an auto-assignment rule, and a dashboard row.

---

## 6. Issue types / request types

| Type | Purpose | SLA-bearing |
|---|---|---|
| **Incident** | Something is broken | Yes — response + resolution |
| **Service Request** | Standard, pre-approved ask (access, provisioning) | Yes — fulfilment |
| **Change** | Modification requiring approval | Approval-gated |
| **Problem** | Root cause behind repeat incidents | No — investigation |

Keep it to these four. Every extra issue type multiplies workflow, screen, and report maintenance.

---

## 7. Workflow

```
                                   ┌──────────────────┐
                                   │  Pending —       │  (SLA PAUSED)
                                   │  Customer/Vendor │
                                   └────────┬─────────┘
                                        ▲   │
                                        │   ▼
  New ──► Triage ──► In Progress L1 ──► ... ──► Resolved ──► Closed
   │        (L1)          │                       ▲            │
   │                      │ escalate              │            │ reopen
   │                      ▼                       │            ▼
   │              In Progress L2 ─────────────────┘        (back to Triage)
   │                      │
   │                      ▼
   └──► Cancelled    L3 / Vendor
```

**Statuses:** New · Triage · In Progress L1 · Escalated to L2 · In Progress L2 · L3/Vendor · Pending Customer · Pending Vendor · Resolved · Closed · Cancelled

### The escalation gate (the most important rule in this system)

The failure mode of every L1/L2 tower is L1 dumping tickets on L2 without troubleshooting (`PROBLEM.md` §4.2). Prevent it in config, not policy:

Put a **workflow validator** on the `In Progress L1 → Escalated to L2` transition requiring:
- `Escalation Reason` (required, select)
- `Troubleshooting Performed` (required, text, min length enforced)
- `KB Article Checked` (required, checkbox or article link)

And a **post-function** that sets `Support Tier = L2` and clears the assignee so the ticket lands in the tower's L2 queue rather than on a named individual.

Measure the resulting **escalation rate per L1 analyst** — that single metric tells you whether L1 is functioning.

### The major-incident fast path — do not gate a P1

A gate that is right for a password reset is actively harmful during an outage. Forcing an analyst to compose a paragraph while the business is stopped trades minutes of downtime for paperwork, and it is the first thing an experienced operator will challenge.

So the gate is **not** universal. There are two escalation transitions:

| Transition | Validators | Who can use it |
|---|---|---|
| `Escalate to L2` | All three fields required | Any L1 agent |
| `Escalate — major incident` | **None.** Immediate. | Major Incident Manager role only |

**Why role-restricted rather than priority-conditional.** Native Jira conditions are understood to branch on permission, role, group and status — not on a field *value* like `Priority = P1` (claim #9, unverified). Restricting the fast path by **role** therefore works with native workflow rules and needs no app. It is also the better design: a fast path should be a deliberate, accountable act by a named incident manager, not a free choice available to anyone feeling time pressure.

**Nothing is lost, only deferred.** A second validator on `Resolved → Closed` requires the same three fields for *every* ticket regardless of path. Majors skip the gate on the way in and pay it on the way out, when the incident is over and the write-up is more accurate anyway.

If the org runs ScriptRunner or JMWE, a genuinely priority-conditional validator is cleaner still — but the design deliberately does not depend on an app being available.

---

## 8. Fields

| Field | Type | Notes |
|---|---|---|
| Tower | Select (single) | Drives routing + queues |
| Support Tier | Select | L1 / L2 / L3-Vendor — set by workflow, read-only to agents |
| Impact | Select | High / Medium / Low |
| Urgency | Select | High / Medium / Low |
| Priority | Select | **Derived** from Impact × Urgency via automation — see matrix below |
| Escalation Reason | Select | Required at escalation |
| Troubleshooting Performed | Paragraph | Required at escalation |
| Affected Service / CI | Select or text | Ties to service catalogue |
| Root Cause | Select | Set at resolution |
| Resolution Code | Select | Fixed / Workaround / No Fault Found / Duplicate / Withdrawn |

### Priority matrix (automate it — never let agents free-pick priority)

| Impact ↓ / Urgency → | High | Medium | Low |
|---|---|---|---|
| **High** | P1 | P2 | P3 |
| **Medium** | P2 | P3 | P3 |
| **Low** | P3 | P3 | P4 |

---

## 9. SLA targets **[JSM]**

| Priority | Time to First Response | Time to Resolution |
|---|---|---|
| P1 — Critical | 15 min | 4 hours |
| P2 — High | 30 min | 8 hours |
| P3 — Medium | 4 hours | 3 business days |
| P4 — Low | 8 hours | 5 business days |

**Pause conditions:** status in (Pending Customer, Pending Vendor). Getting this right is what makes SLA reports defensible — without it, every ticket blocked on a user looks like an SLA failure.

**Calendar:** P1/P2 on 24×7; P3/P4 on business hours. Confirm in §11.

---

## 10. Queues, automation, permissions, reporting

### Queues **[JSM]**
- `L1 — Unassigned` (Tier = L1, assignee empty) — the primary L1 work pool
- `L1 — My Open`
- `L2 — <Tower>` (one per tower, Tier = L2)
- `Breaching in < 1h` (across all tiers — the escalation-of-last-resort view)
- `P1 War Room` (all P1s, all tiers)

### Automation rules
1. **Priority derivation** — on create/edit of Impact or Urgency → set Priority from the matrix
2. **Tower auto-assignment** — on Tower set → assign to `ops-l2-<tower>` group on escalation
3. **P1 alert** — on P1 create → notify tower lead + on-call channel
4. **SLA breach warning** — at 75% of target → comment + notify assignee and lead
5. **Reopen handling** — Resolved → reopened within 7 days → back to Triage, flag `Reopened = true`
6. **Auto-close** — Resolved + no customer response for 5 days → Closed
7. **Stale ticket nudge** — no update in 3 business days → notify assignee

### Permissions
| Role | Rights |
|---|---|
| L1 Agent | Create, transition to L2, comment; **cannot** close P1 or set Root Cause |
| L2 Agent | Full transition rights within own tower; set Root Cause |
| Tower Lead | Reassign across towers, override priority, close P1 |
| Service Desk Manager | Full project admin, SLA config |
| Customer | Portal-only: raise, comment, view own **[JSM]** |

### Reporting — the metrics that actually matter
- **First-Time Resolution rate at L1** — target ≥ 65%; the single best measure of L1 health
- **Escalation rate by tower and by analyst** — spikes reveal training or staffing gaps
- **SLA attainment** by priority and tower
- **MTTR** by tower, split L1-resolved vs L2-resolved
- **Backlog aging** — tickets > 7 / 14 / 30 days
- **Reopen rate** — target < 5%; high values mean L1 is closing prematurely
- **Top 10 recurring issues** → Problem records → KB articles → L1 deflection

---

## 11. Open questions (blocking full build)

1. **Provision JSM, or build on Jira Software?** — see §2. This is the fork in the road.
2. **What are the actual towers?** — §5 is a generic guess; real domain names are needed.
3. **One project or one per tower?** — §3. Only split if towers are separate vendors with data isolation requirements.
4. **Team size and shift model?** — decides 24×7 vs business-hours SLA calendars and whether on-call routing is needed.
5. **Intake channels?** — portal only, or email / Slack / Teams / monitoring-tool webhooks?
6. **Is this a demo or a production rollout?** — a demo can skip permissions hardening and run on the JSM free tier; production needs §10 permissions in full plus a licence count.

---

## 12. Build phases

| Phase | Work | Depends on |
|---|---|---|
| **0. Decide** | Resolve Q1–Q3 in §11 | — |
| **1. Foundation** | Provision JSM; create company-managed `OPS`; create groups and roles | Phase 0 |
| **2. Schema** | Custom fields (§8), issue types (§6), screens, field configs | Phase 1 |
| **3. Workflow** | Statuses, transitions, escalation gate validator + post-functions (§7) | Phase 2 |
| **4. SLA & Queues** | SLA targets with pause conditions, per-tower queues (§9, §10) | Phase 3 |
| **5. Automation** | The 7 rules in §10 | Phase 4 |
| **6. Reporting** | Dashboards per §10 | Phase 5 |
| **7. Pilot** | One tower, ~2 weeks, seeded test tickets; tune SLA and escalation gate | Phase 6 |
| **8. Rollout** | Remaining towers; KB seeded from pilot's top recurring issues | Phase 7 |

Phases 2–4 are REST-API scriptable against this instance (verified: fields, screens, statuses, workflows, schemes and permission schemes all return 200), so the structural build is automated and version-controlled rather than clicked through the admin UI.

Two exceptions, verified rather than assumed: **Automation rules have no public Cloud REST API** (`/rest/api/3/automation/rules` returns 404) — they are built in the rule builder and version-controlled via Automation's JSON export/import. **SLA and queue configuration** is a JSM UI task. See `LIVEDEMO.md` for the full capability probe.

---

## Security note

The API token used to survey this instance was shared in plaintext chat. It grants **full site-admin** access. Rotate it at
`https://id.atlassian.com/manage-profile/security/api-tokens` once this work is done, and for the scripted build use a token stored in an environment variable rather than inline.
