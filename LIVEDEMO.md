# Building a live, functioning demo

How to get from the plan to something you can actually click through in front of your next boss.

---

## 1. What is genuinely scriptable — verified, not assumed

Probed against `singhaditya21.atlassian.net` on 2026-07-20:

| Capability | Endpoint | Status |
|---|---|---|
| Custom fields | `/rest/api/3/field` | ✅ 200 — scriptable |
| Screens & screen schemes | `/rest/api/3/screens` | ✅ 200 — scriptable |
| Statuses | `/rest/api/3/statuses/search` | ✅ 200 — scriptable |
| Workflows & workflow schemes | `/rest/api/3/workflow*` | ✅ 200 — scriptable |
| Issue type schemes | `/rest/api/3/issuetypescheme` | ✅ 200 — scriptable |
| Permission schemes | `/rest/api/3/permissionscheme` | ✅ 200 — scriptable |
| **Automation rules** | `/rest/api/3/automation/rules` | ❌ **404 — no public Cloud REST API** |
| **JSM SLAs & queues** | `/rest/servicedeskapi/*` | ❌ **403 — not licensed on this site** |

**Correction to the earlier plan.** I previously said the whole build was REST-scriptable. That is true for structure — fields, screens, statuses, workflows, schemes, permissions — and **not** true for automation rules, which have no public Cloud REST API and must be built in the rule builder UI.

They are still version-controllable: Jira Automation supports **export/import of rules as JSON**, so the rules live in this repo as artifacts and get imported rather than clicked from scratch. SLA configuration is likewise a JSM UI task.

Say this out loud during the demo. "Structure is scripted, automation rules are exported JSON, SLA config is UI" is a more credible sentence than "it's all automated," and it is the kind of detail that signals you have actually done this.

---

## 2. Recommended architecture

Build the real thing on a real Jira, seed it with realistic data, and make it resettable so you can rehearse.

```
  Jira Service Management (free tier — 3 agents, full SLA engine)
        ▲                    ▲                      ▲
   scripted structure   imported rules JSON    seeded ticket data
   (REST, in repo)      (export/import)        (REST + CSV import)
        │                    │                      │
        └──────────── all in this repo, re-runnable ┘
```

**Why the real product rather than a mock:** the demo claim is "I can build this in Jira." A simulator proves you can build a simulator. Working Jira with a validator that actually blocks an escalation is the moment that lands.

**Why the free tier:** 3 agents and the complete SLA engine, at no cost and no purchase approval. Enough to demonstrate every mechanism in the design.

---

## 3. Seed data is what makes or breaks this

The most common way a live Jira demo dies: the project is empty. No dashboards, no SLA breach, no escalation-rate chart — nothing to show. Budget real effort here.

**Target shape:** ~250 tickets across 6 towers, priority-weighted realistically (roughly 5% P1, 20% P2, 55% P3, 20% P4), about 60% resolved at L1 and 40% escalated, a handful actively breaching, and a few deliberately aged past 14 days for the backlog widget.

**The timestamp constraint — plan around this.** Jira's `created` field is read-only over REST, so a seeder run today produces 250 tickets all created today, and every trend chart is a single vertical spike. Two ways out:

- **CSV import** (Jira UI, admin → External System Import) accepts an explicit Created date. This is the reliable route for backdated history.
- **Seed early.** Run the generator against the site 2–3 weeks before the demo and let real time pass. Cheapest option if the date is known.

Combine them: CSV-import the historical baseline for the charts, then use the REST seeder for the live tickets you will actually manipulate on screen.

---

## 4. Repo layout

> This section was written before the build. The layout below is what was actually
> built; the original plan named eight scripts (`00_env.sh`, `01_project.py`,
> `02_fields.py`, `03_screens.py`, `04_workflow.py`, `05_schemes.py`, `06_seed.py`,
> `99_teardown.py`) and a `data/historical.csv` that were superseded — CSV import
> was never used, the REST seeder covers it.

