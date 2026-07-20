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
| 3 | JSM is not provisioned | ✅ VERIFIED 2026-07-20 | `/rest/servicedeskapi/servicedesk` → 403 |
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
| 11 | JSM free tier includes 3 agents and the full SLA engine | ⚠️ UNVERIFIED | Atlassian's published tiering; not confirmed on this account. **Check before relying on it for the demo.** |
| 12 | Jira's `created` field is read-only over REST, so seeded tickets cannot be backdated | ✅ **VERIFIED 2026-07-20** | All 420 seeded issues carry `created = 2026-07-20`. **Solved rather than worked around:** the `Reported At` datetime field holds the real timeline (2026-04-24 → 2026-07-15) and every filter, gadget and SLA calculation reads it instead of `created`. CSV import is no longer required. |
| 12b | 420 issues seeded with complete, coherent field data | ✅ VERIFIED 2026-07-20 | JQL counts: 420 total · 179 tier-L2 · 179 with all three gate fields populated · 50 SLA-breached · 20 reopened · 77 open · 42 impact-High+urgency-High. |

## Design figures

| # | Claim | Status | Note |
|---|---|---|---|
| 13 | Six towers (EUC, Enterprise Applications, Network, Database, Compute & Storage, Cloud & Security) | 🔵 PLACEHOLDER | Invented, and cut from eight to six so each has enough volume to chart. **Replace with the real org's towers** — one edit in `scripts/config.py`, then re-run build and seed. |
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

## Before the demo — what is left

Items 8 and 12 are now settled by the live build. What remains:

1. **#13 / #13b / #13c** — the placeholder towers, team and intake mix are the most visible
   tell that this is generic. Replacing the tower list is one edit in `scripts/config.py`
   followed by `01_build.py` and `03_seed.py`. **Cheapest fix, largest credibility gain.**
2. **Build the gate validator in the UI** (#8 disproved the scripted route). Until it exists,
   the escalation gate is designed and seeded but not *enforced* — and the live refusal is
   the centrepiece of the run sheet. This is the highest-value remaining build task.
3. **#11** — if the JSM free tier does not include the SLA engine, the SLA half of the demo
   stays field-simulated rather than native. Everything else already works without it.
4. **#10** — automation rule JSON export/import is still untested; it only affects the
   version-control story, not the demo.
