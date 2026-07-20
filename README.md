# L1/L2 Support Tower on Jira

Design and build approach for an L1/L2 IT support tower ticket management system on Jira Service Management, plus the demo materials that present it.

## Contents

| File | What it is |
|---|---|
| [PROBLEM.md](PROBLEM.md) | **Start here.** Why these towers degrade — ten symptoms, five structural root causes, why the problem survives years of effort, and what "solved" means. |
| [PLAN.md](PLAN.md) | Full technical design — field schema, status model, escalation gate and major-incident fast path, SLA targets, priority matrix, permissions, build phases. |
| [demo.html](demo.html) | The presentation page. Sections tagged `CORE` (~10 min spine) or `DEEP DIVE`. Self-contained; works offline. |
| `L1-L2-Tower-Demo.pptx` | 18-slide deck — 10-slide core spine plus appendix A-1 to A-8. |
| [BRIEF.md](BRIEF.md) | One-page written brief, for reading ahead. |
| [LIVEDEMO.md](LIVEDEMO.md) | How to build a live, clickable demo: what is scriptable, seed-data strategy, run sheet, fallbacks. |
| [SCHEMA.md](SCHEMA.md) | **Live reference** — 20 real field IDs, permission scheme, and the seven automation rules as exact recipes. |
| [CONTROL-TOWER.md](CONTROL-TOWER.md) | **What is actually live on the instance** — both projects side by side, every URL, what each view proves, what is still UI-only, and which one to demo. |
| [DEMO-TOMORROW.md](DEMO-TOMORROW.md) | Tonight's checklist and the 12-minute run sheet. |
| [CLAIMS.md](CLAIMS.md) | **Every factual assertion with its verification status.** Nothing enters a deliverable without a row here. |
| [PILOT.md](PILOT.md) | Measured baseline, pilot tower selection, the two-week loop, exit criteria. |
| [ROLLOUT.md](ROLLOUT.md) | Wave sequencing, the KB compounding loop, change management, go/no-go gates. |
| `automation/` | The seven rules as specifications, with build order. |
| `scripts/` | The build. See below. |

## The live app

**Two** complete towers are built and populated on `singhaditya21.atlassian.net`, from the
same design. Counts below were read live on 2026-07-20. Full detail, every URL and the
demo recommendation are in **[CONTROL-TOWER.md](CONTROL-TOWER.md)**.

### `OPS` — Jira Software · **demo this one**