```
shared/                # vendor-neutral, no Jira specifics
  jira_client.py       # thin REST client; reads JIRA_SITE/EMAIL/TOKEN from environment
  domain.py            # towers, priority matrix, SLA targets & calendars, statuses, field names
  fields.py            # runtime field resolver: name -> customfield id, no build artifact
jira_config/           # infrastructure as code; declarative, idempotent, run on change
  jira_schema.py       # the only Jira-specific mapping: type keys, searcher keys, project key
  build.py             # project, custom fields + contexts, screens, field configuration
  workflow.py          # statuses, transitions, the escalation-gate validator
  issuetypes.py        # Incident / Service Request / Change / Problem
  priority.py          # P1–P4 and the priority scheme
  views.py             # saved filters + dashboard gadgets
  reconcile.py         # filter/gadget/queue reconciliation engine + the dry-run write gate
  jsm_build.py         # the ITSM service project, reusing every global object
  jsm_views.py         # agent queues, ITSM filters, dashboard
  repair.py            # one-off remediation of known defects
  state/               # build artifacts — written by jira_config, read by nothing else
  apply.py             # orchestrator: build -> workflow -> issuetypes -> priority -> views
fixtures/              # demo and test data ONLY — never runs in production
  catalog.py           # ticket content: symptoms, services, resolutions per tower
  seed.py              # generate OPS tickets, drive them through transitions
  jsm_seed.py          # the same model retargeted at the ITSM service project
  reset.py             # wipe issues so the demo can be re-run clean
app/                   # the application layer — stateless, read-mostly
  sla_engine.py        # recompute SLA from the timeline
  metrics.py           # the six scoreboard metrics
  cli.py               # python3 -m app.cli sla | metrics
tools/
  check_consistency.py # guards the deliverables against retracted claims
automation/
  *.json               # exported Automation rules, imported via the UI
```

**Idempotency and teardown matter more than they look.** You will rehearse this four or five times. A build that only works against a clean site, or that can't be reset, means your last rehearsal leaves the demo environment in a state you have not practised on.

---

## 5. Build order

| Step | Work | Route |
|---|---|---|
| 1 | Provision JSM free tier | UI, ~10 min |
| 2 | Create project `OPS` | script |
| 3 | Custom fields + contexts | script |
| 4 | Screens, field configuration | script |
| 5 | Statuses, workflow, **escalation gate validator** | script |
| 6 | Bind schemes to project | script |
| 7 | SLA targets + pause conditions | JSM UI |
| 8 | Queues, one per tower | JSM UI |
| 9 | Automation rules | import JSON from `automation/` |
| 10 | CSV-import historical data | UI |
| 11 | REST-seed live tickets | script |
| 12 | Dashboards + filters | UI |

Steps 2–6 are one command. Steps 7–9 are the JSM-native parts that genuinely need the UI.

---

## 6. The run sheet — roughly 12 minutes

The demo has to *show the argument*, not tour the configuration.

1. **Open a P1 in the queue.** Point out the ticket key. This key will not change — that is the whole thesis.
2. **Show Impact and Urgency, not Priority.** Change Urgency; watch automation recompute Priority live. Nobody argues their way to a P1.
3. **Try to escalate without troubleshooting.** *This is the money moment.* The validator refuses. Show the three required fields.
4. **Fill them in, escalate properly.** Same ticket key. Same SLA clock, still running. Show the history — every hand that touched it, in one trail.
5. **Then show the major-incident fast path.** Switch to a P1 and use `Escalate — major incident`: no validators, straight through, restricted to the Major Incident Manager role. Then show the `Resolved → Closed` validator that still demands the same three fields, so the learning is deferred rather than lost. **Expect the question "what about a P1?" — answering it before it is asked is worth more than any other thirty seconds in the demo.**
6. **Move it to Pending Customer.** SLA clock pauses. This is why the SLA report is trustworthy.
7. **Open the dashboard.** First-time resolution at L1, escalation rate by analyst, reopen rate. Land on the pairing: FTR and reopen move against each other, so neither can be gamed.
8. **Close with the phase plan** and the one open question you want them to answer.

Step 3 is the demo, and step 5 is the answer to the hardest question in the room. If you have only four minutes, do steps 1, 3, 4 and 7.

---

## 7. Fallbacks — decide these before you present

Live demos fail on someone else's network. Have all three ready:

- **A — Live Jira.** The real thing.
- **B — Recorded walkthrough.** Screen-record the full run sheet the day before. Covers dead wifi, Atlassian latency, and an expired session. This is not optional; record it.
- **C — [demo.html](demo.html).** The published page works with no network and no Jira. Worst case, you present the argument with the diagrams and skip the click-through.

The recording is the one people skip and regret. Do it after your final rehearsal, while the environment is in a known-good state.

---

## 8. Before any of this — two blockers

1. **Provision JSM**, or the SLA engine, queues and portal do not exist and half the run sheet is impossible.
2. **Rotate the API token.** It has been shared in plaintext and written into local config, and it grants full site admin. Rotate at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens), then export the new one as `JIRA_TOKEN` — the scripts read it from the environment and never store it.

---

## Realistic effort

Roughly **2–3 focused days** to a demo-ready environment: half a day scripting structure, half a day on SLA/queues/automation in the UI, a day on seed data and dashboards, half a day rehearsing and recording. The seed data will take longer than you expect.
