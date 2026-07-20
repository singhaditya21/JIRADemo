# Pilot — one tower, two weeks

The pilot is not a formality. It is where placeholder targets get replaced with
measured ones, where the escalation gate gets tuned against real queue pressure, and
where the first problem records become the KB articles every later tower inherits.

---

## 1. Measured baseline

Run against the live `OPS` project on 2026-07-20, 90-day window, measured on
`Reported At`. SLA state is **computed** by `08_sla.py`, not seeded — P1/P2 on the
24×7 clock, P3/P4 on a business-hours calendar, paused states excluded:

```
python3 scripts/08_sla.py          # recompute SLA from the timeline
python3 scripts/07_baseline.py --days 90 --by-tower
```

| Metric | Measured | Placeholder target | |
|---|---|---|---|
| Volume (90d) | 420 | — | |
| First-time resolution at L1 | **61.8%** (215/348) | ≥ 65% | gap |
| Escalation rate | **40.7%** (171/420) | — | |
| Reopen rate | **4.3%** (15/348) | < 5% | pass |
| Resolution SLA attainment | **78.9%** (306 met / 82 breached) | ≥ 95% | gap |
| Response SLA attainment | **96.6%** | ≥ 95% | pass |
| Open now | 62 | — | |
| Aged over 14 days | **60** | → 0 | gap |
| Escalated with no KB article | **79 (46% of escalations)** | — | the KB backlog |
| Arrived via chat | 43 | — | shadow support, now visible |

**The two numbers that matter most.** 46% of escalations found no KB article — that
is L1's ceiling made visible, and it is the single largest lever in the design. And 60
of 62 open tickets are older than 14 days, which says the backlog is not a queue, it
is a graveyard.

Note the targets are still placeholders (`CLAIMS.md` #15). The pilot's job is to
replace them with targets set from this baseline.

---

## 2. Pilot tower: End User Computing

Chosen by the ranking in `07_baseline.py`, which sorts on volume × improvement
headroom — enough traffic to be statistically meaningful, enough gap to be worth
fixing.

| Tower | Volume | FTR | Escalation | SLA |
|---|---|---|---|---|
| **End User Computing** | **126** | **61.9%** | 41.3% | 81.4% |
| Enterprise Applications | 101 | 62.7% | 37.6% | 78.5% |
| Compute & Storage | 51 | 48.8% | 51.0% | 75.5% |
| Network & Connectivity | 58 | 62.0% | 41.4% | 81.8% |
| Database | 50 | 73.7% | 36.0% | 78.6% |
| Cloud & Security | 34 | 62.1% | 38.2% | 71.0% |

**Why not Compute & Storage**, which has the worst FTR at 48.8%? Volume is 51 over 90
days — under a ticket a day. Two weeks of pilot would produce roughly ten tickets,
which is not enough to tell a real improvement from noise. **Why not Database**, at
73.7%? It is already the healthiest; a pilot there proves nothing.

EUC has the highest volume *and* sits below target. It is also the tower whose
failures are most visible to ordinary staff, so improvement is noticed.

---

## 3. What gets built before day one

The pilot cannot start until these exist. Everything else is already live.

| # | Item | Status |
|---|---|---|
| 1 | **Escalation gate validator** on `In Progress L1 → Escalated to L2` | **Not built.** UI only — `CLAIMS.md` #8. Blocks the pilot. |
| 2 | `Escalate — major incident` transition, restricted to the MIM role | Not built. UI only. |
| 3 | Automation rules 5 (SLA pause) and 6 (reopen) | Specs in `automation/`. Build first. |
| 4 | Automation rules 1–4, 7 | Specs in `automation/`. |
| 5 | Project, fields, statuses, workflow, priorities, queues | ✅ live |
| 6 | Baseline captured | ✅ above |

Item 1 is the gate on everything. Until the validator exists the design is documented
but not enforced, and the pilot would measure a tower that is not actually running the
model.

---

## 4. The two-week loop

**Week 1 — run and observe. Change nothing.**
Resist tuning in week 1. The first days always look bad because people are learning
the new transitions, and reacting to that noise tunes the system to the wrong signal.

- Daily: check `OPS - L1 queue (open)` and the at-risk filters
- Watch **escalation rate per analyst**. One analyst diverging sharply from the rest is
  either a coaching need or the gate being routed around (`PLAN.md` risk).
- Log every complaint about the gate verbatim. These become week 2's changes.

**Week 2 — tune.**
- Adjust SLA targets to the measured baseline, not to the placeholders
- Review every `Escalation Reason = Root cause unclear after triage` — a spike here
  means the runbooks are thin, not that L1 is weak
- Convert the top recurring incidents into problem records
- Write KB articles for the highest-frequency entries in
  `OPS - Escalated with no KB article found`

---

## 5. Exit criteria

Go/no-go for rollout. **Not all of these are improvements** — two are honesty checks.

| # | Criterion | Threshold |
|---|---|---|
| 1 | The gate holds | < 5% of escalations bypass via the major-incident path |
| 2 | FTR moved | ≥ +5 percentage points against the 61.9% EUC baseline |
| 3 | Reopen rate did **not** rise | ≤ baseline + 1pp — *catches FTR bought by closing early* |
| 4 | SLA report is believed | Tower lead can explain any breach without disputing the clock |
| 5 | KB loop produced output | ≥ 10 articles from the no-article-found queue |
| 6 | Agents are not routing around it | No analyst's escalation rate diverges > 2σ from the tower mean |

**Criterion 3 is the important one.** Without it, the pilot can "succeed" by teaching
L1 to close prematurely, and the design will have made things worse while the headline
number improves.

**If criteria 1 or 6 fail, do not roll out.** A gate that is bypassed is worse than no
gate: it produces confident-looking escalation data that is false.

---

## 6. Rehearsal

The environment is resettable, so the pilot can be dry-run end to end:

```bash
python3 scripts/99_reset.py --yes     # wipe issues
python3 scripts/03_seed.py            # fixed RNG seed - identical data every time
python3 scripts/07_baseline.py --by-tower
```

Same dataset every run, so a change in the numbers means a change you made, not
sampling noise.
