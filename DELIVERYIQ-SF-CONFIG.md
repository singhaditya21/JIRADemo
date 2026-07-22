# DeliveryIQ — Salesforce Config-Request Monitoring (design spec)

> **Status: DESIGN ONLY — no code.** A no-code spec/roadmap for adding a Salesforce
> Configuration Request monitoring lens to the existing control tower.
> Source: the two DeliveryIQ slides + the four scoping decisions confirmed in chat
> (2026-07-22). See [PLAN.md](PLAN.md), [ROADMAP.md](ROADMAP.md), [CONTROL-TOWER.md](CONTROL-TOWER.md).

**Confirmed scope**
1. **Data source** — Salesforce Config Requests are tracked as **Jira tickets** (read through the same bake). No live Salesforce API assumed.
2. **"Configuration status" = all three** — pipeline **stage** (Intake→Build→Review→Deploy→Audit) · per-**org deploy state** (validated/deployed/failed) · live **config health**.
3. **Placement** — a **new lens/project ("Delivery / SF Config", `SFC`)** alongside OPS and ITSM in the same tower.
4. **Scope** — **both** the monitoring/status (Audit) surface **and** the three agents' actions (Build/Comply/Coord).

---

## 0. Canonical conventions (authoritative — supersedes the drafted sections)

This spec's Sections 1–7 were drafted in parallel and diverged on names, ids, and enums. **This section is the single source of truth**; where a later section disagrees, this wins.

> **Decisions — RESOLVED 2026-07-22.** All five open decisions are now answered (below), so nothing here is pending: per-org carrier = **Model A (Org Deploy sub-tasks)**; CI/CD deploy writeback = **exists now → deploy state is REAL**; config health = **a real probe writes health + drift → health is REAL**; naming + enums = **the §0 proposals accepted**. Net effect: the deploy-status and config-health half of the lens is **REAL from the start**, not modelled — so the P2 boards ship real, and the P2.5 "code hinge" is already satisfied. The per-record **`Source` badge (CI / Manual / Seeded)** stays, so the integrity strip can still show which cells are CI-written vs hand-entered vs seeded.

**Naming (proposed).**
- Project / lens: name **"Delivery — SF Config"**, key **`SFC`**, lens id **`SFC`** (sits beside `OPS` and `ITSM`).
- Issue type: **"Salesforce Config Request"** (shorthand *SCR*).
- Time anchor: **`Reported At` (cf_10057)** — every windowed cut keys off this, never Jira `created` (same as OPS/ITSM).

