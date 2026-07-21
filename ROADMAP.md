# The Support Control Tower — Product Roadmap

*A tier-aware, escalation-aware intelligence layer for the people who run an L1/L2 support
tower. Grounded in the live instance — `OPS` (Jira Software, 420 issues, 171 escalated) and
`ITSM` (Jira Service Management, 421 issues) on `singhaditya21.atlassian.net`, 90-day window,
baked 2026-07-21. Every number below is measured, not aspired.*

---

## Executive Summary

**What it is.** The control tower is the decision surface for the people who run an L1/L2
support tower: a tier-aware, escalation-aware intelligence layer that reads one continuous
Jira ticket record and answers, in under ten seconds, the single question each role has to
answer that day. It renders as a dashboard but it is not one — a dashboard shows you a
number; this shows you *the number, its numerator and denominator, and the ticket rows behind
the mark*. Every rate in the metric core carries its `num` and `den` (FTR is `215/347`, not
"62%"; resolution SLA is `305/387`, not "79%") because a percentage without its denominator
is the exact failure this product exists to argue against.

**The thesis — one modelling choice everything is downstream of.** *Tier is a workflow STATE,
tower is a FIELD, escalation is a GATED transition.* One issue key, one continuous SLA clock,
one audit trail. That single choice is what makes the hard questions — *is L1 absorbing
enough? which tower to pilot? is this analyst an outlier or noise?* — answerable from data at
all. Split the tiers across two projects and First-Time Resolution becomes unmeasurable, which
is precisely why, in most shops, "L1 reads as a switchboard with a headcount and gets cut."

**Why it beats a native Jira dashboard.** Native gadget grids fail this job for reasons that
are structural, not cosmetic: they cannot rewind a custom datetime (so they cannot draw the
backlog *staling* in place — open flat at ~65 while aged climbs 0→60); they show rates without
denominators; they have no concept of tier as a lens; they cannot pair two metrics on a shared
denominator so neither can be gamed; and they drift silently from the source of truth. The
native dashboard is a *report*. This is an *instrument* — it knows what it cannot honestly say,
and says so in its own footer.

**The North Star.** **L1 First-Time Resolution — the share of closed non-Problem tickets
resolved without ever leaving L1.** Live: `215/347 = 61.8%`, target ≥65%, verdict GAP —
**conditioned on reopen ≤ 5%** (`15/347 = 4.3%`, PASS), reported always as a pair so FTR bought
by premature closure is caught in the same chart. Three drivers move it: L1 capability (the KB
loop — 46% of escalations found no article, the single largest measured lever), gate discipline
(escalation 40.7% against a ≤35% target, every analyst inside a 2σ band), and demand quality
(intake mix, with shadow Chat now visible at ~10%).

**The phased spine.** The horizons are cut where the hard dependencies fall — you cannot alert
on a signal you refresh once a day, drill to a record you never emitted, or trust a trend built
on a gate nobody enforces.

| Horizon | Codename | Theme | The one thing it unlocks |
|---|---|---|---|
| **Now** (0–3 mo) | *Trustworthy Instrument* | Enforce the gate; make numbers defensible under scrutiny | A tower you can hand to an operator, not just demo |
| **Next** (3–9 mo) | *From Snapshot to Signal* | Record-level data + fresher backend + an insights layer | Drill-to-record, and alerting that fires while a ticket can still be saved |
| **Later** (9–18 mo+) | *Close the Loops* | Turn measurement into capability: KB loop, problem loop, cross-instance | L1's resolution ceiling stops being fixed |

**The arc.** *Instrument* (built — make the tower legible) → *Decide* (near — thresholds,
computed pilot verdicts, KB backlog served in priority order) → *Operate* (vision — staffing,
gate tuning, a closed loop from resolved ticket back into L1 capability). Only the first stage
is built today; this roadmap sequences the other two.

**The three highest-leverage bets.** (1) Enforce the escalation gate and ship the record layer
(Now) — the smallest work unlocking the most downstream capability. (2) The near-real-time
backend (Next) — the hard dependency gating all alerting. (3) The KB loop (Later) — 79 of 171
escalations found no article; every other improvement makes the tower *see* better, this one
makes it *get* better.

---

## Table of Contents

- **Executive Summary**
- **Part I — The Phased Roadmap** (the spine): horizons, themes, sequencing, dependencies; the
  horizon × workstream table; what we are deliberately not doing yet.
- **Part II — Personas, Jobs-to-be-Done & the North Star**: six personas and their
  under-ten-second question; the North Star and its supporting metric tree; what "great" looks
  like in 18 months.
- **Part III — The Drill-Down System** (the headline feature): the four-layer drill —
  aggregate → cohort → record list → single record — in one resizable, pinnable, back-stacked
  right-side panel; the bake-pipeline change that makes record layers exist.
- **Part IV — The OPS Chart & Metric Catalog** (exhaustive): 13 themes, ~50 charts, each with
  what it measures, the decision it drives, its visual, its insight, and its drill.
- **Part V — The ITSM Chart & Metric Catalog** (exhaustive, and deliberately distinct): why
  ITSM's catalog is not OPS's; the four ITIL practices OPS structurally cannot cover; the
  data-quality remediation board.
- **Part VI — The Insights & Intelligence Layer**: narrative insights, anomaly detection,
  benchmarks, prescriptive recommendations, the daily digest, alerting, NLQ, forecasting.
- **Part VII — Information Design, Layout & Space Optimisation**: the density laws, the
  responsive grid, how every chart fills its box, the drill panel's coexistence with the board.
- **Part VIII — Data & Analytics Foundation**: the record-level projection, the pure-core
  discipline, segmentation, historical snapshots, timeline-derived SLA, invariants, freshness
  tiers, multi-instance scaling, access-tiered privacy.
- **Part IX — Adoption, Success Metrics, Governance, Risks & Differentiation**: how it lands,
  product-vs-tower metrics, make-vs-buy moat, governance, privacy, top risks.
- **Appendix A — Chart Index / Glossary**: every chart in one place, keyed to its part.
- **Closing — If We Only Did Three Things.**

---

# Part I — The Phased Roadmap

This is the spine. Every other part hangs a set of capabilities off the three horizons named
here, and each capability sits in exactly one horizon for a reason stated below. The ordering
is not a wish list sorted by appetite; it is a dependency graph. You cannot alert on a signal
you refresh once a day, you cannot drill to a record you never emitted, and you cannot trust a
trend built on a gate nobody enforces. The horizons are cut where the hard dependencies fall.

We anchor to what is actually true today, not to the design aspiration. `OPS` is a live Jira
Software tower — 420 issues, 171 at Support Tier L2, 156 with a real `Escalated to L2` status
transition in the changelog, 79 of 171 escalations flagged `KB Article Checked = "Yes - none
found"`, seven automation rules built and enabled. The tower itself is a React app on GitHub
Pages, fed by an **aggregate JSON snapshot** (`OPS-90.json`, `ITSM-90.json`) baked daily by CI
from `app/analytics.py`. That snapshot shape — `scoreboard`, `weekly`, `towers`, `analysts`,
`kb`, `ageing`, `invariants` — is the ground the roadmap builds on, and its two structural
limits (it is a **daily** bake, and it carries **aggregates not records**) are the two
constraints the first two horizons exist to lift.

## NOW (0–3 months) — *Trustworthy Instrument*

**Theme.** Everything the tower currently shows is *computed correctly* — `analytics.py`
reproduces `metrics.py`'s JQL field-for-field, carries every rate with its numerator and
denominator, and abstains (`rate_point` returns `None`) rather than plot a 3-ticket week as 0%
or 100%. But two things undermine it in the room: the escalation gate that generates all that
data is **designed and seeded, not enforced**, and the drill drawers bottom out at an aggregate
plus a Jira deep link rather than the actual rows. Now is about removing the sentences that
begin "well, on a real instance…".

**Outcomes.**
- The `In Progress L1 → Escalated to L2` transition **rejects** an escalation missing
  `Escalation Reason` (`customfield_10046`), `Troubleshooting Performed` (`customfield_10055`),
  or `KB Article Checked` (`customfield_10047`). Today the gate is UI-only: `workflows/create`
  rejects `system:field-required` over REST, so the validator has never been built. This is the
  single highest-value 30-minute task on the instance, and it converts the escalation story from
  "seeded" to "enforced".
- Every `OPS` Closed ticket shows a real `resolution` — the 358 Done tickets currently reading
  "Unresolved" get the same backfill already run on `ITSM`. This is the one place a curious click
  during a demo exposes a defect. It needs explicit sign-off before writing to `OPS`, so it is
  scheduled Now, not deferred.
- The `invariants()` and `check_weekly_sums()` output is surfaced **in the page footer**, not
  just computed. The tower already knows when it is lying (e.g. `ITSM-265`, a Problem carrying a
  Response SLA verdict inside an SLA denominator). Showing that is what earns the right to show
  everything else.
- The `ITSM` native SLA engine is either retargeted off `created` (UI-only work, four SLAs) or
  explicitly fenced off. Until then the rule stands: do not open the native SLA panel, column, or
  report on `ITSM` — it returns `everBreached() = 0` across the project while the modelled
  `Resolution SLA` field shows 68 breaches.

**Headline capabilities** (owning part in brackets):
- *Data foundation (VIII):* keep the daily bake; add a **record-level export** alongside the
  aggregate — one JSON array of the fields `store.Issue` already carries. Prerequisite for all
  Next-horizon drill work, and cheap because CI already holds every row in memory when it computes
  `compute_all`.
- *Information design (VII):* every rate on the page renders as "61.8% · 215/347" and every
  `None` breaks the line rather than plotting zero. A policy to adopt now, before more panels
  arrive and the inconsistency calcifies.
- *Catalogs (IV/V):* publish the honest capability map — the escalation narrative lives in `OPS`;
  on `ITSM` it is tellable only on the nine named closed Service Requests. Badging `ITSM`
  escalation views as partial prevents the demo-day trap.

**Success gate to advance to Next.** (1) An escalation with a blank `Troubleshooting Performed`
is *refused* by the workflow, demonstrated live. (2) `invariants()` renders zero violations on
`OPS` and the footer shows it. (3) The record-level export ships in CI and a single drill drawer
resolves to a real list of issue keys. Until the record layer exists, nothing in Next is
buildable — so this gate is the true fork.

## NEXT (3–9 months) — *From Snapshot to Signal*

**Theme.** Two structural limits get lifted here, in dependency order. First the data goes
**record-level**, which turns the drill from "here is the number behind the mark" into "here are
the 79 tickets, filter and sort them." Then the backend goes **fresher than daily**, the
precondition — not the nice-to-have — for any alerting. You cannot warn at 75% of an SLA target
off a snapshot up to 24 hours stale; by the time the bake runs, a P1 with a 4-hour target has
already breached six times over.

**Sequencing within Next is itself a chain:**

```
  record-level data  ──►  drill-to-record  ──►  saved views / cohorts
        │
        └──►  near-real-time backend  ──►  live KPI strip  ──►  threshold alerting
                                                                      │
   insights engine (reads records) ──────────────────────────────────┘
```

**Outcomes.**
- **Drill-to-record.** Every mark — a scatter point in FTR-vs-reopen, a bar in the KB-gap
  breakdown, an analyst dot outside the 2σ band — opens a right-side drawer listing the underlying
  issue keys with their salient fields, each a Jira deep link. The record export shipped Now makes
  the drawer a thin client over it.
- **Near-real-time backend.** Move from the daily Pages bake to a scheduled short-interval refresh
  (15–30 min) or a webhook-driven update — the token stays server-side exactly as today; only the
  cadence changes. `analytics.py` is already pure with `now` as an argument, so the recompute is
  trivial; the work is in the ingestion path, not the math.
- **Insights engine v1.** The metric core already computes *judgments*, not just values:
  `analyst_escalation` emits a criterion-6 verdict, `pairing_note` emits a Pearson r with its n,
  `tower_table` emits a `pilot_score` = volume × (100 − FTR). The engine surfaces these as
  written-language findings rather than leaving the operator to read them out of a table.
- **Alerting v1.** Once the backend is fresh, the 75%-of-target breach warning (Rule 4's logic,
  currently a 15-minute Jira automation) gets a *dashboard-side* counterpart: the live KPI strip
  flips a tile and the insights feed posts "3 P1s inside the breach window." Built on the
  near-real-time backend, never before it.

**Success gate to advance to Later.** (1) A user can click any mark and reach the tickets behind
it. (2) The KPI strip reflects Jira within the refresh window, verified against a live JQL count.
(3) At least one insight is generated and rendered without a human writing the sentence. Loops
(Later) depend on the insights engine reliably identifying *what* to loop on.

## LATER (9–18 months+) — *Close the Loops*

**Theme.** The first two horizons make the tower *observable and trustworthy*. Later makes it
*generative* — it starts closing the two loops that are the deepest root cause: nothing converts
a solved L2 ticket into an L1-resolvable one (the KB loop), and nothing converts repeat incidents
into a problem record (the problem loop). This is where the tower stops describing the disease and
starts treating it.

**Outcomes.**
- **The KB loop.** Every escalation with `KB Article Checked = "Yes - none found"` (79 today, 46%
  of all escalations — the single largest measured lever) generates a **candidate KB article**
  seeded from the ticket's `Troubleshooting Performed` and `Root Cause`. The insights engine ranks
  the backlog; the loop turns the top of that ranking into draft articles routed for L2 review. As
  articles land, the KB-gap rate is the metric that must move — and the tower already charts it
  weekly (`kb_gap_series`).
- **The problem loop.** Recurring incidents — same `Affected Service`, same `Root Cause`,
  clustered in time — get surfaced as candidate Problem records. `OPS` already has the Problem
  issue type and deliberately excludes Problems from FTR; Later makes the tower *propose* the
  Problem, not just tolerate it.
- **Cross-tower and cross-instance.** The same aggregate+record model runs over multiple
  projects/instances behind one control tower — the model is already project-agnostic. This is
  where a multi-team or MSP deployment becomes real.
- **Predictive / triage assist.** Only here, once record history is deep and clean, does it become
  honest to suggest priority or tower at intake, or forecast breach risk. Built earlier it would
  train on seeded data whose `created` is uniformly today — exactly the trap `analytics.py` avoids
  by keying everything off `Reported At`.

**Success gate.** The KB-gap rate and the escalation rate both *move* against the pilot's own
measured baseline — not against an imported benchmark. That is the whole thesis paying out: L1's
resolution ceiling was fixed; now it rises.

## The roadmap table — horizon × workstream

| Workstream | Now (0–3 mo) | Next (3–9 mo) | Later (9–18 mo+) |
|---|---|---|---|
| **Data foundation** | Record-level export beside the daily aggregate; versioned schema | Near-real-time backend (15–30 min / webhook); record schema hardened | Multi-project / multi-instance ingestion |
| **Drill system** | One drawer resolves to real issue keys | Drill-to-record on every mark; cross-filter; saved cohorts | Loop-aware drawers (draft article / open Problem from a mark) |
| **Insights engine** | Surface `invariants()` + `weekly_sums` in the footer | Verdicts & rankings as prose (pilot_score, 2σ, Pearson r); KB-gap worklist | Recurrence detection; candidate KB & Problem generation; breach-risk |
| **Alerting** | — (deliberately not yet — backend too stale) | Dashboard-side 75%-of-target warnings on the live KPI strip | Predictive breach alerts; escalation-anomaly alerts |
| **OPS catalog** | Enforce escalation-gate validator (UI); backfill `resolution` on 358 tickets | Live KPI strip; cohort views mirroring filters 10035–10054 | KB loop live; problem loop live |
| **ITSM catalog** | Retarget or fence off native SLA; badge partial escalation views | Fold in portal + 19 queues + dashboard 10035 as second lens | Full ITIL: Change/CAB, major-incident, CSAT (once accounts/licensing resolved) |
| **Information design** | "value · num/den" everywhere; broken lines for `None` | Consistent drill affordance; live-vs-stale visual state | Loop/action affordances in the visual language |

## The three highest-leverage bets

1. **Enforce the gate and ship the record layer (Now).** Together they convert the tower from a
   persuasive demo into an operable instrument. The gate is a 30-minute UI task that makes the
   escalation story *true under load* rather than seeded; the record export is the cheap foundation
   (CI already has the rows) that every drill and insight in Next stands on. Highest leverage
   because it is the smallest work unlocking the most downstream capability.
2. **The near-real-time backend (Next).** The hard dependency gating *all* alerting, and alerting
   is what turns a report people admire into a report people act on. `analytics.py` is already pure
   with `now` as an argument, so the metric side is free — the bet is on ingestion cadence, and it
   pays for the entire alerting workstream at once.
3. **The KB loop (Later).** 79 of 171 escalations found no article — 46%, the largest single lever
   the data has ever measured, and the mechanism at the root of L1's permanently-capped ceiling.
   Every other improvement makes the tower *see* better; this one makes it *get* better. Last only
   because it depends on the insights engine (to rank what to write) and the record layer (to seed
   drafts) — but it is the bet the whole design exists to reach.

## What we are deliberately NOT doing yet

- **Provisioning real portal customers on `ITSM`.** It mints real Atlassian accounts and emails
  invitations with **no REST undo**; deferred until there is a reason to own that. Demo the portal
  from the authenticated session, never incognito.
- **Making the native JSM SLA engine the source of truth.** It measures from `created` (today for
  all seeded tickets) and reports zero breaches against 68 real ones. The modelled `Response/
  Resolution SLA` fields stay authoritative until native SLA is retargeted per priority.
- **Approvals / CAB as a live demo on `ITSM`.** All 25 tickets at `Waiting for approval` have an
  empty approver list because the single instance account is excluded from its own approvals; it
  needs a second account.
- **AI auto-resolution or auto-triage.** Off the table until the record history is deep and the
  loops have run — training on data whose `created` collapses to one date would encode exactly the
  lie the model is built to avoid.
- **A staffing model.** Explicit non-goal. The tower measures whether the team is resourced
  correctly; it does not size it.
- **Deleting any shared global object** — the 20 custom fields, four issue types, priority scheme
  10166 back *both* projects. Retiring `ITSM` means detaching from the scheme, never deleting it,
  or `OPS` breaks.

---

# Part II — Personas, Jobs-to-be-Done & the North Star

The spine says *what to build when*. This part says *who for* and *how we know it worked*. Six
personas run this tower; each is grounded in the real workflow — the eleven statuses, the
escalation gate's three fields, the KB loop, the priority matrix — not invented. For each: the
job-to-be-done, the daily decisions, and **the question the tower must answer in under ten
seconds.** The under-ten-seconds test is the product's actual spec.

## 1. Personas

### 2.1 L1 Agent — "the front line" (12 people, three shifts)

Real names in the model: A. Okafor, R. Mehta, S. Lindqvist, D. Fernandes (Shift A,
06:00–14:00); K. Yamamoto, T. Abara, M. Delacroix, P. Novak (Shift B); J. Whitfield, N. Haddad,
L. Petrov, C. Nkemelu (Shift C). 24×7 coverage is what justifies the P1/P2 round-the-clock SLA
targets.

- **Job-to-be-done:** absorb the majority of demand and resolve it first-time, so L2's scarce
  expertise is spent only where it is genuinely required. The entire economic case for the
  two-tier model rests on this one job.
- **Daily decisions:** *Is this mine to resolve, or does it escalate?* If it escalates, *have I
  actually earned the transition* — filled `Escalation Reason` (`cf_10046`), written
  `Troubleshooting Performed` (`cf_10055`), recorded `KB Article Checked` (`cf_10047`)? *Which of
  my open tickets is closest to a breach warning* (rule 4 fires at 75% of target)?
- **10-second question:** *"Of the work I've handled this window, how much did I escalate — and
  am I inside the 2σ band or an outlier?"* Answered from `analyst_escalation`, keyed on the **L1
  Analyst field** (`cf_10053`), never the Jira assignee — because on escalation the assignee moves
  to L2, and crediting the escalation to the person who *received* it would invert the metric.
  Today: pooled 40.7%, mean-across-analysts ~40%, sd ~9, band roughly [22%, 59%]; a new starter's
  first three tickets is excluded by `MIN_ANALYST_N = 20` so it cannot slacken the yardstick.
- **What the tower protects them from:** being measured on volume alone (which rewards
  cherry-picking easy tickets) and being blamed for SLA misses that are actually the customer's
  silence (rule 5 pauses the clock in Pending Customer / Pending Vendor).

### 2.2 L2 Specialist / SME — "the tower expert" (10 people, business hours + on-call)

Real names: e.g. F. Costa & W. Njoroge (Network & Connectivity), I. Marchetti & O. Sandoval
(Compute & Storage). Deep expertise in **one** of the six towers.

- **Job-to-be-done:** resolve what L1 genuinely cannot, set `Root Cause` (`cf_10048`, 8 options)
  and `Resolution Code` (`cf_10049`), and — the job chronically skipped — feed knowledge *back* so
  the same ticket does not escalate again next month.
- **Daily decisions:** *Which escalation in my tower's queue do I take first?* *Is this a one-off
  or the fortieth instance of a recurring failure that should become a Problem record?* *When I
  closed that hard one last week, did I leave a KB article, or close it in a comment L1 will never
  read?*
- **10-second question:** *"What escalated into my tower this window with no KB article to hand,
  and what root causes cluster?"* Answered by `kb_gap_breakdown` by tower and by escalation reason
  — the KB backlog in priority order. Instance-wide, **79 of 171 escalations (46%) found no
  article** (`KB Article Checked = "Yes - none found"`, distinguished in code from "No" = *not
  checked*, so the backlog is never overstated). That 46% is the single largest lever in the design.
- **What the tower protects them from:** working recurring incidents from scratch, and being the
  invisible destination of ungated dumps from L1 — the gate's three required fields mean every
  ticket that reaches them arrives with diagnosis attached.

### 2.3 Team Lead / Shift Lead — "the person accountable for the queue right now"

- **Job-to-be-done:** keep the live queue healthy across a shift — nothing breaching unseen,
  nobody drowning, the hard tickets not aging quietly at the bottom.
- **Daily decisions:** *Who is escalating anomalously and needs coaching* (a spike is a training
  or staffing signal, not a character flaw)? *What is aging that the tower actually OWNS versus
  what is legitimately paused on someone else?* *Is a P1 sitting in a queue instead of being
  worked* (rule 3 assigns P1s to the Major Incident Manager and fires the notification)?
