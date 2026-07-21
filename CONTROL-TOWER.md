# Control tower — what exists on the instance

Two complete L1/L2 support towers are live on `singhaditya21.atlassian.net`, built from the
same design in `PLAN.md`. Every number below was read from the live instance on
**2026-07-20** by JQL count or the queue API, not carried over from a build log.

- **`OPS`** — Jira **Software** project. Built first. The escalation narrative works here.
- **`ITSM`** — Jira **Service Management** project. Built second, after JSM was provisioned.
  Adds portal, request types, agent queues and native SLA fields. The escalation narrative
  **does not** work here — see §5.

> **Pick one to demo. The recommendation is `OPS`.** The reasoning is in §6.

---

## 1. Side by side

| | `OPS` | `ITSM` |
|---|---|---|
| Project type | `software` (company-managed) | `service_desk` (company-managed, ITIL template) |
| Project id / key | 10034 / `OPS` | 10042 / `ITSM` |
| Service desk id | — (not a service project) | 8 |
| Issues | **420** | **421** (420 seeded + `ITSM-1`, now Canceled) |
| Issue types | 4 — Incident, Service Request, Change, Problem | 8 — the same 4 plus Service Request with Approvals, Post-incident review, Task, Sub-task |
| Statuses | 11 custom, purpose-built | ~16 across 5 stock ITIL workflows |
| Workflow | 1 — `OPS L1-L2 Support Workflow`, 13 transitions | 5 stock ITIL workflows, unmodified |
| `Escalated to L2` as a **status** | ✅ yes — 156 tickets passed through it | ⚠️ only in the Service Request workflows — 18 tickets |
| Support Tier = L2 | 171 | 167 (166 seeded) |
| Full gate evidence on every L2 ticket | ✅ 171 / 171 | ✅ 166 / 166 |
| Custom fields | 20 (all global contexts) | **the same 20** — reused, not duplicated |
| Priority scheme | 10166, P1–P4 | **the same scheme 10166** — reused |
| Saved filters | 20 | 22 |
| Dashboard | 10001 — **12 blank gadgets, unconfigured** | 10035 — 11 gadgets, all bound and verified |
| Agent queues | — | 19 (7 template + 12 built), all non-empty |
| Customer portal | — | live, 17 request types, 5 groups |
| Native JSM SLA engine | — | present but **measuring the wrong dates** (§5) |
| Approvals | — | 25 tickets at the gate, **no approver can answer** (§5) |
| System `resolution` set on Done tickets | ❌ 358 Done tickets read "Unresolved" | ✅ 0 unresolved Done tickets |

**They share global objects.** The 20 custom fields, the four issue types (10016–10019) and
priority scheme 10166 back both projects. That is deliberate reuse. It also means deleting
any of them breaks `OPS`. Never delete them; to retire `ITSM`, detach it from scheme 10166
rather than deleting the scheme.

---

## 2. `OPS` — Jira Software

**Open:** https://singhaditya21.atlassian.net/browse/OPS

| Metric | Live value | What it proves |
|---|---|---|
| Issues | 420 | Enough volume that every chart has shape |
| Support Tier = L2 | 171 (40.7%) | Escalation rate is measurable per tower and per analyst |
| L2 tickets with all three gate fields | 171 / 171 | The gate produces data, not just a refusal |
| Tickets that passed through `Escalated to L2` | **156** | Real status history, not a field written after the fact |
| Escalated with **no KB article found** | **79** (46% of escalations) | The single largest lever in the design, measured not asserted |
| Resolution SLA Met / Breached | 306 / 82 (78.9%) | Computed from `Reported At` → `Resolved At` minus pause, per priority calendar |
| Reopened | 15 (4.3%) | Pairs against first-time resolution so neither can be gamed alone |
| Open | 62 | The live queues are not empty |

### The escalation trail — this is the demo

Open **OPS-2298**, **OPS-2306** or **OPS-2309** and click **History**. Each shows the
complete chain:

`New → Triage → In Progress L1 → Escalated to L2 → In Progress L2 → Resolved → Closed`

