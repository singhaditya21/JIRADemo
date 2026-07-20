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
| 8 | Company-managed workflows support **field-required validators** | ⚠️ UNVERIFIED | Could not enumerate — no company-managed project exists on this site yet. Confirm in Phase 1. |
| 9 | Native conditions **cannot** branch on a field *value* (e.g. "Priority = P1") | ⚠️ UNVERIFIED | Native conditions are understood to be permission/role/group/status-based. **The P1 fast path is deliberately designed around role-based restriction so it works either way** (`PLAN.md` §7). |
| 10 | Automation rules are exportable/importable as JSON | ⚠️ UNVERIFIED | Documented Jira feature; not tested here. Affects the version-control story, not the design. |
| 11 | JSM free tier includes 3 agents and the full SLA engine | ⚠️ UNVERIFIED | Atlassian's published tiering; not confirmed on this account. **Check before relying on it for the demo.** |
| 12 | Jira's `created` field is read-only over REST, so seeded tickets cannot be backdated | ⚠️ UNVERIFIED | Drives the CSV-import strategy in `LIVEDEMO.md` §3. Test early — the seed plan depends on it. |

## Design figures

| # | Claim | Status | Note |
|---|---|---|---|
| 13 | Eight towers (Network, Server, Database, Storage, EUC, Applications, Cloud, Security) | 🔵 PLACEHOLDER | Invented. Generic infra split. **Replace with the real org's towers.** |
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

## Before the demo — confirm these four

Ordered by how much damage a wrong answer causes:

1. **#11** — if the free tier does not include the SLA engine, the run sheet is not
   demonstrable and the whole approach needs rethinking.
2. **#8** — if company-managed workflows do not support field-required validators, the
   escalation gate as designed does not exist.
3. **#12** — if `created` cannot be backdated by CSV import either, every trend chart in the
   demo is a single vertical spike.
4. **#13** — placeholder towers are the most visible tell that this is generic. Cheapest fix,
   largest credibility gain.