- **10-second question:** *"Of my open backlog, how much is mine to move versus paused — and
  what's oldest that I own?"* Answered by `ageing_by_status`, which splits the open set into
  **owned vs paused**: on `OPS` today, of 62 open, 41 are the tower's own queue and 21 are
  legitimately paused (14 Pending Customer, 7 Pending Vendor). Without that split the panel would
  *accuse the tower of 21 tickets it is not holding*. And the ageing histogram shows the real
  shape: **54 of 62 open are over 30 days old, oldest 84 days** — nothing new is sitting, the
  backlog is staling in place.
- **What the tower protects them from:** the ownership vacuum after handoff — because the key
  never changes and the clock never resets, "whose court is the ball in" is always answerable.

### 2.4 Service / Ops Manager — "the person accountable for the function"

- **Job-to-be-done:** run the tower as a system — is L1 absorbing enough, is escalation
  concentrated where it signals a gap, is the SLA report *trustworthy enough to be read*, and
  which tower should the next improvement pilot target?
- **Daily/weekly decisions:** *Which tower is both big and weak enough to pilot an intervention?*
  (the `tower_table` `pilot_score = volume × (100 − FTR%)` ranks exactly this — big AND weak ranks
  first, and the score is emitted so the ranking is *auditable*, not asserted). *Is FTR moving
  toward the 65% target* (today 61.8% — a GAP, honestly labelled)? *Is the reopen rate low enough
  that FTR is honest* (4.3%, a PASS)?
- **10-second question:** *"Is the tower healthy this window, and if not, where do I intervene
  first?"* The six-tile scoreboard answers health with verdicts: FTR 61.8% GAP, escalation 40.7%
  GAP, reopen 4.3% PASS, resolution SLA 78.9% GAP, response SLA 96.6% PASS, aged-14d 60 GAP. The
  tower comparison answers *where*: EUC is the largest tower (122 tickets) and typically carries
  the highest pilot score.
- **What the tower protects them from:** distrusting the SLA report. Rule 5's pause is "the rule
  that makes the SLA report trustworthy"; without it every ticket waiting on a user reads as a
  failure and leadership stops opening the report — taking the tower's only feedback loop with it.

### 2.5 Exec / CIO — "the person who funds it"

- **Job-to-be-done:** decide whether the tower is worth what it costs, and whether to fund the
  next stage (JSM provisioning, headcount, automation). The recurring failure: **L1 reads as "a
  switchboard with a headcount" and gets cut** — which raises L2 load and worsens everything,
  because L1's contribution was never *measurable*.
- **Decisions:** *Is L1 demonstrably absorbing demand?* *Is the trend improving quarter over
  quarter?* *Is shadow support shrinking as the tower captures it?*
- **10-second question:** *"Is L1 earning its keep, and is the whole thing getting better or
  worse?"* Answered by the FTR figure with its denominator (`215/347` — a number that *exists*
  only because tier is a state on one key) and the weekly cohort trend. And by the intake mix:
  **Chat = 43 of 420 (10.2%)** is shadow support *dragged into the record* — the most dangerous
  failure because it looks like success.
- **What the tower gives them that no gadget can:** a defensible answer to "what does L1 do?"
  backed by an auditable trail, so the budget conversation is about the mechanism, not the number.

### 2.6 (ITSM) Service-Desk Manager & Change Manager — "the customer-facing twin"

ITSM is a different practice from OPS: customer portal (17 request types), 19 agent queues,
native SLA engine, approvals/CAB, incident/request/change/problem. Two personas own it.

- **Service-Desk Manager — job:** run the customer-facing desk. **Decisions:** queue health
  across 19 queues; is the portal deflecting; is CSAT trending. **10-second question:** *"Is the
  customer-facing desk breaching, and where?"* — answered by the modelled `Resolution SLA` field
  (Met 235 / Breached 68 / In progress 57 / Paused 48), **never the native JSM SLA engine, which
  measures from `created` and is wrong** (`everBreached()` returns 0 project-wide). The tower's job
  here is partly to route the manager *away from* the broken native panel toward the honest one.
- **Change Manager — job:** shepherd changes through CAB approval. **Decisions:** what is awaiting
  CAB, what is cleared to implement, what is stuck. **10-second question:** *"What is at the
  approval gate and for how long?"* — answered from the Change workflow (`Awaiting CAB approval →
  Awaiting implementation`, which runs on ordinary transitions and works end-to-end), **not** the
  native Approvals panel (25 tickets at the gate with an empty approver list; needs a second
  Atlassian account to demonstrate).

> **A candid persona-fidelity note the roadmap carries forward.** On the ITSM twin, three of
> these personas' questions are answerable only via the *modelled* fields, because the native
> engines measure the wrong dates or lack a second account. The vision's Stage 3 ("Operate") is
> gated on JSM SLA retargeting and a real approver — both UI-only or account-blocked today. The
> product is honest about this: it points each persona at the surface that is *true*, and names
> the ones that are not.

## 2. The North Star and the supporting metric tree

**North-Star Metric: L1 First-Time Resolution rate — the share of closed non-Problem tickets
resolved without ever leaving L1.** Live baseline: **`215/347 = 61.8%` (`OPS`, 90-day window),
target ≥ 65%, verdict GAP.**

Why FTR and not SLA attainment or MTTR:

- It is **the single best measure of L1 health** and the direct measure of whether the two-tier
  model's founding assumption — L1 absorbs the majority of volume — is holding. If FTR rises, L2
  load falls, cost falls, and every downstream symptom eases.
- It is **the one number the whole structure was built to make computable.** FTR only exists as an
  honest metric because tier is a *state* on one continuous key. Split the tiers across projects
  and FTR is unmeasurable — which is exactly why L1 "reads as a switchboard and gets cut."
- It is **gamed only in company.** FTR moves up if you close prematurely; but premature closes
  reappear as reopens (`Reopened`, `cf_10052`), and FTR is defined on a shared denominator with
  reopen so *both answer together*. A North Star you cannot cheat alone is the right one.

**The North Star is FTR *conditioned on reopen ≤ 5%.*** Report them as a pair, always. 61.8% FTR
at 4.3% reopen is real progress; 70% FTR at 12% reopen is a tower closing tickets it hasn't fixed.

The supporting tree — FTR is the root; everything below is an input that, if it moves, moves FTR:

```
                     NORTH STAR
        L1 First-Time Resolution  (215/347 = 61.8%, tgt ≥65%)
        — conditioned on Reopen ≤ 5% (15/347 = 4.3%, PASS) —
                          │
      ┌───────────────────┼────────────────────┐
  DRIVER A            DRIVER B              DRIVER C
  L1 capability      Gate discipline       Demand quality
  (KB loop)          (escalation)          (intake)
      │                   │                     │
  KB gap 46%         Escalation 40.7%      Intake mix
  79/171             171/419, tgt ≤35%     Chat 10.2% (shadow)
  per-tower backlog  per-analyst 2σ (0 out) channel quality: FTR/esc by channel
      │                   │                     │
      └─────────► GUARDRAILS (must not degrade as FTR is pushed) ◄──────┘
        Resolution SLA 78.9% (305/387, GAP) · Response SLA 96.6% (PASS)
        Aged >14d 60 (54 of them >30d) · Owned/paused backlog 41/21 of 62 open
```

- **Driver A — L1 capability (the KB loop).** The 46% KB-gap rate is the ceiling on FTR. Every
  escalation with `KB Article Checked = "Yes - none found"` is a candidate article; write it and
  the next instance resolves at L1. `kb_gap_breakdown` serves this as a ranked worklist. **The
  highest-leverage driver.**
- **Driver B — gate discipline.** Escalation rate (40.7%, target ≤35%) is FTR's mirror. The
  per-analyst 2σ band (PILOT criterion 6) finds outliers — a spike is a coaching or staffing
  signal. The gate's three required fields make this a derivation from data rather than an opinion.
- **Driver C — demand quality.** `channel_quality` pairs FTR and escalation *by channel*: if Chat
  (shadow support, now visible at 10.2%) escalates far more than Portal, that is a finding about
  where demand is entering un-triaged.
- **Guardrails.** Push FTR without watching these and you get a tower that closes fast and wrong.
  Resolution SLA (78.9%, GAP) and the aged backlog (60 >14d, 54 of them >30d) are the two that say
  "you are going faster by leaving the hard work to rot."

Every node is already computed in `app/analytics.py` and rendered live. The roadmap's job is to
turn each from *observed* into *acted-on*.

## 3. What "great" looks like in 18 months

Stated so it can be checked, not asserted. Baselines are the pilot's own measured numbers; the
targets are directional shape, not imported benchmarks.

**On the metric tree (the outcome):** (1) **FTR has moved off 61.8% toward and past 65%, reopen
still under 5%** — and the move is *attributable* to specific KB articles and towers. (2) **KB gap
is materially below 46%** because the loop is closed; the gap has become a *flow* that drains, not
a *stock* that accumulates. (3) **The aged backlog is drained** — the 54-of-62-over-30-days shape
is gone. (4) **Escalation ≤ 35% with every analyst inside 2σ**, used for coaching not blame.

**On the product (the capability):** (5) **The tower is the daily surface for all six personas**,
each answered in under ten seconds. (6) **JSM is honest** — native SLA retargeted off `created`,
modelled and native SLA agree, approvals work with a real approver. (7) **The escalation gate is
enforced, not just seeded** — the workflow validator is live. (8) **The loop from resolution back
into capability is automatic** — resolved-with-no-KB nominates an article; recurring `Root Cause`
clusters nominate a Problem. Stage 3, "Operate," is real.

**The one-line test of "great":** a new Ops Manager opens the tower on their first morning, reads
the scoreboard, drills one mark to the ticket rows behind it, and knows — without asking anyone —
which tower to pilot next and why. The number is defensible because its denominator is right
there, the trail is one continuous key, and the page has already told them, in the footer,
everything it cannot honestly claim.

---

# Part III — The Drill-Down System

*The headline feature, and the one the stakeholder emphasised most. Every mark on the control
tower is a claim; the drill is the proof. This part specifies a four-layer drill — aggregate →
cohort → record list → single record — that lives in one resizable, pinnable, back-stacked
right-side drawer, and it specifies exactly what has to change in the bake pipeline to make the
record layers exist at all. It is the concrete UI expression of the data foundation in Part VIII
and the destination of every chart in Parts IV and V.*

## 0. The premise, and the one hard blocker

The tower today ships click-to-drill drawers on every mark, but they bottom out at the *numbers
behind the mark plus a Jira deep link*. That is layer (a) and half of (b). The stakeholder's ask
— "all possible layers of metrics and charts on the drill, down to the record" — requires layers
(c) and (d), and those do not exist yet **because the baked data does not carry issue records.**

Ground truth: `webapp/public/data/OPS-90.json` is the verbatim output of
`analytics.compute_all(rows, now, 90)`. Its top-level keys are `scoreboard`, `weekly`, `backlog`,
`ftr_vs_reopen`, `analysts`, `kb`, `towers`, `intake`, `channel_quality`, `ageing`,
`ageing_by_status`, `invariants`, `weekly_sums` — every one an *aggregate*. `total_issues` is a
scalar (420). There is no `issues[]`, no `records[]`, no per-key row anywhere. The React app has
never seen a single Jira issue; it has seen 20-odd pre-chewed rollups.

So the drill's record layers are, first, a **data-model change to the bake** (Part VIII §1), and
only second a UI change. §7 below specifies the emit; the rest specifies what the drawer does.

## 1. The drawer shell — one surface, four layers, a back stack

**One right-side drawer, not many.** Every mark on every panel opens the *same* drawer instance.
Not a tooltip, not a modal, not a per-panel popover. It docks to the right edge, pushes nothing,
overlays the canvas with a scrim only on mobile.

**Geometry.** Default width `clamp(420px, 38vw, 720px)`. Drag-handle on the left edge, resizable
`360px … 90vw`, persisted to `localStorage` per breakpoint. A **Pin** toggle: pinned, the drawer
reserves layout width and the dashboard reflows to the remaining canvas (so a pinned record list
sits *beside* the scatter it came from, and hovering a scatter point cross-highlights the matching
table row). Unpinned, it floats and dismisses on outside-click / `Esc`. A **Full-screen** toggle
for the record list at census scale (all 420).

**The back stack and breadcrumb.** The drawer holds a navigation stack, not a single view. Each
push appends a crumb; the header renders the full trail and every crumb is clickable to pop back:

```
FTR 61.96%  ›  L2 · Enterprise Apps · P2  ›  47 records  ›  OPS-2306
[layer a]      [layer b cohort filter]      [layer c list]   [layer d record]
```

`Esc` / browser-back / the header `‹` pops one frame; `⌫` on the list pops to (b); clicking the
root crumb collapses to (a). The stack survives a pin and a resize. Closing the drawer preserves
the stack for the session so a re-open resumes where you left. **Every layer is deep-linkable**
(§6): the stack serialises to the URL hash, so a drilled state is a shareable link.

## 2. Layer (a) — Aggregate context

The top frame answers *what is this number and is it good*, using fields `compute_all` already
emits. Every tile is a `tile()` dict carrying `value`, `num`, `den`, `target`, `direction`,
`verdict`. Contents:

- **Headline**: the value, large, with `num/den` beside it — `61.96%  215 / 347`. For `aged_14d`,
  `num`/`den` are `null` and the renderer suppresses the percent sign and shows the raw count `60`
  — it is a stock, not a rate.
- **Definition line**, verbatim from the metric's contract, including its *warts*: FTR states
  "closed non-Problem tickets resolved at L1; Cancelled counts as closed (6 on OPS, 3 at L1)";
  escalation states "denominator is every windowed issue, Problems included"; reopen states
  "numerator ranges the window, denominator is the closed set". These pre-empt the "why is *that*
  ticket in here" objection the record list in (c) will otherwise trigger.
- **Numerator / denominator as clickable chips.** `215 / 347` — clicking `347` opens the record
  list of the *denominator set*; clicking `215` opens the *numerator subset*. This is the
  aggregate→list jump, and why the list must know which predicate produced it (§3).
- **Target & verdict**: `target 65 · direction ge · GAP`. Business targets and the tower's own
  placeholders are visually distinguished — a placeholder target is a design guess and the drill
  labels it as such rather than laundering it into a KPI.
- **Trend spark**: the metric's `weekly` series inline, final bucket dimmed (a cohort still
  filling), points below `MIN_WEEK_DENOM` (10) broken not zeroed. Clicking a week point sets a
  `week` cohort filter and descends to (b).

## 3. Layer (b) — Cohort breakdown ("all possible layers of metrics and charts")

This is the layer the stakeholder means by *charts inside the drill*. Given the aggregate and its
record set, layer (b) slices that set along every dimension the `Issue` record carries and renders
a **small-multiples wall** of mini-charts *inside the drawer*. Each mini-chart is itself drillable:
clicking a bar adds that value as a cohort filter, updates the breadcrumb, and re-renders the
remaining charts against the narrowed set (cross-filter, Tableau-style). The record count updates
live in the crumb.

| Chart | Field (`Issue` attr) | Values on OPS | Overlay |
|---|---|---|---|
| By tower | `tower` (cf_10042) | EUC 122 · Ent Apps 103 · Network 63 · Database 48 · Compute 47 · Cloud 37 | rate per tower (`tower_table`) |
| By tier | `tier` (cf_10043) | L1 vs L2 (170 L2 in window) | — |
| By priority | `priority` P1–P4 | derived Impact×Urgency | SLA attainment per priority |
| By channel | `intake` (cf_10045) | Portal · Email · Monitoring · Chat 43 | FTR/esc per channel (`channel_quality`) |
| By status | `status` | New · Triage · In Progress L1 · Escalated to L2 · In Progress L2 · Pending Customer · Pending Vendor · Resolved · Closed | owned vs paused shading (`ageing_by_status`) |
| By analyst | `l1_analyst` (cf_10053) | ~12 named L1s | 2σ band from `analyst_escalation` |
| By week reported | `week` | 14 Mondays, 2026-04-20 … 2026-07-20 | cohort rate, `MIN_WEEK_DENOM` gaps broken |
| By escalation reason | `escalation_reason` (cf_10046) | 6 options | — (drill context for KB gap) |
| By root cause / resolution code | `root_cause` (8) / `resolution_code` (6) | closed set only | — |
| By SLA outcome | `resolution_sla` | Met 305 · Breached 82 · Paused 21 · In progress · None(=11 Problems) | — |

**Rules that keep (b) honest.** *Denominator discipline carries down* — a cohort slice recomputes
the metric with the same predicate structure as the headline (FTR's cohort excludes Problems from
num and den; escalation's does not); the drill must not silently "fix" the asymmetry, because a
slice that disagrees with the tower on the same screen is worse than one that reproduces a known
wart. *Rates below floor abstain* — a cohort with `< MIN_WEEK_DENOM` or `< MIN_ANALYST_N` = 20
shows its **count** but greys the **rate** and tags it "n too small to state a rate." *Paused /
In-progress / None are shown, not hidden* — the SLA breakdown renders all five states so the drill
*explains* why den=387 and not 419 rather than hiding the 32-ticket gap. The wall is virtualised;
only charts in view compute, and cross-filtering is sub-frame because the set is already local.

## 4. Layer (c) — The record LIST

The dense, multi-column, virtualised table of the actual Jira issues behind the number. This is
where the drill stops being a chart and becomes an audit.

**Column set (default, in order).** Every column maps to an `Issue` attr:

| # | Column | Source | Notes / render |
|---|---|---|---|
| 1 | **Key** | `key` + `url` | monospace, links to `site/browse/KEY` in new tab |
| 2 | Summary | `summary` | truncated, title on hover, grows with drawer width |
| 3 | Type | `issue_type` | Incident · Service Request · Change · Problem; Problem badged (excluded from FTR/reopen) |
| 4 | Status | `status` | colour by `status_category` |
| 5 | Tier | `tier` | L1 / L2 chip |
| 6 | Tower | `tower` | |
| 7 | Priority | `priority` | P1–P4, P1 flagged |
| 8 | L1 analyst | `l1_analyst` | the escalation is *this* person's, never the assignee |
| 9 | L2 analyst | `l2_analyst` | blank at L1 |
| 10 | Reporter/assignee | (system) | seeded = API account on all 420 — show, note the caveat |
| 11 | Reported | `reported_at` | the only real time axis; **not** Jira `created` |
| 12 | Age (d) | `age_days` | right-aligned; ≥14 shaded |
| 13 | SLA remaining / breach | `resolution_sla` + derived | Met/Breached/Paused/—(Problem); for open work, a computed time-to-target bar |
| 14 | Escalation reason | `escalation_reason` | blank if never escalated |
| 15 | KB checked | `kb_checked` | "Yes – none found" flagged red (the KB backlog) |
| 16 | Reopened | `reopened` | Yes badged |
| 17 | Root cause / resolution | `root_cause` / `resolution_code` | closed only |
| 18 | Last update | max(changelog.at) | relative |
| 19 | **Changelog hops** | `len(changelog)` | the tier-hop count; 0 flagged |

**Column management.** Picker (add/remove/reorder, persisted); presets per metric — FTR defaults
to Tier, Reopened, Resolution; KB-gap defaults to Escalation reason, KB checked, Tower; the aged
list to Age, Status, owned/paused. Density toggle; sticky header; Key column freezes on horizontal
scroll. **Sort & filter** on every column (multi-key with `Shift`-click); per-column text/
multi-select/range/boolean filters; a JQL-preview box shows the equivalent Jira query with an
**"Open all in Jira"** button handing the filtered set to the issue navigator via the existing
saved filters (`filter=10035…10054`) or constructed JQL.

**Filter provenance banner.** The header states *exactly* which predicate produced the list,
inherited from the aggregate + cohort crumbs: *"347 closed non-Problem tickets · window 90d ·
tower = Enterprise Apps"*. Non-negotiable because of the known warts: a reader who sees a Cancelled
ticket or a Problem in the escalation denominator will otherwise file a false bug.

**Virtualisation.** Windowed render (~40 DOM rows for a 420-row set); the design target is a real
instance at 10k–100k, so the list is built windowed from day one. Sorting/filtering runs on the
in-memory record array — no network. **Export** CSV/TSV/JSON of the *current filtered, sorted,
column-selected* view, filename encoding the provenance; "Copy keys" for pasting into a Jira `key
in (…)` query. **Per-row deep link + drill**: external Jira link on the Key, plus an internal
chevron pushing layer (d).

**The reconciliation invariant.** `count(list) === den` of the aggregate that opened it, by
construction, and the list footer asserts it: *"347 rows · matches denominator 347 ✓"*. If a
future data change breaks that equality the footer turns red — the same philosophy as
`invariants()`, surfaced to the user rather than buried.

## 5. Layer (d) — Single RECORD detail (the timeline is the point)

One issue, everything the tower knows about it, plus the two histories Jira draws poorly and this
tower draws well: the **tier-hop trail** and the **SLA clock split**.

**Header.** `OPS-2306` · summary · type · status · priority · external Jira link · prev/next
arrows that walk the *current filtered list order* (audit a cohort record by record without
popping back to (c)).

**Field panel — the full set**, grouped as the schema groups them: *Routing* (Tower, Support Tier,
Affected Service, Intake Channel); *Priority derivation* (Impact, Urgency → **Priority**, rendered
as the derivation it is — "High × High → P1", not a free choice); *Escalation gate* (Escalation
Reason, Troubleshooting Performed rendered from ADF, KB Article Checked — with a **gate-evidence
badge**: complete vs incomplete; on OPS 171/171 L2 tickets carry all three); *Closure* (Root Cause,
Resolution Code, Reopened); *SLA state* (Response SLA, Resolution SLA, L1/L2 Analyst); *Timeline
fields* (Reported At, First Response At, Escalated At, Resolved At — beside Jira's own
`created`/`resolutiondate` shown struck-through as the **counterexample**, both uniformly "today").

**The escalation / SLA TIMELINE (changelog).** A horizontal time-ribbon from `reported_at` to
`resolved_at`-or-`now`, built from `Issue.changelog`. It renders a **status band** (every status
transition as a segment: `New → Triage → In Progress L1 → Escalated to L2 → In Progress L2 →
Resolved → Closed`, each labelled with dwell time — the thesis made visual: one key, one continuous
clock, one trail); **tier-hop markers** on the `Escalated At` boundary tying the status hop to the
Support Tier flip and Rule 2 routing; and a **field-change lane** — Priority derivations, Reopened
flips, SLA verdict writes, KB field set — each a pip with a hover card (`frm → to @ at`).

**SLA clock breakdown — running vs paused.** The differentiating panel. Reconstruct the resolution
SLA clock from the changelog: sum elapsed time *outside* the paused statuses (Pending Customer,
Pending Vendor) as **running**, and time inside them as **paused**. Show a stacked bar `running |
paused` against the priority's target, the verdict, and the headroom/overrun. This is why the
tower's SLA report is defensible — a ticket that sat 3 days in Pending Customer is not billed for
the customer's silence — and the single-record view is where that stops being a claim and becomes
arithmetic. *(Response SLA has no pause concept, so its bar is single-tone.)*

**Divergence flags — the drill as lie-detector.** Field-vs-history contradictions must be shown,
not smoothed: **Tier field vs status history** (15 of 171 L2-tagged OPS tickets never passed
through the `Escalated to L2` status — if `tier == L2` but the changelog has no such hop, the
record shows a "tier set without a transition" warning); **Problem carrying an SLA verdict**
(ITSM-265 today — flag `is_problem` with a Met/Breached verdict, the exact offender `invariants()`
hunts, shown at the record it lives on); **Changelog truncated** (if `changelog_truncated`, show a
"history incomplete — call top_up_changelog" band rather than a false-complete ribbon).

**Related items & mini-charts.** Same-tower siblings, same-analyst tickets, same escalation-reason
cohort (each a one-click jump back to a (c) list); and mini-charts placing this record in context
— *its age vs the tower's ageing histogram*, *its analyst's escalation rate vs the 2σ band*, *its
week's cohort FTR*. "All possible layers of metrics and charts" realised at the leaf: the record is
always shown against the distribution it belongs to.

## 6. Interactions, deep links, sharing

- **Hover**: marks preview the drill (count + top-3 cohort) in a lightweight card; the full drawer
  is a click. Pinned-drawer list rows ↔ source-mark cross-highlight both directions.
- **Click**: opens/pushes the drawer at the layer appropriate to the mark — a scoreboard tile → (a);
  a scatter point → (b) pre-filtered to that analyst; a tower-comparison cell → (c) for that tower's
  metric; a changelog-derived mark → (d).
- **Keyboard**: `Esc`/`‹`/browser-back pop; `↑↓` move the list cursor, `Enter` opens (d), `←→` walk
  records in (d); `/` focuses list filter; `p` pin, `f` full-screen, `e` export, `c` copy keys.
  Full keyboard reachability — the drill is an audit tool and must work without a mouse.
- **Deep-linkable drill URLs**: the nav stack serialises to the hash, e.g.
  `#/OPS/90/ftr/cohort=tower:EntApps,tier:L2/list?sort=-age/record=OPS-2306`. Pasting it
  reconstructs the exact drawer state against that day's baked snapshot. **Share** copies it — "look
  at the FTR gap in Enterprise Apps" becomes a link that lands the recipient on the same 47 rows.