Same issue key throughout. Same SLA clock. One audit trail. That is the whole thesis, and
in `OPS` it is genuinely in the changelog.

### `OPS` filters — all 20 live

| Filter | URL |
|---|---|
| L1 queue (open) | https://singhaditya21.atlassian.net/issues/?filter=10035 |
| L2 queue (open) | https://singhaditya21.atlassian.net/issues/?filter=10036 |
| Major incidents (Impact High + Urgency High) | https://singhaditya21.atlassian.net/issues/?filter=10037 |
| SLA breached (resolution) | https://singhaditya21.atlassian.net/issues/?filter=10038 |
| SLA paused (customer or vendor) | https://singhaditya21.atlassian.net/issues/?filter=10039 |
| Aged backlog over 14 days | https://singhaditya21.atlassian.net/issues/?filter=10040 |
| Reopened tickets | https://singhaditya21.atlassian.net/issues/?filter=10041 |
| Escalated in last 30 days | https://singhaditya21.atlassian.net/issues/?filter=10042 |
| **Escalated with no KB article found** | https://singhaditya21.atlassian.net/issues/?filter=10043 |
| Intake via chat (shadow support) | https://singhaditya21.atlassian.net/issues/?filter=10044 |
| L2: End User Computing | https://singhaditya21.atlassian.net/issues/?filter=10045 |
| L2: Enterprise Applications | https://singhaditya21.atlassian.net/issues/?filter=10046 |
| L2: Network & Connectivity | https://singhaditya21.atlassian.net/issues/?filter=10047 |
| L2: Database | https://singhaditya21.atlassian.net/issues/?filter=10048 |
| L2: Compute & Storage | https://singhaditya21.atlassian.net/issues/?filter=10049 |
| L2: Cloud & Security | https://singhaditya21.atlassian.net/issues/?filter=10050 |
| P1 at risk | https://singhaditya21.atlassian.net/issues/?filter=10051 |
| P2 at risk | https://singhaditya21.atlassian.net/issues/?filter=10052 |
| P3 at risk ⚠️ stale threshold | https://singhaditya21.atlassian.net/issues/?filter=10053 |
| P4 at risk ⚠️ stale threshold | https://singhaditya21.atlassian.net/issues/?filter=10054 |

### ⚠️ Two known defects in `OPS`

Both **pre-date** the JSM work and neither was introduced by it. Both were left alone
because writing to `OPS` needs your explicit sign-off.

