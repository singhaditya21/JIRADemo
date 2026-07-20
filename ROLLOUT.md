# Rollout — the remaining five towers

Rollout is a change-management exercise wearing a configuration costume. The build is
already done: adding a tower is one line in `scripts/config.py`. What takes the time
is people, and that is what this document is about.

---

## 1. Sequence

Ordered by risk, not by size. Each wave inherits the KB the previous one produced.

| Wave | Tower | Volume (90d) | Baseline FTR | Why here |
|---|---|---|---|---|
| Pilot | End User Computing | 126 | 61.9% | Highest volume with headroom |
| 1 | Enterprise Applications | 101 | 62.7% | Next-highest volume; similar failure shapes to EUC |
| 2 | Network & Connectivity | 58 | 62.0% | Higher P1 density — do it once the gate is proven under pressure |
| 3 | Compute & Storage | 51 | 48.8% | **Worst FTR.** Needs the accumulated KB most, so it goes late, not early |
| 4 | Database | 50 | 73.7% | Already healthy — least to gain, least to lose |
| 5 | Cloud & Security | 34 | 62.1% | Lowest volume, but worst SLA at 65.5%. Approvals and access make it the most political |

**Compute & Storage goes third, not first, despite having the worst numbers.** A tower
at 48.8% FTR has a knowledge problem, and dropping a gate on it before the KB exists
just converts a knowledge problem into a blocked queue and an angry team.

**Cloud & Security goes last** because its work is entangled with approvals, privileged
access and audit. Those conversations are slower and shouldn't hold up five other towers.

---

## 2. Per-wave mechanics

Two weeks per wave, overlapping — wave *n* runs its second week while wave *n+1* runs
its first.

```bash
# 1. add the tower to TOWERS in scripts/config.py
python3 scripts/01_build.py        # adds the select option, idempotent
python3 scripts/04_views.py        # creates that tower's L2 queue
python3 scripts/07_baseline.py --by-tower   # capture the pre-cutover baseline
```

Then, per wave:

1. **Capture the baseline first.** Without a pre-cutover number the tower can argue
   afterwards that it was always that way.
2. **Brief L2 before L1.** L2 feels the gate as a change in what arrives; if they
   haven't been told why, they read it as L1 being obstructive.
3. **Two weeks of run and tune**, following the same loop as `PILOT.md` §4.
4. **Go/no-go against `PILOT.md` §5 exit criteria**, measured for that tower.

---

## 3. The KB compounding loop — the actual point of sequencing

At baseline, **46% of escalations found no KB article** (79 of 171). That is the number
rollout exists to move.

```
   pilot escalations with no article  ->  problem records  ->  KB articles
                                                                   |
                              wave 1 inherits them, escalates less  |
                                                                   v
                              wave 2 inherits more  ->  ...  ->  wave 5 inherits most
```

Each wave should start with a lower escalation rate than the last, purely from
inherited knowledge. **If wave 2's opening escalation rate is not below wave 1's, the
loop is not working** — and that is a more important signal than any individual
tower's FTR. Investigate before continuing rather than pushing on to wave 3.

Track it explicitly: opening escalation rate per wave, plotted across waves.

---

## 4. Change management — the part that is not configuration

`PROBLEM.md` §9 names this as out of scope for the 8-week technical build. It is not
out of scope for rollout, and it is where rollouts actually fail.

**The gate will be experienced as distrust.** An L1 analyst who has escalated freely
for years will read the validator as an accusation. Say the real reason out loud:
without recorded escalation reasons, L1 has no evidence of its own contribution and
gets cut at budget time. **The gate is the mechanism by which L1 can prove its value.**
That framing is true, and it is the difference between adoption and resentment.

- **Brief tower leads first**, one week ahead. They will be asked to defend it.
- **Publish escalation-rate-per-analyst to the team, not just to managers.** Used as a
  coaching input it works; used as a secret management metric it breeds gaming.
- **Say what happens to the KB gap list.** If analysts flag missing articles and
  nothing is ever written, they stop flagging within a fortnight.
- **Name an owner for the KB.** An unowned knowledge base decays to noise, and then
  "check the KB" becomes theatre.

---

## 5. Go/no-go gates between waves

Do not start the next wave if any of these hold:

| Signal | Meaning | Action |
|---|---|---|
| Gate bypass > 5% in the previous wave | The fast path is being abused | Tighten transition permissions; re-brief; **do not proceed** |
| Reopen rate rising across waves | FTR is being bought by premature closure | Stop. Re-examine closure criteria |
| Opening escalation rate not falling wave over wave | KB loop is not compounding | Investigate KB quality before adding towers |
| Any tower lead cannot explain their SLA figures | The clock is still wrong somewhere | Fix pause conditions first |
| Aged backlog growing | Rollout is outpacing capacity | Pause and drain |

---

## 6. After the last wave

Rollout ends when configuration stops changing. The system is only finished when:

1. **Placeholder targets are gone.** Every target in `CLAIMS.md` marked 🔵 has been
   replaced by one derived from measured baselines.
2. **The problem loop runs without prompting** — recurring incidents become problem
   records because someone owns that, not because someone remembered.
3. **The SLA report is read.** The real test is not attainment, it is whether anyone
   opens the report. `PROBLEM.md` 3.3 is only fixed when leadership uses it again.
4. **Escalation rate per analyst is a coaching conversation**, not a scoreboard.

Then the towers currently listed as placeholders (`CLAIMS.md` #13) should be revisited
— by that point the real operational boundaries will be visible in the escalation data,
and they are unlikely to match the six guessed at the start.