- **Provenance in every share**: the hash carries window + cohort + sort, so a shared link is
  self-describing and reconciles to the same denominator the sender saw (subject to snapshot date,
  which the drawer stamps: "as baked 2026-07-21 09:56Z").

## 7. The data model: baked/static vs live — what has to change

**Today (static).** The CI bake writes aggregates only. Layers (a) and (b) are *already possible*
from the current files — (b)'s cohort charts are re-slices of sets the reducer already walks, so
the cheapest first increment is to have the bake emit those cohort cross-tabs as first-class JSON.
But (c) and (d) need **records**.

**The emit change (required for (c)/(d)).** Extend the bake to serialise a per-project record array
— the `IssueStore.dump()` path already exists and round-trips every `_ISSUE_ATTRS` field including
the parsed `changelog`. Concretely: `OPS-records.json`, one object per issue with the columns §4
needs and the `changelog` §5 needs. At 420 issues with ≤9 changelog entries each this is small
(low hundreds of KB, gzip to tens). Keep it **separate from the aggregate file** and
**lazy-loaded**: the dashboard boots on the small aggregate JSON; the record array is fetched on
the *first* drill to (c). **Reconciliation is a build-time invariant** — the bake asserts
`len(records) == total_issues` and that each metric's denominator equals the count of records
satisfying its predicate; a drill list that can't match its headline fails CI, not the demo.

**Scale story for static.** 420 today; a real tower is 10k–100k. The path: (i) per-window slices
(`OPS-90-records.json`) cap the hot set; (ii) shard by tower/month for lazy fetch; (iii) drop
`changelog` from the list-level array and fetch it per-key only on descent to (d). The drawer's
lazy-fetch boundary (list vs record) maps cleanly onto this shard boundary.

**The live path (progressive enhancement, same UI).** The token stays in CI and never reaches the
browser. So "live" is either a thin read-only proxy that runs the same `store.fetch` against Jira
and returns records for one key or one JQL, or — for the single record — a direct deep link into
Jira as the escape hatch. The drawer is built so the **record source is pluggable**:
`getRecords(predicate)` and `getRecord(key)` resolve against the baked array by default and against
the proxy when one is configured. Layers (a)–(c) run entirely on the snapshot; only (d)'s "refresh
this record live" button, if present, crosses to Jira — and degrades to the browse link when no
proxy exists. **Freshness honesty**: every drilled view stamps the snapshot time and offers "open
live in Jira." It shows the baked truth, labels its age, and is always one link from the system of
record. It never implies real-time it doesn't have.

---

# Part IV — The OPS Chart & Metric Catalog

*The exhaustive catalog for the `OPS` Jira Software tower. Where Part III specifies how a drill
behaves, this part specifies what there is to drill into. Every mark here opens the right-side
drawer of Part III; every metric is a pure function in `app/analytics.py` over `app.store.Issue`
records.*

The OPS tower runs the tier-as-state model: `Support Tier` (`cf_10043`) is L1/L2/L3-Vendor,
`Tower` (`cf_10042`) is a six-value field, escalation is the gated transition `In Progress L1 →
Escalated to L2` — one issue key, one SLA clock keyed off `Reported At` (`cf_10057`), one
changelog. That model is what makes this catalog possible: nearly every metric is a *cut of a
single record set*, not a cross-project join.

Ground truth (live OPS, 90-day window, 2026-07-20): **420 issues · 171 escalated (40.71%) · FTR
215/348 (61.78%) · reopen 15/348 (4.31%) · resolution SLA 306/82 (78.87%) · response 96.58% · KB
gap 79/171 (46.20%) · 62 open · 60 aged ≥14d · 43 shadow-chat.** Every rate carries its num/den.

**Legend.** `[BUILT]` = live today · `[NEW]` = net-new · `[NO-ITSM]` = no honest ITSM equivalent.
Each entry: NAME · MEASURES (fields/statuses) · DECISION · VISUAL · INSIGHT · DRILL.

## Theme A — Intake & demand

**A1. Intake channel mix `[BUILT]`** · MEASURES: count by `Intake Channel` (`cf_10045`) in model
order Portal/Email/Monitoring/Chat; Chat flagged `shadow`. · DECISION: is shadow support (Chat)
material enough to formalise? · VISUAL: horizontal stacked bar / donut, Chat highlighted. ·
INSIGHT: Chat is 43/420 = 10.2% — demand that previously never reached a ticket. · DRILL:
`filter=10044`, record list of the 43.

**A2. Weekly intake volume (demand curve) `[BUILT]`** · MEASURES: `count` per `monday(reported_at)`
week across the 14-week axis, optionally split by channel. · DECISION: staffing to the arrival
curve, not the average. · VISUAL: stacked area over 14 weeks. · INSIGHT: whether demand is flat or
trending; current week dimmed (partial cohort). · DRILL: week bucket → issues reported that week.

**A3. Intake → priority skew `[NEW]`** · MEASURES: `Priority` distribution within each `Intake
Channel`; Monitoring is seeded to skew high-priority by design. · DECISION: does automated
(Monitoring) intake catch P1/P2 faster than human channels? · VISUAL: 100%-stacked bar, channel ×
priority. · INSIGHT: validates "monitoring intake makes P1 detection faster than a human noticing"
as measurement, not rhetoric. · DRILL: cell → Monitoring ∩ P1 issues.

**A4. Intake mix by tower `[NEW]`** · MEASURES: `Intake Channel` × `Tower` counts. · DECISION:
which towers are portal-mature vs still email/chat-driven. · VISUAL: heatmap (6 towers × 4
channels). · INSIGHT: a tower dominated by Chat is a formalisation target. · DRILL: cell → tower ∩
channel.

## Theme B — Triage & the front line (L1)

**B1. Front-line queue (L1 open work) `[BUILT]`** · MEASURES: `is_open` rows where `tier == L1`,
grouped by `status` in {New, Triage, In Progress L1}. · DECISION: where L1 work piles up before it
moves. · VISUAL: funnel New→Triage→In Progress L1. · INSIGHT: a New-heavy queue means triage is the
bottleneck, not resolution. · DRILL: `filter=10035` (L1 queue open).

**B2. Triage dwell (time in New+Triage) `[NEW][NO-ITSM]`** · MEASURES: reconstructed from the
timeline — for escalated/resolved rows, `first_response_at − reported_at` and time before `In
Progress L1`; ITSM cannot draw this because native history keys off `created` (uniformly today). ·
DECISION: is the delay in *starting* work or in *doing* it? · VISUAL: box-plot of dwell days per
tower. · INSIGHT: separates queue latency from handling time. · DRILL: outlier → issue with its
four timeline stamps.

**B3. First-response attainment (response SLA) `[BUILT]`** · MEASURES: `Response SLA` (`cf_10050`)
Met/Breached; live 96.58%. No Paused concept on response. · DECISION: is L1 acknowledging fast
enough. · VISUAL: gauge + trend line. · INSIGHT: response nearly always met (96.6%) while
resolution lags (78.9%) — the gap is *fixing*, not *answering*. · DRILL: breached-response issues.

**B4. First-response attainment by priority `[NEW]`** · MEASURES: response SLA Met/Breached split
by `Priority`, against P1 15m / P2 30m / P3 4h / P4 8h. · DECISION: are we fast where speed is
contractual (P1)? · VISUAL: small-multiple gauges per priority. · INSIGHT: a P1 response miss is a
different severity than P4. · DRILL: priority ∩ breached.

## Theme C — Escalation & the gate

**C1. Escalation rate (headline) `[BUILT]`** · MEASURES: `tier == L2` / all windowed rows, Problems
**included** (deliberate asymmetry vs FTR — reproduces metrics.py 171/420 = 40.71%). · DECISION: is
L1 resolving enough at first tier. · VISUAL: scoreboard tile, target 35% ("le"), verdict GAP. ·
INSIGHT: 40.7% > 35% — L1 is passing too much up. · DRILL: `filter=10036` L2 queue.

**C2. Escalation rate per L1 analyst — 2σ band `[BUILT][NO-ITSM]`** · MEASURES: per `L1 Analyst`
(`cf_10053`, a text field, **never** the Jira assignee), escalated/handled with tower mean and
±2σ; `MIN_ANALYST_N=20` floor excludes thin samples; per-analyst binomial z complements population
σ. · DECISION: PILOT exit criterion 6 ("no analyst diverges > 2σ") — computed, not asserted. ·
VISUAL: dot plot, analysts sorted by rate, shaded 2σ band, greyed sub-floor analysts. · INSIGHT:
"12 analysts, 0 outside 2σ — criterion 6 met." ITSM has no L1 Analyst discipline and its assignee
is the API account, so this cannot exist there. · DRILL: analyst dot → their escalations, with
`Escalation Reason` per ticket.

**C3. Escalation gate evidence completeness `[NEW]`** · MEASURES: of `tier == L2` rows, share
carrying all three gate fields — `Escalation Reason` (`_10046`), `Troubleshooting Performed`
(`_10055`), `KB Article Checked` (`_10047`). Live: 171/171 complete. · DECISION: is the gate
producing data or being bypassed? · VISUAL: completeness bar (3 fields × 171). · INSIGHT: proves
"the gate produces data, not just a refusal." · DRILL: any incomplete → the offending issue.

**C4. Gate-bypass detector (field-set-after-fact) `[NEW][NO-ITSM]`** · MEASURES: rows with `Support
Tier = L2` that **never passed through the `Escalated to L2` status** — 15 of 171 on OPS (156 have
real status history). Detectable only because status history exists in the Software workflow. ·
DECISION: which "escalations" are real transitions vs a field written directly. · VISUAL: 156 vs 15
split bar, the 15 listed. · INSIGHT: the OPS-local version of the ITSM problem (where 122 Incidents
claim L2 but 0 passed through Escalated) — so it doubles as the argument for demoing OPS. · DRILL:
the 15 keys; History tab deep link.

**C5. Why work escalates (escalation reason mix) `[BUILT]`** · MEASURES: count by `Escalation
Reason` across the 6 options (Requires elevated access / Beyond documented runbook / Suspected
platform defect / Vendor engagement required / Root cause unclear after triage / Change required to
resolve). · DECISION: which reasons are *fixable at L1* (access, runbook) vs *legitimately L2*
(platform defect). · VISUAL: horizontal bar, biggest first. · INSIGHT: "Requires elevated access"
and "Beyond documented runbook" are org/process fixes, not skill gaps. · DRILL: reason bar → issues
grouped by tower.

**C6. Escalation reason × tower matrix `[NEW]`** · MEASURES: `Escalation Reason` × `Tower` counts. ·
DECISION: targeted remediation — e.g. give EUC L1 elevated-access rights. · VISUAL: heatmap (6×6). ·
INSIGHT: reasons concentrate by tower; the fix is per-cell. · DRILL: cell.

**C7. Escalation reason × root cause confusion `[NEW]`** · MEASURES: `Escalation Reason` (at
escalation) vs `Root Cause` (`_10048`, set at resolution) for resolved L2 rows. · DECISION: were
escalations *diagnostically correct*? · VISUAL: Sankey / confusion matrix. · INSIGHT: "Suspected
platform defect" that resolves as "Configuration error" = an escalation that shouldn't have
happened — a training signal. · DRILL: mismatched cell → issues.

## Theme D — Tier flow & ping-pong

**D1. Tier flow Sankey `[NEW][NO-ITSM]`** · MEASURES: status-to-status transition counts from the
changelog across the 11 OPS statuses. · DECISION: visualise the actual paths vs the designed one. ·
VISUAL: Sankey. · INSIGHT: shows the L3/Vendor and Cancelled leakage paths; ITSM's Incident workflow
has no Escalated node so it cannot render this honestly. · DRILL: any flow edge → issues that took
it.

**D2. De-escalation / ping-pong count `[NEW]`** · MEASURES: rows whose changelog shows `In Progress
L2 → In Progress L1` (or re-entry into Escalated to L2 more than once). · DECISION: detect bouncing
between tiers — the hidden tax the single-key model is meant to expose. · VISUAL: count tile + list.
· INSIGHT: even a handful signals unclear L1/L2 ownership boundaries. · DRILL: the bouncing issues
with their transition sequence.

**D3. Time-in-tier decomposition (L1 vs L2 dwell) `[NEW][NO-ITSM]`** · MEASURES: from timeline
fields — L1 dwell = `escalated_at − reported_at`; L2 dwell = `resolved_at − escalated_at`; for
non-escalated resolved, L1 dwell = `resolved_at − reported_at`. · DECISION: where the calendar time
actually goes. · VISUAL: stacked horizontal bar per tower (L1 / L2 segment). · INSIGHT: a long *L1*
segment before escalation is wasted triage; a long *L2* segment is a specialist-capacity problem.
ITSM's collapsed history can't split this. · DRILL: bar → issues sorted by segment length.

