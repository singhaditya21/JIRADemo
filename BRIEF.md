# Building an L1/L2 Support Tower on Jira

**A one-page brief** · Aditya Singh · 2026-07-20

---

### The problem is not "we need a ticket system"

Every L1/L2 support tower already has one. They fail anyway, and they fail the same three ways:

1. **Ticket ping-pong.** L1 forwards to L2 without troubleshooting. L2 sends it back. Nobody owns it.
2. **L1 can't prove its value.** If you can't measure what L1 resolves without escalating, L1 looks like an expensive switchboard — and gets cut.
3. **SLA reports nobody trusts.** Clocks that run while a ticket waits on the customer make every team look like it's failing, so leadership stops reading the report.

All three are *configuration* problems, not people problems. That's the good news — configuration is fixable in weeks.

---

### The design decision that fixes all three

**Tier is a workflow state. Tower is a field. It is one project, one ticket, one clock.**

The instinct is to give L1 and L2 separate projects or separate queues that hand off between them. That instinct is the root cause. A handoff creates a new ticket ID, restarts the SLA clock, and splits the audit trail — which is precisely why ping-pong is invisible, why L1's contribution can't be measured, and why MTTR can't be computed end to end.

Instead, escalation becomes a **workflow transition** that flips a `Support Tier` field from L1 to L2 and reassigns to the tower group. Same ticket key. Same clock, running continuously. One history showing every hand that touched it.

Everything else in the build follows from that one choice.

---

### The mechanism: enforce discipline in config, not policy

"L1 must troubleshoot before escalating" is a policy. Policies erode under queue pressure.

Put a **workflow validator** on the `In Progress L1 → Escalated to L2` transition that will not let the ticket move unless the agent has filled in Escalation Reason, Troubleshooting Performed, and KB Article Checked. A **post-function** then sets the tier and clears the assignee so the ticket lands in a tower queue rather than on a named person.

The gate does two jobs. It blocks the lazy escalation, and it generates the data for **escalation rate per analyst** — the single metric that tells you whether L1 is working, and who needs coaching.

**But the gate must not apply to a major incident.** Forcing a paragraph of write-up while the business is stopped trades outage minutes for paperwork. So there is a second transition — `Escalate — major incident` — with no validators, restricted to the **Major Incident Manager role**. Role-restricted rather than priority-conditional, because native Jira conditions branch on role and permission rather than field value, so this works without a paid app; and because a fast path should be a deliberate, accountable act rather than a free choice under pressure. Nothing is lost: a validator on `Resolved → Closed` requires the same three fields on every ticket, so majors pay the gate on the way out, when the write-up is more accurate anyway.

Two other things get automated for the same reason: **priority** is derived from an Impact × Urgency matrix rather than agent-picked, and **SLA clocks pause** when a ticket is waiting on a customer or vendor. The first stops priority inflation. The second is what makes the SLA report defensible enough that leadership keeps reading it.

---

### The scoreboard

Six metrics, and only six. They are chosen so that gaming one degrades another.

| Metric | Target | What it tells you |
|---|---|---|
| First-time resolution at L1 | ≥ 65% | Is L1 actually resolving, or just routing |
| Escalation rate per analyst | Trend | Who needs coaching; where the KB has gaps |
| Reopen rate | < 5% | Whether L1 is closing prematurely to game FTR |
| SLA attainment by priority | ≥ 95% | Contractual health |
| MTTR, split L1 vs L2 | Trend | Where time actually goes |
| Backlog aging > 14 days | → 0 | What's quietly rotting |

*FTR and reopen rate are deliberately paired: you cannot inflate one without the other exposing you.*

---

### Where the value is — stated without a fabricated number

Every unit of demand L1 absorbs is a unit L2 does not pay for, and L2 capacity is the scarce, expensive resource. That is the economic argument, and it holds without needing a spreadsheet.

**There is deliberately no ROI model here.** Building one would mean inventing a per-ticket cost, a baseline resolution rate and a monthly volume — none of which has been measured for this organisation. A fabricated model invites argument about the inputs instead of the mechanism, and it is the single most likely thing to fail under questioning.

The honest sequence is instrument, measure a baseline through the pilot, then quantify. The pilot produces the real numbers in two weeks; anything offered before that is decoration. The build itself is configuration against an existing Jira licence, not new software spend.

---

### Can it actually be built?

Yes, and the structural half of it without touching the admin UI. Custom fields, issue types, screens, statuses, workflows and validators are all reachable through the Jira REST API — so that part of the build is scriptable, version-controlled and reproducible across environments rather than a series of undocumented clicks.

Two honest exceptions. **Automation rules have no public Cloud REST API**; they are built in the rule builder and version-controlled through Automation's JSON export/import. **SLA targets and queues** are configured in the Service Management UI. Structure is scripted, rules are exported JSON, SLA config is UI — that division is worth stating plainly, because it is the shape of every real Jira build.

**One licensing caveat, worth raising early:** SLAs, agent queues, request types, approvals, and the customer portal are Jira **Service Management** features. They do not exist in Jira Software. A tower built on Jira Software alone means hand-rolling an SLA clock in automation rules — the most brittle possible foundation. JSM's free tier covers 3 agents and includes the full SLA engine, which is enough to build and prove the entire design before anyone signs a purchase order.

---

### Delivery

Eight phases, roughly eight weeks to full rollout, with a working system far earlier.

**Decide** (licensing, tower list) → **Foundation** (project, groups, roles) → **Schema** (fields, issue types, screens) → **Workflow** (statuses, the escalation gate) → **SLA & Queues** → **Automation** → **Reporting** → **Pilot one tower, two weeks** → **Roll out the rest.**

The pilot is not a formality. It is where SLA targets and the escalation gate get tuned against real traffic, and where the first Problem records turn into the KB articles that drive L1 deflection in every tower that follows.

**Biggest risk:** agents route around the escalation gate by misusing a different transition. **Mitigation:** the pilot's escalation-rate data exposes it within days, and transition permissions are tightened before rollout.

---

**Appendix:** full design — field schema, status model, SLA targets, priority matrix, permission scheme, and the seven automation rules — is in `PLAN.md`.
