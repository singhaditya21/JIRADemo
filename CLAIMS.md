# Claims register

Every factual assertion in this repo, with how it is known. Written because a claim was
previously asserted in four documents before being checked, and shipped wrong.

**Rule: nothing enters a deliverable without a row here first.**

| Status | Meaning |
|---|---|
| ✅ **VERIFIED** | Probed against the live instance on the date shown. Reproducible. |
| ⚠️ **UNVERIFIED** | Plausible but not tested here. Must be confirmed before being stated as fact. |
| 🔵 **PLACEHOLDER** | Invented to illustrate shape. Not research. Must be replaced with real values. |
| ⛔ **RETRACTED** | Was asserted, found false, corrected. Kept so the error is not reintroduced. |

---

## Instance facts

| # | Claim | Status | Evidence |
|---|---|---|---|
| 1 | Site is `singhaditya21.atlassian.net`; account has site-admin rights | ✅ VERIFIED 2026-07-20 | `/rest/api/3/mypermissions` → `ADMINISTER`, `CREATE_PROJECT`, `ADMINISTER_PROJECTS` all true |
| 2 | Only `jira-software` is licensed | ✅ VERIFIED 2026-07-20 | `/rest/api/3/applicationrole` returns one role |
| 3 | JSM is not provisioned | ⛔ **SUPERSEDED 2026-07-20 (later same day)** | Was true when probed. JSM was provisioned during the day: `/rest/servicedeskapi/info` → 200 `isLicensedForUse: true`, and `service_desk` now appears in `/rest/api/3/project/type`. See #32. |
| 4 | Two pre-existing projects, `KAN` and `SAM1`, both team-managed | ✅ VERIFIED 2026-07-20 | `/rest/api/3/project/search` → `style: next-gen` |
| 5 | Fields, screens, statuses, workflows, schemes, permissions are REST-scriptable | ✅ VERIFIED 2026-07-20 | All endpoints → 200 |
| 6 | Automation rules have **no** public Cloud REST API | ✅ VERIFIED 2026-07-20 | `/rest/api/3/automation/rules` → 404 |
| 7 | Team-managed projects expose no workflow validators or conditions | ✅ VERIFIED 2026-07-20 | `/rest/api/3/workflows/capabilities?projectId=10001` → all rule arrays empty |
| 8 | The escalation-gate validator can be created over REST | ⛔ **DISPROVED 2026-07-20** | `workflows/create` rejects `system:field-required` with *"Rule cannot be applied to this type or is unsupported"*. Three payload variants tried (comma list, JSON array, single field) plus `system:validator-field-required`. The same payload succeeds with validators removed, so the workflow structure is fine and the **validator specifically is UI-only**. |
| 9 | Native conditions **cannot** branch on a field *value* (e.g. "Priority = P1") | ⚠️ UNVERIFIED | Still not confirmed. **The P1 fast path is deliberately designed around role-based restriction so it works either way** (`PLAN.md` §7). |
| 8b | Statuses, workflows and workflow schemes are creatable over REST | ✅ VERIFIED 2026-07-20 | 11 statuses created; `OPS L1-L2 Support Workflow` with 13 transitions created and bound to `OPS` via scheme 10036. All 11 statuses confirmed live on the project. |
| 8c | `statusReference` in `workflows/create` must be a caller-generated UUID | ✅ VERIFIED 2026-07-20 | Passing status IDs returns *"The reference 10012 is not a UUID"*. Existing statuses are referenced by supplying `id` alongside the UUID. |
| 8d | Textarea custom fields require ADF, not a bare string | ✅ VERIFIED 2026-07-20 | 179 of 420 seed writes failed with *"not valid Atlassian Document"* until `Troubleshooting Performed` was wrapped. |
| 8e | Project **lead** is not automatically in the `Administrators` project role | ✅ VERIFIED 2026-07-20 | Issue deletion returned 403 despite site-admin rights until the account was added to role 10002. Blocks seed reset — matters before a rehearsal. |
| 10 | Automation rules are exportable/importable as JSON | ⚠️ UNVERIFIED | Documented Jira feature; not tested here. Affects the version-control story, not the design. |
| 11 | JSM free tier includes 3 agents and the full SLA engine | ✅ **PARTLY VERIFIED 2026-07-20** | The **SLA engine is confirmed present** — a new JSM project auto-provisions 4 SLA metrics with goals and a default calendar (see #37, #50). Agent-count tiering still unverified and irrelevant to the demo. |
| 12 | Jira's `created` field is read-only over REST, so seeded tickets cannot be backdated | ✅ **VERIFIED 2026-07-20** | All 420 seeded issues carry `created = 2026-07-20`. **Solved rather than worked around:** the `Reported At` datetime field holds the real timeline (2026-04-24 → 2026-07-15) and every filter, gadget and SLA calculation reads it instead of `created`. CSV import is no longer required. |
| 12b | 420 issues seeded with complete, coherent field data | ✅ VERIFIED 2026-07-20 | JQL counts: 420 total · 179 tier-L2 · 179 with all three gate fields populated · 50 SLA-breached · 20 reopened · 77 open · 42 impact-High+urgency-High. |

## Design figures

| # | Claim | Status | Note |
|---|---|---|---|
| 13 | Six towers (EUC, Enterprise Applications, Network, Database, Compute & Storage, Cloud & Security) | 🔵 PLACEHOLDER | Invented, and cut from eight to six so each has enough volume to chart. **Replace with the real org's towers** — one edit in `shared/domain.py`, then re-run build and seed. |
| 13b | 26-person team: 12 L1 across 3 shifts, 10 L2, 3 leads, 1 major incident manager | 🔵 PLACEHOLDER | Invented working default. Drives the 24×7-for-P1/P2 vs business-hours-for-P3/P4 calendar split. Analyst names are fictional. |
| 13c | Intake mix: Portal 42% / Email 28% / Monitoring 18% / Chat 12% | 🔵 PLACEHOLDER | Invented. Monitoring is deliberately skewed toward high priority; Chat exists to represent shadow support being pulled into the record. |
| 14 | SLA targets: P1 15min/4h, P2 30min/8h, P3 4h/3d, P4 8h/5d | 🔵 PLACEHOLDER | Conventional-looking defaults. Not derived from any contract. |
| 15 | First-time resolution target ≥ 65% | 🔵 PLACEHOLDER | **No source.** Set from the pilot's measured baseline instead (`PROBLEM.md` §8). |
| 16 | Reopen rate < 5%, SLA attainment ≥ 95% | 🔵 PLACEHOLDER | Same — conventions, not benchmarks. |
| 17 | Impact × Urgency → Priority matrix | 🔵 PLACEHOLDER | Standard shape; the *mechanism* (derived not chosen) is the point, the cell values are tunable. |
| 18 | Build reaches rollout in ~8 weeks | ⚠️ UNVERIFIED | Estimate for technical build only. **Excludes change management and training** — see `PROBLEM.md` §9. |
| 19 | Demo environment is ~2–3 days of effort | ⚠️ UNVERIFIED | Estimate. Seed data is the least predictable part. |

## Retracted

| # | Claim | Status | What happened |
|---|---|---|---|
| R1 | "Phases 2–6 are all REST-API scriptable", including automation rules and SLA config | ⛔ RETRACTED 2026-07-20 | False. Asserted in `PLAN.md`, propagated to `BRIEF.md`, `demo.html` and the deck before anyone checked. Automation rules → 404 (#6); SLA config is JSM UI. Corrected in all four. **This register exists because of this error.** |
| R2 | Illustrative business case: baseline $55,000/mo → $42,500/mo, saving ~$150k/yr | ⛔ RETRACTED 2026-07-20 | Internally inconsistent. It charged escalated tickets at L2 cost only, while the same design requires *every* ticket to pass through L1 triage first — so escalated tickets incur both costs. Corrected arithmetic gives ~$70,000 → ~$51,250. **Removed rather than repaired**: no cost input was ever real, and an ROI model nobody asked for is pure downside in a capability demo. |

---

## Phase build — verified 2026-07-20

| # | Claim | Status | Evidence |
|---|---|---|---|
| 20 | Four ITSM issue types created and bound via scheme | ✅ VERIFIED | Incident/Service Request/Change/Problem, scheme 10165. Binding required deleting all `Task` issues first — a scheme cannot be applied while issues use types outside it. |
| 21 | Custom P1–P4 priorities and a priority scheme are creatable over REST | ✅ VERIFIED | Priorities 10000–10003, scheme 10166. `iconUrl` is required on create; the scheme needs `mappings.in` for every built-in priority before Jira will drop them. |
| 22 | Seeded priority now lands on the real `priority` field | ✅ VERIFIED | Earlier seeds only wrote the derived priority into the description, so every priority-based queue was blind. P1 42 / P2 43 / P3 172 / P4 163. |
| 23 | Problems are excluded from SLA attainment | ✅ VERIFIED | 11 Problems carry no Response/Resolution SLA. Including investigations would penalise the tower for doing root-cause work. |
| 24 | 20 saved filters live, including per-tower L2 queues and SLA at-risk views | ✅ VERIFIED | At-risk JQL must use full priority names (`"P1 - Critical"`), not the short code. |
| 25 | Measured 90-day baseline | ✅ VERIFIED | FTR 61.8% · escalation 40.7% · reopen 4.3% · resolution SLA 81.6% · response SLA 82.2% · 60 aged >14d · **46% of escalations found no KB article**. Produced by `app/metrics.py`. |
| 26 | Pilot tower selected from data, not preference | ✅ VERIFIED | End User Computing: 126 volume, 61.9% FTR. Ranked on volume × headroom — see `PILOT.md` §2. |
| 28 | SLA state is **computed from the timeline**, not seeded | ✅ VERIFIED 2026-07-20 | `app/sla_engine.py` recomputes Response/Resolution SLA from `Reported At` → `Resolved At` minus changelog-derived pause time, on the calendar each priority is governed by. 409 issues updated. The seeded values were static decoration: a ticket could blow its target and still read "Met". |
| 29 | P3/P4 targets are **business hours**, not elapsed hours | ✅ VERIFIED 2026-07-20 | Measuring a business-hours target on a 24×7 clock reported 61.9% attainment; on the correct calendar it is 78.9%. "3 business days" is 24 business hours, not 72 elapsed. `SLA_TARGETS` corrected from (4, 72)/(8, 120) to (4, 24)/(8, 40) with `SLA_CLOCK` naming the calendar. |
| 30 | JSM cannot be provisioned via any reachable API | ✅ VERIFIED 2026-07-20 | `servicedeskapi` 403; `applicationrole` lists only `jira-software`; creating a `service_desk` project returns *"invalid project type... not available in your Jira instance"*; `api.atlassian.com/admin/v1/orgs` returns 401 (API tokens do not authenticate the org admin API). Provisioning is a product/billing action in admin.atlassian.com. |
| 31 | An existing Jira Software project cannot be converted to a service project | ⚠️ UNVERIFIED — **now moot** | Never tested, because the question was answered by rebuilding instead: `ITSM` was created fresh as a `service_desk` project reusing every global object `OPS` uses (#42, #43). The rebuild took one scripted run, which is the practical answer regardless of whether conversion is possible. |
| 27 | Automation rule files are specs, not verified Jira exports | ⚠️ **UNVERIFIED BY DESIGN** | `automation/*.json` map 1:1 to the rule builder but have never been round-tripped through Jira import. Build in UI, export, then replace. Stated plainly in `automation/README.md`. |

---

## JSM build — probed and built 2026-07-20

Supersedes #3, #11 and #30. JSM was provisioned mid-day; `ITSM` was then built, seeded,
reviewed and repaired. Counts below re-read from the live instance after the repair pass.

### Capability probes

| # | Claim | Status | Evidence |
|---|---|---|---|
| 32 | JSM is provisioned and licensed on this site | ✅ VERIFIED 2026-07-20 | `/rest/servicedeskapi/info` → 200, `isLicensedForUse: true`. `/rest/api/3/project/type/service_desk` → 200. Directly reverses #3 and unblocks #30. |
| 33 | The ITSM project template key is `com.atlassian.servicedesk:itil-v2-service-desk-project` | ✅ VERIFIED 2026-07-20 | Proven by creating projects with it 4× → HTTP 201. Exactly 3 `service_desk` templates exist on this site; enumerated via `/rest/project-templates/1.0/templates`, the only working template-enumeration endpoint. |
| 34 | The ITIL template ships 4 of the 5 wanted issue types; **Post-incident review must be added separately** | ✅ VERIFIED 2026-07-20 | Template creates exactly 7 types — Incident, Service Request, Change, Problem, Service Request with Approvals, Task, Sub-task. `[System] Post-incident review` (10025) added via `PUT /rest/api/3/issuetypescheme/{id}/issuetype` → 204. Note **PUT**, not POST (POST → 405). |
| 35 | The ITIL template **reuses** global issue types 10016–10019 rather than creating copies | ✅ VERIFIED 2026-07-20 | `OPS` and `ITSM` are now backed by the same four issue type objects. Proven safe across four create/delete cycles — `OPS` retained all four. **Consequence: those issue types must never be deleted.** |
| 36 | JSM **agent queues are creatable and updatable over REST** — but **not deletable** | ✅ VERIFIED 2026-07-20 | `POST`/`PUT /rest/servicedesk/1/servicedesk/{projectKey}/queues` → 200 (internal endpoint; path takes the **project key**, not the service desk id). No delete route exists: 12 paths tried plus GraphQL introspection of 1,592 mutations. The public `servicedeskapi` queue route is `Allow: GET` only. **Every REST-created queue is permanent.** |
| 37 | JSM **SLA metrics and goals are UI-only**; SLA **calendars are fully REST-writable** | ✅ VERIFIED 2026-07-20 | A systematic 56-path sweep across 4 API roots returned zero non-404 hits, with POST and PUT probed separately. Method control: Jira returns 405 when the path exists but the verb does not, so a 404 `No endpoint` rules the path out for all methods. Calendars: full CRUD confirmed on `/rest/workinghours/1/api/calendar`. |
| 38 | Request types are **create/delete only** — no update, grouping, form fields or icon | ✅ VERIFIED 2026-07-20 | `OPTIONS` on `requesttype/{id}` returns `GET,HEAD,DELETE,OPTIONS`. `groupIds` and `iconId` in the create payload → 400. A REST-created request type gets only a `summary` field and belongs to no portal group. **A UI pass is required to build usable portal forms.** |
| 39 | Portal branding, portal settings and knowledge base have **no REST endpoints at all** | ✅ VERIFIED 2026-07-20 | `/rest/servicedeskapi/portal`, `/servicedesk/{id}/settings`, `/servicedesk/{id}/knowledgebase` all → 404 `No endpoint`. |
| 40 | Approval **configuration** (the `approval.*` status properties) is UI-only | ✅ VERIFIED 2026-07-20 | Every payload shape to `workflows/create|update/validation` → bare 400, including the verbatim read payload and a minimal `{"statuses":[],"workflows":[]}`. Approvals are driven by status properties, readable **only** via the old `GET /rest/api/3/workflow/search?expand=statuses.properties` — the new API returns `{}` and would silently strip them on a read-modify-write. |
| 41 | Portal **customer accounts** can be created over REST, but it is a one-way door | ⚠️ UNVERIFIED **by choice** | `POST /rest/servicedeskapi/customer` is reachable and permission-granted — proven by validation-error progression (400 field errors, not 403/404). **Not executed:** it provisions a real Atlassian account and emails an invite, and no REST delete exists. Adding *existing* accounts as customers **is** verified (`POST .../servicedesk/{id}/customer` → 204, confirmed by read-back). |

### The `ITSM` build

| # | Claim | Status | Evidence |
|---|---|---|---|
| 42 | `ITSM` (project 10042, service desk 8) is live with the full tower schema | ✅ VERIFIED 2026-07-20 | `service_desk`, company-managed. 171 field/screen associations across 9 screens; `createmeta` confirms all 20 tower fields settable on create for all 7 non-subtask issue types. |
| 43 | The 20 custom fields and the P1–P4 scheme were **reused, not recreated** | ✅ VERIFIED 2026-07-20 | All 20 fields sit on global contexts (`isGlobalContext`, `isAnyIssueType`), so `ITSM` uses the identical `customfield_*` ids as `OPS`. **Zero fields created.** Priority scheme 10166 now lists both projects. |
| 43b | Attaching a project to an existing priority scheme needs a shape not used in `jira_config/priority.py` | ✅ VERIFIED 2026-07-20 | `projects.add` must be an **object** `{"ids":[10042]}`, not a list, **and** a top-level `mappings.in` is mandatory even for a project with zero issues. The bare 400 this produces has been silently swallowed by the try/except at `jira_config/priority.py:49`. `OPS` is unaffected — it got its association at creation. |
| 44 | 420 tickets seeded into `ITSM` with coherent cross-field data | ✅ VERIFIED 2026-07-20 | Live JQL: 420 labelled `tower-seed` (421 project total). Incident 267 / Service Request 85 / with-Approvals 25 / Change 31 / Problem 13. P1 38 / P2 43 / P3 195 / P4 144, none empty. 166 seeded L2 tickets, **all** carrying all three gate fields; 0 gate-field leakage onto non-escalated tickets. |
| 45 | 12 agent queues and 22 saved filters built; all queues non-empty | ✅ VERIFIED 2026-07-20 | 19 queues live (7 template + 12 built), counts re-read from `/rest/servicedeskapi/servicedesk/8/queue?includeCount=true`. Filters 10064–10085. |
| 46 | Dashboard 10035 has 11 gadgets, **all bound to real filters** | ✅ VERIFIED 2026-07-20 | Every gadget's `config` property read back and confirmed to resolve to a live filter id and a real custom field. Contrast `OPS` dashboard 10001 — see #52. |
| 47 | Stock ITIL workflows set **no resolution**, so seeded Done tickets read "Unresolved" | ✅ VERIFIED 2026-07-20 | Found and fixed in `ITSM`: `statusCategory = Done AND resolution = Unresolved` is now **0**. All seven template queues filter `resolution = Unresolved`, so before the fix the entire project showed as open. Required adding `resolution` to all 9 `ITSM` screens. |
| 48 | `Closed` is terminal and non-editable in the `ITSM` Incident and Problem workflows | ✅ VERIFIED 2026-07-20 | `jira.issue.editable=false`. 203 tickets were frozen with no resolution and no way out. Repaired by flipping the property, backfilling, and flipping it straight back — each workflow asserted to be used by the `ITSM` scheme alone first. **This is also why 46 residual field repairs remain blocked** (#51). |

### `ITSM` — what does **not** work

| # | Claim | Status | Evidence |
|---|---|---|---|
| 49 | **The escalation narrative does not work in `ITSM`** | ✅ VERIFIED 2026-07-20 | The `Escalated` status exists only in the two Service Request workflows. `issuetype = Incident AND "Support Tier" = L2` is 122, but the same query `AND status WAS Escalated` is **0**. Project-wide only **18** tickets ever entered `Escalated`. Field data says escalated; History says otherwise. **Demo escalation from `OPS`**, or from the nine closed Service Requests `ITSM-59, 91, 142, 271, 288, 356, 379, 396, 399`. |
| 50 | **Native JSM SLA figures are meaningless** — they measure from `created`, which is today | ✅ VERIFIED 2026-07-20 | `"Time to resolution" = everBreached()` returns **0** project-wide while the modelled `Resolution SLA` field shows 68 breaches. Native goals are also keyed to issue type, not priority (a P1 and P4 Incident carry identical targets), native SLA is blank on all 44 Changes and Problems, and 278 Done tickets show a running "Time to close" clock. **Do not open the native SLA panel or sort a queue by an SLA column.** Retargeting is UI-only per #37. |
| 50b | The `ITSM` SLA clock is **24×7 for all priorities** — *not* the business-hours split of #29 | ✅ VERIFIED 2026-07-20 | Verdicts were recomputed on a single 24×7 elapsed clock and the decision recorded in `jira_config/state/.jsm_state.json` → `sla_clock`. `OPS` uses the business-hours model; `ITSM` does not. **Do not narrate a business-hours split when demoing `ITSM`.** |
| 50c | `ITSM` SLA counts after repair | ✅ VERIFIED 2026-07-20 | Resolution: Met 235 / Breached 68 / In progress 57 / Paused 48. Response: Met 346 / Breached 63. Tickets in the breach queue contradicted by their own dates: **0** (was 39). |
| 51 | 46 `ITSM` field inconsistencies remain unrepaired, blocked by #48 | ⚠️ **KNOWN AND UNFIXED** | 28 Closed Incidents reading "Met" against their own dates (these fail **safely** — they under-report, and do not pollute the breach queue), 12 Closed Problems with a null verdict, 6 chronology inversions (worst: `ITSM-401`, 7.1h). Unblocking needs a workflow-property unlock that was denied by the permission system and deliberately not circumvented. |
| 51b | `ITSM` approvals are **not demonstrable** | ✅ VERIFIED 2026-07-20 | All 25 tickets at `Waiting for approval` have an empty native approver list and no decision. The workflow sets `approval.exclude=reporter,assignee` and the seeder is the reporter of every ticket, so the only account on the instance is excluded from its own approvals. Needs a second Atlassian account. **Present the Change workflow** (`Awaiting CAB approval → Awaiting implementation`) instead — it runs on ordinary transitions and works. |
| 51c | The `ITSM` portal has **no customers** and no knowledge base | ✅ VERIFIED 2026-07-20 | Anonymous portal access redirects to login. `knowledgebase/article?query=vpn` → size 0. Demo the portal from the authenticated session only. Frame the 86-ticket "KB Gap" queue as the tower's own evidence field, not a Confluence-backed KB. |

### `OPS` — verified untouched, plus two pre-existing defects

| # | Claim | Status | Evidence |
|---|---|---|---|
| 52 | **`OPS` was not modified by any JSM work** | ✅ VERIFIED 2026-07-20 | Independent post-run audit: 420 issues, 171 L2, 171 with all gate fields, 4 issue types, 11 statuses with matching categories, workflow `OPS L1-L2 Support Workflow` at `versionNumber: 0`, all 20 fields still on single global contexts, all 20 filters live. Decisive tripwire: `project = OPS AND updated >= "2026-07-20 15:00"` returns **0**, while all JSM work ran 15:40–16:26. `OPS`'s two screens (10013–10014) are disjoint from `ITSM`'s nine (10195–10203) and neither gained `resolution`. |
| 53 | `OPS` dashboard 10001 renders as 12 blank gadgets | ✅ **FIXED 2026-07-20** | Was real: all 12 gadgets had no `config` property because `jira_config/views.py` never passed a filter id. Repaired by `jira_config/repair.py` — all 12 now bound to a named filter, verified by reading each `config` property back. 12/12 resolve to a live filter. |
| 54 | 358 `OPS` Done tickets carry no `resolution` | ✅ **FIXED 2026-07-20** | Repaired by `jira_config/repair.py`. Resolution derived from each ticket's existing Resolution Code rather than blanket-set to Done, so closure data stays coherent: Done 175, Duplicate 80, Won't Do 55, Cannot Reproduce 48. `statusCategory=Done AND resolution=Unresolved` is now **0**. |
| 55 | `OPS` filters `P3 at risk` and `P4 at risk` use **stale thresholds** | ⛔ **RETRACTED 2026-07-20** | **The finding was wrong.** It compared business-hour targets directly against elapsed-hour JQL without converting. A business day is 8h of a 24h day, so 75% of a 24-business-hour P3 target = 18 business hours = **54 calendar hours** — exactly the `-54h` already in the filter. Same for P4: 30 business hours = 90 calendar hours = `-90h`. Verified empirically: both thresholds return identical counts (14 and 18). **No change made.** |
| 56 | 15 `OPS` L2 tickets never passed through the `Escalated to L2` status | ✅ VERIFIED 2026-07-20 | 171 tagged L2, 156 with the status in history. A far smaller version of #49. **Open `OPS-2298`, `OPS-2306` or `OPS-2309`** — all three carry the full seven-step chain — rather than a random L2 ticket. |
| 57 | `scratchpad/baseline.json` is **stale** | ✅ VERIFIED 2026-07-20 | It records SLA 81.6% / response 82.2%; live `OPS` is now 78.9% / 96.6% (Met 306, Breached 82). Only the four SLA figures moved — volume, closed, FTR, escalated, reopened, aged and KB-gap are bit-identical — which is the signature of the intentional SLA recompute in commits `e902c5e`/`e66cab5`. **Any slide quoting 81.6% or 82.2% contradicts the live dashboard.** |
| 58 | `OPS` and `ITSM` are now **coupled through shared global objects** | ✅ VERIFIED 2026-07-20 | Priority scheme 10166 lists both; issue types 10016–10019 back both; all 20 custom fields sit on single global contexts serving both. This is the permitted reuse, but it widens the blast radius: **to retire `ITSM`, detach it from scheme 10166 rather than deleting the scheme, and never delete those issue types or field contexts.** |

### Methodology note — worth keeping

| # | Claim | Status | Evidence |
|---|---|---|---|
| 59 | `customfield_NNNNN` is **not a valid JQL clause name** on this instance — it returns 0 instead of erroring | ✅ VERIFIED 2026-07-20 | Caught when mutually exclusive queries both returned 0 against 420 issues. **Any verification written with `customfield_` syntax false-passes every check.** Use `cf[10043]` or the quoted field name. All counts in this register were re-run with the correct syntax. |
| 60 | Intermittent CloudFront 403 HTML pages are **not** Jira responses | ✅ VERIFIED 2026-07-20 | Identical calls return 403-HTML then 200 on immediate retry. Any probe script must retry on a 403 whose body contains `cloudfront`, or it will record false negatives. This was the single largest source of wrong conclusions during probing. |

## Before the demo — what is left

Items 8, 12, 11 and 30 are now settled by the live builds. What remains, highest value first:

1. **Build the gate validator in the UI** (#8 disproved the scripted route). Until it exists,
   the escalation gate is designed and seeded but not *enforced* — and the live refusal is
   the centrepiece of the run sheet. **Still the highest-value remaining build task.**
   `DEMO-TOMORROW.md` §1 is the 30-minute recipe.
2. **Decide about `OPS` #53 and #54** — the blank dashboard and the 358 unresolved Done
   tickets. Both are pre-existing, both are one scripted pass to fix, and both require your
   explicit sign-off because they mean writing to `OPS`. **Do not fix silently.** The
   cheapest mitigation costs nothing: don't open dashboard 10001, don't linger on the
   Resolution field of a Closed ticket.
3. **#13 / #13b / #13c** — the placeholder towers, team and intake mix are the most visible
   tell that this is generic. Replacing the tower list is one edit in `shared/domain.py`
   followed by a rebuild and reseed. **Cheapest fix, largest credibility gain.**
4. **#57** — regenerate `baseline.json`. Any slide still quoting 81.6% or 82.2% contradicts
   the live dashboard.
5. ~~**#55**~~ — **nothing to do.** The filters were right; the generator was wrong.
   `jira_config/views.py` now converts business-hour targets to elapsed hours and
   reproduces `-54h`/`-90h` exactly, so a re-run is a no-op rather than a regression.
6. **#51** — the 46 residual `ITSM` field inconsistencies, blocked on a workflow unlock that
   needs your approval. All fail in the safe direction; ignorable for tomorrow.
7. **#10** — automation rule JSON export/import is still untested; it only affects the
   version-control story, not the demo.

**If you are demoing `ITSM` rather than `OPS`, read #49, #50 and #51b first.** They are the
three things that will visibly contradict the story if someone clicks the wrong tab.


## Repair pass — 2026-07-20

| # | Claim | Status | Evidence |
|---|---|---|---|
| 60 | JQL clause names used across all scripts are sound | ✅ VERIFIED 2026-07-20 | Partition test: for each clause, `count(X) + count(NOT X)` must equal 420. All six pass — Support Tier, Troubleshooting Performed, Resolution SLA, Intake Channel, Reported At, Reopened. Control confirms the trap in #59: `customfield_10043=L2` returns **0** rather than erroring. No script places a `customfield_NNNNN` inside JQL. |
| 61 | `OPS` integrity survived the repair pass | ✅ VERIFIED 2026-07-20 | Post-repair: 420 issues, 171 tier-L2, 171 with gate evidence, 0 Done-without-resolution, 12/12 gadgets bound. |
| 62 | Probe agents left unremovable state in `SUP` | ✅ VERIFIED 2026-07-20 | Three queues named `ZZ DELETE ME - *` (ids 29, 37, 45) created while establishing that queue deletion has **no API** (#36). They cannot be removed over REST — **UI-only cleanup**. Also five trashed probe projects: `JSMTEST`, `ZZSLA`, `ZZTMP1-4`. `OPS` and `ITSM` unaffected. |
| 63 | Seeded resolution codes over-represent `Duplicate` | ⚠️ **KNOWN AND UNFIXED** | 80 of 358 closed `OPS` tickets (22%) resolve as Duplicate, because the seeder picks uniformly from four incident resolution codes. Implausible for a real tower. Cosmetic and only visible if resolution is charted; fixing needs a reseed, which was not worth the risk before the demo. |

## Refactor — layer split, 2026-07-20

See [ARCHITECTURE.md](ARCHITECTURE.md). Nothing on the live instance changed; every
verification below was read-only or `--dry-run`.

| # | Claim | Status | Evidence |
|---|---|---|---|
| 64 | The repo is split into five packages with a one-way dependency direction | ✅ VERIFIED 2026-07-20 | `scripts/` eliminated; 20 files `git mv`'d (all recorded as renames) into `shared/`, `jira_config/`, `fixtures/`, `app/`, `tools/`. Per-layer import blockades run over all 20 modules: `app` with `jira_config`+`fixtures` banned → all import; `jira_config` with `fixtures`+`app` banned → all import; `shared` with every sibling banned → all import. `shared/domain.py` binds **zero** imports, not even stdlib, and a scan of its 23 public symbols against 11 Jira-shaped patterns (`customfield_\d+`, `com.atlassian`, `cf[`, searcher/template/scheme keys) returns zero hits. All `sys.path.insert` hacks removed — modules run as `python3 -m pkg.module`. |
| 65 | `app/` resolves custom-field ids **by name at runtime** and reads no build state | ✅ VERIFIED 2026-07-20 | `shared/fields.py` queries `/rest/api/3/field`; the former `sla_engine.resolve_fields()` that read `.build_state.json` is gone. **Proven by isolation, not by grep:** `app/` and `shared/` copied into an empty directory where `jira_config/` does not exist on disk — `python3 -m app.cli sla --project OPS --dry-run` exits 0 with byte-identical output (420 evaluated, Met 306 / Breached 82, 78.9%). Instance-independence shown the same way: `metrics --project ITSM` returns a full report (421 volume, 62.7% FTR, 77.6% SLA) with no `OPS` artifact reachable. The resolver independently reproduced the artifact's own choice of `customfield_10044` for the duplicated `Urgency` name (#66b). |
| 65b | `app/` metrics and SLA output is unchanged by the refactor | ✅ VERIFIED 2026-07-20 | Pre-refactor code extracted from `git archive HEAD scripts` and run live for a true old-vs-new comparison. **SLA: byte-identical** (`cmp` passes, md5 `9480f8cc…`, `diff` empty). **Metrics: zero numeric change** — every number tokenised in both files; all 216 original tokens present in identical sequence. The only diff is two banner lines now naming the project (`Baseline for OPS…`, `=== OPS ALL TOWERS…`), which is the parameterisation that lets the same tool report on `ITSM`. **Any doc or screenshot quoting `=== ALL TOWERS - last 90d ===` verbatim is stale.** |
| 66 | `jira_config/views.py` is now idempotent, **gadgets included** — this was the root cause of #53 | ✅ VERIFIED 2026-07-20 | The append-only gadget block that left dashboard 10001 with 12 blank gadgets is replaced by reconciliation: gadgets are matched by title, bound to their filter and left in place; only missing ones are created. `python3 -m jira_config.views --dry-run` against the live instance reports **20 filters unchanged, 12 gadgets matched, 0 created / 0 updated, `0 write(s) issued`**, and two consecutive dry runs diff clean. #53 remains FIXED — this removes the cause rather than repeating the repair, so `views.py` is now safe to re-run. |
| 66b | `Urgency` exists **twice** on this instance, and name-based resolution must break the tie | ✅ VERIFIED 2026-07-20 | `/rest/api/3/field` returns `customfield_10044` (ours) and `customfield_10071` (JSM ITIL template). Both are type `select` with a global context, so type- and project-narrowing cannot separate them; the tie is broken on description via `/rest/api/3/field/search`, which is **mandatory** because `/rest/api/3/field` returns `description: null` for all 91 custom fields. The resolver warns on stderr, names both ids, selects `10044`, and renders the ambiguous name as `cf[]` in generated JQL per #59. Pin explicitly with `JIRA_FIELD_ID__URGENCY=<id>`. |