**D4. Escalation latency `[NEW]`** · MEASURES: `escalated_at − reported_at` for L2 rows. · DECISION:
are we escalating early (good, if it's going to escalate anyway) or after L1 churns on it? · VISUAL:
histogram of latency days. · INSIGHT: late escalation is double-billed SLA time. · DRILL: bucket →
issues.

## Theme E — SLA (response vs resolution, pause-aware)

**E1. Resolution SLA outcome `[BUILT]`** · MEASURES: `Resolution SLA` (`_10051`) Met/Breached only;
**Paused, In progress, None excluded** — Paused (21 live: 14 Pending Customer, 7 Pending Vendor) is
the customer's silence, not the tower's failure; None = the 11 Problems. Live 306/82 = 78.87%. ·
DECISION: are we hitting resolution targets. · VISUAL: Met/Breached/Paused/In-progress donut with
only Met+Breached in the denominator. · INSIGHT: the pause-aware denominator is the trust mechanism
— without rule 5 every ticket waiting on a user reads as failure. · DRILL: `filter=10038`.

**E2. SLA attainment by priority `[NEW]`** · MEASURES: resolution SLA Met/Breached by `Priority`
against P1 4h / P2 8h / P3 3 business-days / P4 5 business-days, each on its **own calendar** (P1/P2
24×7, P3/P4 business hours). · DECISION: are breaches concentrated in contractually-critical
priorities? · VISUAL: grouped bar per priority. · INSIGHT: a P1 breach is a war-room event; a P4
breach is noise. Must never measure a business-hours P3 target on a 24×7 clock. · DRILL: priority ∩
breached.

**E3. Response vs resolution paired attainment `[NEW]`** · MEASURES: both SLA fields side by side;
response 96.58% vs resolution 78.87%. · DECISION: is the problem answering or fixing? · VISUAL: dual
gauge / slope. · INSIGHT: the 18-point gap localises the failure to resolution time. · DRILL: issues
that met response but breached resolution.

**E4. SLA pause coverage (rule 5 effectiveness) `[NEW]`** · MEASURES: rows in `Pending
Customer`/`Pending Vendor` with `Resolution SLA = Paused` vs those in a pending status *without*
Paused set. · DECISION: is automation rule 5 firing on every pending transition? · VISUAL: coverage
bar (should be 100%). · INSIGHT: any pending-but-not-paused row is a rule-5 miss that shows as a
false breach. · DRILL: the leaking issues.

**E5. Weekly SLA trend (cohort) `[BUILT]`** · MEASURES: `weekly_series` resolution & response rate
per reported-week cohort, `rate_point` with `MIN_WEEK_DENOM=10` floor. · DECISION: is attainment
improving or drifting. · VISUAL: two lines over 14 weeks, final bucket dimmed, gaps where denom <
10. · INSIGHT: cohort semantics — "of tickets *reported* that week, how many met SLA." · DRILL: week
point → that cohort.

**E6. Breach concentration by tower `[NEW]`** · MEASURES: breached-resolution count per `Tower`. ·
DECISION: which tower's SLA is failing. · VISUAL: bar. · INSIGHT: pairs with the tower table's
`sla_pct` column to rank remediation. · DRILL: tower ∩ breached.

## Theme F — Knowledge (KB gap / coverage / debt / deflection)

**F1. KB gap rate `[BUILT]`** · MEASURES: escalations where `KB Article Checked = "Yes - none
found"` / all L2 rows. Live 79/171 = 46.20%. The option means *checked and absent* — distinct from
"No" (not checked, a process failure). · DECISION: the single largest lever in the design — write
the missing articles. · VISUAL: scoreboard tile + weekly count bars. · INSIGHT: 79 tickets went to
L2 with no article to hand. · DRILL: `filter=10043`.

**F2. KB gap by tower (the write-next backlog) `[BUILT]`** · MEASURES: `kb_gap_breakdown` count of
"Yes - none found" per `Tower`, biggest first. · DECISION: prioritise which tower's KB to build. ·
VISUAL: ranked bar. · INSIGHT: the actionable output — the KB backlog in priority order. · DRILL:
tower → the gap issues (each an article to write).

**F3. KB gap by escalation reason `[BUILT]`** · MEASURES: gap count per `Escalation Reason`. ·
DECISION: what *kind* of article is missing (runbook vs access guide). · VISUAL: ranked bar. ·
INSIGHT: "Beyond documented runbook" gaps are runbooks to write. · DRILL: reason → issues.

**F4. KB check discipline `[NEW]`** · MEASURES: three-way split of `KB Article Checked` across L2
rows: "Yes - article applied" / "Yes - none found" / "No". · DECISION: separate *content gap* from
*process gap* ("No" = didn't check). · VISUAL: 100%-stacked bar. · INSIGHT: "No" rows are the ones
to coach; "none found" rows are the ones to author. · DRILL: segment → issues.

**F5. KB deflection potential `[NEW]`** · MEASURES: L1-resolved rows where `KB Article Checked =
"Yes - article applied"` vs escalated rows with "Yes - none found," grouped by `Root Cause` /
`Affected Service`. · DECISION: estimate escalations avoidable if the top-N missing articles
existed. · VISUAL: pareto of gap themes with cumulative deflection line. · INSIGHT: quantifies KB
ROI — "these 5 articles would have deflected N escalations." · DRILL: theme → issues. *Note:* ITSM
labels its equivalent a "KB Gap" queue but has **no knowledge base** (`knowledgebase/article` size
0); on OPS this is honestly the `KB Article Checked` evidence field.

## Theme G — Quality (FTR ↔ reopen, first-contact)

**G1. First-time resolution (FTR) `[BUILT]`** · MEASURES: closed rows (`counts_as_closed`,
non-Problem) with `tier == L1` / all closed. Live 215/348 = 61.78%. Problems excluded both sides.
Known wart: `Cancelled` has statusCategory Done, so 6 withdrawn tickets (3 at L1) count as
first-time resolutions — reproduced from metrics.py deliberately. · DECISION: the single best
measure of L1 health (target ≥65%). · VISUAL: scoreboard tile, verdict GAP. · INSIGHT: 61.8% < 65%.
· DRILL: L1-closed issues.

**G2. FTR ↔ reopen paired panel `[BUILT]`** · MEASURES: both on one chart, **shared denominator**
(the closed set); reopen numerator = `Reopened = Yes` (`_10052`) over the window, denom = closed. FTR
0-100 left axis, reopen 0-20 right axis, both labelled. · DECISION: is FTR real or bought by
premature closing? · VISUAL: dual-axis lines + `pairing_note` Pearson r ("r = -0.42 over 11 weeks,"
n visible, never causal). · INSIGHT: the honesty mechanism — lifting FTR by closing early enlarges
the reopen denominator, so neither metric moves alone. · DRILL: reopened issues (`filter=10041`).

**G3. Reopen rate `[BUILT]`** · MEASURES: `Reopened = Yes` / closed. Live 15/348 = 4.31%, target
<5%. Rule 6 sets the flag on `Resolved → Triage` within 7 days. · DECISION: is L1 closing
prematurely. · VISUAL: scoreboard tile, verdict PASS. · INSIGHT: 4.31% under target — closes are
sticking. · DRILL: the 15 reopened.

**G4. Reopen cohort by tower / resolver `[NEW]`** · MEASURES: reopened rows by `Tower` and by
original `L1 Analyst`/`L2 Analyst`. · DECISION: is premature-close concentrated somewhere. · VISUAL:
bar. · INSIGHT: one resolver or tower driving reopens is a targeted fix. · DRILL: group → issues.

**G5. Resolution code mix `[NEW]`** · MEASURES: distribution of `Resolution Code` (`_10049`: Fixed /
Workaround applied / No fault found / Duplicate / Withdrawn by requester / Referred to vendor /
Fulfilled / Implemented / Rolled back / Known error documented). · DECISION: quality of closures —
high "No fault found" or "Workaround" signals unresolved root cause. · VISUAL: treemap/bar. ·
INSIGHT: "Workaround applied" without a paired Problem is deferred debt. · DRILL: code → issues.

## Theme H — Capacity & analyst performance

**H1. L1 analyst load `[NEW][NO-ITSM]`** · MEASURES: handled count per `L1 Analyst` (denominator of
C2). · DECISION: is work evenly distributed across the 12 seeded L1? · VISUAL: bar, sorted. ·
INSIGHT: load imbalance confounds any per-analyst rate. ITSM assignee is the API account. · DRILL:
analyst → their issues.

**H2. L2 analyst load by tower `[NEW]`** · MEASURES: L2 rows per `L2 Analyst` within tower (e.g.
Cloud & Security has a single L2, Z. Adeyemi). · DECISION: single-point-of-failure detection. ·
VISUAL: bar grouped by tower. · INSIGHT: a one-person tower is a bus-factor risk. · DRILL: analyst →
issues.

**H3. Shift-level throughput `[NEW]`** · MEASURES: L1 handled/escalated aggregated to the three
shifts (A/B/C). · DECISION: is night shift (C) escalating more for lack of L2 cover? · VISUAL:
grouped bar per shift. · INSIGHT: staffing/coverage argument. · DRILL: shift → analysts → issues.

**H4. Handling time per analyst `[NEW]`** · MEASURES: median `lifetime_days`/`response_hours` per
analyst. · DECISION: efficiency vs the escalation-rate outlier check (fast-but-escalates vs
slow-but-resolves). · VISUAL: scatter (rate vs handling time). · INSIGHT: separates "dumps quickly"
from "works it then escalates." · DRILL: point → analyst issues.

## Theme I — Ageing & backlog flow

**I1. Aged backlog (≥14d) `[BUILT]`** · MEASURES: `is_open` and `reported_at ≤ now−14d`,
**unwindowed** snapshot. Live 60. · DECISION: how much old work is rotting. · VISUAL: scoreboard
tile, target 0. · INSIGHT: 60 tickets aged past 14 days. · DRILL: `filter=10040`.

**I2. Open-work ageing histogram `[BUILT]`** · MEASURES: `age_days` of open rows in half-open
buckets 0-3/3-7/7-14/14-30/30-60/60+; ≥14d shaded. Live: 62 open, min 7.4d, max 84.1d, 54/62 over 30
days. · DECISION: is the backlog new (fixable) or stale (rotting)? · VISUAL: histogram, breach
buckets shaded, "54 over 30d" annotated. · INSIGHT: bimodal-degenerate — nothing new is sitting; the
queue is ageing in place. · DRILL: bucket → issues.

**I3. Ageing owned vs paused `[BUILT]`** · MEASURES: same buckets split by whether `status` ∈
`SLA_PAUSED_STATUSES`; 21 paused (14 Pending Customer, 7 Pending Vendor) vs 41 owned. · DECISION:
don't accuse the tower of work it's legitimately waiting on. · VISUAL: stacked histogram. · INSIGHT:
41 of 62 open are the tower's *own* queue; 21 are waiting on someone else. · DRILL: owned/paused
segment → issues.

**I4. Backlog reconstruction (open vs aged over time) `[BUILT][NO-ITSM]`** · MEASURES:
`backlog_as_of(t)` at each week boundary — open flat ~65, aged climbs 0→60. Rests on the invariant
`resolved_at is None ⇔ not Done`. · DECISION: is the backlog *growing* or *staling*? · VISUAL: two
lines over 13 boundaries + now. · INSIGHT: "the backlog is not growing, it is staling — the same
queue, ageing in place." **Jira structurally cannot draw this** (no stored history of a custom
datetime field to rewind), the whole point. · DRILL: boundary point → issues open at that instant.

**I5. Flow: arrivals vs completions `[NEW]`** · MEASURES: per week, reported count vs resolved count
(net backlog change). · DECISION: are we keeping up with demand? · VISUAL: dual bar + cumulative net
line. · INSIGHT: weeks where arrivals > completions explain the aged climb. · DRILL: week → arrived /
resolved sets.

## Theme J — Priority / Impact × Urgency

**J1. Impact × Urgency matrix (priority derivation) `[NEW]`** · MEASURES: counts across the 3×3
`Impact` (`_10004`) × `Urgency` (`_10044`) grid, coloured by derived `Priority`. · DECISION: audit
that priority is *derived* (rule 1), never free-picked. · VISUAL: 3×3 heatmap. · INSIGHT: the
anti-inflation story made visible — agents answer two questions, automation assigns priority. ·
DRILL: cell → issues.

**J2. Priority-derivation conformance (rule 1) `[NEW]`** · MEASURES: rows where stored `Priority` ≠
`PRIORITY_MATRIX[(impact, urgency)]`. · DECISION: is automation rule 1 enforcing the matrix? ·
VISUAL: conformance % + violation list. · INSIGHT: any non-conforming row is a manual override or a
rule failure. · DRILL: violating issues.

**J3. Open work by priority `[NEW]`** · MEASURES: open rows by `Priority`. · DECISION: is the open
queue weighted to high priority (bad) or low (fine)? · VISUAL: stacked bar. · INSIGHT: pairs with
ageing — an aged P1 is the worst cell. · DRILL: `filter=10051/10052` P1/P2 at risk.

**J4. Priority inflation trend `[NEW]`** · MEASURES: share of P1/P2 over time. · DECISION: is
severity creeping up (or being gamed)? · VISUAL: stacked-area over 14 weeks. · INSIGHT: derivation
should keep the mix stable; a P1 spike is real or a matrix problem. · DRILL: week ∩ priority.

## Theme K — Major incident

**K1. Major-incident volume & MTTR `[NEW]`** · MEASURES: P1 rows (Impact High × Urgency High → P1),
MTTR = `resolved_at − reported_at`. · DECISION: how bad and how fast on the fast path. · VISUAL:
count tile + MTTR distribution. · INSIGHT: P1s are the fast-path (role-restricted, gate bypassed on
entry). · DRILL: `filter=10037`.

**K2. Major-incident MTTA `[NEW]`** · MEASURES: `first_response_at − reported_at` for P1s against
the 15-minute target. · DECISION: is detection→acknowledge fast enough. · VISUAL: gauge vs 15m. ·
INSIGHT: pairs with A3 (Monitoring intake should drive MTTA down). · DRILL: P1 issues with stamps.

**K3. Fast-path accountability `[NEW][NO-ITSM]`** · MEASURES: P1s escalated via `Escalate — major
incident` (Major Incident Manager role only) vs standard gate. · DECISION: was the fast path used
deliberately by the accountable role, not as a pressure-release valve? · VISUAL: split bar. ·
INSIGHT: the permission scheme's *negative* grant (L1 lacks the major-incident transition) made
visible. A Software-workflow permission story with no ITSM analogue. · DRILL: P1 issues by
transition path.

## Theme L — Automation-rule effectiveness

Automation is invisible until you measure it. Seven rules are live; each has a health metric.

**L1. Rule 1 — priority derivation conformance `[NEW]`** — see J2.

**L2. Rule 5 — pause coverage `[NEW]`** — see E4. The load-bearing one: rule 5 is "the rule that
makes the SLA report trustworthy." Metric: % of pending-status rows correctly Paused.

**L3. Rule 6 — reopen catch rate `[NEW]`** · MEASURES: `Resolved → Triage` transitions within 7 days
vs those flagged `Reopened = Yes`. · DECISION: is rule 6 flagging every premature close? · VISUAL:
catch % + misses. · INSIGHT: an uncaught reopen flatters FTR — this guards the G1↔G3 pair. · DRILL:
unflagged reopens.

**L4. Rule 4 — breach-warning lead time `[NEW]`** · MEASURES: for breached rows, whether the 75%
warning fired and how long before breach. · DECISION: is the warning early enough to save the
ticket? · VISUAL: lead-time histogram. · INSIGHT: warnings that fire *after* breach are useless. ·
DRILL: breached ∩ warning-timing.

**L5. Rule 7 — auto-close backlog control `[NEW]`** · MEASURES: rows in `Resolved` older than 5 days
without customer response (should be swept to `Closed`). · DECISION: is the Resolved column becoming
a second backlog? · VISUAL: count trend. · INSIGHT: a growing Resolved pile means rule 7 isn't
firing. · DRILL: stuck-Resolved issues.

**L6. Rule 2 — routing correctness `[NEW]`** · MEASURES: escalated rows where `Support Tier = L2` and
assignee cleared vs still assigned to an individual. · DECISION: did escalation land in a tower
queue, not on a person? · VISUAL: coverage bar. · INSIGHT: guards the "queue not a name" design. ·
DRILL: mis-routed issues.

## Theme M — Tower comparison & cross-cut (the spine)

**M1. Tower comparison table `[BUILT]`** · MEASURES: per `Tower` (model order — EUC, Enterprise
Apps, Network, Database, Compute & Storage, Cloud & Security) volume, closed, `ftr_pct`,
`escalation_pct`, `sla_pct`, aged, open, and `pilot_score = volume × (100 − ftr_pct)` with
`pilot_rank`. · DECISION: which tower to pilot/fix first — big **and** weak. · VISUAL: sortable table
with rank, zero-volume towers still shown. · INSIGHT: the ranking is auditable, not asserted — first
place is big *and* weak, not merely weak. · DRILL: tower row → its issues; each metric cell → its
slice.

**M2. Channel quality (FTR & escalation per channel) `[BUILT]`** · MEASURES: `ftr` and `escalation`
computed within each `Intake Channel`. · DECISION: is Chat (shadow) worse quality than Portal? ·
VISUAL: grouped bar per channel. · INSIGHT: makes the shadow-support claim measurable. · DRILL:
channel ∩ metric.

**M3. Root-cause pareto `[NEW]`** · MEASURES: `Root Cause` distribution (8 values) across resolved
rows, with cumulative line. · DECISION: which root causes drive the most volume → Problem records →
KB → deflection. · VISUAL: pareto. · INSIGHT: "Unknown - monitoring added" is observability debt;
"Access / permission misconfiguration" is an IAM fix. · DRILL: cause → issues.

## Integrity strip (should ship on every OPS view)

**N1. Invariant footer `[BUILT]`** · MEASURES: `invariants()` — Problems carrying an SLA verdict, KB
numerator ⊄ escalation denominator, `resolved_at`⇔Done mismatch, age-bucket partition,
reconstruction = snapshot, missing `Reported At`. · DECISION: is any panel silently lying? · VISUAL:
footer badges (green/red). · INSIGHT: a red invariant means the affected panel must be *suppressed*,
not shown. · DRILL: violation → offending keys.

**N2. Weekly-sum reconciliation `[BUILT]`** · MEASURES: `check_weekly_sums` — weekly buckets must
partition the window (volume, closed, escalated, KB gap). · DECISION: does the page agree with
itself? · VISUAL: pass/fail line. · INSIGHT: a row that falls off the axis vanishes from sparklines
while still counting in headlines — this catches it. · DRILL: n/a (acceptance check).

## Why so many OPS charts have no ITSM equivalent

The differentiators are all **Software-workflow / changelog / L1-Analyst-field** artefacts:
tier-flow Sankey (D1), gate-bypass detector (C4), backlog reconstruction (I4), per-analyst
escalation band (C2/H1), time-in-tier (D3), fast-path accountability (K3). ITSM's Incident workflow
has **no `Escalated` status** (122 Incidents claim L2, 0 passed through it), its assignee is the
single API account, its native dates are all "today," and it has **no knowledge base** behind its
KB-gap queue. OPS measures how the *team* works; a customer service desk measures customer
experience — ITSM's territory, the next part's catalog. Where they overlap (intake mix, priority
derivation, SLA outcome, KB gap, tower cut) the metric is equally true in both; where OPS is unique
it is because it can see *inside* the escalation, and ITSM cannot.

---

# Part V — The ITSM Chart & Metric Catalog

*The exhaustive, ITIL-native catalog for the `ITSM` Jira Service Management desk — deliberately
distinct from Part IV. The previous part measures how the team works; this one measures customer
experience. Same `analytics.py` engine where they overlap, entirely different practices where they
do not. Live values from `webapp/public/data/ITSM-90.json` (generated 2026-07-21, 420 issues) and
`CONTROL-TOWER.md`.*

## 0. Why ITSM's catalog is NOT OPS's catalog

OPS is a **Jira Software** L1/L2 escalation tower. Its whole analytic surface argues one thesis:
*tier is a state, tower is a field, escalation is a gated transition* — FTR-vs-reopen pairing,
per-analyst 2σ bands, KB gap, backlog staling. It has no customer, no portal, no approvals, no
change calendar, no CSAT. It is an **internal operations** instrument.

ITSM is a **Jira Service Management ITIL desk (service desk id 8)**: a customer-facing portal (17
request types, 5 groups), 8 issue types (Incident / Service Request / Service Request with
Approvals / Change / Problem / Post-incident review / Task / Sub-task), 19 agent queues, native SLA
engine, CAB approvals. Its catalog therefore covers four ITIL practices OPS structurally cannot:
**Incident, Request Fulfilment, Change, Problem** — plus the customer dimensions (**CSAT/CES,
portal deflection, approvals**) that only exist once there is a requester on the other side.

**ITSM-only metric families** (no OPS analogue): CSAT/CES, change success rate & change-caused
incidents, CAB approval cycle time, problem→incident reduction, portal deflection & self-service,
request-type fulfilment aging, request-type SLA cuts, freeze-window adherence. **Shared-but-recut**
families (same engine, ITSM data): SLA attainment, KB gap, backlog aging, escalation, intake mix —
identical pure functions, split by *request type* and *practice* rather than by *tier*.

**Three data-quality caveats every ITSM chart must respect** (full remediation board in §13, which
the roadmap burns down before these charts go live):
- **DQ-1 · Native SLA measures the wrong dates** — the native JSM engine clocks from `created`
  (uniformly today), so `everBreached()`=**0** while modelled `Resolution SLA` shows 47 breaches. →
  **Every SLA chart reads the modelled fields `Resolution SLA` (cf_10051) / `Response SLA`
  (cf_10050), never the native panel.**
- **DQ-2 · Approvals have no approver** — all 25 `Waiting for approval` tickets have an empty native
  approver list (one seeded account). → Approval-cycle charts are modelled from status-transition
  timestamps, not the native approval object.
- **DQ-3 · Escalation status is Service-Request-only** — `issuetype = Incident AND status WAS
  Escalated` returns 0, though 122 Incidents carry `Support Tier`=L2. → Incident escalation is read
  from the `Support Tier` (cf_10043) / `Escalated At` (cf_10059) fields, not status history.

## 1. Incident Management

**1.1 Incident MTTA.** *Measures:* mean `First Response At` (cf_10058) − `Reported At` (cf_10057)
over Incidents. *Why:* the customer-facing promise is "someone has it"; MTTA is the first SLA a
requester feels. *Visual:* line by reported-week with a P1–P4 target-band overlay. *Insight:*
separates "slow to pick up" from "slow to fix." *Drill:* week point → Incident keys with both
timestamps → `browse/ITSM-###`.

**1.2 Incident MTTR, pause-aware.** *Measures:* mean `Resolved At` − `Reported At` minus time in
`Pending`/`Waiting for customer`/`Waiting for support`, Incidents only. *Why:* the headline number
leadership tracks. *Visual:* box-plot per priority (P1–P4). *Insight:* the spread, not the mean — a
4h P1 mean hides the 18h tail that becomes the escalation. *Drill:* box outlier → the slow Incident.

**1.3 Incident resolution SLA attainment.** *Measures:* `Resolution SLA` (cf_10051) Met /
(Met+Breached), Incident type. Live desk-wide: **253 Met / 47 Breached = 84.3%**. *Why:* the
contractual number. *Visual:* stacked bar Met/Breached/Paused/In-progress per priority. *Insight:*
Paused broken out so the desk is not billed for the customer's silence. *Drill:* Breached → filter
`10067` (68 rows on the queue snapshot).

**1.4 Incident reopen rate.** *Measures:* `Reopened` (cf_10052) = Yes over closed Incidents. Live:
**10 / 300 = 3.3% (PASS)**. *Why:* customer-facing reopen is a broken-promise signal, worse than an
internal one. *Visual:* rate line + count bars, dual axis. *Insight:* pairs with FTR so neither is
gameable (OPS `ftr_vs_reopen` applied to Incidents). *Drill:* ITSM reopened → those keys.

**1.5 Major-incident count & MTTR.** *Measures:* Incidents with `Impact`=High AND `Urgency`=High,
the P1 fast path. Live: **Major Incidents queue = 12**. *Why:* majors are reputational events; MTTR
is a board metric. *Visual:* timeline swim-lane, one bar per major, length = duration, colour =
met/breached. *Insight:* how many, how long, how many recurred. *Drill:* filter `10066` → the 12
keys → History tab.

**1.6 Incident priority matrix heatmap.** *Measures:* count by `Impact` × `Urgency` (3×3), priority
derived P1–P4 (scheme 10166, rule 1). *Why:* proves priority is *derived* not negotiated — the
anti-inflation control. *Visual:* 3×3 heatmap, diagonal labelled P1…P4. *Insight:* a bulge in
High/High that later resolves as trivial exposes urgency inflation at intake. *Drill:* cell →
Incidents at that pair.

**1.7 Incident volume by tower.** *Measures:* Incident count by `Tower` (cf_10042). Live spread (all
types): EUC 126, Enterprise Apps 101, Network 63, Database 46, Compute & Storage 46, Cloud &
Security 38. *Why:* where the fire is. *Visual:* horizontal bar, six towers. *Insight:* EUC +
Enterprise Apps are >54% of the desk. *Drill:* bar → tower's Incident queue.

**1.8 Incident escalation rate (tier crossover).** *Measures:* Incidents with `Support Tier`=L2 ÷
all Incidents — read from the **field**, not status (DQ-3). Desk-wide **158/420 = 37.6% (GAP)**.
*Why:* even customer-facing, an over-escalating L1 is a training/staffing signal. *Visual:*
per-tower bar vs 35% reference line. *Insight:* Enterprise Apps 44.6% is the outlier tower. *Drill:*
tower bar → L2 Incidents in that tower.

**1.9 Recurring-incident cluster (→ Problem candidate).** *Measures:* Incidents grouped by `Affected
Service` (cf_10056) + `Root Cause` (cf_10048) with count ≥ threshold. *Why:* the bridge into Problem
management — recurring incidents are unfound problems. *Visual:* treemap, service × root-cause.
*Insight:* the biggest tile is next quarter's problem record. *Drill:* tile → member Incidents →
"create linked Problem".

## 2. Service Request Fulfilment

**2.1 Request volume by request type.** *Measures:* count by JSM **request type** (17 live across 5
portal groups). *Why:* Service Requests are a different SLA and staffing world than Incidents.
*Visual:* ranked bar. *Insight:* which self-service forms carry the load. *Drill:* bar → portal
request-type queue. *Caveat:* REST-created request types get only a `summary` field and no group;
the roadmap back-fills form fields and portal-group membership in the UI.

**2.2 Fulfilment SLA attainment by request type.** *Measures:* `Resolution SLA` Met/Breached, split
by request type. *Why:* a "reset password" and a "provision a laptop" cannot share one target.
*Visual:* dot-plot, one row per request type, attainment on x. *Insight:* the long-tail slow request
types the desk under-resources. *Drill:* row → that type's breached requests.

**2.3 Request fulfilment aging.** *Measures:* open Service Requests by age bucket
(0-3/3-7/7-14/14-30/30-60/60d+) from `Reported At`. Live open Service Requests = 22. *Why:* requests
silently rot behind incident firefighting. *Visual:* stacked age histogram, ≥14d shaded. *Insight:*
how much of the request backlog is genuinely stale vs fresh. *Drill:* bucket → the aged requests.

**2.4 Portal self-service deflection rate.** *Measures:* share of requests raised via **Portal**
(cf_10045) vs Email/Chat. Live intake: **Portal 199 (47.4%)**, Email 104 (24.8%), Monitoring 63
(15%), Chat 54 (12.9%). *Why:* portal-first is the ITIL efficiency lever. *Visual:* donut + trend of
portal share. *Insight:* nearly a quarter still arrives by email — a deflection opportunity worth a
form. *Drill:* channel slice → those requests.

**2.5 Shadow-support (Chat) intake.** *Measures:* requests via **Chat** (cf_10045 = Chat, flagged
`shadow`). Live: **54 (12.9%)**. *Why:* chat intake is work that historically never reached a ticket
— dragging it into the record is the point. *Visual:* weekly chat-volume bars. *Insight:* the size
of the shadow desk. *Drill:* filter chat intake → those tickets.

**2.6 First-time-fulfilment (no escalation) rate.** *Measures:* Service Requests closed at `Support
Tier`=L1 ÷ closed Service Requests — the request analogue of FTR. Desk-wide **193/300 = 64.3%
(GAP)**. *Why:* a request that needed L2 was probably an automation/self-service miss. *Visual:* rate
line by week. *Insight:* which request types should be fully automated. *Drill:* week → escalated
requests.

**2.7 Approvals-bearing vs standard requests.** *Measures:* split of "Service Request with Approvals"
vs plain "Service Request". *Why:* approval-gated requests have an extra cycle that must not be
blamed on the fulfilment team. *Visual:* two-bar comparison of cycle time. *Insight:* approval wait,
not fulfilment work, dominates gated requests. *Drill:* → §7 approval charts.

## 3. Change Management *(ITSM-only — OPS has the Change issue type but no CAB/calendar practice)*

**3.1 Change success rate.** *Measures:* Changes reaching `Completed`/`Closed` with a clean
Resolution Code and no linked change-caused Incident ÷ all implemented Changes. Live Change queue =
7 open. *Why:* the single ITIL change KPI. *Visual:* gauge + trend. *Insight:* whether the desk's
changes land clean. *Drill:* gauge → implemented Changes → linked Incidents.

**3.2 Failed & backed-out changes.** *Measures:* Changes with `Resolution Code` = Workaround / No
fault found / Withdrawn, or a back-out transition. *Why:* failure rate is the risk dial. *Visual:*
bar by change type (standard/normal/emergency). *Insight:* emergency changes fail disproportionately
— the case for more CAB. *Drill:* bar → the failed change keys.

**3.3 Emergency-change ratio.** *Measures:* emergency Changes ÷ all Changes. *Why:* a high emergency
ratio means change management is being bypassed under pressure — the change analogue of OPS's
major-incident fast-path abuse. *Visual:* stacked area over time. *Insight:* rising emergency share
= process erosion. *Drill:* → emergency Change list.

**3.4 CAB approval cycle time.** *Measures:* time in `Awaiting CAB approval` → `Awaiting
implementation` (status-transition timestamps, per DQ-2 not the native approval object). Live:
`Awaiting CAB approval` = 4 open. *Why:* CAB is the most common change bottleneck. *Visual:*
histogram of approval durations. *Insight:* the CAB tail that stalls the pipeline. *Drill:* bar →
Changes awaiting CAB → History tab (the honest path — runs end-to-end unlike Incident/SR approvals).

**3.5 Change calendar / freeze-window adherence.** *Measures:* Changes scheduled inside a declared
freeze window vs outside. *Why:* freeze violations are audit findings. *Visual:* calendar heatmap,
day × change count, freeze days marked. *Insight:* who is shipping during a freeze. *Drill:* calendar
cell → that day's Changes. *(Roadmap: needs a scheduled-start field; not yet seeded.)*

**3.6 Change-caused incidents.** *Measures:* Incidents linked to a Change ÷ implemented Changes,
trailing window. *Why:* the outcome metric change management exists to minimize — the truest measure
of change quality. *Visual:* line, change-caused incidents per week. *Insight:* which change types
generate the most downstream incidents. *Drill:* point → the Change → its caused Incidents.

**3.7 Change volume & lead time by type.** *Measures:* count and `Reported At`→`Resolved At` lead
time by standard/normal/emergency. *Why:* throughput and predictability of the change pipeline.
*Visual:* grouped bar. *Insight:* standard changes should be fast and many; if not, the
standard-change catalog is under-built. *Drill:* bar → change keys.

## 4. Problem Management *(ITSM-only practice)*

**4.1 Open problems & known-error backlog.** *Measures:* count of Problem type, split investigating
vs known-error (has documented `Root Cause` + workaround). Live Problem queue = 1 open. *Why:* known
errors are the deflection library. *Visual:* two-series area (open problems vs known errors).
*Insight:* whether root-cause work is converting into reusable knowledge. *Drill:* → Problem list.

**4.2 RCA cycle time.** *Measures:* `Reported At`→`Resolved At` for Problems (Problems are excluded
from FTR/SLA by design — a Problem is *supposed* to sit for weeks). *Why:* RCA that never finishes
never deflects. *Visual:* box-plot of Problem durations. *Insight:* the RCA tail. *Drill:* box → slow
Problems. *DQ note:* 12 Closed Problems carry a null SLA verdict and native SLA is blank on all
Problems — this chart uses modelled dates only.

**4.3 Recurring-incident → problem linkage.** *Measures:* Incidents linked to an open Problem ÷ all
Incidents in the window. *Why:* proves problems are actually attached to the incidents they explain.
*Visual:* sankey, Incident clusters → Problems. *Insight:* the unlinked recurring clusters (from
1.9) that *should* have a problem. *Drill:* flow → member Incidents.

**4.4 Problem→incident reduction (deflection proof).** *Measures:* incident volume for an `Affected
Service` before vs after its Problem closed. *Why:* the ROI of problem management — the one chart
that justifies the practice to finance. *Visual:* before/after bar per resolved Problem. *Insight:*
which RCAs actually cut recurring volume. *Drill:* bar → the Problem and its pre/post Incidents.

**4.5 Problems by root cause.** *Measures:* Problem count by `Root Cause` (cf_10048, 8 options).
*Why:* systemic cause categories drive where to invest (infra vs process vs vendor). *Visual:*
horizontal bar. *Insight:* the dominant systemic failure mode. *Drill:* bar → Problems with that
cause.

## 5. SLA / OLA

**5.1 SLA attainment by request type & priority (matrix).** *Measures:* `Resolution SLA` Met% across
(request type × priority). *Why:* the single most decision-dense SLA view. *Visual:* heatmap
green→red on attainment, cell = n. *Insight:* the hot cells are the SLA renegotiation or staffing
case. *Drill:* cell → those breached tickets.

**5.2 Time-to-first-response SLA.** *Measures:* `Response SLA` (cf_10050) Met/(Met+Breached). Live:
**334 Met / 73 Breached = 82.1% (GAP)**. *Why:* response is the SLA customers judge the desk on
hourly. *Visual:* stacked bar per priority + trend. *Insight:* response is failing worse than
resolution (82% vs 84%) — an intake-triage staffing problem. *Drill:* Breached → those tickets'
`First Response At` gaps.

**5.3 Resolution SLA outcome mix.** *Measures:* Met / Breached / In-progress / **Paused** counts.
Modelled: 253 / 47 (+ Paused, In-progress excluded from rate). *Why:* the pause bucket makes the
report trustworthy — rule 5 sets `Resolution SLA`=Paused in `Pending` statuses. *Visual:* four-slice
pie. *Insight:* paused volume is the customer's clock, not the desk's. *Drill:* slice → filter
(breached `10067`, paused equivalent).

**5.4 OLA: L1→L2 handoff time.** *Measures:* `Escalated At` (cf_10059) − `First Response At`
(cf_10058) — the internal operating-level agreement between tiers. *Why:* the customer SLA can pass
while an internal handoff quietly rots. *Visual:* histogram of handoff durations. *Insight:* slow
handoffs that will become customer breaches next. *Drill:* bar → tickets in `Escalated to L2` (30
open).

**5.5 Pause-time attribution.** *Measures:* total time in `Pending`/`Waiting for customer`
(customer's clock) vs `Waiting for support`/vendor (desk's clock). Live open: Pending 21, Waiting for
customer 2, Waiting for support 5. *Why:* separates "we're slow" from "they're slow" — the argument
that saves the SLA report. *Visual:* stacked bar, customer-pause vs desk-pause. *Insight:* how much
breach risk is genuinely outside the desk's control. *Drill:* segment → tickets currently paused on
that side.

**5.6 Native-vs-modelled SLA reconciliation (data-quality panel).** *Measures:* native
`everBreached()` (=0, DQ-1) alongside modelled `Resolution SLA` breaches (=47). *Why:* the roadmap's
fix-tracking panel — makes the native-SLA defect visible and shrinks to zero when native goals are
retargeted to `Reported At`. *Visual:* two counters side-by-side with a delta. *Insight:* the gap
*is* the bug. *Drill:* → the 47 modelled breaches the native engine misses.

## 6. CSAT / CES *(ITSM-only — no OPS analogue; requires a customer)*

**6.1 CSAT score & response rate.** *Measures:* native JSM satisfaction rating (1–5) on resolved
requests; mean and % of resolved rated. *Why:* the only outcome metric that comes from the
*customer*. *Visual:* running mean line + response-rate bar. *Insight:* whether SLA-met tickets are
actually satisfying (they often aren't). *Drill:* rating → the rated request + comment. *Caveat:*
requires provisioned customers (none today); roadmap-gated on customer accounts.

**6.2 CSAT vs SLA-met cross-tab.** *Measures:* CSAT distribution among SLA-met vs SLA-breached
tickets. *Why:* the killer finding — "we hit SLA and they're still unhappy." *Visual:* grouped bar,
CSAT bins × SLA outcome. *Insight:* where the SLA target measures the wrong thing. *Drill:* cell →
those tickets.

**6.3 CES (customer effort proxy).** *Measures:* effort proxy from reopen count (cf_10052) +
customer public-comment count per ticket. *Why:* effort predicts churn better than satisfaction.
*Visual:* effort-score distribution. *Insight:* the high-effort request types to redesign. *Drill:* →
high-effort tickets.

**6.4 CSAT by tower / agent / request type.** *Measures:* mean CSAT segmented. *Why:* localizes
dissatisfaction to a team or a form. *Visual:* small-multiple bars. *Insight:* the one tower dragging
the desk score. *Drill:* segment → its low-rated tickets.

## 7. Agent Queue Health & Workload

**7.1 Queue depth across all 19 queues.** *Measures:* live count per JSM agent queue. Live snapshot:
All open 106, Unassigned 45, Incidents 51, Service requests 22, Change 7, Problem 1, L1 Queue 63, L2
– All Towers 43, plus six per-tower L2 queues and Major Incidents 12. *Why:* the agent's actual
worklist. *Visual:* horizontal bar, all queues, sorted. *Insight:* where work is piling. *Drill:* bar
→ the queue.

**7.2 Unassigned / triage backlog.** *Measures:* `Unassigned work items` queue = 45. *Why:*
unassigned = un-owned = SLA-at-risk. *Visual:* single big number + trend. *Insight:* 45 unowned of
106 open is a triage-discipline gap. *Drill:* → the unassigned queue.

**7.3 Workload distribution (agent balance).** *Measures:* open tickets per `L1 Analyst` / `L2
Analyst` (cf_10053/54 — text fields; the instance has one licensed user so the seeded assignee is the
API account, hence analyst *fields* not assignee, exactly as OPS does). *Why:* uneven load is burnout
and SLA risk. *Visual:* bar per analyst with a mean line. *Insight:* the overloaded analyst. *Drill:*
bar → that analyst's open tickets. *Caveat:* one real user — illustrative until staffed.

**7.4 Per-analyst escalation 2σ band (ported from OPS).** *Measures:* escalation rate per `L1
Analyst` with pooled mean ± 2σ, small-sample floor `MIN_ANALYST_N`=20. *Why:* the same "no analyst
diverges >2σ" criterion, on the ITSM population. *Visual:* dot-per-analyst with shaded band.
*Insight:* who over-escalates. *Drill:* dot → their escalated tickets.

**7.5 Queue SLA-risk mix.** *Measures:* within each queue, % of tickets ≥75% of SLA target elapsed
(rule 4 threshold). *Why:* depth alone lies — a shallow queue full of near-breach tickets is more
urgent than a deep fresh one. *Visual:* queue bars tinted by at-risk share. *Insight:* reprioritize
by risk, not size. *Drill:* → at-risk tickets in that queue.

## 8. Approvals (CAB / Manager)

**8.1 Approval backlog & aging.** *Measures:* tickets in `Waiting for approval` (25) and `Awaiting
CAB approval` (4) by age. *Why:* approval is pure wait — the bottleneck most invisible to the
fulfilment team. *Visual:* aging histogram of pending approvals. *Insight:* the stalled approvals
nobody owns. *Drill:* → `Waiting for approval` tickets.

**8.2 Approval cycle time (modelled).** *Measures:* status-transition duration through the approval
state (per DQ-2, **not** the native approval object — all 25 approver lists are empty). *Why:* how
long approval *actually* takes. *Visual:* histogram + median. *Insight:* the approval SLA to set.
*Drill:* → ticket History tab.

**8.3 Approval defect panel (data-quality).** *Measures:* count of pending-approval tickets with an
empty approver list (=25, DQ-2). *Why:* the roadmap fix-tracker — shrinks to zero once a second
Atlassian account is provisioned. *Visual:* counter. *Insight:* approvals are *seeded* but not
*demonstrable* until staffed. *Drill:* → the 25 tickets. *Honest-path note:* demo the **Change**
approval (`Awaiting CAB approval → Awaiting implementation`), which runs on ordinary transitions and
works end-to-end.

## 9. Backlog & Aging

**9.1 Aged backlog (>14d) — snapshot.** *Measures:* open AND `Reported At` ≤ −14d, project-wide,
**unwindowed**. Live: **105** (queue "Aged Backlog – 14 days+" = 101 on the earlier snapshot).
*Why:* the desk's staling debt. *Visual:* big number + reconstruction line. *Insight:* backlog isn't
*growing*, it's *aging in place* (OPS's finding, reconstructed from `Reported At`/`Resolved At` — a
view Jira structurally can't draw). *Drill:* → filter `10069`.

**9.2 Backlog aging by request type.** *Measures:* age histogram split by request type. *Why:* an
aged *incident* and an aged *change* mean different things. *Visual:* stacked age histogram, series =
request type. *Insight:* which catalog items rot. *Drill:* bucket → those tickets.

**9.3 Owned vs paused aging.** *Measures:* open work in each age bucket split by whether status ∈
`SLA_PAUSED_STATUSES`. Live by-status of open work: Escalated to L2 30, Waiting for approval 25,
Pending 21, Open 7, Work in progress 7, In Progress 5, Waiting for support 5, Awaiting CAB 4,
Escalated 4, Waiting for customer 2, Implementing 1. *Why:* don't accuse the desk of tickets
legitimately paused on a customer or an approver. *Visual:* diverging stacked bar, owned vs paused
per bucket. *Insight:* ~48 of the open set is paused — not the desk's active queue. *Drill:* segment
→ those tickets.

**9.4 Backlog inflow vs outflow (cumulative flow).** *Measures:* weekly created vs resolved (by
`Reported At`/`Resolved At`). *Why:* whether the desk is keeping up; the slope is the story.
*Visual:* CFD, band width = WIP. *Insight:* widening band = losing ground. *Drill:* week → arrivals/
departures.

## 10. SLA-at-Risk & Breach Forecast

**10.1 SLA-at-risk queue (75% burn).** *Measures:* not-done tickets past 75% of their priority target
elapsed since `Reported At` (rule 4's exact JQL). *Why:* warn while it can still be saved. *Visual:*
countdown table sorted by remaining time, + count by priority. *Insight:* the save-list for the next
hour. *Drill:* row → the ticket.

**10.2 Breach forecast (end-of-day / week).** *Measures:* projected breaches from current burn rate
across open tickets. *Why:* staffing decision — pull people onto the queue now? *Visual:* fan chart,
projected breaches with band. *Insight:* the expected breach count if nothing changes. *Drill:* → the
tickets projected to breach.

**10.3 P1/P2 at-risk board.** *Measures:* P1 and P2 tickets nearing breach. *Why:* highest-cost
breaches first. *Visual:* two-column kanban, P1 / P2. *Insight:* the majors about to slip. *Drill:*
card → the ticket.

## 11. Knowledge & Deflection

**11.1 KB gap (escalated, no article found).** *Measures:* `KB Article Checked` (cf_10047) = "Yes -
none found" ÷ escalations. Live: **91 / 158 = 57.6%**. *Why:* the single biggest deflection lever.
*Visual:* big rate + weekly count bars (count never abstains, share-line breaks below
`MIN_WEEK_DENOM`). *Insight:* 91 escalations found no article — a concrete writing backlog. *Drill:* →
KB Gap queue (86 on snapshot) / filter `10072`.

**11.2 KB gap by tower.** *Measures:* gap count by `Tower`. Live: EUC 26, Enterprise Apps 26, Network
16, Cloud & Security 10, Compute & Storage 8, Database 5. *Why:* which article to write next.
*Visual:* horizontal bar / heatmap. *Insight:* EUC and Enterprise Apps tie for the thinnest KB.
*Drill:* bar → those escalations.

**11.3 KB gap by escalation reason.** *Measures:* gap by `Escalation Reason` (cf_10046). Live: Root
cause unclear after triage 24, Requires elevated access 17, Suspected platform defect 15, Vendor
engagement required 14, Change required to resolve 11, Beyond documented runbook 10. *Why:* the *kind*
of missing knowledge — "root cause unclear" wants a diagnostic runbook; "requires elevated access"
wants a permissions self-service. *Visual:* ranked bar. *Insight:* not all gaps are article-shaped.
*Drill:* reason → those tickets.

**11.4 Deflection funnel.** *Measures:* portal views → KB article views → tickets deflected → tickets
raised. *Why:* the self-service ROI story. *Visual:* funnel. *Insight:* where the portal fails to
deflect. *Drill:* stage → the requests that fell through. *Caveat:* **there is no Confluence-backed
KB** on the instance (`knowledgebase/article` size 0) — frame the "KB Gap" as the desk's own `KB
Article Checked` evidence field. The roadmap either connects a Confluence space or keeps this as an
evidence metric, explicitly.

## 12. Portal & Channel

**12.1 Intake channel mix.** *Measures:* volume by `Intake Channel` (cf_10045), model order. Live:
Portal 199, Email 104, Monitoring 63, Chat 54. *Why:* channel strategy — every non-portal channel is
a deflection and automation gap. *Visual:* donut + trend. *Insight:* 53% of intake bypasses the
portal. *Drill:* slice → those tickets.

**12.2 Channel quality (FTR & escalation by channel).** *Measures:* FTR and escalation rate per
channel. *Why:* makes the shadow-support claim measurable. *Visual:* grouped bar, FTR vs escalation
per channel. *Insight:* whether chat/email intake is lower-quality than portal. *Drill:* channel →
its tickets.

**12.3 Monitoring-origin (event-driven) volume.** *Measures:* `Intake Channel` = Monitoring (63,
15%). *Why:* event-driven tickets are the automation frontier — should auto-triage and often
auto-resolve. *Visual:* trend line. *Insight:* the automatable slice. *Drill:* → monitoring tickets.

**12.4 Portal availability / anonymous-access defect (data-quality).** *Measures:* a flag — the portal
redirects to login anonymously (no customers provisioned). *Why:* roadmap fix-tracker. *Visual:*
status badge. *Insight:* demo from the authenticated session, not incognito. *Drill:* portal id 8.

## 13. Cross-cutting: the ITSM data-quality remediation board

A dedicated panel the roadmap burns down — every item a *known* defect from `CONTROL-TOWER.md`,
sitting where a chart would otherwise silently lie:

| # | Defect | Live count | Chart affected | Fix (route) |
|---|---|---|---|---|
| DQ-1 | Native SLA clocks from `created` (=today) | `everBreached()`=0 vs 47 modelled | all §5 | retarget native SLA to `Reported At` (UI) |
| DQ-1b | Native goals keyed to issue type not priority | P1≡P4 targets | 1.3, 5.1 | re-key goals to priority (UI) |
| DQ-1c | Native SLA blank on Changes/Problems; 278 "time to close" clocks still running | 44 + 278 | 3.x, 4.2 | complete/retarget SLA config (UI) |
| DQ-2 | Approvals have empty approver list | 25 | §8 | provision 2nd account |
| DQ-3 | `Escalated` status is Service-Request-only | Incidents WAS Escalated = 0 (122 tier-L2) | 1.8, 5.4 | add Escalated to Incident workflow, or read the field |
| DQ-4 | 28 Closed Incidents "Met" against own dates (fail *safe*) | 28 | 1.3, 5.3 | backfill — blocked by `jira.issue.editable=false` |
| DQ-5 | 12 Closed Problems null SLA verdict; 6 chronology inversions | 18 | 4.2 | same unlock |
| DQ-6 | No Confluence KB behind "KB Gap" | article count 0 | 11.4 | connect KB or reframe as evidence |
| DQ-7 | ~11% of tickets have empty History (created into intake status) | ~46 | any History-tab drill | pick demo tickets deliberately |

**Invariants stay green.** `analytics.py` `invariants()` currently returns **[]** on ITSM-90 — the
one historically-live violation (ITSM-265, a Problem carrying `Response SLA`=Met, which legitimately
sits in the response denominator because `metrics.py`'s JQL has no issue-type clause either) is the
model *reporting* the wart rather than masking it. Every chart above inherits that discipline: a rate
always ships with its numerator and denominator, and a panel whose invariant fails is **suppressed**,
not shown dimmed.

## 14. The record-level drill contract (all charts)

Every mark uses the Part III interaction: **click → right-side drawer** listing the underlying
records (key, `Reported At`, priority, tower, the field(s) that put it in this bucket) → **Jira deep
link** to `browse/ITSM-###`, an agent **queue** URL, or a saved **filter** (ITSM filters
`10064`–`10085`). The drawer shows the numbers behind the mark — never a bare percentage. This is the
same drill affordance OPS ships; what changes on ITSM is the *destination* (portal, queues, request
types) and the *dimension* (request type, practice, customer), not the mechanism.

---

# Part VI — The Insights & Intelligence Layer

*The "so what" engine on top of the charts. Parts IV and V give the tower a measurement surface;
this part gives it interpretation — and it is integral, not a bolt-on. Every insight is a view of a
fact record the Part III drawer can reconcile.*

Today the tower answers *what is the escalation rate* (170/419 = 40.6% on OPS) with unusual honesty.
It does not answer **so what** — *up from what, driven by which tower, costing which SLA, fix it
how*. That gap is this part. The insights layer reads the same model `compute_all` already emits,
computes deltas, anomalies, targets, recommendations and forecasts, and surfaces them as narrative —
without ever inventing a number the drill panel can't reconcile.

**Where it lives.** Nothing here needs a live backend, and adding one would break the security
posture (token in CI, static bake). The engine is a new pure module — `app/insights.py` — taking
**two** inputs: today's `compute_all` result and a retained history of prior bakes. The roadmap
change is to (a) archive each dated bake under `webapp/public/data/history/OPS-90/2026-07-21.json`
rather than overwrite, and (b) run `insights.compute(today, history)` and emit an `insights` block
into the same JSON the page already loads. Every mechanism below is a function over snapshots that
already exist — no new Jira calls, same pure-function testability.

**The non-negotiable, inherited from the metric core.** **Every insight carries the arithmetic that
produced it and a deep link to the records behind it.** An insight that says "escalation up 12%" with
no `48→54 of ~130` and no filter URL is exactly the untrustworthy artefact that makes the SLA report
nobody opens. The engine abstains far more readily than it asserts, and every abstention reuses the
same `MIN_WEEK_DENOM = 10` / `rate_point` floor the charts already use.

## 6.1 Automated narrative insights

**What.** Plain-language sentences generated from the model, ranked by materiality, e.g. *"Escalation
rate is 40.6% (170/419), 5.6pts above the 35% target and up 3.1pts week-over-week. Compute & Storage
is the driver: 51.0% escalation (26/51) against a tower mean of 40.3%. Three escalation reasons —
Suspected platform defect (19), Requires elevated access (16), Root cause unclear after triage (14) —
account for 62% of the KB-gap backlog."* Every clause is a value already in `compute_all`. The layer
does not compute anything new — it **selects, ranks and phrases** what the model found.

**Logic.** For each headline metric the engine assembles a fact record `{value, num, den, target,
verdict, wow_delta, top_driver, top_driver_share}`, scores each for *materiality* — (distance from
target) × (denominator size) × (magnitude of change) — so a GAP on a 419-ticket denominator outranks
a PASS on 12, and emits the top N as templated sentences. The "driver" clause is a one-level
decomposition generalising the `pilot_score = volume × (100 − ftr_pct)` logic `tower_table` already
uses.

**Surfaces.** Three altitudes, same content: (1) a one-line **headline banner** atop the Overview
lens; (2) a dedicated **Insights feed** (a new left-rail view beside Overview/L1/L2); (3) **inline on
the chart** (the analyst panel's `criterion_6: "met"` rendered as "12 analysts, 0 outside 2σ —
criterion 6 met"). Clicking any sentence opens the **same right-side drill drawer** every mark opens,
pre-filtered. On ITSM the phrasing carries the §5 caveats: escalation narrative is sourced from the
`Support Tier = L2` field (167 tickets), not `status WAS Escalated` (which returns 18 and would
contradict the field).

## 6.2 Anomaly & change detection

**What.** Noticing that something *moved* — WoW/MoM deltas, spikes against the metric's own history,
threshold crossings (PASS→GAP, or crossing 75% of an SLA target), and short-horizon breach
forecasting. Turns a static 78.8% resolution-SLA tile into "fell from 82.1% to 78.8% over three
weeks; Compute & Storage (75.5%) is already below the project line."

**Logic.** *WoW/MoM deltas* computed on the cohort `weekly_series` — and this is where the layer must
be most careful: a week's point is a **reported-week cohort rate** and the final buckets are thin by
construction (`rate_point` already returns `null` below `MIN_WEEK_DENOM`). The delta engine compares
the **last two *complete* weeks**, never a complete week against the in-progress one. Suppressing the
edge-week swing is the single highest-value trust decision here. *Spikes* via a metric-history
z-score (`|z| > 2`), deliberately the same 2σ rule `analyst_escalation` uses, so the page has one
definition of "unusual." *Threshold crossings* are verdict flips between yesterday's and today's
bake — the highest-priority events, also firing on the SLA 75%-of-target line to mirror **automation
rule 4**. *SLA-breach forecasting* over open, not-paused tickets against the priority calendar
(`SLA_CLOCK`: P1/P2 24×7, P3/P4 business hours), reusing the exact clock rule 4 fires on.

**Surfaces.** Deltas as **sparkline annotations and arrow chips** on every scoreboard tile (greyed
when not stateable). Spikes and crossings become **Insights-feed items** and, if severe, the headline
banner. The breach forecast gets a **"at-risk today" panel** beside the front-line queue, listing
keys ordered by time-to-breach. On ITSM the forecast **must not** touch the native SLA engine — only
the modelled `Resolution SLA` field and the `Reported At` clock.

## 6.3 Benchmarks & targets

**What.** What "good" is, without importing a benchmark from another organisation ("a target imported
from another company is worse than no target"). Three frames: pilot-baseline→target, tower-vs-tower,
trend-to-target.

**Logic.** *Baseline→target* freezes the **first full-window bake as the pilot baseline**
(`webapp/public/data/baseline/OPS-90.json`) and renders every metric as *baseline → today → target*:
FTR 61.8% → 62.0% → 65%. The number moves from placeholder to earned once a real baseline is frozen.
*Tower-vs-tower* turns `tower_table`'s `pilot_rank` into "this tower vs the tower median and the best
tower": Compute & Storage FTR 48.8% sits 13pts below the project 62.0% and 25pts below Database's
73.7% — the best tower becomes the internal benchmark, legitimate because it is *this organisation's
own* demonstrated ceiling. *Trend-to-target* fits a slope to the retained history: "at +0.15pts/week
FTR reaches 65% in ~20 weeks" — or, honestly, "FTR is flat; at the current slope it does not reach
target."

**Surfaces.** A **target-gauge** on each tile (baseline tick, current fill, target line); a **tower
league table** sortable by gap-to-best; a **trend-to-target caption** under the weekly trend; the
pilot exit criteria as a **scorecard strip** (computed verdicts, never hardcoded). Every target shows
*provenance*: a placeholder target is badged as such; a baseline-derived target is badged "from pilot
baseline, frozen 2026-XX-XX." A cross-project SLA benchmark is explicitly *not* offered because
ITSM's clock is 24×7 for all priorities, not OPS's business-hours split.

## 6.4 Prescriptive recommendations

**What.** Closing the loop from *observation* to *action*, tied to the model so the estimate is
auditable: *"Write KB articles for the top 3 escalation reasons (49 of 79 KB-gap escalations).
Closing them at the observed FTR lift is worth an estimated −6 to −8pts of escalation."* Or:
*"Compute & Storage escalates at 51.0% (26/51) on 12% of volume; targeting its 15 KB-gap tickets
addresses the single largest headroom in the tower."*

**Logic.** Rules over the model, each with an explicit shown estimate. *KB backlog:* `kb.by_reason`/
`kb.by_tower` already rank "which articles to write next"; the recommendation is the top-3 slice with
an impact estimate as a **range with its assumption stated**, never a point promise. *Analyst
rebalancing:* triggered when a tower's escalation rate exceeds the mean by a set margin AND its L2
staffing is thin; names the tower and the load gap, not specific people. *Aged backlog:* targets the
**owned-and-aged** set specifically (41 of 62 open are owned; accusing the tower of the 21 paused is
the exact error rule 5 prevents).

**Surfaces.** A **"Recommended actions" card** in the Insights feed, each with its estimate and a
*"see the 3 articles to write"* link into the drill drawer, ranked by modelled impact — so the top
card is always the largest lever (on OPS, the KB gap). Every recommendation shows its arithmetic and
assumption inline ("assumes 50% deflection per article; adjust the slider to re-estimate"), framed as
a *lever with an estimate*, never a prediction. On ITSM the KB-gap recommendation carries the §5
honesty note: there is *no* Confluence-backed KB, so "write an article" means standing one up.

## 6.5 "What changed since yesterday" digest

**What.** A dated diff between today's bake and yesterday's — the fastest way for a lead to start the
day. *"Since yesterday: escalation +1.2pts (168→170 L2); 1 new aged ticket (OPS-2298, now 15d);
resolution SLA unchanged; 2 tickets newly at-risk (OPS-2411, OPS-2419); no invariant violations."*
The human-scale companion to §6.2, one-day horizon, phrased as a changelog.

**Logic.** The daily bake loads yesterday's retained snapshot and diffs: scoreboard value deltas,
verdict flips, new/closed aged tickets (set difference on keys), new at-risk tickets, and — importantly
— **new invariant violations**, because a panel whose invariant just fired is asserting something the
data no longer supports.

**Surfaces.** The **top of the Insights feed**, dated, collapsible by category — and the natural
payload for the §6.6 subscription. A "since last Monday" and "since baseline" toggle reuses the same
diff against a different snapshot. Each line links to the specific keys that entered or left a set;
the diff is reproducible by hand. The digest explicitly reports "no changes" days rather than going
silent, so a quiet day is distinguishable from a broken bake.

## 6.6 Alerting & subscriptions

**What.** Push, not pull — email/Slack digests on a schedule, plus threshold alerts ("tell me the
moment reopen crosses 5%", "P1 breach forecast > 0"). The tower stops being a page someone remembers
to open and starts arriving.

**Logic.** Two classes, both run in **CI** where credentials already live. *Scheduled digests:* the
daily bake gains a final step rendering the §6.5 digest and POSTing to a Slack webhook / email —
the same architectural pattern as automation rule 7 (scheduled daily auto-close). *Threshold alerts:*
verdict flips and z-score spikes fire an out-of-band message, subject to a **hysteresis/cooldown** so
a metric oscillating around its target line doesn't alert every day. Subscriptions are **static config
checked into the repo** (`subscriptions.yaml`), because there is no backend to store them and CI is
the only trusted actor.

**Surfaces.** In Slack/email, as the digest. In the UI, a **"subscribe" affordance** on any metric or
saved view that generates the YAML snippet to add (a reviewable PR, not a hidden setting). Every alert
links back to the exact page view and drill drawer that substantiates it. Because subscriptions are
code-reviewed config, there is an audit trail of who subscribed to what.

## 6.7 Natural-language querying of the tower

**What.** Ask in English — *"what's the escalation rate for Network last month?"*, *"show me aged
tickets in Compute & Storage over 30 days"* — and get the number **with its denominator and a drill
link**, not a chatbot paragraph.

**Logic.** NLQ over the **pre-computed model, not over Jira**. A query resolves to (dimension =
tower/analyst/channel/priority) × (metric = escalation/ftr/sla/reopen/aged) × (window/segment). Two
tiers: (1) a **structured query builder / DSL** the UI exposes as chips — deterministic, testable,
and it *cannot* return a number that isn't in the model; (2) an **LLM-assisted parser** that maps free
text to that DSL, with the DSL result — not the LLM — producing the number. The LLM chooses *which*
slice; `analytics.py` computes *the value*. For anything the model doesn't pre-aggregate, the answer
is an honest "not computed — here's the closest Jira filter."

**Surfaces.** A **query bar** atop the Insights feed; results render as a **mini-panel + drawer**
identical to a drill result. The answer shows the compiled query ("tower = Network, metric =
escalation, window = 90d → 24/58 = 41.4%") so the user can see *what was asked was what was
answered*. On ITSM, NLQ inherits every §5 guardrail.

## 6.8 Forecasting & capacity planning

**What.** Forward-looking: intake and backlog projection, and the staffing question the tower is
*designed* to answer — *is L1 absorbing enough volume, and where does L2 need hands?*

**Logic.** *Intake forecast:* a seasonal-naive/trend model on the weekly reported-volume series, with
a stated confidence band; built on the single valid `Reported At` axis and says so. *Backlog
projection:* extends `backlog_series`' slope — turning "staling in place" into "at this rate, 80 aged
by mid-August unless close-rate rises." *Capacity/staffing:* forecast intake × observed escalation
rate per tower → L2 demand per tower, compared to `L2_ANALYSTS` headcount (EUC 2, Enterprise Apps 2,
Network 2, DB 2, Compute 2, Cloud 1). Output is a **relative** load-vs-capacity ratio per tower —
Compute & Storage's 51% escalation on rising volume against 2 analysts flags before Cloud's 36% on 1
— explicitly *not* an absolute headcount number (the staffing-model non-goal).

**Surfaces.** A **forecast overlay** on the backlog and intake charts (dashed projection, shaded
band); a **capacity heat strip** in the tower-comparison panel, worst first. Every forecast shows the
model, the history it was fit on, and a band that widens with horizon; where the sample is too short
to fit, the forecast is suppressed, not guessed.

## 6.9 How the whole layer earns trust

Four properties, each inherited from the metric core: (1) **Every insight is a view of a fact record,
one click away** — the templater is fed only numbers that exist in `compute_all`. (2) **The engine
abstains loudly** — sub-floor weeks/analysts/snapshots produce "not stateable," never a zero or a
confident spike. (3) **Provenance is on the face of every number** — placeholder vs baseline target,
modelled vs native SLA, `Reported At` vs the unusable `created`. (4) **It is reproducible offline** —
`insights.compute(today, history)` over frozen JSON is a full regression test.

## 6.10 Build sequence

One hard prerequisite and a natural ordering: **P0 — snapshot retention** (CI stops overwriting bakes;
unblocks everything time-aware). **P1 — narrative + benchmarks** (pure functions over *today's* model;
highest immediate value; freezes the baseline). **P2 — change detection + digest** (needs ≥2
snapshots). **P3 — alerting** (CI-side push of the P2 digest). **P4 — recommendations** (depends on
the P1 benchmark frame). **P5 — NLQ + forecasting** (most build-heavy; forecasting needs a meaningful
history window). Every layer runs identically against OPS and ITSM because both emit the same model
shape from the same 20 shared fields — with ITSM's §5 caveats carried as data-driven annotations, not
narrated exceptions a presenter has to remember.

---

# Part VII — Information Design, Layout & Space Optimisation

*"No real estate left within the charts — space optimally occupied." A first-class design principle,
not a finishing pass. Where Part III governs the drill and Part VI the narrative, this part governs
the pixels: how every chart fills its box, how the grid packs, and how the drill panel coexists with
the board.*

The current tower already uses an `auto-fill` grid and inline-SVG charts with `width="100%"`, but
"fills the width" and "fills the *space*" are different claims. A panel can span the column and still
waste a third of its canvas on a 150px hardcoded label gutter (`Bars` in `charts.jsx`, `labW = 150`),
a fixed `w = 520` viewBox that letterboxes on a wide column, or a legend below the plot instead of
inside it. The governing idea is Tufte's **data-ink ratio** applied literally: maximise the share of
pixels that encode a number, drive chart junk to zero. Everything below is a rule an engineer could
implement against the existing `styles.css` / `charts.jsx`.

## 1. Density philosophy — the seven laws

1. **Data-ink first.** No gradient fills, drop shadows on data marks, 3-D, background image, or
   decorative gridlines. The one fill we keep is the sparkline's `opacity="0.12"` wash under the line.
2. **Small multiples over one big chart.** The tower comparison (6 towers) is far more legible as six
   aligned mini-bars sharing one x-scale than a grouped bar chart. Reserve large single charts for
   genuinely single series (the backlog stale-line).
3. **Sparklines are first-class.** Every scoreboard metric with a `weekly` series gets a word-sized
   90px trend in-tile. A number without its trajectory is half a fact — 78.9% SLA is different news if
   it was 88% four weeks ago.
4. **Every rate shows its fraction.** `compute_all` emits `num`/`den` on every tile deliberately. The
   renderer must print both. A density rule *and* an honesty rule.
5. **Abstain visibly, never silently.** A `None` week must **break the line**, not plot a zero. Empty
   space that means "not enough data" is information; a false zero is a lie on stage.
6. **Model order, not data order.** Towers render in `D.TOWERS` order, channels in
   `D.INTAKE_CHANNELS` order, so a zero-volume tower still appears as a zero row and Chat sits in a
   stable slot across regenerations. Stable position lets the eye build muscle memory.
7. **No chart junk, but keep the min/max labels.** The sparkline prints its first and last y-value as
   9px mono text at the baseline corners. That is the correct amount of axis: two numbers that bound
   the series, no tick forest.

## 2. Responsive grid that fills width at every breakpoint

The current grid (`repeat(auto-fill, minmax(min(100%, 380px), 1fr))`) is the right skeleton and needs
three extensions.

**Extension A — panel weight classes.** Assign width by information shape: `.span-1` (default — tiles,
single distributions, the intake donut); `.span-2` (time series needing horizontal room for 14 weekly
points: `BacklogFlow`, `PairingPanel`, the weekly trend); `.span-full` (wide tables that would
otherwise scroll: `Towers` 8×6, `AnalystBand` 12 analysts + 2σ band). Add a mid-tier at `1200px` where
`.span-full` stays full but `.span-2` drops to `span 1` so a 2-up layout does not force a lone panel
onto its own row.

**Extension B — `auto-fill`→`auto-fit` for sparse lenses.** On a wide screen an odd panel count under
`auto-fill` leaves phantom empty tracks (auto-fill *reserves* empty columns). `auto-fit` *collapses*
empty tracks and lets real panels expand. For this page **`auto-fit` is the correct default** and
directly serves "no real estate left."

**Extension C — dense packing.** Add `grid-auto-flow: dense` so a `.span-2` panel's 1-track hole is
back-filled by the next `.span-1` panel instead of leaving whitespace. Acceptable here because panels
are self-titled and independent — no narrative requires strict top-to-bottom reading within a lens.

**Container-query upgrade (near-term).** Wrap each panel body in a container context
(`container-type: inline-size`) and switch the chart's internal geometry on `@container` width, not
`@media`. This is what finally lets a chart fill *its own* box rather than the window's.

## 3. How each chart fills its allotted space

The failure today is fixed pixel viewBoxes and hardcoded gutters. **Aspect handling:** `Sparkline`
uses `preserveAspectRatio="none"` (fine for a decorative spark), but `BacklogFlow` — where slope is
the message — gets `xMidYMid meet` and a height that tracks container width via `aspect-ratio`. Fixed
`h` values become floors, not constants, so a tall column fills vertically. **Axis economy:** drop
full axes; the vocabulary is min/max endpoint labels, in-canvas value labels on bars, and **direct
labelling** on multi-series lines (put the series name at the *end* of the line in its colour — the
reader never crosses to a legend). **In-canvas legends:** render the donut legend *inside* the centre
hole; never a `.legend` flex row consuming a fresh 24px band. **Edge-to-edge plotting:** replace
`Bars`' `labW = 150` / `valW = 56` constants (236px of a 520px canvas = 45% gutter before a single bar
is drawn) with a **measured** label gutter = `max(measured longest label, 22% of width)` capped at
30%; on narrow containers move the label *above* each bar so the full width becomes plot — the single
biggest space reclaim on mobile.

| Panel | Primitive | Fill rule |
|---|---|---|
| Scoreboard tiles | number + `.kpi-spark` | value at `1.55rem`, 90px spark edge-to-edge, num/den in `.sub` |
| Weekly trend | `Sparkline` | `.span-2`, `meet` aspect, break on `None` weeks |
| FTR-vs-reopen | dual-axis line | `.span-2`, both axes labelled with range, direct end-labels |
| Analyst 2σ band | `AnalystBand` | `.span-full`, 640px+ floor, gutter sized to longest name |
| KB gap by tower/reason | `Bars` | gutter = measured, value labels in-bar-right |
| Tower comparison | table + inline mini-bars | `.span-full`, sparkline column per metric |
| Intake mix | donut | legend in centre hole, Chat slice flagged `shadow` |
| Ageing histogram | `Bars` vertical | ≥14d buckets shaded `--warn`, "54 of 62 over 30d" in-canvas |
| Backlog & flow | dual line (open/aged) | `.span-2`, meet aspect, "not growing, staling" is the slope |

## 4. The always-on KPI strip & progressive disclosure

The strip stays pinned above the lens grid at every breakpoint, `repeat(auto-fit, minmax(150px, 1fr))`
with a 1px `--rule` gap reading as hairline dividers — a table without table chrome. Six KPIs for OPS
Overview: FTR 61.8%, escalation 40.7%, reopen 4.3%, resolution SLA 78.9%, response SLA 96.6%, aged-14d
60. Each tile: mono uppercase label, big value (tabular-nums), sub-line with num/den and a verdict
pill, a 90px spark. **Tier-aware relabelling:** under L1 the strip foregrounds FTR, response SLA,
escalation-*out*; under L2, escalation-*in* volume, resolution SLA, KB gap — same `scoreboard` object,
reframed, no recomputation. **Progressive disclosure, three depths:** *Glance* (value + verdict —
"are we okay?"); *Context* (in-tile spark + num/den — "trending which way, over how many?"); *Detail*
(click opens the drawer with the full breakdown + Jira link — "which tickets?"). Every tile is
keyboard-activatable, so depth 3 is reachable without a mouse.

## 5. The right-side drill panel — layout & coexistence with the board

Today `Drawer` is an **overlay** with a scrim — but an overlay *hides the board it is explaining*. The
upgrade is **push, not overlay, on wide screens**: **≥1200px: push** — the drawer docks right and the
`main` grid shrinks its `max-width` (transitioned 160ms), so the chart the user clicked stays visible
beside its own explanation; grid `auto-fit` reflows automatically. **<1200px: overlay** — not enough
width to push without crushing the board. This is the one place a query switches interaction model,
not just geometry. **Resizable & remembered width:** a 4px drag handle, clamps `[360px, 640px]`,
persists to `localStorage`. Internal layout stays tight: sticky header, a single big number
(`.drill-big`) as the answer, a `.kv` definition grid for the breakdown, a `.drill-note` for the
metric's caveat, a pinned `.drawer-jira` CTA deep-linking Jira with the exact JQL. The drawer *reuses*
`Sparkline`/`Bars` — the drill trend is the same primitive as the panel, so they cannot disagree.

## 6. Dashboard composition per lens & per project

**Per lens** — each is a curated deck, not the same 13 panels reshuffled. *Overview (10 panels):* the
whole system, reading top-left (health) to bottom-right (where work is stuck). *L1 (7 panels):* front
line — queue-by-status(L1), response SLA, the FTR-vs-reopen honesty pair, the analyst 2σ band, KB gap
as "what you couldn't deflect," channel quality, intake. The question: *what should we escalate and
who is escalating oddly?* *L2 (7 panels):* second line — queue-by-status(L2), resolution SLA, KB gap
as debt to *write*, escalation reasons, tower comparison, ageing-by-status, backlog flow. The
question: *what is arriving, and what KB articles clear the most future load?*

**Per project.** `OPS` and `ITSM` share the metric core but not the story. The composition rule:
**panels whose data is untrustworthy on a project are suppressed on that project, not shown greyed.** A
panel that would mislead is worse than a missing panel. Drive this off `invariants()` — a panel resting
on a *failed* invariant (`backlog_series` if its `Resolved At` iff Done check fires) is **suppressed
entirely**, exactly as the metric core mandates.

## 7. Theming, typography & colour for accessibility

**Theming.** Three modes from one button: `dark` → `light` → `auto`, persisted. Every colour is a CSS
variable (`--ink`, `--accent`, `--ok/--warn/--crit`) redefined per theme — a brand swap is editing ~14
variables. **Typography.** Two families: a system sans for prose, a mono for every *number, label, and
axis* — tabular-nums means digits align in columns and never jitter as a live value ticks. **Colour &
accessibility (WCAG 2.1 AA, colour-blind-safe):** semantic colour is *reinforced*, never sole carrier
— PASS/GAP is a text pill *and* a colour; an SLA-breach bar is `--crit` *and* labelled; outlier dots
sit *outside* the 2σ band so position encodes the alarm and colour only confirms it. Contrast verified
(`--crit` on light ~5.9:1, on dark ~5.2:1, both clear AA). `:focus-visible` outlines on every clickable
tile/row — keyboard drill reachability is a hard requirement.

## 8. Saved views, personalisation & layout editing

A view = `{project, days, lens, drawerWidth, panelOrder, hiddenPanels}` serialised to a URL hash *and*
named in `localStorage` — hash-first so a view is **shareable by link** with no backend. **Layout
editing:** an "arrange" toggle turns each panel header into a drag handle and adds per-panel hide/show;
because panels are self-contained and the grid is `auto-fit` + `dense`, reordering never breaks layout.
**Defaults are curated, not empty** — a first-time visitor lands on the designed Overview deck;
personalisation is opt-in. Never ship an empty canvas the user must assemble (the 12-blank-gadget
failure of dashboard 10001, restated in React).

## 9. Export & share

Four backend-free outputs: **PNG** (per-panel and whole-board, rendered client-side from the inline
SVG); **PDF** (a print stylesheet forcing light theme, expanding every `.span-*` to full width
one-per-row, dropping interactive affordances — `window.print()` needs no library); **Link** (the
URL-hash saved view); and **Embed / TV-wallboard mode** (`?mode=wallboard` — hides all chrome, pins the
KPI strip large, cycles lenses on a timer, disables the drawer, forces high-contrast, re-polls on the
existing 5-min cadence). The wallboard is the highest-density presentation of all — pure data-ink,
zero interaction chrome — and the truest test of the "space optimally occupied" mandate.

## 10. Anti-patterns to avoid

Wasted whitespace inside a chart (the `labW = 150` gutter, 45% of the canvas); giant single-number
cards (a 4rem number alone is a poster — every big number carries its fraction, trend, and verdict);
sparse tables (few rows → render as bars; reserve tables for the dense cases); fixed pixel viewBoxes
that letterbox; false zeros (plotting `None` as 0 — the edge weeks would read 0% and 100%, the two
loudest, emptiest points); legends far from data; colour as sole signal; empty default canvas; and
overlay drills that hide their own subject (on a wide screen, push, don't cover).

---

# Part VIII — Data & Analytics Foundation

*What the data/model layer must become to power the record-level drills of Part III, every chart in
Parts IV–V, and the insights of Part VI. This is the substrate under all of them, and its keystone —
the record-level projection — is the Now-horizon dependency the whole Next horizon stands on.*

The tower is honest about one thing above all: every percentage carries its numerator and denominator,
and every panel that cannot state a number abstains. That discipline lives in `app/analytics.py` —
pure functions over `app/store.Issue` records, `compute_all(rows, now, days)` the single entry point.
But the *artifact that reaches the browser* is not those records — it is the aggregate JSON in
`OPS-90.json`/`ITSM-90.json`, and the record layer that produced those rollups is thrown away at the
CI boundary. That is the gravity well this part pushes against: **drills, segmentation, real trends,
and trust checks all want the records, and the records are exactly what the current pipeline
discards.**

## 1. The core constraint: aggregate-only baked JSON

Read the top-level keys of `OPS-90.json` and there is no `issues` array — 14 `weekly` points, 13
`backlog` points, 6 `towers` rows, 4 `intake` rows, and no way to get from any mark back to the
tickets underneath it. The KB-gap panel is the cleanest example of the cost: `kb_gap_breakdown` already
computes the backlog *in priority order*, but a manager who clicks a tower's gap count gets a count and
a filter URL, not the tickets with their troubleshooting notes to write the article from. The insight
is computed and then amputated at the last mile.

**Enabler — record-level dataset.** Emit, alongside the rollups, a **record-level projection**: one
row per issue carrying exactly the fields drills and client-side segmentation need. `store.Issue`
already defines the shape — `key`, `tower`, `tier`, `priority`, `intake`, `status`,
`escalation_reason`, `kb_checked`, `root_cause`, `resolution_code`, `l1_analyst`, `l2_analyst`, the
four real timeline datetimes, the two SLA verdicts, and the derived booleans that *are the
denominators* (`counts_as_closed`, `counts_as_ftr`, `is_escalated`, `is_reopened`, `kb_gap`,
`is_open`, `is_problem`). 420 OPS + 421 ITSM rows of ~two dozen scalar fields is tens of kilobytes
gzipped. Once the records ride along, **every drill becomes a client-side filter of an array already
in the browser**, and the Jira deep link degrades gracefully to what it should always have been: an
*escape hatch to the source of truth*, not the only way to see a row. The unlock cascades — the drawer
can page, sort, and sub-segment without CI; a tooltip can list top-5 contributing keys; the "78.9%
SLA, 306/82" drawer can enumerate the 82 breached and the 21 paused-and-excluded, so the exclusion is
auditable rather than asserted.

## 2. Keep the analytics core pure — the drill must not fork the model

The reason the tower reconciles to the CLI baseline field-by-field is that there is exactly one model.
`compute_all(rows, now, 90)` against a frozen snapshot is a complete regression test runnable offline
in milliseconds. The temptation the record layer introduces is a second computation path: the browser
now has the raw rows, so it is tempting to let JavaScript recompute a rate during a drill. **That is
the failure mode to design out from day one.** The moment escalation rate is computed in Python for the
headline and re-derived in JS for the drill, the two will disagree — over a Problem that should be in
the denominator, over `Cancelled` counting as Done, over the reopen numerator that ranges the window
while its denominator is the closed set. A JS reimplementation will not know these warts are
load-bearing and will "fix" them.

**Enabler — segment-aware pure core.** Keep *all* arithmetic in the pure core and make the record layer
a **transport of inputs, not a substitute for the computation**. `compute_all` grows the ability to
run over any sub-population — same functions, same denominators, restricted `rows`. The bake
pre-computes the segment cuts the UI offers by calling the *same* functions with filtered inputs; the
browser *selects which pre-computed cut to show*, or at most filters the record array for enumeration
(listing keys) — never re-derives a published rate. The invariant to protect: **any number with a
percent sign came out of `analytics.py`.** The browser may show rows; it may not do statistics.

## 3. Segmentation dimensions as first-class

Every dimension the tower cuts on is already a field on the record, but the *baked* form only exposes
the handful of cuts someone hard-coded a panel for. The dimensions that deserve first-class status:
**Tower** (cf_10042, 6 values — the primary routing cut); **Tier** (L1/L2/L3-Vendor — the
workflow-state axis that is the whole thesis); **Priority** (P1–P4, derived — carried but **barely cut
on today**; SLA-by-priority is a named target metric currently uncomputed); **Channel**
(Portal/Email/Monitoring/Chat — Chat flagged `shadow`); **Status** (11 on OPS — `ageing_by_status`
separates owned from paused); **Analyst** (`L1/L2 Analyst` text fields, never the API-account
assignee); **Request type** (ITSM only, 17 types — **not on `store.Issue` at all today**, a genuine
schema extension); **Issue type** (present via `is_problem` but not a general cut).

**Enabler — a segmentation contract.** Treat these dimensions as a declared set so a cut on any (or a
crosstab of two) is a supported operation of the pure core rather than a bespoke function. The record
layer makes *enumeration* free; the pure core makes *rates* correct. Together they turn "escalation
rate by priority within Database" from a code change into a selection. The discipline that rides along:
`MIN_WEEK_DENOM` and `MIN_ANALYST_N` exist because a cut can slice the population below the point where
a rate means anything — a tower × priority × week cell will routinely hold three tickets, and the
honest rendering is a broken line, not a spike.

## 4. Historical snapshots — the difference between a trend and a re-slice

The subtlest and most important gap. The tower has exactly **one time axis: `Reported At`**. Jira's own
`created`/`resolutiondate` are uniformly *today* because the seeder cannot backdate them over REST, and
`analytics.py` bans them from every time axis. So today's "trends" are **cohort re-slices of the
current state, not history**: a `weekly_series` week is a *cohort* rate ("of tickets reported that
week, how many *ended up* meeting SLA"), which is why recent weeks are thin and must be dimmed. It means
the tower can never answer "was escalation rate rising *in May* as we saw it then."

The one genuinely historical thing is `backlog_series`/`backlog_as_of` — "the panel Jira structurally
cannot draw." Because the four timeline datetimes are stored *values*, `backlog_as_of(rows, t)` can
rewind (open at `t` iff reported by `t` and not resolved by `t`), revealing the real finding: open flat
at ~65 while aged climbs 0→60 — *staling, not growing*. But the ceiling: reconstruction cannot recover
anything whose *value* changed without a timestamp — a ticket's priority three weeks ago, how long it
sat in `Escalated to L2`. That history lives in the **Jira changelog**, which `store.Issue` already
carries and then **drops at the aggregate boundary** just like the records.

**Enabler — a snapshot store.** Two moves in order of cost: (1) **Persist the daily bake as a time
series** — keeping dated outputs instead of overwriting immediately yields *real* observed trends to
sit *beside* the cohort trends; nearly free, a retention policy on an artifact already produced. (2)
**Promote the changelog to a first-class timeline** — the parsed changelog surviving the bake as a
record-level companion (transitions per issue, timestamped) turns "156 tickets passed through
`Escalated to L2`" into a *distribution of how long they sat there*, the substrate for MTTR-by-tier
(a named target metric not yet computed). The governing invariant already exists: `backlog_as_of`'s
soundness rests on "`Resolved At is None` iff `statusCategory != Done`" — if it fires, suppress the
panel rather than show a reconstruction the data no longer supports.

## 5. SLA from the timeline as the source of truth

`_sla` excludes three states from the denominator, each deliberate: **Paused** (21 live — counting a
paused ticket as breached "bills the tower for the customer's silence"), **In progress** (not yet
adjudicated), and **None** (exactly the 11 Problems). The SLA calendar differs across projects: OPS
runs P1/P2 on 24×7 and P3/P4 on business hours, while ITSM records 24×7 for *all* priorities — so the
same field means subtly different things per project. On OPS the SLA verdict is a **stored field**,
written once by `sla_engine.evaluate` because JSM was not provisioned — a *snapshot*, not recomputed
from the live timeline.

**Enabler — the timeline as the SLA source of truth.** Compute SLA attainment from `reported_at →
first_response_at` and `reported_at → resolved_at`, minus paused intervals, against the per-priority
calendar — every time, from the timeline, rather than trusting a stored verdict. The building blocks
exist (`sla_engine.business_hours_between`, the paused-status set). This makes the verdict
**reconstructable** (auditable in a drill — "breached because 9.2 business hours elapsed against an
8-hour P2 target, with no pause"), **robust to a wrong stored verdict** (28 Closed ITSM Incidents read
"Met" against their own dates, failing *safely* only because nothing recomputes them), and it is the
clean seam for the JSM migration: a timeline-derived computation is the vendor-neutral definition that
lets the tower cross-check the native engine rather than inherit its bugs.

## 6. Data quality, trust, and invariants

The tower's most distinctive asset: it treats data quality as a first-class, *rendered* output.
`invariants()` checks every assumption a panel silently rests on; `check_weekly_sums()` verifies the
weekly buckets partition the window so a row cannot vanish from a sparkline while still counting in the
headline. In both baked files today these arrays are **empty** — the bar to hold. The invariants encode
real, discovered defects: **Problems carrying an SLA verdict** (ITSM-265, live); **the ITSM native-SLA
wrong-dates problem** (`everBreached()` = 0 while the modelled field shows 68 breaches — "do not open
the native SLA panel"); **the approvals gap** (25 tickets with an empty approver list, so Change/CAB
analytics are *not computable* today — a data-availability fact the foundation must surface, not paper
over); **timeline chronology inversions and unset resolution** (358 OPS Done tickets with no
`resolution` value).

**Enabler — invariants as a shipping contract, extended to the record layer.** Once rows ship, new
invariants become checkable client-side and enforceable at bake time: every drilled row belongs to the
aggregate it was reached through, every record's derived booleans are self-consistent (`kb_gap` implies
`is_escalated`; `counts_as_ftr` implies `counts_as_closed`), and every rate shown in a drawer
re-derives from the rows it enumerates. The governing rule: **a panel whose invariant has failed is
asserting something the data no longer supports — so suppress it rather than show it.**

## 7. Refresh cadence — baked-daily vs a live path

The current architecture is a deliberate, defensible compromise: data is **baked daily by CI** (a job
holds the token, runs `fetch` — 5 requests / ~4s for OPS's 420 issues — runs `compute_all`, commits
the JSON), the token stays in CI and **never reaches the browser**. Genuinely good for a public
artifact: no server, no token to leak, no Jira load from viewers, a static site that cannot be knocked
over. Its ceiling: numbers are **up to 24 hours stale** and there is no interactive path for anything
the bake did not pre-compute. Fine for a manager's daily review; not fine for "which P1s are breaching
*right now*."

**Enabler — a tiered freshness model**, not a binary: (1) **Baked daily (today)** — trend, baseline,
board-review; the right default and the safe public tier. (2) **Baked more often + snapshot retention**
— bake hourly, keep dated outputs; cheaper than a live backend, buys the observed-trend series. (3) **A
token-holding backend for the live path** — record-level drills paging fresh rows, real-time breach
clocks — requires a service holding the token, because the token *cannot* live in a public browser.
This is the real architectural fork: a server, an auth boundary, per-viewer Jira load, a secret to
manage. The pure core makes it *possible* without a rewrite (the backend runs the same `analytics.py`),
but it is a deliberate tier: **the static tier serves the *argument* (the 90-day baseline, trends,
structural claims); a live tier serves *operations* (the queue you work from), and only the latter
needs the token-holding backend.**

## 8. Multi-project and multi-instance scaling

The tower already runs over two projects — `OPS-90.json` and `ITSM-90.json` are the same `compute_all`
output shape over different `--project` inputs — because `app/` resolves custom-field ids **by name at
runtime** through `shared/fields.py`, which is what lets the metrics run against *any* instance built
to this design. The friction is real and visible: `OPS-90.json` carries a warning that `Urgency` is
*ambiguous on this instance* — two custom fields share the name (`cf_10044` and `cf_10071`) — and the
resolver picks one and says so, with an override to pin it. Multiply that across instances and it
becomes the central scaling problem: **the same logical field has different ids, and sometimes
duplicate names, per instance.**

**Enabler — an instance registry and a normalized model.** Scaling to N projects across M instances
needs: (a) a declared per-instance field-resolution manifest so a bake is reproducible and a new
instance is onboarded by configuration, not code; (b) aggregate + record outputs keyed by `(instance,
project, window)`; and (c) explicit modelling of where projects legitimately *diverge* so cross-project
rollups do not silently average incomparable things. OPS and ITSM are the worked example of divergence
that must be respected, not smoothed: OPS's escalation is a genuine status (156 tickets through
`Escalated to L2`) while ITSM's `Escalated` exists only in two Service Request workflows (18 tickets);
OPS uses business hours for P3/P4 while ITSM records 24×7 for all; ITSM adds request types and CSAT OPS
lacks. A naive "total escalation rate across both projects" is a category error. Make each tower
comparable *on the dimensions that are genuinely shared* (the 20 common fields, the priority scheme)
and carry the divergences as first-class context.

## 9. Privacy and access

The record-level move makes this unavoidable. The tower is served from **public GitHub Pages**. The
aggregate JSON today is defensible in the open — counts and rates, no ticket content, no requester
identity, no free text. Shipping record-level rows changes that calculus completely: `store.Issue`
carries `Troubleshooting Performed` (free text, the whole point of which is real diagnostic detail),
`Affected Service`, analyst names, `Root Cause`, and the changelog. On a *production* instance those
fields contain customer-identifying and operationally sensitive information, and a public static page
that ships them is a data-exposure incident regardless of how useful the drill is. The demo instance is
safe because it is seeded; the design must not bake that safety in as an assumption.

**Enabler — access-tiered projections**, decided at bake time (a public page cannot keep a secret it
has already shipped). A **public projection** carries only what the aggregates already imply — keys,
dimensions, timeline datetimes, SLA verdicts, derived booleans — everything needed for counting,
sorting, and deep-linking, and *nothing* free-text or identifying; the drill deep-links to Jira for the
sensitive detail, which Jira then gates behind the viewer's own permissions. A **private projection** —
the full record, free text and changelog included — is only ever served from an authenticated,
access-controlled deployment (the §7 token-holding backend, behind SSO). This maps onto the freshness
tiers cleanly. The rule: **the bake decides what leaves the trusted boundary, and once a field is in a
public JSON it is public forever — so the projection, not the UI, is where privacy is enforced.**

## Summary — the dependency spine

**Record-level projection (§1)** is the keystone: it unblocks real drills, client-side segmentation,
and record-level trust checks at once. It is only safe if the **pure core stays the sole source of
every rate (§2)** and only responsible through **access-tiered projections (§9)**. **First-class
segmentation (§3)** and **timeline-derived SLA (§5)** are the pure core earning its keep over richer
inputs. **Historical snapshots (§4)** are the one thing the one-axis model genuinely cannot do and the
highest-value net-new capability. **Invariants as a shipping contract (§6)** is what lets all of this
scale without a silent disagreement found on stage. **Freshness (§7)** and **multi-instance (§8)** are
the deployment envelope — with the token-holding backend as the single fork separating the public
*argument* from the operational *surface*.

---

# Part IX — Adoption, Success Metrics, Governance, Risks & Differentiation

*The preceding parts argue *what to build*. This one argues how the thing lands, how we know it
worked, why it cannot be bought off a shelf, and what will most plausibly kill it — grounded in the
instance as it stands on 2026-07-21.*

## 1. How the product lands

The control tower is a **reporting and decision surface**, not the operational change. The operational
change — one issue key, one SLA clock, the enforced escalation gate, the KB loop — is what `PILOT.md`
and `ROLLOUT.md` sequence. The tower rides that sequence rather than running ahead of it, for one
reason: a dashboard over a tower not yet running the model shows numbers nobody believes, and a
disbelieved dashboard is dead on arrival.

- **Pilot — End User Computing (126 tickets, 61.9% FTR).** The tower is the pilot's instrument.
  `PILOT.md` §5 exit criteria are *already computed panels*, not manual analyses: criterion 6 renders
  `criterion_6: "met" | "gap"` as a line ("12 analysts, 0 outside 2σ — criterion 6 met"), never a
  hardcoded string. Criteria 2 (FTR moved ≥ +5pp) and 3 (reopen did not rise) are the paired
  `ftr_vs_reopen` panel, which exists precisely so FTR bought by premature closure is caught in the
  same chart. The pilot *is* the tower's first real user.
- **Wave rollout — Enterprise Apps → Network → Compute & Storage → Database → Cloud & Security.** Each
  wave gets a per-tower view (`tower_table()` emits one row per tower in model order, zero-volume towers
  as zero rows). The tower's job across waves is to make the *compounding KB loop* visible: opening
  escalation rate must fall wave over wave — "if wave 2's opening escalation rate is not below wave
  1's, the loop is not working." That is a *go/no-go gate between waves*, not a vanity trend.
- **General availability = the tower is read without prompting.** "The real test is not attainment, it
  is whether anyone opens the report." Adoption of *this product* is precisely a tower manager opening
  the page unprompted to answer a live question.

**The two honesty checks come first, deliberately.** Criteria 3 (reopen did not rise) and 6 (no routing
around the gate) block rollout even when the headline improves. A product that ships its own
falsification tests on the front page is a different category of trustworthy from one that ships a
green number.

## 2. Success metrics for the product itself

Note the distinction the whole repo is built on: **metrics of the support tower** (FTR, escalation,
SLA — the content) versus **metrics of the software product** (is anyone using it, does it change
decisions — this section). The latter must not be vanity.

| Metric | Definition on this instance | Why it is not vanity | Target posture |
|---|---|---|---|
| **WAU (tower managers + leads)** | Distinct human openers per week, against the known population: 3 leads + 1 MIM + tower managers | Small, closed, nameable population — 8–10 people. "6 of 8 leads opened it this week" is a real number | Set from pilot |
| **Decisions-influenced** | go/no-go and wave gates resolved *using a panel* — logged as a KB/problem record or a wave decision | The product's actual job: adjudicating the seven exit criteria and five between-wave gates | Every gate decision cites the panel that settled it |
| **Time-to-insight** | Wall-clock from question to answer | The answer used to be unavailable at any latency — "nobody can answer from data." The counterfactual is ∞, not "slow" | Sub-minute via drill drawer vs. a JQL session |
| **Drill usage** | Fraction of sessions that open ≥1 right-side drawer | Distinguishes *looking* from *interrogating*. A tower drilled into is being trusted enough to check | Rising drawer-opens/session across waves |
| **Insight-acted-on rate** | KB articles written from the `kb_gap_breakdown` list ÷ gap items surfaced | Closes to the operational loop: "if analysts flag missing articles and nothing is ever written, they stop flagging within a fortnight" | ≥10 articles from the no-article queue |
| **Baseline-replacement rate** | Placeholder targets replaced by measured ones | The product is *finished per tower* only when its placeholders are gone. Cannot be gamed — you either measured or you didn't | → 0 placeholders at GA |

**Deliberately excluded as vanity:** page-view totals, session duration (longer is ambiguous), panel
count, "insights generated." The repo's own culture rejects these — an unbid ROI model was *removed* as
"pure downside in a capability demo." **Instrumentation reality:** the Pages deployment is static with
no server to log against, so WAU/drill telemetry needs either a lightweight privacy-preserving beacon
(aggregate counts only) or — more honestly for a closed 8-person audience — a **manual decision log**
alongside the wave gates. For a population this small, the manual log is more trustworthy: you can name
every user, so you can ask them.

## 3. Make-vs-buy: why not native Jira dashboards or off-the-shelf BI

This is the moat, and every claim is a specific thing the alternatives *structurally cannot do* on this
data.

**Why not native Jira dashboards.** `ITSM` dashboard 10035 is a genuinely good native dashboard — 11
bound gadgets, real distributions. It is also the ceiling, and the ceiling is low: (1) **No
custom-datetime trending** — native gadgets key off `created`, uniformly today; the native "Time to
resolution" SLA reports 0 breaches across the whole `ITSM` project while the modelled field shows 68.
(2) **No backlog rewind** — `backlog_as_of` reconstructs open-and-aged at any past instant; "the panel
Jira structurally cannot draw." (3) **No pause-aware SLA** — native JSM measures from `created` and
cannot express the business-hours-P3/P4 vs 24×7-P1/P2 split; `_sla()` excludes the 21 legitimately
paused so the tower is not "billed for the customer's silence." (4) **No per-analyst normalisation** —
`analyst_escalation()` is a 2σ band with a `MIN_ANALYST_N = 20` floor whose justification is *measured*
(without it one new starter's first three tickets widens the band to [7%, 82%], inside which no real
outlier can be detected). (5) **Blank-gadget failure mode** — `OPS` dashboard 10001 rendered as 12
blank gadgets; native dashboards fail quietly and wrong, while the tower ships an `invariants()` footer
that *suppresses* a broken panel.

**Why not off-the-shelf BI (Tableau / Power BI / Looker).** BI could draw the marks. What it cannot
cheaply replicate is the **fidelity contract**: `analytics.py` reproduces `metrics.py`'s JQL answers
*field-by-field, warts included* — FTR excludes Problems but escalation does not (40.7%, not 39.6%);
`Cancelled` counts as Done. A BI analyst re-implementing these would "improve" the asymmetries and the
tower would then **contradict the CLI baseline on the same screen** — the exact failure the module's
docstring exists to prevent. And the **insights are structural, not empirical**: `ftr_vs_reopen` shares
a denominator so neither metric can be gamed alone; `pairing_note` ships Pearson r "with the n visible,
and NEVER as a claim of causation." Off-the-shelf BI optimises for "make the number look good"; this
optimises for "make the number un-gameable." Opposite objective functions. **One model, many front
ends** — the static tower, the React app, and the metrics CLI all consume `analytics.build_model`, so
they cannot disagree; a BI layer is a *fourth* implementation, and the fourth is where the disagreement
lives.

**The moat, stated once:** the value is not the charts — it is the ~40 encoded, tested, warts-preserved
metric decisions in `analytics.py`, each with a comment saying why it is that way and what breaks if you
"fix" it. That is a body of operational judgement. Charts are a commodity; the judgement is not, and it
does not survive a port to a tool that treats metrics as drag-and-drop.

## 4. Governance and trust

The repo already runs a governance regime most products never reach: **Single source of truth** —
`app/metrics.py` is the reference implementation; `analytics.py` reproduces it exactly and the rule is
explicit, "if a wart is ever fixed, it must be fixed in metrics.py FIRST and both must move together."
**Versioned claims** — `CLAIMS.md` exists "because a claim was previously asserted in four documents
before being checked, and shipped wrong"; every assertion carries a status (VERIFIED / UNVERIFIED /
PLACEHOLDER / RETRACTED) and its evidence, and retractions are *kept* so the error is not reintroduced.
**Data quality as a rendered contract** — `invariants()` and `check_weekly_sums()` are executable
governance, not a policy document. **Placeholders are labelled, not hidden** — every rate renders with
its numerator and denominator.

## 5. Privacy and security

The hosting model is the crux and is already correct — the roadmap's job is to keep it correct as scope
grows. **Public host, no server, no token** — the browser fetches only static JSON; it never calls
Jira. **The data on a public page is the real exposure surface** — the baked JSON contains ticket keys,
tower names, statuses, SLA verdicts, and — critically — **analyst names on the escalation-rate panel**.
*Publish-to-team* is not *publish-to-the-internet*. **Roadmap requirement: the escalation-per-analyst
panel must not carry real names on a public URL.** Options in order of preference: (a) private
Pages/access-controlled host for any named-individual view; (b) pseudonymise analysts in the public
bake and keep the mapping in CI; (c) aggregate-only public view with the named view behind auth. This
is the single highest-priority privacy item and it is currently unaddressed. **PII minimisation at the
bake** — the export should emit the narrowest model the panels need; free-text fields
(`Troubleshooting Performed`) should not leave CI unless a panel renders them. **Deep links, not
embedded data** — every drawer keeps the sensitive detail in Jira behind Jira's auth. **No credentials
in the repo.**

## 6. Top risks and mitigations

| # | Risk | How it shows up here | Mitigation (grounded) |
|---|---|---|---|
| 1 | **Data drift** — snapshot diverges from live Jira | The scheduled rules *will* mutate the instance (auto-close ~39 Resolved tickets; breach-warning starts commenting); `baseline.json` already went stale (81.6%/82.2% vs live 78.9%/96.6%) | Daily bake keeps Pages within 24h by construction. **Rule: no slide or panel quotes a number older than the last bake; kill stale artifacts like `baseline.json` on sight.** |
| 2 | **Scope creep** — panels grow faster than trust | 13 panels today; every new one is a new place a number can disagree | The layer boundary is the brake: a new panel is a pure function over the same records, testable offline in ms. New panels must ship with an `invariants()` entry or they don't ship. |
| 3 | **Jira API limits / fragility** | Intermittent CloudFront 403 HTML "were the single largest source of wrong conclusions during probing"; the internal automation API is undocumented | The tower reads Jira in **5 requests** for 420 issues — cheap, once daily. Baking in CI means the public site never touches Jira live. Retry on cloudfront-403. |
| 4 | **Over-alerting** — the tower becomes noise | The breach-warning rule comments on every open P1/P2 daily; a tower that pings constantly gets muted | Alerts fire on *derived, paused-aware* SLA state, not raw elapsed. The `rate_point()` floor already refuses to plot noise; extend that discipline to alerts — no alert on a sub-floor denominator. |
| 5 | **Vanity metrics** — the product measures its own activity | The temptation of page views, panel counts | §2 excludes these by name; the precedent is the removed ROI model. Every product metric ties to a decision it changed, or it is cut. |
| 6 | **Gate bypass / gaming** — corrupts the data the tower reads | If the gate is routed around via the major-incident fast path, "it produces confident-looking escalation data that is false" | The tower *measures the bypass* — fast-path usage and per-analyst 2σ divergence are panels, so gaming is visible in the instrument, not hidden by it. |

## 7. Guiding principles

1. **Reproduce the wart, then argue about it in the open.** A tower that silently disagrees with the
   CLI baseline is worse than one that reproduces a known wart — disagreement discovered in the room is
   the worst outcome.
2. **Every rate carries its denominator.** "61.8% 215/348" on every tile.
3. **Abstain rather than lie.** A broken line, not a plotted zero, below 10 tickets; suppress a panel
   whose invariant fired.
4. **Nothing enters a deliverable without a claim-register row first.** Publish the known-wrong list;
   keep retractions so errors don't return.
5. **Placeholders are labelled, and their removal is the finish line.**
6. **The app outlives the vendor.** `app/` resolves fields by name at runtime and reads no build state,
   so the metrics run against any instance built to this design.
7. **The token stays in CI; the public page shows aggregates and links to detail** — and no named
   individual on a public URL.
8. **Measure decisions changed, not pixels served.**

---

# Appendix A — Chart Index / Glossary

Every chart in Parts IV and V in one place, with its ID, name, status, and the decision it drives.
`[B]` = built today · `[N]` = net-new · `[×I]` = no honest ITSM equivalent. Full definitions live in
the catalogs; this is the lookup table.

## A.1 — OPS charts (Part IV)

| ID | Name | Status | Drives |
|---|---|---|---|
| A1 | Intake channel mix | B | Formalise shadow (Chat) support? |
| A2 | Weekly intake volume (demand curve) | B | Staff to the arrival curve |
| A3 | Intake → priority skew | N | Does Monitoring catch P1/P2 faster? |
| A4 | Intake mix by tower | N | Which towers are portal-mature |
| B1 | Front-line queue (L1 open work) | B | Where L1 work piles up |
| B2 | Triage dwell (New+Triage) | N ×I | Delay in starting vs doing |
| B3 | First-response attainment (response SLA) | B | Is L1 acknowledging fast enough |
| B4 | First-response attainment by priority | N | Fast where speed is contractual? |
| C1 | Escalation rate (headline) | B | Is L1 resolving enough at first tier |
| C2 | Escalation per L1 analyst — 2σ band | B ×I | PILOT criterion 6 (no analyst >2σ) |
| C3 | Escalation gate evidence completeness | N | Is the gate producing data |
| C4 | Gate-bypass detector | N ×I | Real transitions vs field-set-after-fact |
| C5 | Why work escalates (reason mix) | B | Which reasons are L1-fixable |
| C6 | Escalation reason × tower matrix | N | Per-cell remediation |
| C7 | Escalation reason × root cause confusion | N | Were escalations diagnostically correct |
| D1 | Tier flow Sankey | N ×I | Actual paths vs designed |
| D2 | De-escalation / ping-pong count | N | Bouncing between tiers |
| D3 | Time-in-tier decomposition (L1 vs L2 dwell) | N ×I | Where calendar time goes |
| D4 | Escalation latency | N | Escalating early or after churn |
| E1 | Resolution SLA outcome | B | Hitting resolution targets |
| E2 | SLA attainment by priority | N | Breaches in critical priorities? |
| E3 | Response vs resolution paired attainment | N | Answering or fixing |
| E4 | SLA pause coverage (rule 5) | N | Is rule 5 firing on every pending |
| E5 | Weekly SLA trend (cohort) | B | Improving or drifting |
| E6 | Breach concentration by tower | N | Which tower's SLA is failing |
| F1 | KB gap rate | B | Write the missing articles |
| F2 | KB gap by tower (write-next backlog) | B | Which tower's KB to build |
| F3 | KB gap by escalation reason | B | What kind of article is missing |
| F4 | KB check discipline | N | Content gap vs process gap |
| F5 | KB deflection potential | N | Escalations avoidable by top-N articles |
| G1 | First-time resolution (FTR) — North Star | B | The single best measure of L1 health |
| G2 | FTR ↔ reopen paired panel | B | Is FTR real or bought by early closing |
| G3 | Reopen rate | B | Is L1 closing prematurely |
| G4 | Reopen cohort by tower / resolver | N | Is premature-close concentrated |
| G5 | Resolution code mix | N | Quality of closures |
| H1 | L1 analyst load | N ×I | Is work evenly distributed |
| H2 | L2 analyst load by tower | N | Single-point-of-failure detection |
| H3 | Shift-level throughput | N | Is night shift escalating more |
| H4 | Handling time per analyst | N | Dumps-quickly vs works-then-escalates |
| I1 | Aged backlog (≥14d) | B | How much old work is rotting |
| I2 | Open-work ageing histogram | B | Backlog new (fixable) or stale (rotting) |
| I3 | Ageing owned vs paused | B | Don't accuse the tower of paused work |
| I4 | Backlog reconstruction (open vs aged over time) | B ×I | Growing or staling |
| I5 | Flow: arrivals vs completions | N | Keeping up with demand |
| J1 | Impact × Urgency matrix (priority derivation) | N | Priority derived, not free-picked |
| J2 | Priority-derivation conformance (rule 1) | N | Is rule 1 enforcing the matrix |
| J3 | Open work by priority | N | Queue weighted to high priority? |
| J4 | Priority inflation trend | N | Is severity creeping up |
| K1 | Major-incident volume & MTTR | N | How bad and how fast on the fast path |
| K2 | Major-incident MTTA | N | Detection→acknowledge fast enough |
| K3 | Fast-path accountability | N ×I | Fast path used by the accountable role |
| L1–L6 | Automation-rule effectiveness (rules 1,5,6,4,7,2) | N | Is each live rule actually firing |
| M1 | Tower comparison table | B | Which tower to pilot — big AND weak |
| M2 | Channel quality (FTR & escalation per channel) | B | Is Chat worse quality than Portal |
| M3 | Root-cause pareto | N | Which root causes drive most volume |
| N1 | Invariant footer | B | Is any panel silently lying |
| N2 | Weekly-sum reconciliation | B | Does the page agree with itself |

## A.2 — ITSM charts (Part V)

| ID | Name | Family | Drives |
|---|---|---|---|
| 1.1 | Incident MTTA | Incident | First SLA a requester feels |
| 1.2 | Incident MTTR (pause-aware) | Incident | The headline incident number |
| 1.3 | Incident resolution SLA attainment | Incident | The contractual number |
| 1.4 | Incident reopen rate | Incident | Broken-promise signal |
| 1.5 | Major-incident count & MTTR | Incident | Reputational events, board metric |
| 1.6 | Incident priority matrix heatmap | Incident | Priority derived not negotiated |
| 1.7 | Incident volume by tower | Incident | Where the fire is |
| 1.8 | Incident escalation rate (tier crossover) | Incident | Over-escalating L1 signal |
| 1.9 | Recurring-incident cluster (→ Problem) | Incident | Bridge into Problem management |
| 2.1 | Request volume by request type | Request | The fulfilment catalog load |
| 2.2 | Fulfilment SLA by request type | Request | Long-tail slow types |
| 2.3 | Request fulfilment aging | Request | Requests rotting behind incidents |
| 2.4 | Portal self-service deflection rate | Request | The ITIL efficiency lever |
| 2.5 | Shadow-support (Chat) intake | Request | Size of the shadow desk |
| 2.6 | First-time-fulfilment rate | Request | Which types to fully automate |
| 2.7 | Approvals-bearing vs standard requests | Request | Isolate approval wait |
| 3.1 | Change success rate | Change | The single ITIL change KPI |
| 3.2 | Failed & backed-out changes | Change | The risk dial |
| 3.3 | Emergency-change ratio | Change | Change management bypassed under pressure |
| 3.4 | CAB approval cycle time | Change | The most common change bottleneck |
| 3.5 | Change calendar / freeze-window adherence | Change | Freeze violations (audit findings) |
| 3.6 | Change-caused incidents | Change | The truest measure of change quality |
| 3.7 | Change volume & lead time by type | Change | Pipeline throughput/predictability |
| 4.1 | Open problems & known-error backlog | Problem | Root-cause work → reusable knowledge |
| 4.2 | RCA cycle time | Problem | RCA that never finishes never deflects |
| 4.3 | Recurring-incident → problem linkage | Problem | Are problems attached to their incidents |
| 4.4 | Problem→incident reduction (deflection proof) | Problem | The ROI of problem management |
| 4.5 | Problems by root cause | Problem | Where to invest (infra/process/vendor) |
| 5.1 | SLA attainment by request type & priority | SLA/OLA | The decision-dense SLA view |
| 5.2 | Time-to-first-response SLA | SLA/OLA | The SLA customers judge hourly |
| 5.3 | Resolution SLA outcome mix | SLA/OLA | The pause bucket = trust |
| 5.4 | OLA: L1→L2 handoff time | SLA/OLA | Internal handoff rotting |
| 5.5 | Pause-time attribution | SLA/OLA | "We're slow" vs "they're slow" |
| 5.6 | Native-vs-modelled SLA reconciliation | SLA/OLA | Fix-tracker (the gap is the bug) |
| 6.1 | CSAT score & response rate | CSAT | The only customer-sourced outcome |
| 6.2 | CSAT vs SLA-met cross-tab | CSAT | "SLA-met and still unhappy" |
| 6.3 | CES (customer effort proxy) | CSAT | Effort predicts churn |
| 6.4 | CSAT by tower / agent / request type | CSAT | Localize dissatisfaction |
| 7.1 | Queue depth across all 19 queues | Queue | The daily standup artifact |
| 7.2 | Unassigned / triage backlog | Queue | Un-owned = SLA-at-risk |
| 7.3 | Workload distribution (agent balance) | Queue | Burnout / SLA risk |
| 7.4 | Per-analyst escalation 2σ band (ported) | Queue | Who over-escalates |
| 7.5 | Queue SLA-risk mix | Queue | Reprioritize by risk, not size |
| 8.1 | Approval backlog & aging | Approvals | Stalled approvals nobody owns |
| 8.2 | Approval cycle time (modelled) | Approvals | The approval SLA to set |
| 8.3 | Approval defect panel (data-quality) | Approvals | Fix-tracker (empty approver list) |
| 9.1 | Aged backlog (>14d) snapshot | Backlog | The desk's staling debt |
| 9.2 | Backlog aging by request type | Backlog | Which catalog items rot |
| 9.3 | Owned vs paused aging | Backlog | Don't accuse the desk of paused work |
| 9.4 | Backlog inflow vs outflow (CFD) | Backlog | Is the desk keeping up |
| 10.1 | SLA-at-risk queue (75% burn) | At-risk | The save-list for the next hour |
| 10.2 | Breach forecast (EOD / week) | At-risk | Pull people onto the queue now? |
| 10.3 | P1/P2 at-risk board | At-risk | Highest-cost breaches first |
| 11.1 | KB gap (escalated, no article found) | Knowledge | The biggest deflection lever |
| 11.2 | KB gap by tower | Knowledge | Which article to write next |
| 11.3 | KB gap by escalation reason | Knowledge | The kind of missing knowledge |
| 11.4 | Deflection funnel | Knowledge | Where the portal fails to deflect |
| 12.1 | Intake channel mix | Portal | Channel strategy |
| 12.2 | Channel quality (FTR & escalation) | Portal | Shadow-support made measurable |
| 12.3 | Monitoring-origin volume | Portal | The automatable slice |
| 12.4 | Portal availability / anon-access defect | Portal | Fix-tracker (demo authenticated) |
| 13 | ITSM data-quality remediation board | Cross-cut | The defects the roadmap burns down |

## A.3 — Glossary of load-bearing terms

- **FTR (First-Time Resolution)** — closed non-Problem tickets resolved at L1 ÷ all closed non-Problem.
  The North Star. `215/347 = 61.8%` on OPS.
- **Escalation rate** — `tier == L2` ÷ all windowed rows, Problems *included* (deliberate asymmetry vs
  FTR). `171/419 = 40.7%`.
- **KB gap** — escalations with `KB Article Checked = "Yes - none found"` (checked and absent, distinct
  from "No" = not checked). `79/171 = 46%` on OPS — the single largest measured lever.
- **Reported At** (`cf_10057`) — the tower's only valid time axis; Jira's `created` is uniformly today
  on the seed.
- **Paused** — SLA clock stopped in Pending Customer / Pending Vendor; excluded from the SLA
  denominator so the tower is not "billed for the customer's silence."
- **`pilot_score`** — `volume × (100 − FTR%)`; ranks which tower to pilot (big AND weak first).
- **2σ band** — per-analyst escalation band with a `MIN_ANALYST_N = 20` floor; PILOT criterion 6.
- **`MIN_WEEK_DENOM` (10)** — below this, `rate_point` returns `None` and the line breaks rather than
  plotting a 0%/100% edge-week artifact.
- **`invariants()`** — the rendered data-quality contract; a panel whose invariant fails is
  *suppressed*, not shown.
- **Cohort trend vs observed trend** — a `weekly_series` point is a *cohort* rate (of tickets reported
  that week); observed trends require snapshot retention (Part VIII §4).

---

# Closing — If We Only Did Three Things

If the roadmap were cut to three moves, these are the three — chosen because each is the smallest work
that unblocks the most, and because together they convert the tower from a persuasive demo into a
decision surface an operator trusts.

1. **Ship the escalation-per-analyst privacy fix, and enforce the gate.** The privacy fix is the one
   item where the current design is *actively wrong* for a public host — it exposes named individuals'
   escalation rates on the open internet, and it blocks nothing to fix (pseudonymise at the bake, keep
   the mapping in CI). Alongside it, build the workflow validator so the `In Progress L1 → Escalated to
   L2` transition *rejects* a missing gate field — the 30-minute UI task that converts the escalation
   story from "seeded" to "enforced." Together they make the tower safe to show and true under load.

2. **Ship the record layer and wire the pilot/wave gates in as rendered verdicts.** The record-level
   export (CI already holds the rows) is the keystone the entire Next horizon stands on — drill-to-
   record, client-side segmentation, and record-level trust checks all fall out of it at once. Then
   make the product *adjudicate* the decisions `PILOT.md`/`ROLLOUT.md` already specify: criterion 6
   already computes `met`/`gap`; opening-escalation-rate-per-wave is one line on existing series. This
   is what turns a dashboard into a decision surface and gives every product metric something real to
   attach to.

3. **Kill stale artifacts and make single-source a CI check.** Regenerate `baseline.json` (still
   quoting ghost numbers), and make "no number ships without its denominator and its `CLAIMS.md` row" a
   CI gate — because the entire moat is trust in the numbers, and trust is lost one un-reconciled figure
   at a time. The tower's distinctive claim is not that it charts well; it is that it never lies, and
   knows what it cannot say. That claim is worth defending mechanically.

*The one-line test of success, restated: a new Ops Manager opens the tower on their first morning,
reads the scoreboard, drills one mark to the ticket rows behind it, and knows — without asking anyone —
which tower to pilot next and why.*

---

<sub>*This roadmap was synthesised from nine parallel deep-dive analyses (personas, horizons,
the drill-down system, the OPS and ITSM chart catalogs, insights, information design, the data
foundation, and adoption), each grounded by reading the live repo — `PROBLEM.md`, `PLAN.md`,
`SCHEMA.md`, `CONTROL-TOWER.md`, `app/analytics.py`, and the baked `OPS-90.json` / `ITSM-90.json`
models — then assembled into one document. It is a living plan: every number is measured against
the instance as of 2026-07-21 and should be re-grounded as the instance evolves.*</sub>