- **Project:** [OPS](https://singhaditya21.atlassian.net/browse/OPS) — company-managed, 20 custom fields, 11 statuses, 13-transition workflow
- **Four ITSM issue types**, **P1–P4 priority scheme** derived from Impact × Urgency and set on the real Priority field
- **420 seeded tickets** across 6 towers — 171 escalated with complete gate evidence, 82 SLA-breached, 15 reopened, 62 open
- **156 tickets carry the full escalation trail in their history** — `New → Triage → In Progress L1 → Escalated to L2 → In Progress L2 → Resolved → Closed`. This is the demo; open `OPS-2298`, `OPS-2306` or `OPS-2309`.
- **79 escalations found no KB article** (46%) — the measured closing argument
- **[20 saved filters](https://singhaditya21.atlassian.net/issues/?filter=10035)** — per-tower L2 queues, SLA at-risk views, KB-gap and shadow-support queues
- **[Dashboard 10001](https://singhaditya21.atlassian.net/jira/dashboards/10001)** — 12 gadgets, all bound to named filters (repaired, CLAIMS #53). All 358 Closed tickets now carry a proper resolution (#54).

### `ITSM` — Jira Service Management · the "what's next"

JSM was provisioned mid-build, so the tower was rebuilt as a service project — **reusing**
every global object rather than duplicating it (same 20 fields, same priority scheme).

- **Project:** [ITSM](https://singhaditya21.atlassian.net/browse/ITSM) — service desk 8, ITIL template, 8 issue types
- **[19 agent queues](https://singhaditya21.atlassian.net/jira/servicedesk/projects/ITSM/queues)**, all non-empty · **[dashboard 10035](https://singhaditya21.atlassian.net/jira/dashboards/10035)** with 11 bound gadgets · **[customer portal](https://singhaditya21.atlassian.net/servicedesk/customer/portal/8)** with 17 request types
- **420 seeded tickets** — Resolution SLA Met 235 / Breached 68 / In progress 57 / Paused 48
- ⚠️ **The escalation story does not work here.** `Escalated` exists only in the Service Request workflows, so an escalated Incident's History contradicts its own fields. **Demo escalation from `OPS`.** Also avoid the native SLA panel and the approval gate — CLAIMS #49, #50, #51b.

```bash
source your-env-file             # JIRA_SITE, JIRA_EMAIL, JIRA_TOKEN

# OPS — Jira Software
python3 scripts/01_build.py      # project, fields, screens      (idempotent)
python3 scripts/02_workflow.py   # statuses + workflow           (idempotent)
python3 scripts/03_seed.py       # 420 tickets   --dry-run first (reproducible: fixed seed)
python3 scripts/04_views.py      # filters + dashboard           (gadget block NOT idempotent)
python3 scripts/05_issuetypes.py # Incident/Request/Change/Problem
python3 scripts/06_priority.py   # P1-P4 priorities + scheme
python3 scripts/07_baseline.py --by-tower   # measure the six scoreboard metrics
python3 scripts/08_sla.py        # recompute SLA from the timeline, not seeded values
python3 scripts/99_reset.py      # wipe issues so you can rehearse again

# ITSM — Jira Service Management (writes only scripts/.jsm_state.json)
python3 scripts/10_jsm_build.py  # service project, reuse fields + priorities (idempotent)
python3 scripts/11_jsm_seed.py   # 420 tickets   --dry-run / --pilot N / --backfill-only
python3 scripts/12_jsm_views.py  # 12 agent queues, 22 filters, dashboard 10035
```

The seeds use a fixed RNG seed, so the same data comes back every time. `99_reset.py` exists
because you will rehearse this four or five times.

**One exception to idempotency: the gadget block in `04_views.py` is not idempotent** — it
appends unbound gadgets on every run, which is why `OPS` dashboard 10001 now holds 12 blank
ones. Do not re-run it to fix them.

**Seeded history spans 2026-04-24 to 2026-07-15 even though every issue was created on
one day.** Jira's `created` is read-only over REST, so the real timeline lives in a
`Reported At` datetime field and every filter and gadget reads that instead. Without this,
all 420 tickets stack on a single day and every trend chart is one vertical spike.

**Change the towers to the real ones** by editing `TOWERS` in `scripts/config.py` and
re-running build and seed. That is the single highest-value change available.

## Working rules

Four artifacts state one argument, so corrections drift. Two mechanisms prevent it:

1. **[CLAIMS.md](CLAIMS.md) is the source of truth for facts.** Claims are `VERIFIED`, `UNVERIFIED`, `PLACEHOLDER` or `RETRACTED`. A claim not in the register does not belong in a deliverable.
2. **`python3 scripts/check_consistency.py` before committing.** It scans all six documents *and the deck* for retracted claims and for claims missing their required caveat.

Both exist because a claim was once asserted in four places before being checked, and shipped wrong — recorded as R1 in the register.

## The design in three lines

**Tier is a workflow state. Tower is a field. It is one project.** Escalation is a transition that flips `Support Tier` and reassigns — same ticket key, same continuous SLA clock, one audit trail. Splitting L1 and L2 into separate projects breaks all three, which is why ping-pong stays invisible and L1's contribution can't be measured.

The mechanism that makes it work is a **workflow validator** on `In Progress L1 → Escalated to L2` requiring Escalation Reason, Troubleshooting Performed and KB Article Checked. It enforces in configuration what policy cannot, and generates the escalation-rate-per-analyst data that tells you whether L1 is functioning.

The gate is **not** universal: a second transition, `Escalate — major incident`, carries no validators and is restricted to the Major Incident Manager role, because gating a P1 trades outage minutes for paperwork. A validator on `Resolved → Closed` requires the same three fields on every ticket, so majors pay the gate on the way out rather than skipping it.

**There is deliberately no ROI model.** Every cost input would be invented. The pilot measures a real baseline in two weeks; anything before that is decoration.

## Instance state as of 2026-07-20

Verified against `singhaditya21.atlassian.net`:

- **Jira Service Management is now provisioned** (`/rest/servicedeskapi/info` → `isLicensedForUse: true`). Earlier in the day it was not, and that claim survives as CLAIMS #3 marked SUPERSEDED. The `ITSM` project, its portal, request types, agent queues and native SLA fields all exist as a result.
- Structural config *is* REST-scriptable (fields, screens, statuses, workflows, schemes, permissions, filters, dashboards and gadget binding all return 200). So are JSM **SLA calendars**, **request type create/delete**, and — via an undocumented internal endpoint — **agent queue create and update**.
- **UI-only, each confirmed by probe rather than assumed:** workflow validators (so the escalation gate must be clicked, not scripted); automation rules — no public Cloud REST API, `404`, version-controlled via Automation's JSON export/import instead; SLA metrics and goals (a 56-path sweep found zero endpoints); agent queue **deletion** (no REST or GraphQL route — every queue created is permanent); request type update, grouping and form fields; portal branding and knowledge base.

The full capability map with evidence is in [CONTROL-TOWER.md](CONTROL-TOWER.md) §4 and CLAIMS #32–#41.

## Credentials

No credentials in this repo. Scripts read `JIRA_SITE`, `JIRA_EMAIL` and `JIRA_TOKEN` from the environment. `.claude/settings.local.json` is gitignored because Claude Code can record command history there, including tokens.