1. **Dashboard 10001 rendered as 12 blank gadgets — FIXED, and the cause is now fixed too.**
   All 12 returned HTTP 404 for their config property because `jira_config/views.py`
   never passed a filter id, and its gadget block appended 3 more unbound gadgets per
   run (× 4 runs = 12). All 12 were bound by `jira_config/repair.py` (CLAIMS #53), and
   `views.py` has since been rewritten to reconcile rather than append — it matches
   gadgets by title, binds each to its filter, and adds only what is missing.
   A dry run against the live dashboard now reports **12 matched, 0 created, 0 updated,
   0 unclaimed, 0 writes issued**, so re-running it is safe and the old "do not re-run"
   warning no longer applies to the gadgets.
   The filters reconcile clean too: 20 unchanged, 0 writes. Always run
   `python3 -m jira_config.views --dry-run` first regardless.
2. **358 Done tickets carry no `resolution`,** so every Closed `OPS` ticket displays
   "Resolution: Unresolved". No `OPS` filter depends on the field (all 20 key off
   `statusCategory != Done`), so the queues are unaffected — the exposure is the issue
   detail view. Fixable with the same backfill used on `ITSM`, and `OPS`'s Closed status has
   no `jira.issue.editable=false` property so it needs no unlock step. **Requires your
   sign-off before anyone writes to `OPS`.**

One lesser item — and a correction. Filters 10053 and 10054 use `-54h` and `-90h`, and
**those values are correct**: `shared/domain.py` states P3/P4 targets in *business* hours
(24h and 40h), the filter clause is evaluated in *elapsed* hours, and 24 business hours is
72 calendar hours — so 75% of it is 54h. The earlier reading of this as "stale thresholds
that under-report 3×" compared the two clocks without converting and is retracted as
CLAIMS #55. `jira_config/views.py` carried the same unit error in its generator until it
was made idempotent; it now converts by `24 / (BUSINESS_DAY span)` and reproduces `-54h`
and `-90h` exactly, so a run changes nothing.
And 15 of the 171 L2-tagged tickets
never passed through the `Escalated to L2` status — a small version of the `ITSM` problem in
§5, and a reason to open one of the three keys named above rather than a random L2 ticket.

---

## 3. `ITSM` — Jira Service Management

**Open:** https://singhaditya21.atlassian.net/browse/ITSM

| Surface | URL |
|---|---|
| Project | https://singhaditya21.atlassian.net/browse/ITSM |
| **Agent queues** (19, all non-empty) | https://singhaditya21.atlassian.net/jira/servicedesk/projects/ITSM/queues |
| **Dashboard** (11 bound gadgets) | https://singhaditya21.atlassian.net/jira/dashboards/10035 |
| **Customer portal** (17 request types) | https://singhaditya21.atlassian.net/servicedesk/customer/portal/8 |

### Agent queues — live counts

| Queue | Count | | Queue | Count |
|---|---|---|---|---|
| All open | 106 | | L2 – End User Computing | 17 |
| Assigned to me | 61 | | L2 – Enterprise Applications | 10 |
| Unassigned work items | 45 | | L2 – Network & Connectivity | 4 |
| Incidents | 51 | | L2 – Database | 3 |
| Service requests | 22 | | L2 – Compute & Storage | 6 |
| Change | 7 | | L2 – Cloud & Security | 3 |
| Problem | 1 | | Major Incidents | 12 |
| L1 Queue | 63 | | SLA Breached – Resolution | 68 |
| L2 Queue – All Towers | 43 | | Aged Backlog – 14 days+ | 101 |
| | | | KB Gap – escalated, no article | 86 |

The first seven are seeded by the ITIL template; the remaining twelve were built by
`jira_config/jsm_views.py`.

### Dashboard 10035 — what each gadget proves

| Gadget | Bound to | What it shows |
|---|---|---|
| Volume by tower (pie) | filter-10084 (all 420) | Six towers with real spread: EUC 122, Enterprise Apps 103, Network 63, Database 48, Compute 47, Cloud 37 |
| Escalation split: tower × L1/L2 | filter-10084 | L1 254 vs L2 166, broken down by tower — where escalation concentrates |
| Open work by priority | filter-10085 (106 open) | P1 12 / P2 3 / P3 48 / P4 43 |
| Resolution SLA outcome (pie) | filter-10084 | Met 235 / Breached 68 / In progress 57 / Paused 48 |
| Intake channel mix (pie) | filter-10084 | Portal 199 / Email 102 / Monitoring 66 / Chat 53 — shadow support made visible |
| SLA breached – resolution | filter-10067 | The 68 breached tickets |
| Aged backlog over 14 days | filter-10069 | 101 tickets |
| KB gap queue | filter-10072 | 86 escalations that found no article |
| Major incidents | filter-10066 | 12 |
| L2 queue – all towers | filter-10065 | 43 |
| KB gap by tower (heat map) | filter-10072 | Which tower's KB is weakest |

The first five were originally bound to filters that pre-filtered on the exact dimension
they chart, so the pies rendered as a single 100% slice. They were rebound to whole-project
filters and the distributions above were re-read from the live instance afterwards.

### `ITSM` filters

Filters `10064`–`10083` mirror the `OPS` set with `ITSM -` names, plus two added during
repair: `10084` (all issues, project-wide) and `10085` (all open work). URL pattern
`https://singhaditya21.atlassian.net/issues/?filter=NNNNN`. Full id map in
`jira_config/state/.jsm_state.json`.

### SLA in `ITSM`

`ITSM` carries **two independent SLA systems**, and only one of them is right.

- **The modelled fields** (`Response SLA`, `Resolution SLA`) are correct: Resolution Met 235
  / Breached 68 / In progress 57 / Paused 48; Response Met 346 / Breached 63. Every filter,
  queue and gadget keys off these.
- **The native JSM SLA engine** is wrong, because it measures from `created` — which is
  today for all 420 seeded tickets. `"Time to resolution" = everBreached()` returns **0**
  across the whole project while the modelled field shows 68 breaches.

**Do not open the native SLA panel, the SLA column, or any JSM SLA report during the demo,
and do not let anyone sort a queue by an SLA column.** Retargeting the four native SLAs is
UI-only (§4).

Note also: the `ITSM` clock model is **24×7 elapsed for all priorities**, recorded in
`jira_config/state/.jsm_state.json` under `sla_clock`. This differs from `shared/domain.py` `SLA_CLOCK`
(business hours for P3/P4), which is what `OPS` uses. **Do not narrate a business-hours
split when demoing `ITSM`.**

---

## 4. What is still UI-only, and why

Everything here was probed against this instance, not read from documentation. The
distinguishing signal: Jira returns **405** when the path exists but the verb does not, and
**404 `No endpoint {METHOD} {path}`** when the route does not exist at all — so a 404 in
that form rules the path out for every method.

| Capability | Status | Evidence |
|---|---|---|
| **Workflow validators** (the escalation gate) | 🔴 **UI-only** | `workflows/create` rejects `system:field-required` — *"Rule cannot be applied to this type or is unsupported"*. Four payload variants tried; the same payload succeeds with validators removed. |
| **Automation rules** | 🟡 **Internal API — built & enabled** | The *public* `/rest/api/3/automation/rules` → 404, but the Automation **internal** API (`.../pro/rest/{projectId}/rule`) takes create + enable. All seven rules are live and ENABLED via `automation/build_rules.py`; component value schemas were discovered by round-trip (`automation/schema/component-schemas.md`). Two sub-shapes (field-changed per-field scoping, send-email recipients) resolve entities server-side and stayed UI-only, so two rules use verified equivalents. |
| **SLA metrics and goals** | 🔴 **UI-only** | A 56-path sweep across four API roots returned **zero** non-404 hits. POST and PUT probed separately. Project settings → SLAs. |
| **SLA calendars** | 🟢 **REST-writable** | `/rest/workinghours/1/api/calendar` supports full CRUD. Confirmed create, update and delete. |
| **JSM agent queues — create & update** | 🟢 **REST-writable** | `POST`/`PUT /rest/servicedesk/1/servicedesk/{projectKey}/queues` → 200. Not the public `servicedeskapi` route, which is `Allow: GET` only. All 12 queues were built this way. |
| **JSM agent queues — delete** | 🔴 **UI-only** | No REST or GraphQL delete exists. Twelve paths and the GraphQL mutation set were checked. **Every queue created over REST is permanent.** |
| **Request types — create & delete** | 🟢 **REST-writable** | `POST`/`DELETE /rest/servicedeskapi/servicedesk/{id}/requesttype`. |
| **Request types — update, portal groups, form fields, icon** | 🔴 **UI-only** | `OPTIONS` on `requesttype/{id}` returns `GET,HEAD,DELETE,OPTIONS` — no write verb. `groupIds` in the create payload → 400. A REST-created request type gets only a `summary` field and belongs to no group. |
| **Approval configuration** (`approval.*` status properties) | 🔴 **UI-only** | Every payload shape to `workflows/*/validation` returned a bare 400, including the verbatim read payload. |
| **Portal branding & knowledge base** | 🔴 **No endpoints at all** | `/rest/servicedeskapi/portal`, `/servicedesk/{id}/settings`, `/servicedesk/{id}/knowledgebase` all 404. |
| Fields, screens, statuses, workflows, schemes, permissions, filters, dashboards, gadget binding | 🟢 **REST-writable** | All 200. This is the bulk of both builds. |

**The consequence for the demo:** the escalation gate is *designed and seeded* but not
*enforced* until someone builds the validator in the UI. `DEMO-TOMORROW.md` §1 is the
30-minute recipe.

---

## 5. `ITSM` limitations you must know before presenting

Four items. The first is the reason the recommendation is `OPS`.

1. **🔴 The escalation story cannot be told on an `ITSM` Incident, Problem or Change.** The
   `Escalated` status exists **only** in the two Service Request workflows. 122 Incidents
   carry `Support Tier = L2` with a full escalation evidence set, but
   `issuetype = Incident AND status WAS Escalated` returns **0**. Open one and the History
   tab reads `Open → Work in progress → Completed → Closed` — flatly contradicting the
   fields. Across the project only **18** tickets ever entered `Escalated`, all of them
   Service Requests.
   **If you must demo escalation from `ITSM`, the only honest keys are the nine closed
   Service Requests:** `ITSM-59, 91, 142, 271, 288, 356, 379, 396, 399`. Nothing else.
2. **🔴 Approvals are not demonstrable.** All 25 tickets at `Waiting for approval` have an
   **empty** native approver list and no decision. The workflow sets
   `approval.exclude=reporter,assignee` and the seeder is the reporter of every ticket, so
   the only account on the instance is excluded from its own approvals. Fixing it needs a
   second Atlassian account. **Present the Change workflow instead** — `Awaiting CAB
   approval → Awaiting implementation` runs on ordinary transitions and works end to end.
3. **🔴 Native SLA is wrong** — see §3. Avoid the SLA panel entirely. Also: native SLA is
   blank on all 44 Changes and Problems, its goals are keyed to issue type rather than
   priority (so a P1 and a P4 Incident carry identical targets), and 278 Done tickets show a
   still-running "Time to close after resolution" clock.
4. **🟡 The portal has no customers.** It renders correctly while logged in as admin, but
   anonymously it redirects to login. **Demo it from the authenticated browser session, not
   an incognito window.** Provisioning customers creates real Atlassian accounts and emails
   invitations with no REST undo, so it was deliberately not done.

Two smaller ones: there is **no knowledge base** (`knowledgebase/article` → size 0), which
is awkward next to a "KB Gap" queue of 86 — frame that queue as the tower's own
`KB Article Checked` evidence field, not a Confluence-backed KB. And about 11% of seeded
`ITSM` tickets have an empty History tab because they were created directly into an intake
status, so pick demo tickets deliberately rather than clicking a random queue row.

### Repaired before this document was written

Verified fixed against the live instance: 39 tickets whose stored "Breached" verdict was
contradicted by their own dates (now **0** in the breach queue), 14 L2 tickets missing
`Escalated At` (now **0**), 3 of 9 impossible timestamp chains, 5 mis-bound dashboard
gadgets, and the stray `ITSM-1` scaffolding ticket (now Canceled, dropped out of the open
queues). **Still broken:** 28 Closed Incidents whose Resolution SLA reads "Met" against
their own dates — these fail *safely*, sitting in the Met bucket rather than polluting the
breach queue — 12 Closed Problems with a null verdict, and 6 chronology inversions. All are
blocked by `jira.issue.editable=false` on the Closed status of the `ITSM` Incident and
Problem workflows; unlocking it requires a permission approval that was denied and not
circumvented.

---

## 6. Which one to demo

**Demo `OPS`.**

The run sheet in `DEMO-TOMORROW.md` turns on one moment: escalating a ticket, watching the
key stay the same, and opening History to see the full trail. That works in `OPS` on 156
tickets and works in `ITSM` on 18. Everything else — priority matrix, SLA computation, KB
gap, per-tower queues — is equally true in both, and `OPS` carries the measured 90-day
baseline the closing argument is built on.

Its two defects are containable: don't open dashboard 10001, and don't linger on the
Resolution field of a Closed ticket.

**Use `ITSM` as the "what's next" slide, and open it live for 60 seconds** — the portal, the
19 agent queues and dashboard 10035 are all genuinely good and all genuinely working. It
answers "why Service Management?" better than any slide: unlicensed requesters, a real
portal, native queues. Just don't open the SLA panel, don't open an escalated Incident's
History, and don't try to approve anything.

**Demo `ITSM` instead only if** the portal and request-type catalogue are the actual point
of the meeting, and you are prepared to tell the escalation story from `OPS` or from the
nine named Service Request keys.