**Field-id allocation (proposed).** New `SFC`-only custom fields take the next free block from **cf_10061** upward, allocated once at build time by `jira_config/build.py` — the ids in Sections 1/4/5 are *placeholders*, not live ids (unlike `SCHEMA.md`'s verified cf ids). Reused fields keep their existing verified ids (Tower cf_10042, Impact cf_10004, Urgency cf_10044, dates cf_10057–10060, SLA cf_10050/10051, etc.), given a **project-scoped context** for `SFC` so new options don't leak into OPS/ITSM.

**Canonical enums (proposed).**
- **Deploy State** (per org): `Not started · Validated · Deploying · Deployed · Failed · Rolled back`.
- **Config Health** (per org): `Healthy · Degraded · Failing · Unknown` — **default `Unknown`**; a health verdict with no fresh `Health Checked At` renders **stale/`Unknown`, never green**.
- **Source** (on both Deploy State and Config Health): `CI writeback · Manual · Seeded` — this field is what lets the integrity strip say *"N of M orgs have real CI-written state; the rest are modelled."*

**Per-org carrier — RESOLVED: Model A (`Org Deploy` sub-tasks).** An SCR targets N orgs, each with its own deploy state + health; a flat Jira field can't hold "Deployed in UAT, Failed in Prod." **Chosen: one `Org Deploy` sub-task per target org**, each carrying its own `Deploy State`, `Config Health`, `Health Checked At`, `Source`, and evidence links; the parent SCR carries the roll-up. Per-org counts then reconcile **natively** — "orgs where deploy failed" is literally a sub-task query, num/den exact, the tower's non-negotiable. The bake reads the sub-tasks as child records; the roll-up (e.g. SCR is "Deployed" only when *all* target orgs are Deployed) is computed in `analytics.py`. (Model B — a `Deploy Matrix` JSON field — is dropped.)

**Config-health source — REVISED 2026-07-22: MODELLED, no live Salesforce.** The earlier decision assumed a real health/drift probe would write back. There is **no live Salesforce instance** in this deployment (per the agreed scope — config requests are tracked *as Jira issues*), so per-org `Deploy State` and `Config Health` are **MODELLED**, not observed telemetry. The writeback job (`app/sfc_writeback.py`) maintains them on each `Org Deploy` sub-task with a **real** `Health Checked At` and `Source = Modelled`. What stays **REAL**: the Jira writeback itself and the timestamp — so the staleness guard is genuine: a verdict whose `Health Checked At` is stale renders **`Unknown`/greyed**, never green. If a real Salesforce org is ever connected, swap `deploy_health_model()` for the Tooling/Metadata API and write `Source = CI writeback` to distinguish observed from modelled.

**The writeback — REVISED: a real Jira-side job maintaining MODELLED values.** A GitHub Action (`sfc-writeback.yml`) writes `Deploy State`, `Config Health`, and `Health Checked At` back to Jira per run with `Source = Modelled`. The mechanism is real (real Jira mutations, real timestamps); the values are modelled because there is nothing to observe. The `Source` badge (Modelled / Seeded / Manual) is rendered per cell, so the integrity strip honestly reports which cells the writeback job refreshed vs. raw-seeded, and nothing is dressed up as a live Salesforce read.

---

## 1. Domain & data model — the Salesforce Config Request

A **Salesforce Config Request** (issue type key `SCR`) is one deployable unit of Salesforce configuration — a package or change set — tracked from intake to audited deployment across one or more target orgs. It is the atom the new **`SFC` lens** ("Delivery / SF Config") counts, exactly as `OPS` counts Incidents and `ITSM` counts requests. It lives in a new company-managed project `SFC` so it can carry its own workflow and screens while **reusing the same 20 global custom fields** that back `OPS` and `ITSM` (`CONTROL-TOWER.md` §1) — reuse, not duplication, so the bake's name→id resolution and every reconciliation invariant keep working unchanged.

**Lifecycle intent.** Its lifecycle is *not* the L1/L2 incident lifecycle — it is the DeliveryIQ pipeline. One `SCR` moves `Intake → Build → Review → Deploy → Audit`, produces a change artifact, deploys to a set of orgs, and ends with an evidence pack. The five stages map to purpose-built statuses (`Intake · In Build · In Review · Awaiting CAB · Deploying · Deployed · Audit · Done`, plus `Rolled Back · Cancelled`); **`DeliveryIQ Stage` is *derived from status*, never hand-set**, the same way Priority is derived from Impact×Urgency — so the stage panel and a status filter cannot disagree.

### The one modelling decision that shapes everything: the per-org fan-out

A single `SCR` targets N orgs, and each org has its own deploy state and health. A flat Jira field is single-valued and cannot honestly hold "Deployed in UAT, Failed in Prod." Two honest models, and the choice is a real fork:

- **Model A — Deploy sub-tasks (recommended when CI can create them).** One `Org Deploy` sub-task per target org, each carrying its own `Deploy State`, `Config Health`, and evidence links; the parent `SCR` carries the roll-up. Per-org counts then **reconcile natively** — a drill list of "orgs where deploy failed" is literally a sub-task query, num/den exact — which is the tower's non-negotiable (`BRIEF`/design principles). Cost: issue-count inflation and a second screen.
- **Model B — structured roll-up field.** One `Deploy Matrix` text/JSON field on the parent (`org → {state, health, run}`), written by CI, that the bake parses into per-org rows at model time. Lighter, but a text blob reconciles only as well as the parser, and it is *only as real as the CI writeback*.

Recommendation: **Model A** where the pipeline can write sub-tasks; **Model B** as the degraded fallback. The field table below names the fields that live on whichever carrier the org picks.

### Field table — reused tower fields (existing custom-field ids, repurposed for `SFC`)

Each is an existing field from `SCHEMA.md` §1. Where the semantics shift, the shared select needs a **project-scoped context** for `SFC` so its options don't leak into `OPS`/`ITSM` (the 20 fields are global contexts today — adding options globally would pollute the other two lenses; a company-managed second context is the clean fix).

| Field | id | Jira type | What it means for an `SCR` | Set by | REAL vs MODELLED |
|---|---|---|---|---|---|
| Tower | `cf_10042` | Select (scoped ctx) | **Requesting team / delivery squad** — the primary dashboard cut axis, preserving "one axis drives every panel" | Author at intake | **REAL** |
| Priority | system, scheme `10166` | Priority | P1–P4, **derived** Impact×Urgency by automation rule 1 | Automation | **REAL** (derived) |
| Impact | `cf_10004` | Select | Business **blast radius** of the change (how much of the org it touches) | Author / BUILD | **REAL** |
| Urgency | `cf_10044` | Select | Deadline pressure | Author | **REAL** |
| Intake Channel | `cf_10045` | Select | Backlog grooming / Portal / Monitoring / Chat — where the request came from | Author | **REAL** |
| Affected Service | `cf_10056` | Text | Salesforce business service touched (e.g. Lead-to-Cash, Service Console) | Author | **REAL** |
| Support Tier | `cf_10043` | Select (scoped ctx) | Execution path: **Agent / Human / Vendor** (which of the three DeliveryIQ agents drove it) | Workflow post-fn | **REAL** |
| Resolution Code | `cf_10049` | Select | Closure disposition — reuses existing `Implemented / Rolled back / Withdrawn by requester` options verbatim | BUILD/COORD at close | **REAL** |
| Reported At | `cf_10057` | DateTime | Request raised (Intake) — every chart keys off this, never `created` | Intake/seeder | **REAL** |
| First Response At | `cf_10058` | DateTime | BUILD classified + estimated (Intake→Build handoff) | BUILD agent | **REAL if BUILD writes it; else MODELLED** |
| Escalated At | `cf_10059` | DateTime | COORD raised a conflict / handoff to a human | COORD agent | **REAL if written** |
| Resolved At | `cf_10060` | DateTime | Audit complete / evidence pack ready | BUILD/COMPLY | **REAL** |
| Response SLA | `cf_10050` | Select | Pipeline SLA proxy: time-to-first-build | computed by `analytics.py` | **MODELLED** (computed from dates) |
| Resolution SLA | `cf_10051` | Select | Pipeline SLA proxy: intake→deploy, pause-aware | computed | **MODELLED** (computed) |
| L2 Analyst | `cf_10054` | Text | Named **human reviewer / owner** at the Review gate | Review stage | **REAL** |

Deliberately **unused** on `SCR` (kept null rather than repurposed, so no panel implies data that isn't there): `Escalation Reason`, `Troubleshooting Performed`, `KB Article Checked`, `Root Cause`, `L1 Analyst`, `Reopened`. `Reopened`'s *concept* re-appears as `Redeployed` below rather than overloading the incident field.

### Field table — new custom fields (`SFC`-only; ids assigned by `jira_config/build.py`)

| Field | Jira type | Who/what sets it | REAL vs MODELLED |
|---|---|---|---|
| **Target Orgs** | Multi-select checkbox — options are the named orgs (`Prod`, `Full-copy UAT`, `QA`, `Dev`, `Scratch`, …) | Author at intake — this is the deploy fan-out set | **REAL** (declared intent) |
| **Config Component Type** | Multi-select — `Field`, `Flow`, `Validation Rule`, `Permission Set`, `Page Layout`, `Custom Object`, `Apex-adjacent metadata`, `LWC-adjacent` | Author / BUILD from the diff | **REAL** |
| **Change Risk** | Select — `Low / Medium / High` (distinct from business Impact; it drives whether CAB is required) | BUILD assessment | **REAL** (a modelled estimate, but authored) |
| **Change-Set / Package Ref** | Text (URL-shaped) — sfdx package name, change-set name, or git ref/SHA | BUILD | **REAL** |
| **Deploy State** *(per org — sub-task field in Model A, or a cell of `Deploy Matrix` in Model B)* | Select — `Not started / Validated / Deploying / Deployed / Failed / Rolled back` | **CI/CD pipeline writeback** ideally | **MODELLED unless a CI writeback sets it → then REAL.** This is the single most important honesty line in the lens. |
| **Deploy State Source** | Select — `CI writeback / Manual / Seeded` | pipeline or human | **REAL** — it is a fact about *who wrote the state*, and it is what lets the INTEGRITY strip say "N of M orgs have real CI-written state, the rest are manual/modelled" rather than asserting it |
| **Config Health** *(per org)* | Select — `Healthy / Degraded / Failing / Unknown` | a **scheduled health probe** writing back | **MODELLED — the tower never reads Salesforce live.** REAL only if a probe (metadata-diff / CLI scan / monitoring integration) writes this field; otherwise it is a deploy-time snapshot at best, and `Unknown` by default |
| **Config Health Checked At** | DateTime | health probe | **REAL** (freshness of the snapshot — a health verdict with no timestamp must render as stale, not green) |
| **CAB Approval** | Select — `Not required / Pending / Approved / Rejected` | COMPLY / CAB human | **REAL** (mirrors `ITSM`'s Change gate, which is the one approval path that works end-to-end there) |
| **CAB Approver** / **CAB Decided At** | Text (or user) / DateTime | CAB | **REAL** |
| **Evidence Links** (PR · CI run · Deploy log) | Jira web-links / issue links / URL fields | BUILD + COMPLY (evidence as a byproduct) | **REAL that a link exists**; the linked artifact is external and not re-fetched by the bake |
| **Redeployed** | Select — `Yes / No` | automation on a second deploy after `Failed`/`Rolled back` | **REAL** (pairs against deploy success so neither can be gamed — the `SFC` analogue of `Reopened`) |
| **DeliveryIQ Stage** | Select (**derived from status**, not hand-set) — `Intake / Build / Review / Deploy / Audit` | bake, from the status map | **REAL** (derived; reconciles with status by construction) |

**Stage derivation** (bake, so a stage count always equals a status filter): `Intake ← {Intake}` · `Build ← {In Build}` · `Review ← {In Review, Awaiting CAB}` · `Deploy ← {Deploying, Deployed, Rolled Back}` · `Audit ← {Audit, Done}`.

### Population booleans (reconciliation — mirrors `store.build_issue`)

Each `SCR` record carries pre-computed booleans so a client-side filter agrees with the aggregate exactly, the same pattern as `is_escalated`, `kb_gap`, `counts_as_ftr`:

- `is_deployed_all` = every `Target Org` has `Deploy State == Deployed`
- `has_deploy_failure` = any org `Deploy State in {Failed, Rolled back}`
- `is_health_degraded` = any org `Config Health in {Degraded, Failing}`
- `awaiting_cab` = `CAB Approval == Pending`
- `cab_blocked` = `Change Risk == High AND CAB Approval != Approved` (the gate that should stop a high-risk deploy)
- `evidence_complete` = has PR link **and** CI-run link **and** a deploy log for every deployed org (COMPLY's "evidence as a byproduct", made countable)
- `deploy_state_is_real` = `Deploy State Source == CI writeback` — the provenance boolean that lets the INTEGRITY strip quantify real-vs-modelled per record instead of hand-waving it
- `health_is_fresh` = `Config Health Checked At` within the probe interval (else the health verdict renders grey/stale, never green)

### The honest sentence for this lens

*Intent, ownership, risk, artifact refs, CAB decisions, timestamps and evidence-link presence are **REAL from Jira**. Per-org **deploy state** and **config health** are **only as real as whatever writes them** — REAL when the CI/CD pipeline and a health probe write back into these fields, MODELLED (or `Unknown`/seeded) otherwise — and the tower never reads Salesforce live. `Deploy State Source`, `Config Health Checked At`, and the `deploy_state_is_real` / `health_is_fresh` booleans exist precisely so the lens can state, on-screen and per record, which of the two it is.*

Relevant grounding files (all absolute): `/Users/adityasingh/PersonalWork/JIRADemo/SCHEMA.md` (the 20 field ids reused), `/Users/adityasingh/PersonalWork/JIRADemo/shared/domain.py` (`SELECT_FIELDS`, Tower/Priority model), `/Users/adityasingh/PersonalWork/JIRADemo/app/store.py` `build_issue` (population-boolean pattern this section mirrors), `/Users/adityasingh/PersonalWork/JIRADemo/CONTROL-TOWER.md` §1 (global-context reuse and the ITSM Change/approval precedent).

## 2. Lifecycle → Jira workflow (the five stages as statuses)

The Salesforce-config work lands as a third **lens** — label **"Delivery / SF Config"**, project key `SFDX`, one issue type **`Salesforce Config Request`** (SFCR) — read through the exact same bake as `OPS`/`ITSM`. It gets its own workflow because the DeliveryIQ five-stage flow is not an L1/L2 escalation flow and must not be forced into `OPS`'s status ladder.

The governing rule for this section, and the thing that keeps the lens honest: **the pipeline STAGE is a workflow status (structurally REAL from Jira); per-org DEPLOY STATE and CONFIG HEALTH are fields (only as REAL as whatever writes them).** Stage lives in the status because Jira's transition engine, changelog and statusCategory already carry it for free — that is what makes ageing, the timeline and a stage-Sankey work with zero new plumbing. Per-org state cannot live in the single status (one request fans out to N target orgs that succeed and fail independently), so it lives in fields and *rolls up* into the status. Every stage timestamp, transition and actor is real Jira changelog; every "validated / deployed / healthy" bit is real **only if the CI/CD pipeline writes it back**, and is labelled MODELLED on the integrity strip otherwise.

### 2.1 The status ladder — five stages, concrete statuses

One primary status per DeliveryIQ stage on the happy path, plus explicit off-path/parking statuses so the changelog and stage-Sankey have honest nodes. `statusCategory` is assigned exactly the way `shared/domain.py STATUSES` does (neutral `new`/`indeterminate`/`done` slug, bridged in `jira_schema.STATUS_CATEGORY`), so the tower's done-vs-open logic needs no SF special case.

| DeliveryIQ stage | Jira status | statusCategory | `sof()` node (new) | primary actor |
|---|---|---|---|---|
| INTAKE | `Intake` | new | intake | User (drops ticket) |
| INTAKE (parked) | `Triage Hold` | indeterminate | intake | COMPLY / COORD |
| BUILD | `Building` | indeterminate | build | BUILD |
| BUILD (bounced) | `Changes Requested` | indeterminate | build | User / COMPLY |
| REVIEW | `In Review` | indeterminate | review | User + COMPLY |
| DEPLOY | `Deploying` | indeterminate | deploy | BUILD |
| DEPLOY (failure) | `Deploy Failed` | indeterminate | deploy | BUILD / COORD |
| DEPLOY (reversed) | `Rolled Back` | indeterminate | deploy | BUILD |
| AUDIT | `In Audit` | indeterminate | audit | COMPLY + User |
| terminal | `Done` | done | done | — |
| terminal (killed) | `Withdrawn` | **done** | done | User |

Rationale for the two terminals: `Withdrawn` carries statusCategory **Done** on purpose — it mirrors the load-bearing `OPS` wart that `Cancelled` is Done, so `closed_set` counts a withdrawn request as closed and the drill count reconciles against the JQL baseline instead of quietly disagreeing in the room. `Deploy Failed`/`Rolled Back` are *indeterminate*, not done: a failed deploy is still open work and must keep ageing.

### 2.2 Transitions and gates (entry/exit criteria + who acts)

Each transition is a Jira workflow transition with a **condition/validator = the gate**. "Who acts" is the DeliveryIQ role; the *field that records it* is named in parentheses and is what the bake reads.

| Transition | Gate (exit criteria that must be true to fire) | User | BUILD | COMPLY | COORD | REAL vs MODELLED |
|---|---|---|---|---|---|---|
| `Intake → Triage Hold` | auto: authorization or dependency check not yet green | — | classifies + estimates (`Change Class`, `Est. Effort`) | authorization unresolved (`Authorization` = Pending) | dependency scan flags a clash (`Dependency State`) | REAL (transition + fields) |
| `Intake → Building` (or `Triage Hold → Building`) | change classified **and** `Authorization = Approved` **and** `Dependency State ∈ {clear, waived}` | approves plan | draft plan attached | validates authorization | dependency scan clear | REAL |
| `Building → In Review` | change drafted **and** `Unit Tests = pass` in scratch/sandbox **and** COMPLY action-log complete | — | writes + tests change (`Test Result`, `Coverage %`) | every action logged (evidence byproduct) | routes conflicting WIP | `Unit Tests`/`Coverage %` REAL **iff** CI writeback; else MODELLED |
| `In Review → Building` = `Changes Requested` | reviewer rejects business logic or reviewer-check fails | reviews business logic | — | reviewer check fails (`Reviewer Check`) | stalled-PR alert | REAL (this is the review ping-pong) |
| `In Review → Deploying` | `Approval = Approved` (CAB/change approval) **and** `Test Result = green` **and** `Lint = pass` | CAB approval (`Approval`) | tests + lint green | reviewer sign-off | — | approval REAL (Jira approval); test/lint gate REAL iff CI writeback |
| `Deploying → In Audit` | rollup: **∀ target org `Deploy State = deployed`** (see 2.3) | — | validation + deploy | evidence captured | incident routing armed | MODELLED unless pipeline writeback |
| `Deploying → Deploy Failed` | rollup: **∃ org `Deploy State = failed`** and none still in-flight | — | reads failure | logs failure evidence | routes to incident (can spawn an `OPS`/`ITSM` incident, linked) | MODELLED unless writeback |
| `In Audit`/`Deploying → Rolled Back` | post-deploy health regression or manual revert | approves revert | executes rollback | captures rollback evidence | routes incident | MODELLED unless writeback |
| `In Audit → Done` | evidence pack assembled **and** dashboard reviewed | reviews dashboard (<1 hr/wk) | moves to next ticket | evidence pack ready (`Evidence Pack`) | bottleneck report | REAL (Jira) |
| `* → Withdrawn` | User cancels | withdraws | — | — | — | REAL |

Rationale: the gates are the DeliveryIQ stage-actions made enforceable — Jira *conditions* block the transition, so a request cannot reach `Deploying` without a real `Approval = Approved` record. That is the same shape as the existing **C4 gate-bypass detector** (`OPS` L2 work whose changelog never crossed `Escalated to L2`); the SF-lens analog is **"deployed without CAB"** — a request whose timeline reached `sof = deploy` with no prior `In Review` hop carrying `Approval = Approved`. It reuses the `crossed()` timeline predicate verbatim, only swapping the target status.

### 2.3 Where the Deploy sub-states live (per-org field + rollup)

`validating / deployed / failed / rolled-back` are **not** four workflow statuses — they are values of a repeatable field **`Deploy State`**, one instance per target org (modelled either as fields keyed by org, `Deploy State · <ORG>`, or — recommended for clean reconciliation — one **deploy sub-record** per (request × org) so each org gets its own status, changelog and ageing row). Domain: `not-targeted / validating / validated / deploying / deployed / failed / rolled-back`. `Target Orgs` (multi-select) is the denominator.

The single `Deploying` status is a **rollup** of the per-org field, so the status count always reconciles against a field-derived count (the tower's non-negotiable RECONCILES rule):

- stay `Deploying` while `∃ org Deploy State ∈ {validating, deploying}`
- `→ In Audit` when `∀ targeted org Deploy State = deployed`
- `→ Deploy Failed` when `∃ org Deploy State = failed` **and** `∄ org still in-flight`
- `→ Rolled Back` when `∃ org Deploy State = rolled-back`

REAL vs MODELLED: `Deploy State` is REAL **only** when the CI/CD job (e.g. an `sf project deploy` callback) PATCHes it back onto the Jira issue. With no writeback it is manual/MODELLED and the panel header must say so — the tower never implies it read Salesforce live. A **`Deploy Source`** enum (`pipeline-writeback` / `manual` / `unset`) is carried per record so a panel can split "N orgs deployed" into evidence-backed vs asserted, exactly how CSAT ships as a labelled proxy.

### 2.4 Config health (live org state) is a field, never a live read

`Config Health` (select: `healthy / degraded / drift-detected / broken / unknown`) + `Config Health Checked At` (date) + `Health Source` (`monitor-writeback / ci-smoke / manual / unset`), per targeted org. This is the third "configuration status" dimension. It is **MODELLED by default** and only promoted to REAL when a monitor or post-deploy smoke test writes it back; `Config Health Checked At` gives every health panel an explicit staleness axis so the integrity strip can state "health as of T, from `<source>`" rather than implying continuous live telemetry.

### 2.5 Coexistence with `tof()`, the changelog timeline, and the ageing panels

The point of putting stage in the *status* is that most of the tower is stage-agnostic and keeps working untouched; the one OPS-specific classifier does **not** transfer, and we are honest about that rather than pretending it does.

- **Ageing / `ageing_by_status` — UNCHANGED.** They key off `Reported At` and the statusCategory done/open split. Because every SF status above carries a `statusCategory`, an SFCR buckets into the ageing histogram and the per-status ageing breakdown with zero code change. `Reported At` remains the only time axis (seeder/automation stamps it; Jira `created` is still today-collapsed over REST).
- **Single-record status-changelog timeline (drill layer 4) — UNCHANGED.** It renders raw `{field, from, to, at}` hops. SFCRs carry the same compact changelog the bake writes for `OPS`/`ITSM`, so the record drawer and the four-layer drill (aggregate → cohort small-multiples → record list → timeline) work as-is, deep-linking to Jira via JQL on `project = SFDX`.
- **`tof()`-driven `TierFlow` + `TierSankey` — DO NOT REUSE on this lens.** `tof()` is an OPS-tier regex (`l2|escalat|implement → L2`, `pending|waiting → wait`, `resolv|closed|cancel → done`, else `L1`). Run over SF status names it collapses `Intake/Building/In Review/Deploying/In Audit/Deploy Failed` all to `"L1"` and only `Done/Withdrawn` to `"done"` — a meaningless near-single-node Sankey. So these two panels are tagged **`[NO-SFDX]`**, exactly as they are already `[NO-ITSM]` (ITSM has no `Escalated` node), and are suppressed on this lens.
- **Stage-flow reuses the *primitives*, not the classifier.** The SF lens gets a sibling **`sof()`** ("stage-of-flight": `intake/build/review/deploy/audit/done`, the last column of the 2.1 table) that feeds the **same** `Sankey` SVG primitive and the same hop-distribution counting over `r.timeline` that `TierSankey`/`TierFlow` use — only the per-node classifier swaps. This is precisely the pattern already in the code (`lensPanels` is project-aware; D1 is suppressed on ITSM). The stage-Sankey then honestly shows the real leakage paths — `In Review → Changes Requested` review ping-pong, `Deploying → Deploy Failed → Building`, `In Audit → Rolled Back` — as first-class ribbons, each drillable to the requests that took that edge.

### 2.6 REAL-from-Jira vs MODELLED ledger (for the integrity strip)

- **REAL, structural (no extra writer):** pipeline `stage` (workflow status), every status transition and the full changelog timeline, `Reported At` + stage-entry timestamps, actor per stage (assignee / agent field), Jira-enforced gates (`Approval`, transition conditions), ageing, stage-Sankey, gate-bypass ("deployed without CAB"), `Withdrawn`-as-Done reconciliation.
- **REAL only if a writer exists (else MODELLED, must be labelled):** per-org `Deploy State`, `Test Result`/`Coverage %`/`Lint` (need CI/CD writeback), `Config Health` (needs a monitor/smoke writeback). Each carries a `*_Source` enum so a panel splits evidence-backed from asserted.
- **MODELLED / proxy (never dressed as live):** any deploy or health bit whose `*_Source = manual/unset`; the tower states "from Jira field `<name>`, source `<source>`, as of `<checked-at>`" and never implies a live Salesforce read.

Files inspected to ground this section (all absolute): `/Users/adityasingh/PersonalWork/JIRADemo/shared/domain.py` (STATUSES, statusCategory bridge, field-by-NAME + select-field conventions), `/Users/adityasingh/PersonalWork/JIRADemo/webapp/src/panels.jsx` (`tof()` at line 789, `TierSankey`/`TierFlow`, C4 gate-bypass `crossed()` at ~1740, record `timeline` shape), `/Users/adityasingh/PersonalWork/JIRADemo/app/analytics.py` (`ageing`/`ageing_by_status`, `Reported At` time axis, closed_set/Cancelled wart), and `/Users/adityasingh/PersonalWork/JIRADemo/CONTROL-TOWER.md` + `/Users/adityasingh/PersonalWork/JIRADemo/ROADMAP.md` (OPS/ITSM lens model, Theme D `[NO-ITSM]` suppression).

I have enough to match the repo's voice, field conventions (`Title Case name → customfield id resolved at bake`), record population-boolean style (`is_*`, `*_gap`, `counts_as_*`), and the four-layer-drill / reconciliation discipline. Here is my section.

---

## 3. The configuration-status model (three dimensions)

A Salesforce-config request in the **`DLVR`** lens ("Delivery / SF Config") is one Jira issue of type **SF Config Request**, read through the same bake as `OPS` and `ITSM`. "Configuration status" is not one field — it is **three orthogonal dimensions**, each derived differently and each with a different honesty grade. The bake resolves every field by **name → `customfield` id at runtime** (same mechanism as the other two lenses), computes the three dimensions once in `app/analytics.py`, and stamps the population booleans below onto each record so a client-side drill filter and the server-side aggregate can never disagree.

The one sentence that governs the whole section: **the tower never reads Salesforce. Stage is real because Jira owns status; deploy-state and health are only as real as whatever last wrote them back to a Jira field.** Every panel that shows deploy-state or health carries a provenance chip — `REAL (CI writeback)` or `MODELLED / manual` — driven by a per-record `deploy_source` / `health_source` enum, never a global assumption.

---

### 3a. Pipeline STAGE — REAL-from-Jira

**What it is.** Where the request sits in the DeliveryIQ five-stage flow: **Intake → Build → Review → Deploy → Audit**.

**How it is represented.** A `Stage` enum on each record, *derived from Jira `status`* — not a separate field an agent can desync from the workflow. The `DLVR` workflow's statuses map many-to-one onto the five stages, exactly as `status → status_category` already does in the other lenses:

| Stage | `status` values that map to it | Terminal? |
|---|---|---|
| **Intake** | `Intake`, `Triage`, `Needs Info` | no |
| **Build** | `In Build`, `Blocked` | no |
| **Review** | `In Review`, `Changes Requested` | no |
| **Deploy** | `Ready to Deploy`, `CAB Approval`, `Deploying` | no |
| **Audit** | `Deployed / Monitoring`, `Closed`, `Cancelled` | yes (`Closed`/`Cancelled`) |

**Derivation.** `analytics.stage(status)` returns the bucket; the record also carries `stage_index ∈ 0..4` (for ordering and for the "days-in-stage" timeline), and `is_stage_regressed` — true when the status changelog shows a backward hop (e.g. `In Review → In Build`), the config-request equivalent of a reopen. *Rationale:* stage is the one dimension Jira is natively authoritative for, so it is graded **REAL** unconditionally — status and its changelog live in Jira, not in a system we are trusting to write back.

**Panel.** *Delivery pipeline* — a five-column stage board (small-multiples per target-org-set or per requesting team), each column header showing its count and its share of the open population.

---

### 3b. Per-ORG DEPLOY STATE — REAL only with a CI/CD writeback, else MODELLED

**What it is.** One config request commonly targets several orgs (e.g. `UAT`, `Staging`, `Prod-EU`, `Prod-US`). Deploy state is **per org**, not per request — so it is a *repeating* structure, which is the hard part, because a flat Jira custom field cannot hold a variable-length list of typed rows.

**How it is represented (pseudo-schema).** A repeating record of:

```
DeployTarget := { org: string,
                  state: enum(validated | deployed | failed | rolled-back),
                  deployId: string,     # the Metadata API async deploy id
                  timestamp: datetime }
```

stored **two ways at once**, deliberately:

1. **Authoritative detail — a Jira issue entity property `sf.deploy`** (`/rest/api/3/issue/{key}/properties/sf.deploy`), a JSON array of `DeployTarget`. REST-writable, versioned with the issue, and JQL-reachable per element via `issue.property[sf.deploy].state`. This is what the bake reads to build the per-org matrix. *Rationale:* an entity property is the only place a variable-length typed list survives without a marketplace app; a JSON blob in a Textarea would not be queryable per-org.
2. **Scalar roll-ups — real custom fields, so JQL/filters/queues work without parsing JSON:** `Target Orgs` (multi-select — the denominator of orgs), `Deploy Rollup` (select: `Not started | Partial | Deployed | Failed | Rolled back`), `Deployed Org Count` (number), `Last Deploy Id` (text), `Last Deploy At` (datetime).

**Rollup rule (exact, precedence-ordered).** Over the orgs listed in `Target Orgs`:

- `Rolled back` if **any** org state is `rolled-back`; else
- `Failed` if **any** org is `failed`; else
- `Deployed` **iff every** target org is `deployed`; else
- `Partial` if at least one is `deployed`/`validated` but not all; else
- `Not started`.

*Rationale:* "the request is deployed" must mean **all** target orgs are deployed — a request green on UAT but failed on Prod-US is not "deployed", and the precedence puts the worst honest state first so the rollup can never flatter a failure.

**REAL vs MODELLED — the load-bearing distinction.** The `sf.deploy` property and `Deploy Rollup` are only meaningful if something writes them:

- **REAL:** the BUILD agent's deploy job (SF CLI, `sf project deploy start`) posts each org's result back to Jira via REST on completion — real `deployId`, real `state`, real `timestamp`, `deploy_source = "ci"`. This is the target design and the only configuration in which the deploy matrix is trustworthy.
- **MODELLED / manual:** absent that hook, an engineer sets `Deploy Rollup` by hand, or the seeder fills it — `deploy_source = "manual" | "seed"`. Same fields, same panels, but every mark renders with the `MODELLED` chip and the integrity strip states it. *We never imply the value came from a pipeline it did not come from.*

**Panel.** *Deploy matrix* — request (row) × target-org (column), each cell coloured by state, with the rollup as a row summary. This is the `DLVR` analogue of the SLA-outcome pie: a distribution the audience can drill into a record and then into that record's per-org history.

---

### 3c. Live CONFIG HEALTH — never live; a timestamped Jira opinion

**What "health" can honestly mean for a Jira-tracked request.** Not "the tower inspected the org" — the tower cannot. Health is a **bundle of post-deploy signals, each a Jira field written by the same pipeline**, plus a freshness stamp:

| Signal | Field | Type | Written by |
|---|---|---|---|
| Post-deploy validation | `Validation Status` | select: `Passed \| Failed \| Not run` | deploy/validate job |
| Apex test outcome | `Apex Test Pass %` | number | test run in the deploy |
| Org coverage | `Org Coverage %` | number | test run; **<75% blocks a Prod deploy — SF's own hard gate**, so this doubles as a deploy precondition |
| Config drift | `Drift Flag` | select: `In sync \| Drift detected \| Unknown` | scheduled `deploy --dry-run` / source-tracking diff |
| Freshness | `Health Checked At` | datetime | any of the above |

**Composite derivation.** `Config Health ∈ {Healthy | Degraded | Failing | Unknown}`:

- `Failing` if `Validation Status = Failed` **or** `Org Coverage % < 75`;
- `Unknown` if `Validation Status = Not run` **or** `Health Checked At` is null;
- `Degraded` if `Drift Flag = Drift detected` **or** the check is **stale** (`Health Checked At` older than the freshness window, `health_stale = true`);
- `Healthy` only if validation passed, coverage ≥ 75, drift `In sync`, and fresh.

**Honest limits — state them on the strip.**

- The tower does **not** query Salesforce. Every value above is a Jira field; "Healthy" means *the last writeback said so, at `Health Checked At`* — not "healthy now". Precedence deliberately puts `Unknown` above `Degraded`/`Healthy` so a never-run request is never painted green.
- **Drift cannot be inferred from Jira at all.** With no scheduled compare job, `Drift Flag = Unknown` and `Config Health` is capped at `Degraded`/`Unknown` — we never assume in-sync.
- `health_source ∈ {ci, manual, seed, none}` grades every health value exactly as deploy-state is graded; `none` forces `Unknown` and the `MODELLED` chip.

**Panel.** *Config-health ribbon* — Healthy / Degraded / Failing / Unknown counts across the open population, dr“illable to the record and its `Health Checked At` timeline, with stale and drift called out as their own sub-filters.

---

### 3d. Reconciliation rule (so every count adds up)

Each record carries the exact booleans the panels sum, so a drill list filtered client-side equals the aggregate by construction — the tower's non-negotiable:

```
stage ∈ {intake,build,review,deploy,audit}     # partitions N exactly once
is_deployed_all   = Deploy Rollup == Deployed
is_deploy_failed  = Deploy Rollup == Failed
is_rolled_back    = Deploy Rollup == Rolled back
deploy_pending    = Deploy Rollup ∈ {Not started, Partial}
is_healthy | is_degraded | is_failing | health_unknown   # partitions N once
coverage_ok = Org Coverage % >= 75
drift_detected = Drift Flag == Drift detected
health_stale = age(Health Checked At) > freshness_window
deploy_source, health_source ∈ {ci, manual, seed, none}  # provenance
```

**Two identities the panels must satisfy:**

1. **Per-request dimensions each partition the population once.** `Σ stage buckets = Σ deploy-rollup buckets = Σ health buckets = N` (every request lands in exactly one bucket of each dimension). Each Kanban column, deploy-rollup slice, and health-ribbon segment equals a count of its boolean.
2. **The deploy *matrix* reconciles on a different denominator — call it out.** The per-org cells sum over **org × state**, so the denominator is **Σ |Target Orgs|**, not `N`: a request targeting three orgs contributes three cells. The identity is `deployed-cells + validated + failed + rolled-back + pending-cells = Σ|Target Orgs|`. This is a **deliberate mismatched pair** (record-level rollup vs org-level cells), documented the same way the FTR-numerator / reopen-denominator mismatch is in `analytics.py` — so no one "tidies" the matrix denominator back to `N` and silently breaks it.

**Provenance reconciles too.** Every panel reports `real = Σ(source == "ci")` vs `modelled = Σ(source != "ci")`, and the integrity strip states the split verbatim (e.g. *"Deploy state: 41 of 60 REAL from CI writeback, 19 MODELLED/manual — the tower does not read Salesforce"*). A dimension with zero CI writebacks renders entirely under the `MODELLED` chip rather than pretending to be a live status.

Enough context. I have the repo's design-doc voice, the real field/status/panel conventions (SCHEMA.md, CONTROL-TOWER.md, ROADMAP.md), the tri-state honesty pattern, and the existing cross-lens Problem→Incident linker to anchor COORD's incident routing. Here is section 4.

## 4. The three agents' actions, surfaced as monitorable outputs

The `Delivery / SF Config` lens does not only show *where a request is* (stage, per-org deploy state, config health — §2). It shows *the work the three agents did to move it there*, because a status with no evidence behind it is exactly the thing this tower exists to refuse. Slide 1's structure maps one-to-one onto three columns the tower can monitor on a single issue: **OUTPUT is what BUILD produced, EVIDENCE is what COMPLY captured, COORDINATION CONTEXT is what COORD emitted.** All three land as fields, links, changelog entries or attachments on one `SF Config Request` issue (project `DELIV`, one issue key end-to-end — the same "one key, one audit trail" choice that carries `OPS`), so the tower reads them through the identical Jira bake and every mark drills the same four layers.

**The one honesty rule for this entire section.** Everything below is a Jira artifact. It is *exactly* as real as whatever wrote it. Three sources, tagged on every row:

- **REAL** — native Jira, present and free today: workflow status (= stage), the status-changelog timeline (= the action log), issue links, Story Points, assignee, attachments, comments. The bake already carries these for `OPS`/`ITSM`.
- **WRITEBACK** — REAL *only if* the CI/CD pipeline (or the Claude Code BUILD hook) POSTs the result back to the Jira field via REST after each run. Until that writeback exists it is **MODELLED**: the seeder stamps a plausible distribution so the panels have shape for the demo, and the integrity strip names each such field as modelled. This covers everything that claims to know something about Salesforce or the build — test/lint/coverage/deploy/health/changeset/evidence-pack-ref.
- **MODELLED** — never a raw Jira field; computed once in `app/analytics.py` (so panels and CLI cannot disagree) from the REAL/WRITEBACK fields: the readiness rollup, the bottleneck report, stall thresholds, estimate-vs-actual variance.

**The tower never reads Salesforce.** Per-org deploy state and config health (§2) are Jira fields; this section pins down *who writes them* — BUILD's deploy step — and nothing here implies a live org read.

### 4.0 The monitored-field model (proposed — bake resolves NAME→id at runtime)

New fields continue the `OPS` scheme past its current max (`customfield_10060`); ids are indicative because the bake keys off field **name**, exactly as today.

| Agent | Field | id | Type | Records | Source |
|---|---|---|---|---|---|
| BUILD | Build Plan | 10061 | Textarea (ADF) | classify + approach note | REAL (BUILD writes) |
| BUILD | Build Estimate | 10062 | Number (or reuse Story Points) | estimated effort | REAL |
| BUILD | Change Set Ref | 10063 | URL/Text | PR / metadata changeset deep-link | WRITEBACK |
| BUILD | Test Result | 10064 | Select — Pass / Fail / Not run | Apex/Jest CI outcome | WRITEBACK |
| BUILD | Test Coverage % | 10065 | Number | org-min coverage at build | WRITEBACK |
| BUILD | Lint Result | 10066 | Select — Pass / Warn / Fail | PMD/ESLint static scan | WRITEBACK |
| COMPLY | Authorization Check | 10067 | Select — Authorized / Not authorized / N-A | intake authorization verdict | REAL (COMPLY writes) |
| COMPLY | Authorization Basis | 10068 | Text | CAB/approval/ticket ref behind the verdict | REAL |
| COMPLY | Reviewer Check | 10069 | Select — Passed / Changes requested / Not reviewed | business-logic review verdict | REAL |
| COMPLY | Reviewer | 10070 | Text | named reviewer (text — instance has one licensed user, per SCHEMA §1) | REAL |
| COMPLY | Evidence Pack | 10071 | Select — Ready / Building / N-A | pack rollup state (see §4.4) | MODELLED |
| COMPLY | Evidence Pack Ref | 10072 | URL | attachment/Confluence link to the assembled pack | WRITEBACK |
| COORD | Dependency Scan | 10073 | Select — Clear / Conflicts found / Not scanned | intake dependency verdict | REAL |
| COORD | Stalled Alert At | 10074 | DateTime | last stall nudge stamped | WRITEBACK (else MODELLED from age) |

Deploy result and Config Health are **not** re-declared here — they are §2's per-org fields; this section only asserts that **BUILD's Deploy step is their writer** and that per-org write is WRITEBACK. The action log needs no field: it is the native changelog the bake already carries as a compact status-timeline. *Why so few new fields:* every field must gate a transition or feed a scoreboard mark (SCHEMA §1's rule); rollups and reports are derived, not stored, so they cannot drift from their inputs.

### 4.1 BUILD — the OUTPUT column

| Stage | Output | Jira representation | Monitored as (panel · formula, carries num/den) | Source |
|---|---|---|---|---|
| Intake | classification + estimate | `Build Plan`, `Build Estimate` | *Build coverage* · `#(has_build_plan)/#(all)` — a request in Build with no plan is a red row | REAL |
| Build | drafted change | `Change Set Ref` → PR/changeset | *Draft throughput* · `#(Change Set Ref present)/#(reached Build)`; drill opens the PR | WRITEBACK |
| Review | test + lint result | `Test Result`, `Test Coverage %`, `Lint Result` | *Build quality* · test-pass `#(=Pass)/#(reached Review)`, coverage p50/min, lint-fail count | WRITEBACK |
| Deploy | deploy result per org | §2 per-org Deploy State (BUILD writes) | *Deploy outcome* · per org `#(deployed)/#(attempted)`, `#(failed)` as a drillable cohort | WRITEBACK |
| Audit | "moved to next ticket" | transition to Closed + cycle-time stamp | *Estimate vs actual* · `Build Estimate` − measured stage dwell, per tower | REAL + MODELLED |

**Evidence it leaves** (what makes it auditable): the changelog transition, the plan text, the linked PR, and the test/lint verdict fields — all timestamped by the writer. **Coordination context it emits** (what COORD consumes): "PR opened", "deploy failed on org X" — the state changes that trigger stalled-PR and incident routing below. *Why estimate-vs-actual is MODELLED:* Jira's `created` is uniformly today for seeded data (SCHEMA §1), so dwell is measured from the stage-changelog, not `created`, exactly as `OPS` measures everything off `Reported At`.

### 4.2 COMPLY — the EVIDENCE column

| Stage | Output | Jira representation | Monitored as (panel · formula) | Source |
|---|---|---|---|---|
| Intake | authorization check | `Authorization Check` + `Authorization Basis` | *Authorization coverage* · `#(Authorized)/#(all)`; any request past Intake without `Authorized` is a gate violation (mirrors the OPS escalation gate) | REAL |
| Build | action log | native changelog (no field) | *Action completeness* · `#(non-empty changelog)/#(all)`; empty-history rows flagged (the `ITSM` "empty History tab" defect, caught not hidden) | REAL |
| Review | reviewer check | `Reviewer Check` + `Reviewer` | *Review pass rate* · `#(Passed)/#(reached Review)`, `#(Changes requested)` as reopen-analog | REAL |
| Deploy | evidence pack | `Evidence Pack` + `Evidence Pack Ref` | *Evidence readiness* — see §4.4 | MODELLED + WRITEBACK |
| Audit | pack ready for auditor | `Evidence Pack = Ready` | *Audit-ready share* · `#(Ready)/#(reached Deploy)` — the <1 hr/wk audit claim, made countable | MODELLED |

*Why the action log is REAL and free:* COMPLY's "log every action" is not a new artifact — it is the status-changelog the tower already bakes. The honest framing to the room is that COMPLY *surfaces* Jira's own audit trail, it does not invent one.

### 4.3 COORD — the COORDINATION CONTEXT column

| Stage | Output | Jira representation | Monitored as (panel · formula) | Source |
|---|---|---|---|---|
| Intake | dependency scan | `Dependency Scan` + `is blocked by` links | *Dependency map* · `#(Conflicts found)/#(scanned)`; blocked cohort drillable | REAL |
| Build | conflict routing | Jira issue links (`blocks`/`is blocked by`) | *Conflict graph* · count of live blocking edges; each edge a real link, not a label | REAL |
| Review | stalled-PR alert | `Stalled Alert At` + dwell-in-status | *Stalled work* · `#(dwell > threshold in Review)`; **degrades honestly** on a daily bake (see §4.6) | WRITEBACK / MODELLED |
| Deploy | incident routing | **cross-lens link to an `OPS`/`ITSM` Incident** | *Deploy→incident linkage* · `#(failed deploys linked to an incident)/#(failed)` | REAL |
| Audit | bottleneck report | analytics-derived rollup (no field) | *Stage bottleneck* · median dwell per stage × tower; the COORD "bottleneck report" as a chart | MODELLED |

*Why incident routing is REAL:* the cross-lens issue link already exists in this repo — the Problem→Incident linker (83 live links; `tools/`/linker) — so COORD routing a failed deploy to an incident is the *same* link machinery pointed at the new lens, not a new capability. That is the strongest REAL claim in this section and should be demoed live. *Why the bottleneck report is MODELLED:* it is a derivation over stage dwell computed once in `analytics.py`, so the panel and the CLI report the identical bottleneck — never two numbers.

### 4.4 How "evidence pack ready" is represented — and why it reconciles

`Evidence Pack = Ready` is **not** a free-set flag. It is a MODELLED boolean computed in `analytics.py` as an AND over the rows that must exist:

```
evidence_pack_ready(request) =
   Authorization Check == Authorized
   AND changelog non-empty
   AND Test Result == Pass  AND  Lint Result != Fail
   AND Reviewer Check == Passed
   AND Deploy State == deployed  for EVERY target org      (§2)
```

Because "Ready" is the conjunction of its evidence rows, the readiness panel **reconciles exactly**: its numerator equals the count of requests where every underlying boolean is true, and the record drill lists precisely which rows are missing on the not-ready requests (this mirrors the tower's population-boolean rule — the record carries the exact predicate so a client filter agrees with the aggregate). `Evidence Pack Ref` (the assembled attachment/Confluence link) is WRITEBACK and orthogonal: a pack can be *computed-ready* before the artifact is *assembled*, and the panel shows that gap rather than papering over it. *Why compute rather than store:* a stored "Ready" flag can be set while its evidence is absent — the precise dishonesty ("evidence pack ready" as theatre) this lens is meant to expose.

### 4.5 REAL vs MODELLED ledger (what the integrity strip must say)

| Claim on screen | Verdict | Integrity-strip line |
|---|---|---|
| Stage, action log, review verdict, authorization, dependency/conflict/incident links | **REAL** | "Stage, audit trail, reviews, authorization and cross-team links are read from Jira." |
| Change Set Ref, Test/Lint/Coverage, per-org Deploy State, Config Health, Evidence Pack Ref | **WRITEBACK — REAL iff the pipeline posts back; otherwise MODELLED** | "Build, test and deploy results are written by the CI/CD pipeline into Jira. Where no writeback is wired, they are seeded and labelled modelled — the tower does not read Salesforce." |
| Evidence-pack-ready, bottleneck report, estimate-vs-actual, stall threshold | **MODELLED (derived)** | "Readiness, bottleneck and variance are computed from the fields above, not entered." |

### 4.6 Honest limits

- **Config health is the least real thing here** and BUILD/COMPLY do not produce it — it is a *post-deploy readback* that only a Salesforce→Jira writeback can make real. Absent that, it is MODELLED; say so (§2 owns the field, this section owns the disclaimer that no agent output stands behind it yet).
- **Stalled-PR alerting needs freshness the daily bake does not have.** On today's once-a-day snapshot, `Stalled Alert At` can only be *reconstructed* from stage dwell, not fired in time to save a PR — so it ships as a lagging indicator, and true alerting is a **Next**-horizon capability gated on the near-real-time backend (ROADMAP Part I). Do not narrate live alerting off a daily bake.
- **Do not fabricate timing the changelog cannot support.** Every dwell, cycle-time and variance keys off the stage-changelog, never `created` (uniformly today for seeded data) — the same discipline that keeps the `OPS` trend charts honest.

## 5. The "Delivery / SF Config" lens — panels & drills

New lens id `SFC` in `index.json`, a third switchable project alongside `OPS` and `ITSM`. Backed by a Jira project (key `SFC`, "Delivery — Salesforce Config") with one primary issue type, **`SF Config Request`**, read through the *same* bake: fields by NAME→`customfield` id at runtime, a compact status-changelog timeline on every record, one `analytics.compute_all(rows, now, window)` so the panels and any CLI cannot disagree. Everything below reconciles the same way the OPS panels do — a drill list's row count equals the mark's numerator/denominator, and every record carries the population booleans that let a client-side filter reproduce the aggregate exactly.

**The one honesty rule for this whole lens, stated once and enforced in the model.** The tower never reads Salesforce. *Pipeline stage, time-in-stage and "stalled" are REAL* — they are derived from the Jira **status changelog**, the same mechanism that makes the OPS tier-flow honest. *Per-org deploy state and config health are Jira fields, and are only as real as whatever writes them.* The design assumes a **CI/CD writeback** (SF CLI / DevOps Center / Gearset / Copado posting to Jira with a service token) and records the provenance of each such field in a companion `… Source` select — `CI writeback` / `Manual` / `Seeded-model`. Any board that reads deploy state or health **renders the value with its source badge**, folds absent-writeback rows into an explicit **`Unknown`** bucket, and is forbidden from painting `Unknown` green. This is the config-lens equivalent of the ITSM "native SLA measures the wrong date" honesty note: the number exists, but the strip says who wrote it.

### 5.0 Pseudo-schema — the fields this lens reads

Proposed NEW fields (ids continue the live scheme, which currently ends at `customfield_10060`; existing OPS/ITSM fields are reused unchanged where they apply — `Tower` `cf_10042`, `Reported At` `cf_10057`).

| Field | Proposed id | Type | Provenance | Feeds |
|---|---|---|---|---|
| Target Orgs | `customfield_10070` | Multi-select `{DEV, UAT, STG, PROD}` | REAL — set at Intake | funnel population, org board denominators |
| Deploy State — *‹org›* (family of 4) | `customfield_10071`…`_10074` | Select `{Not started, Validated, Deployed, Failed, Rolled back}` | **Writeback** | org×state heatmap, success rate |
| Deploy Source | `customfield_10088` | Select `{CI writeback, Manual, Seeded-model}` | REAL (meta) | integrity board, source badges |
| Deploy Run Id / Pipeline URL | `customfield_10086` | Text (URL) | Writeback (proof) | record-layer link-out, integrity |
| Deployed At — *‹org›* (family) | `customfield_10087`… | DateTime | Writeback | lead-time to PROD |
| Config Health — *‹org›* (family) | `customfield_10075` (PROD)… | Select `{Healthy, Drifted, Degraded, Unknown}` | **Writeback (org scan)** | health board |
| Config Health Score | `customfield_10076` | Number 0–100 | Writeback | health board sort |
| Health Checked At / Health Source | `customfield_10077` / `_10089` | DateTime / Select | REAL (meta) | staleness, source badge |
| Change Type / Change Risk | `customfield_10078` / `_10079` | Select `{config, metadata, flow, apex}` / `{low, med, high}` | REAL | cohort cuts, at-risk weighting |
| Evidence: Plan Approved · Tests Passed · Static Scan Clean · CAB Approval · Deploy Log · Post-Deploy Validation | `customfield_10080`…`_10085` | Select `{Yes, No, N/A}` | **Comply-written** | evidence-pack board |
| Evidence Source | `customfield_10090` | Select `{Agent, Human, Seeded-model}` | REAL (meta) | integrity board |

**Stage is computed, never stored** — like Support Tier is bucketed from status in OPS. `STAGE_OF(status)` maps the `SFC` workflow's statuses onto the five DeliveryIQ stages:

| Stage | Statuses (statusCategory) |
|---|---|
| INTAKE | `Intake` · `Triaged` (To Do) |
| BUILD | `In Build` · `Build Blocked` (In Progress) |
| REVIEW | `In Review` · `Changes Requested` (In Progress) |
| DEPLOY | `Ready to Deploy` · `Deploying` · `Deploy Failed` (In Progress) |
| AUDIT | `In Audit` · `Evidence Ready` (In Progress) · `Done` · `Cancelled` (Done) |

Record booleans the model stamps (so filters reconcile to aggregates): `stage`, `time_in_stage_h`, `is_stalled`, `deploy_failed_any`, `deployed_prod`, `rolled_back_any`, `evidence_complete`, `health_known_prod`, `health_healthy_prod`, `writeback_backed`.

---

### 5.1 KPI strip (six tiles — the scoreboard for this lens)

Same contract as the OPS six-tile scoreboard: each tile carries `num`/`den`, a target, a verdict (`PASS`/`GAP`), and a one-click drill. Counter-metrics are paired so no headline can be gamed alone (the config-lens analogue of FTR↔reopen).

| Tile | Formula | Provenance | Target / verdict | Drill |
|---|---|---|---|---|
| **Lead time → PROD** | median(`Deployed At — PROD` − `Reported At`) over windowed requests that reached PROD-Deployed | REAL clock + writeback stamp | ≤ 10 business days · "le" | requests deployed to PROD |
| **PROD deploy success** | `deployed_prod` / (`deployed_prod` + PROD-`Failed` attempts) | Writeback | ≥ 90% · GAP if below | `Deploy State — PROD = Failed` |
| **Rollback rate** *(counter-metric)* | `rolled_back_any` / `deployed_prod` | Writeback | ≤ 5% — pairs against success so a reckless deploy can't flatter it | `Deploy State — PROD = "Rolled back"` |
| **Stalled / at-risk WIP** | distinct open requests with any at-risk reason (§5.7) | REAL (changelog) | flow health, not a rate | the at-risk queue |
| **Evidence-pack readiness** | `evidence_complete` / requests at DEPLOY∪AUDIT | Comply-written | ≥ 95% before DEPLOY | incomplete packs |
| **PROD config health** | `health_healthy_prod` / `health_known_prod`, **with `Unknown` shown beside it** | Writeback (org scan) | informational — labelled, never a fake green | health board |

Rationale: five stages, three "config status" dimensions (stage / per-org deploy / health) and the Comply surface each get exactly one headline; the sixth tile is a counter-metric. Health is deliberately *informational with an Unknown companion* rather than a pass/fail, because a red/green health verdict the writeback can't support would be the exact dishonesty the integrity strip exists to forbid.

---

### 5.2 Five-stage delivery funnel `[NEW]`

MEASURES: count of windowed `SF Config Request` rows per `STAGE_OF(status)` — Intake → Build → Review → Deploy → Audit — with a **stalled overlay** per stage (`is_stalled` = open AND `time_in_stage_h ≥ STALL[stage]`, thresholds `{Intake 24h, Build 72h, Review 48h, Deploy 24h, Audit 120h}`). · DECISION: where does delivery pile up, and where is it *stuck* vs merely *in flight*? · VISUAL: five-bar funnel/flow with a hatched stalled sub-bar on each stage; small "Done this window" endcap. · RECONCILES: stage counts **partition** the windowed population — `Σ stage = total windowed rows` (a `check_stage_sums` acceptance line mirrors OPS's `check_weekly_sums`); the stalled sub-bar count equals the at-risk queue rows tagged `stalled@stage`. · PROVENANCE: **REAL** (status + changelog only). · DRILL: stage bar → `project = SFC AND status in (‹stage statuses›)`; stalled sub-bar → same `AND ‹status› WAS status AFTER -‹threshold›` proxy, resolved precisely in the record layer from the changelog.

### 5.3 Per-org deploy-status board — org × state heatmap `[NEW]`

MEASURES: rows = orgs `{DEV, UAT, STG, PROD}`, cols = `{Not started, Validated, Deployed, Failed, Rolled back}`; cell = count of requests whose `Deploy State — ‹org›` = state, over the population `Target Orgs ∋ org`. · DECISION: which org is red, and at which state does promotion stall (validated-but-not-deployed = a stuck CAB; failed = a broken deploy)? · VISUAL: 4×5 heatmap, red-weighted on `Failed`/`Rolled back`, each cell badged with the dominant `Deploy Source`. · RECONCILES: each **org row sums to `count(Target Orgs ∋ org)`** — `Not started` is a real cell, not a gap, so nothing falls off; project-wide `Σ Deployed(PROD)` equals the KPI `deployed_prod` numerator by construction. · PROVENANCE: **Writeback** — cells whose `Deploy Source = Seeded-model` are cross-hatched and counted separately in a "modelled" strand; a board that is all-`CI writeback` is the only one that earns a plain fill. · DRILL: cell → `project = SFC AND cf[10074] = "Failed"` (PROD example); org header → `Target Orgs = PROD`.

### 5.4 Config-health board `[NEW]`

MEASURES: per org, count by `Config Health — ‹org›` ∈ `{Healthy, Drifted, Degraded, Unknown}` over the **deployed-on-org** population (health is only meaningful once something shipped there). `Unknown` = deployed but no health writeback within staleness `Health Checked At > now − 24h`. · DECISION: did a green deploy actually leave the org healthy, or did it drift after? · VISUAL: per-org stacked bar (Healthy/Drifted/Degraded/Unknown) + a `Config Health Score` distribution; a staleness chip ("last scan 3h ago"). · RECONCILES: `Healthy + Drifted + Degraded + Unknown = deployed-on-org count`; `health_known_prod = Healthy+Drifted+Degraded` feeds the KPI denominator, so the tile and this board cannot disagree. · PROVENANCE: **Writeback (org scan), fully MODELLED without it.** If no scan job exists, every eligible cell is `Unknown` and the board says "no health writeback configured — this panel reports coverage, not health." This is the panel most likely to imply a live Salesforce read; it must not. · DRILL: segment → `project = SFC AND cf[10075] = "Drifted"`; `Unknown` segment → deployed-to-PROD requests with stale/empty `Health Checked At`.

### 5.5 Evidence-pack readiness board (COMPLY) `[NEW]`

MEASURES: per request, an evidence checklist of six fields (Plan Approved, Tests Passed, Static Scan Clean, CAB Approval, Deploy Log, Post-Deploy Validation); `evidence_complete` = all six ∈ `{Yes, N/A}`. Board shows per-item completeness bars and an overall ready share, gated at the DEPLOY and AUDIT bands. · DECISION: is the audit pack a byproduct of the work (DeliveryIQ's "evidence as a byproduct"), or a scramble at CAB? · VISUAL: six horizontal item bars (n Yes / n No / n N/A) + a "packs complete" gauge; a per-request checklist in the record layer. · RECONCILES: `ready = count(evidence_complete)` equals the drill CSV row count; each item bar's three segments sum to the band population, so a missing item can't hide. · PROVENANCE: **Comply-written** — `Evidence Source` distinguishes `Agent` (auto-captured), `Human`, `Seeded-model`; the integrity board (§5.8) reconciles agent-claimed evidence against an actual changelog/comment. · DRILL: "incomplete" → `project = SFC AND STAGE in (Deploy, Audit) AND (cf[10080] = No OR cf[10083] = No OR …)`; item bar → requests failing that item.

### 5.6 Bottleneck / cycle-time-by-stage (COORD) `[NEW]`

MEASURES: median and p90 **time-in-stage** per stage, computed from the status changelog across resolved (and, separately, in-flight) requests; rendered as a stacked lead-time waterfall so the fat stage is obvious. · DECISION: which stage owns the lead time — is the tax in Review (people) or Deploy (CAB/pipeline)? · VISUAL: stacked horizontal bar per stage (median) with p90 whiskers; a companion "aging in current stage" histogram for open work. · RECONCILES: per-stage samples are drawn from the same changelog the funnel uses, so `Σ time-in-stage` for a single request equals its Intake→Done elapsed. **Honesty guard:** the headline **Lead time** KPI is measured end-to-end, *not* summed from stage medians (medians don't add) — the strip says so, and a `check_leadtime` line asserts the end-to-end figure is not reconstructed from the stack. · PROVENANCE: **REAL** (changelog). · DRILL: stage bar → requests currently in that stage, sorted by time-in-stage desc; whisker → the p90 record's timeline.

### 5.7 Stalled-request / at-risk queue `[NEW]`

MEASURES: distinct open requests carrying **any** at-risk reason — `stalled@stage` (time-in-stage over threshold) ∪ `deploy_failed_any` ∪ `rolled_back_any` ∪ `Build Blocked`/`Changes Requested` status ∪ `evidence_incomplete AND stage ≥ Deploy` ∪ `Config Health ∈ {Degraded, Drifted}` ∪ `Change Risk = high AND stalled`. Each row is tagged with its reason set. · DECISION: the single "work the room now" list for Coord. · VISUAL: sortable, virtualised record list with reason chips, CSV / copy-keys, deep-link out — the standard record layer. · RECONCILES: queue count = **distinct union** (an issue red for two reasons counts once); a per-reason breakdown sums to ≥ the queue count and the overlap is shown, so the union and its parts are both auditable; every row's chips are the record booleans, so a JQL filter on any reason reproduces its slice. · PROVENANCE: **mixed** — reason chips inherit their source badge, so a "deploy failed" driven by `Seeded-model` is visibly weaker than one from `CI writeback`. · DRILL: row → record timeline; reason chip → the JQL for that reason, e.g. `project = SFC AND cf[10074] = "Failed"` or `project = SFC AND status = "Build Blocked"`.

### 5.8 Agent-actions integrity board (BUILD · COMPLY · COORD) `[NEW]`

MEASURES: for each of the three agents, the count of actions **claimed** vs **evidenced** in Jira — Build (plans/tests/deploys written), Comply (evidence fields set, checks logged), Coord (conflicts routed, alerts posted). Evidence = a matching changelog entry or comment authored by the agent/CI service account, or a field whose `… Source` badge is not `Seeded-model`. · DECISION: are the three agents actually acting, or is the lens narrating seeded data? This is the board that keeps DeliveryIQ honest about itself. · VISUAL: three lanes, each a claimed/evidenced/​unevidenced split bar; red on `unevidenced`; a provenance mix donut (`CI writeback` / `Manual` / `Seeded-model`) across the lens. · RECONCILES: `evidenced + unevidenced = claimed`; every `unevidenced` action is a red invariant that **suppresses** the dependent headline (a deploy-success rate built on `Seeded-model` states is shown greyed with a "modelled — no CI writeback" label, never as a live metric). Mirrors OPS's `invariants()` footer (N1). · PROVENANCE: this board *is* the provenance surface. · DRILL: lane → `project = SFC AND cf[10088] = "Seeded-model"` (Build example) → the offending keys; agent lane also links out to the automation-rule run log where one exists.

---

### 5.9 Four-layer drill & lens integrity strip

Every mark above opens the same drawer the tower already ships: **(a)** aggregate context (the stage/org/agent number with its num/den and target) → **(b)** cohort small-multiples (slice the mark by `Tower` `cf_10042`, `Change Type` `cf_10078`, target org, and `Deploy Source`) → **(c)** the record list (sortable, filterable, CSV / copy-keys, virtualised, deep-linked via `…/issues/?jql=` with `cf[id]` clauses) → **(d)** the single-record timeline: the status changelog (REAL) interleaved with per-org deploy events and the evidence checklist, each event badged with its `… Source`.

The lens ships its own **integrity strip** (the config-lens counterpart of the OPS invariant footer), stating in plain language what this lens can and cannot honestly say:

- **Can say (REAL, from Jira/changelog):** stage distribution, WIP, stalled work, time-in-stage, lead time, evidence-field completeness, and the provenance mix itself.
- **Can say only as well as the writeback (labelled):** per-org deploy state, deploy success/rollback rate, config health — each tied to `Deploy Source` / `Health Source`, with `Unknown` never laundered into green.
- **Cannot say:** anything read live from Salesforce. There is no org connection; "config health" is a Jira field a scan job writes, or it is `Unknown`.

Acceptance lines that must stay green for the lens to render: `check_stage_sums` (stages partition the window), org-row sums = `Target Orgs ∋ org`, health segments = deployed-on-org count, KPI numerators equal their board's marks, and `check_leadtime` (end-to-end, not stage-summed). Any red line suppresses its panel rather than showing a number the data can't back — the same discipline as the rest of the tower.

I have everything I need. Here is my section.

---

## 6. Outcome metrics & how they are measured (honestly)

Every slide outcome is a **before/after ratio over a cycle-time median or a coverage rate**, computed from the request's own timeline fields — never a headline typed into a tile. The discipline is the one the OPS lens already enforces: a figure only ships if a drill list reconciles to its num/den, durations are **medians with a `MIN_WEEK_DENOM`-style floor** (a 3-request week states no rate), and every clock is `sla_engine.business_hours_between` on the priority calendar, not elapsed wall-time. Three things are true of *every* metric below and are said once here so they need not be repeated:

1. **The *current* arm is REAL-from-Jira; the *before* arm is MODELLED until a baseline accrues.** "Triage cut 60–80%", "days→hours", "−40%", "halved", "weeks→hours" are all `(baseline − current) / baseline`. On a seeded green-field demo there is no pre-DeliveryIQ manual era in the data, so at t0 the frozen baseline *is* the seed and every delta is 0 or asserted. The honest demo shows the **current** median as real and badges the reduction "modelled — no manual baseline yet."
2. **The clean way to make the delta REAL is a within-dataset contrast, not a cross-era guess.** Add a `Delivery Mode` select (Agent / Manual) to the request. Then before/after is two cohorts measured on *the same clock in the same dataset* — the same move the OPS lens makes with `Reported At` instead of `created`, and the same move that turns "escalation up 12%" into `48→54 of ~130`.
3. **Per-org deploy state and config health are only as real as their writer.** `Deploy State[org]`, `Deployed At[org]` and `Config Health` are Jira fields. They are REAL only if the CI/CD pipeline (SF CLI + DevOps Center / the delivery GitHub Action) `PATCH`es the request over REST on each org event. Absent that writeback they are **manual/modelled**, and any deploy-time or health metric built on them is a data-entry artifact, not a measurement. The lens badges each org column with its provenance exactly as OPS badges CSAT a proxy and ITSM badges `Support Tier`-vs-`status WAS Escalated`. **The tower never reads Salesforce live.**

**The timeline fields each formula reads** (the SF-Config analogues of OPS's four datetime fields; seeded to carry real history because `created` is uniform and collapses every trend into one spike; resolved by *name* at runtime per ARCHITECTURE §2, so no id is compiled in):

| Field (name) | Stamps | Feeds |
|---|---|---|
| `Requested At` | drop into Intake | the window anchor for the whole lens — every cut keys off it |
| `Triaged At` | leaves Intake (BUILD classified+estimated · COMPLY authorized · COORD dep-scanned) | Intake |
| `Build Started At` | user approves plan → BUILD begins | Build |
| `Review Ready At` | BUILD hands off; tests+lint green | Build / Review |
| `Review Passed At` | business-logic review approved | Review |
| `CAB Approved At` | user CAB approval | Deploy |
| `Validated At[org]` / `Deployed At[org]` | per-org validation / deploy (writeback-sourced) | Deploy |
| `Audit Ready At` | evidence pack assembled | Audit |

Derived hours mirror `export_pages._h(...)`: `triage_latency_h`, `build_cycle_h`, `review_cycle_h`, `deploy_cycle_h[org]`, `ttr_config_h` (`Requested At`→first `Deployed At`), `evidence_lag_h` (`Deployed At`→`Audit Ready At`).

### INTAKE — "triage cut 60–80%"
**Formula.** `triage_latency_h = business_hours(Requested At → Triaged At)`, reported as the **median over requests that have left Intake** (`Pipeline Stage ∈ {Build,Review,Deploy,Audit}`) — reconciles to that exact drill set. The slide number is `(baseline_median − current_median)/baseline_median`. A companion **clean-intake rate** = share of requests with all three intake stamps present (BUILD classification + estimate, COMPLY `Authorization = Validated`, COORD dependency scan) / requests in window.
**REAL:** the current median and the clean-intake rate — both are field-presence and timestamp arithmetic, the same class as OPS `response_hours` and `kb_gap_pct`. **MODELLED:** the 60–80% cut until a `Delivery Mode = Manual` cohort or a real frozen baseline supplies the "before".
**Caveat:** this is triage **cycle time**, a proxy for triage *effort* — we do not fabricate agent-seconds. A faster median can reflect easier request mix, so it renders beside volume, never alone.

### BUILD — "days→hours" · agent prop "60–80% faster delivery"
**Formula.** `build_cycle_h = business_hours(Build Started At → Review Ready At)`, median. End-to-end delivery is `ttr_config_h = business_hours(Requested At → first Deployed At)`, the SF analogue of OPS `ttr_h`. "days→hours" is the current median stated in hours; "60–80% faster delivery" is the before/after ratio on `ttr_config_h`.
**REAL:** both current medians, and the full per-request Intake→…→Deploy path (reconstructed from the status changelog the records already carry in `timeline[]`). **MODELLED:** the reduction until a baseline/`Manual` arm exists.
**Caveat:** cycle time includes queue/wait, not just active BUILD work — so it is paired with stage-mix the way `ftr_vs_reopen` shares one denominator, so shrinking it by batching easy tickets can't masquerade as speed.

### REVIEW — "review −40%"
**Formula.** `review_cycle_h = business_hours(Review Ready At → Review Passed At)`, median among passed requests. Companion **review-rework rate** = count of Review→Build transitions in the changelog / requests entering Review — a *structural* signal, defined like OPS `Reopened` so it cannot be gamed by re-labelling.
**REAL:** current review-cycle median and the rework count (both from record + changelog). If CI writes a `Checks = green` field back, the mechanical **lint/test-pass** portion is REAL too. **MODELLED:** the −40% until baseline.
**Caveat:** separate the *mechanical* gate (tests/lint — automatable, the part we claim) from *business-logic* review (human — the part we do not). We never imply the agent approves business logic; the human review clock is whatever it is.

### DEPLOY — "halved time"
**Formula.** `deploy_cycle_h[org] = business_hours(Validated At[org] → Deployed At[org])` and `cab_to_deploy_h = business_hours(CAB Approved At → Deployed At)`, medians. **Deploy success rate** = `Deployed / (Deployed + Failed)` over per-org `Deploy State`, rendered as a **`DeployMatrix`** (request × target org, cell = state + provenance badge).
**REAL only if the writeback exists** (honesty note 3). On the seeded demo, `Deploy State[org]`, `Validated At`, `Deployed At` are **seeded → MODELLED**, labelled so on every cell — no live SF API is assumed. **MODELLED:** additionally, the "halved" delta until baseline.
**Caveat:** the per-org matrix is the one panel most likely to look live and be manual. Its integrity badge states the writer (pipeline / manual) per org; a column with no writeback shows state but no deploy-time metric — we don't compute a duration from two hand-typed timestamps.

### AUDIT — "weeks→hours" · agent prop "audit prep weeks→hours"
**Formula.** The honest primary is **evidence coverage** = share of deployed requests whose evidence pack is complete at `Deployed At` (all required COMPLY fields + linked change/test/approval artifacts present) — a *coverage* rate, pure field-presence, fully REAL. Secondary is `evidence_lag_h = business_hours(Deployed At → Audit Ready At)`; if evidence is genuinely a byproduct this trends toward ~0.
**REAL:** coverage and `evidence_lag_h`, and the AUDIT claim itself — "manager reviews the dashboard in <1 hr/wk" is demonstrated by the lens existing and reconciling, not modelled. **MODELLED:** "weeks→hours" as a *labor* saving until a manual-audit-prep baseline is frozen. We report coverage rising, not fabricated weeks saved.
**Caveat:** coverage measures that evidence *is present and linked*, not that a human judged it sufficient — that is the honest ceiling of a Jira-only source.

### COORD — agent prop "meeting tax→zero"
**This is the one the data cannot fully carry, and the integrity strip says so.** Jira holds no meeting hours. **REAL surrogates:** `coordination_coverage` = share of cross-team dependencies detected-and-routed on the request (COORD-written issue links / conflict flags) / total dependencies, and `conflict_lead_time_h` = business_hours(conflict flagged → target-stage entry) — both are links-and-timestamps, the class the tower already trusts. **MODELLED / not-sourced:** "meeting tax→zero" as an hours-saved figure. It ships in the strip as *"async coordination coverage X%; meeting-hours-avoided is not sourced from Jira and is not asserted."*

### How the two mechanisms make the deltas honest
- **Frozen baseline** (`{project}-baseline.json`, `_freeze_baseline`, write-once, `frozen_at`): extend its key set from the six OPS scores to `triage_latency_h`, `build_cycle_h`, `review_cycle_h`, `deploy_cycle_h`, `ttr_config_h`, `evidence_lag_h`, `evidence_coverage`. Each outcome then renders as a **target-gauge tile: baseline → today → target**, and every "60–80% / −40% / halved / weeks→hours" carries a provenance badge — "placeholder" until the baseline reflects a real manual-era org, "from pilot baseline, frozen 2026-XX-XX" after. On a fresh seed baseline==today, so the tiles honestly read *no movement yet*.
- **Snapshot history** (`{project}-history.json`, `_append_history`, one UTC-date-keyed point per `*/30` bake, last-write-wins, capped 180, CI commit-back `[skip ci]`, rendered by `SnapshotTrends`): append these same medians/rates each bake, so the reduction is **shown accruing deploy-over-deploy** with a direction-aware sparkline (down-is-good on cycle-times, up-is-good on coverage) — a real slope, or an honest "flat, no movement yet." This is what converts an asserted "days→hours" into `72h → 41h → 9h` a reviewer can drill.

**The lens's "what it cannot honestly say" line:** *cycle-time reductions are real numbers but the "before" is modelled until a baseline or a `Delivery Mode=Manual` cohort accrues; per-org deploy state and config health are only as real as the CI/CD writeback and are seeded/modelled here; meeting-hours-saved is not sourced from Jira.*

---

Files I read to ground this section (all absolute):
- `/Users/adityasingh/PersonalWork/JIRADemo/app/export_pages.py` — `_freeze_baseline`, `_append_history`, `_history_point`, `_record` timing derivations (`escalation_latency_h`, `l2_dwell_h`, `ola_handoff_h`, `ttr_h`).
- `/Users/adityasingh/PersonalWork/JIRADemo/app/metrics.py` and `/Users/adityasingh/PersonalWork/JIRADemo/app/analytics.py` — num/den reconciliation, `rate_point`/`MIN_WEEK_DENOM`, `ftr_vs_reopen` paired-panel honesty, weekly cohort series.
- `/Users/adityasingh/PersonalWork/JIRADemo/SCHEMA.md` — the four datetime timeline fields and the `Reported At`-not-`created` rule I mirrored.
- `/Users/adityasingh/PersonalWork/JIRADemo/ARCHITECTURE.md` — resolve-by-name rule, two-front-ends-one-model.
- `/Users/adityasingh/PersonalWork/JIRADemo/ROADMAP.md` §6.3 (baseline→target freeze) and `/Users/adityasingh/PersonalWork/JIRADemo/CLAIMS.md` #146/#159 (snapshot-history + frozen-baseline verification) and `/Users/adityasingh/PersonalWork/JIRADemo/.github/workflows/pages.yml` (commit-back cadence).

I have the repo's voice and conventions. Writing Section 7 now.

## 7. Integrity, dependencies & the phased build sequence

This lens inherits the tower's first law — **every figure reconciles, and nothing the data can't support is fabricated** — and then meets the one fact that makes SF-config harder than OPS or ITSM: **the interesting dimensions live outside Jira.** Pipeline *stage* is a real Jira artefact (it is the workflow status, in the changelog, same as OPS tier). Per-org *deploy state* and live *config health* are not — they are Jira fields whose truth depends entirely on **what writes them.** Absent a CI/CD writeback, they are a human's typed intention, not a reading of an org. The whole integrity posture below turns on keeping that line visible on every mark.

### 7.1 Integrity posture — what this lens can and cannot honestly say

Split by provenance, not by panel. `[REAL]` = an artefact Jira itself produces; `[MODELLED]` = a value only as true as whatever writes it, badged as such until a writeback is proven.

| Claim | Status | Why / what backs it |
|---|---|---|
| A request is *at stage* Intake/Build/Review/Deploy/Audit | **`[REAL]`** | Stage **is** the workflow status. `status WAS X` is real changelog — the same honesty that makes OPS's escalation trail defensible. The stage funnel and per-stage cycle time need **zero** external signal. |
| Stage **cycle time / dwell** | **`[REAL]`** | Computed from stage-timeline DateTime fields (`Intake At`…`Audit At`, cf_10061+), keyed off those, **never off `created`** — same rule as SCHEMA §1: a seeder run today stamps `created`=today and collapses every trend into one spike. |
| Which orgs a request **targets** | **`[REAL]`** | `Target Orgs` (multi-select) is authored on the ticket; it is a scope statement, not an org reading. |
| Per-org **deploy state** (Validated / Deployed / Failed) | **`[MODELLED]` until P2.5** | `Deploy State — <Org>` is a Jira select. It is REAL **only** once a CI/CD job writes it with `Deploy Source = CI/CD writeback`. Until then it is Manual/Modelled and must be badged. **The tower never reads Salesforce live.** |
| Live **config health** in an org | **`[MODELLED]` until an org-scan writeback** | `Config Health` + `Health Checked At` are as real as their `Health Source`. With no scan feed, "Healthy" means "nobody typed otherwise" — which is not health. Renders **Unknown**, never green, when unbacked or stale. |
| **Agent actions** (Build tested, Comply authorised, Coord routed) | **`[REAL]` if hook-written, else `[MODELLED]`** | Evidence-as-byproduct only holds if the agent (or its hook) writes the field. Hand-entered agent fields are `[MODELLED]` and say so. |
| Outcome metrics (deploy success rate, change-failure rate, lead time) | **derived** | Only as real as their inputs — REAL where they reduce over stage/timeline, MODELLED where they reduce over deploy-state until P2.5. |

**The one honest sentence for this lens** (the on-screen integrity strip, mirroring OPS's): *"Stage and cycle-time are read from Jira's own workflow history. Per-org deploy state and org health are Jira fields — real only where the CI/CD pipeline writes them back (badge: CI); everywhere else they are manual or seeded and labelled MODELLED. This tower does not connect to Salesforce."*

**Lens integrity strip — invariants that suppress a lying panel** (extends the OPS `invariants()`/N1–N2 contract):

- **N-SF1 · Provenance invariant.** Every `Deploy State` and `Config Health` value carries a `Source`. A panel that would render a `Modelled`/`Manual` value as a fact is **badged MODELLED**; if it can't be badged it is **suppressed**, not dimmed. Same rule OPS uses to refuse to show a red invariant.
- **N-SF2 · Reconciliation / partition.** Stage buckets partition the population (`Intake+Build+Review+Deploy+Audit+Done+Blocked = total`); every per-org deploy-matrix cell count **equals** its record-drill list; every rate ships numerator/denominator exact. A population boolean on each record encodes the rule so a client filter agrees with the aggregate.
- **N-SF3 · Freshness.** `Config Health` older than its threshold, or a `Deploy State` with no writeback since the last known CI run, renders **Unknown/Stale** — never the last-good colour. Every drilled view stamps the snapshot time (inherited from the bake's freshness contract).
- **N-SF4 · Stage↔deploy consistency (the wart-catcher).** A request at stage **Audit** with any `Target Org` whose `Deploy State ≠ Deployed` is a contradiction and is **flagged, not hidden** — the exact discipline that surfaces OPS's "171 tier-L2 but 15 never passed the Escalated status" and ITSM's DQ-3. The tower reports its own inconsistencies rather than masking them.

### 7.2 Open questions & dependencies

Ordered; #3 is the hinge the whole "status" half of the request rests on.

1. **Issue-type & lens creation (config).** New issue type **Salesforce Config Request**; new **company-managed** project as the lens (candidate key `SFDX` / name *Delivery — SF Config*) vs an issue type inside a shared project. Company-managed is required for the same reason as OPS §4 — shared workflow/screen/field contexts. New custom fields get **global contexts**; ids are **allocated at P0 from the next free block (cf_10061+)** — the ids used above are placeholders until the P0 build stamps them (do not treat them as live, unlike SCHEMA.md's verified ids).
2. **Per-org data shape.** Is the target-org set **small and enumerable** (Dev/QA/UAT/Staging/Prod → one `Deploy State — <Org>` select each, which aggregates cleanly and reconciles by N-SF2), or **unbounded** (→ deploy state must become a **child "Deployment" issue** per org, and the matrix aggregates over children)? This decision blocks the P2 schema. Recommend the fixed-org field model unless orgs are genuinely per-customer.
3. **★ Does a CI/CD hook write deploy status back to Jira?** The pivotal dependency. If the SF CLI / GitHub Action pipeline writes `Deploy State`, `Config Health`, `*_At` and `Source=CI` back on each run, P2/P3 are **REAL**; if not, they are permanently **MODELLED** and the lens honestly ships as a *plan-of-record* board, not an org monitor. Needs: a bot account + scoped token, the writeback verb (Jira REST issue-update from CI — note automation-rule creation has **no public REST API** per SCHEMA §4, so the writeback is a CI job, not a Jira automation rule), a `deploy result → Deploy State — <org>` field map, and an org-naming convention shared with #2.
4. **Is there any real org-health signal at all?** A drift/health scan (SF CLI, org-scan) feeding `Config Health`, or is health modelled from deploy outcomes? Decides whether the health board is a monitor or a proxy. If proxy, it ships **clearly labelled** — never a fake green.
5. **Seed data.** Need ~N seeded requests spanning a real date window (e.g. 90 days) with **genuine stage changelog and stage-timeline dates**, so funnels/cycle-time have shape — same seeding discipline and same `created`-is-uniformly-today caveat as OPS/ITSM. Seed deploy/health values with `Source=Modelled` so P2 renders honestly before any writeback exists.
6. **Are agent actions actually hook-written?** Do BUILD/COMPLY/COORD write their evidence fields via hooks (making §P3 REAL and "evidence as byproduct" literal), or are they hand-entered (MODELLED)? Governs whether the agent ledger is evidence or narration.
7. **Gate enforcement is UI-only.** Any stage-gate validator (e.g. "cannot enter Deploy without Comply authorisation") is **UI-built** — `system:field-required` is rejected over the workflow REST API (CONTROL-TOWER §4 / SCHEMA §4, verified). So gates are **designed and seeded** at P0 but not **enforced** until built in the admin UI, exactly like the OPS escalation gate.

### 7.3 Phased, no-code-first build sequence

Deliberately front-loads everything that is **REAL with zero Salesforce code** (P0–P1), and defers the only code — the CI writeback — to a single named hinge (P2.5). Each phase states its provenance so the lens is never accidentally claiming more than it can back.

| Phase | Work | Depends on | Provenance at ship | Exit criterion |
|---|---|---|---|---|
| **P0 — Seed + issue type + workflow** *(config only, no code)* | Create the `SFDX` lens, `Salesforce Config Request` issue type; workflow **statuses = the stages** (Intake · In Build · In Review · Deploying · Audit · Done, side-states Blocked · Deploy Failed); fields cf_10061+ (`Target Orgs`, `Deploy State — <Org>`, `Deploy Source`, `Config Health`, `Health Source`, `Health Checked At`, stage-timeline dates, agent-action fields); screens/contexts; **seed** requests across a 90-day window with real stage history, all deploy/health values `Source=Modelled`. | Q1, Q2, Q5 | everything MODELLED, badged | lens has population and shape; funnel renders; nothing claims to read an org |
| **P1 — Stage funnel + record drill** | The **SF Config stage funnel** (Intake→Build→Review→Deploy→Audit), **per-stage cycle time / dwell**, four-layer drill (aggregate → cohort → record list w/ CSV/copy-keys → single-record **stage timeline**), Jira deep-links by JQL. | P0 | **`[REAL]`** (stage is changelog) | the honest core is live and defensible **with no writeback at all** — this is the OPS-equivalent thesis surface |
| **P2 — Deploy-status + health boards** | **Per-org deploy matrix** (org × Deploy State heatmap), **deploy failure rate by org**, **config health board** (health distribution), **health freshness** (age of `Health Checked At`), and the **deploy/health provenance panel** (share by `Source` — the integrity panel that makes N-SF1 visible). | P0 | **`[MODELLED]`**, every mark badged | boards render honestly against seeded data; provenance panel shows 100% Modelled — the "before" state |
| **P2.5 — CI/CD writeback** *(the one code hinge)* | Wire the pipeline (SF CLI + GitHub Action) to write `Deploy State`, `Config Health`, `*_At`, `Source=CI` back to Jira via REST under a scoped bot token. | **Q3**, Q4 | flips P2 marks to **`[REAL]`** as `Source=CI` share climbs | provenance panel shows real CI share; N-SF4 consistency check goes green on written records |
| **P3 — Agent actions + evidence** | **Agent action ledger** (BUILD tested/PR, COMPLY authorised/evidence-pack, COORD conflicts/dependencies), **evidence completeness by stage**, **authorization gate (Comply)**, **conflict & dependency board (Coord)**. | P0; Q6, Q7 | `[REAL]` where hook-written, else `[MODELLED]` | evidence is a byproduct of the agents' own writes, not hand-curated; gate designed (UI-enforced per Q7) |
| **P4 — Outcome metrics + baseline** | **Lead time Intake→Deployed**, **deploy success rate**, **change-failure rate**, **audit-prep time**, and a measured **90-day SF Config baseline**; wire the lens `invariants()` (N-SF1–4) into the shared integrity strip and weekly-sum reconciliation. | P1–P3 | derived; each metric inherits its inputs' provenance | outcome tiles carry arithmetic + drill; baseline is measured, not asserted; strip is green or the panel is suppressed |

**Sequencing rationale.** P0→P1 deliver a fully honest, fully REAL lens **before a single line of Salesforce or CI code exists** — because stage lives in Jira, the funnel and cycle-time thesis stands alone, exactly as OPS's escalation trail does. P2 ships the deploy/health boards **openly modelled**, so the provenance panel's journey from *100% Modelled* to *mostly CI* at P2.5 becomes the visible proof that the writeback landed — the integrity story and the build story are the same story. Everything code-bearing is isolated to P2.5, and if Q3 comes back "no writeback," the lens degrades gracefully to a plan-of-record board that never once pretends to have looked at an org.

---

## Open items & integrity checks

**1. Cross-section contradictions (must be reconciled before build)**
- **Project key / lens id / issue-type name are inconsistent across all seven sections.** Key: `SFC` (§1,§5) vs `SFDX` (§2,§7) vs `DLVR` (§3) vs `DELIV` (§4). Lens id: `SFC` vs `DLVR`. Issue type: `SCR` / `SFCR` / `SF Config Request`. Pick one triple and sweep.
- **Field-id blocks collide.** §4.0 assigns cf_10061–10074 to agent-action fields; §5.0 assigns 10070–10090 to deploy/health; §6/§7 claim cf_10061+ for stage-timeline DateTime fields. Three sections mint overlapping ids from the same "next free block." Needs one allocation table.
- **The time anchor field is named two ways.** §1/§5/§7 reuse `Reported At` (cf_10057); §6 invents `Requested At` as "the window anchor for the whole lens." Same field, two names — every windowed cut keys off it, so this must resolve to one.
- **The "one modelling decision that shapes everything" (per-org fan-out) is decided differently four times.** §1: sub-task (A) or JSON field (B); §2.3: sub-record or `Deploy State · <org>` fields; §3b: entity property `sf.deploy` + scalar rollups; §5.0: fixed `Deploy State — <org>` cf family. The section that calls it a "real fork" never closes it, and later sections silently assume incompatible carriers.
- **Enums diverge.** Deploy State: 6-value (§1) vs 7-value hyphenated (§2.3) vs 4-value (§3b). Config Health: `Failing` (§1,§3) vs `broken`+`drift-detected` (§2.4) vs `Drifted` (§5). Source enum: `Seeded`/`unset`/`seed`/`Seeded-model` across §1/§2/§3/§5. Canonicalize each.
- **Status ladder + stage map differ.** Status names (`In Build`/`Building`, `Deployed`/`Deploying`/`Deployed·Monitoring`) and the killed-terminal (`Withdrawn`, Done — §2 vs `Cancelled` — §5) are not aligned; §1/§2.1/§3a/§5.0 give four stage→status tables. The N-SF4 wart-catcher can't be coded until one map is authoritative.

**2. Salesforce-live-read risk (Jira-only data)**
- The framing sentence ("tower never reads Salesforce") is present in every section — good. The **exposure is the health surface**: §3c is titled "Live CONFIG HEALTH," §2.4 "live org state," §5.4 asks "did it drift after?", plus a 0–100 `Config Health Score`, "Drift detected," and a "last scan 3h ago" chip. These read as live telemetry. Keep the honest-limit copy, but retitle (drop "Live") and ensure the staleness chip and `Unknown`-default are rendered *on the panel*, not only in the strip.
- Drift specifically **cannot be derived from Jira** (stated in §3c) yet appears as a first-class health value in §2.4/§5.0/§5.4 — make sure a no-scan demo shows `Unknown`, never `In sync`/`Healthy`.

**3. Decisions still owed by the user**
1. Canonical **project key + lens id + issue-type name** (one triple).
2. **Per-org carrier**: sub-task vs entity-property vs fixed per-org field family — this blocks the P2 schema.
3. **Does a CI/CD writeback exist?** (§7 Q3, the hinge) — determines whether the entire deploy/health half is ever REAL or ships permanently as plan-of-record.
4. **Any real health/drift signal**, or is health an explicit proxy capped at `Unknown`/`Degraded`?
5. One **canonical enum set** for Deploy State, Config Health, and `*_Source`.

**4. Single biggest honesty risk**
At t0 (seeded, no writeback) the lens's flagship differentiators — the **per-org deploy matrix and config-health board** — are **100% MODELLED**, yet they are the most visually "live-looking" panels (heatmaps, health scores, scan-age chips). The danger is not the strip's wording; it's that a viewer reads a fully-seeded matrix as an org monitor. Enforce it structurally: N-SF1 must *suppress or cross-hatch* every non-CI cell, and the deploy/health tiles must render greyed under a "modelled — no CI writeback" label until the provenance panel shows a real `Source=CI` share — so the boards physically cannot present seeded data as a Salesforce reading.
