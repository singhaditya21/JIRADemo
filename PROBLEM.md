# Problem statement

Why an L1/L2 support tower degrades, what that costs, and what "fixed" would mean.

> **Read this first.** The design in `PLAN.md` only makes sense against this problem. Every
> mechanism there exists to close a specific failure named here.

---

## 1. Context

An L1/L2 tower is a two-tier support organisation sitting between users and the systems they
depend on. **L1** takes everything, triages it, and resolves what it can from a known-error
base. **L2** holds deep expertise in one technical domain — a *tower* — and takes what L1
cannot resolve. A third tier, usually a vendor, sits behind L2 for defects and hardware.

The structure is chosen for economics, not elegance. L1 is cheaper, broader and easier to
staff; L2 is scarce and expensive. The entire value of the model rests on one assumption:
**that L1 absorbs the majority of volume so L2 is spent only where expertise is genuinely
required.** Every failure below is a variation on that assumption quietly breaking.

---

## 2. The operating reality

Four conditions shape every decision in the design. They are not problems — they are the
terrain.

- **Volume is uneven and unpredictable.** Demand arrives in bursts tied to releases, month-end
  and outages, not in a smooth queue.
- **Skill is deliberately asymmetric.** L1 is not a junior version of L2; it is a different
  job. Designing as if L1 is "L2 with less training" produces a tower that neither triages nor
  resolves.
- **The team cannot stop taking tickets.** There is no maintenance window for the support
  function. Any change must land under live load.
- **The customer's perception is set by the first hour**, not the resolution. A ticket resolved
  in three days with contact in ten minutes rates better than one resolved in a day in silence.

---

## 3. Symptoms — what people actually complain about

These are the observable behaviours. None of them is the problem; all of them are downstream
of §4.

**3.1 Ticket ping-pong.** L1 forwards without troubleshooting; L2 bounces it back as
insufficiently diagnosed. The ticket accumulates handoffs and no progress. Nobody is
accountable between the bounces.

**3.2 L1 cannot demonstrate its value.** Ask what proportion of demand L1 absorbs and nobody
can answer from data. At budget time L1 reads as a switchboard with a headcount, and gets cut —
which raises L2 load, which worsens everything else.

**3.3 SLA reports nobody trusts.** Clocks run while the ticket waits on the customer, so
attainment looks catastrophic regardless of performance. Leadership stops opening the report,
and with it goes the only feedback loop the tower had.

**3.4 Priority inflation.** When the requester sets priority, everything is urgent. P1 stops
meaning "the business is stopped" and starts meaning "this person is annoyed." Real majors then
compete for attention with noise.

**3.5 Knowledge never flows back.** L2 solves something genuinely hard, writes it in a comment,
and closes. L1 never learns it. The identical ticket escalates again next month. **L1's
resolution ceiling is permanently capped at whatever its people happened to already know.**

**3.6 Shadow support.** When raising a ticket is slower than direct-messaging an engineer,
users direct-message the engineer. That work becomes invisible: it is absent from volume data,
uncounted in capacity planning, and unprotected by any SLA. The tower's metrics improve while
the actual service degrades — the most dangerous failure mode here, because it looks like
success.

**3.7 Recurring incidents treated as novel.** The same failure is worked from scratch forty
times a month. Nobody asks why it happens, because no mechanism makes recurrence visible.

**3.8 Queue cherry-picking.** Given a shared queue and individual metrics, agents take the easy
tickets. Hard tickets age quietly at the bottom until someone escalates by complaint.

**3.9 Ownership vacuum after handoff.** Once escalated, who answers to the customer? Usually
nobody has been told it is still theirs, so the customer chases — and chasing becomes the
fastest way to get service, which teaches everyone to chase.

**3.10 L1 attrition.** If every interesting ticket escalates, L1 is a dead-end job. People
leave, taking their known-error knowledge with them, and first-time resolution resets to zero
with each new hire. This is the loop that makes the other failures permanent.

---

## 4. Root causes — the structural layer

The ten symptoms reduce to five design faults. This is the actual problem.

**4.1 The handoff is modelled as a new ticket, not a state change.**
Separate projects or queues per tier means escalation mints a new key, restarts the SLA clock
and splits the audit trail. *Consequence:* ping-pong is invisible (3.1), L1's contribution is
unmeasurable (3.2), end-to-end MTTR cannot be computed, and ownership evaporates at the seam
(3.9). **This single choice causes more damage than the other four combined.**

**4.2 Triage discipline is policy, not configuration.**
"Troubleshoot before escalating" is a rule people are told. Under queue pressure, told-rules
lose to the clock every time. *Consequence:* 3.1, and no data on why anything escalated.

**4.3 Priority is an opinion rather than a derivation.**
Free-set priority is a negotiation between requester emotion and analyst fatigue.
*Consequence:* 3.4, and every SLA target downstream becomes meaningless.

**4.4 The clock has no concept of whose court the ball is in.**
An SLA that cannot pause measures elapsed time, not service. *Consequence:* 3.3.

**4.5 There is no loop from resolution back into capability.**
Nothing converts a solved L2 ticket into an L1-resolvable one, and nothing converts repeat
incidents into a problem record. *Consequence:* 3.5, 3.7, a permanently capped L1 (3.2) and,
eventually, 3.10.

---

## 5. Why this persists

Every symptom has a plausible local explanation that points away from the structure:

| Symptom | The comfortable explanation | What it actually is |
|---|---|---|
| Ping-pong | "L1 needs more training" | No enforced gate (4.2) |
| L1 looks low-value | "L1 is genuinely low-value" | It is unmeasurable (4.1) |
| SLA misses | "We are understaffed" | The clock is wrong (4.4) |
| Repeat incidents | "The infrastructure is old" | No problem loop (4.5) |
| Everything is a P1 | "Our users are demanding" | Priority is an opinion (4.3) |

Each explanation is locally reasonable, which is precisely why the structural cause survives
years of well-intentioned effort. Training, hiring and escalation policies all get tried first,
because they follow from the comfortable explanation. **The failure is not that people have not
worked at this. It is that the work has been aimed one level too high.**

---

## 6. Cost of inaction

Deliberately stated without a currency figure — see §8.

- **Confidence.** Once the SLA report is distrusted, the tower has no way to prove it is
  improving, and improvement stops being funded.
- **Attrition.** 3.10 compounds: each departure lowers first-time resolution, raising L2 load,
  making L1 duller, driving the next departure.
- **Shadow demand.** 3.6 means the true service picture is unknown and unknowable. Capacity
  planning is fiction.
- **Escalation-by-relationship.** When chasing works, service quality becomes a function of who
  the user knows. Quiet teams are served worst.
- **Optionality.** None of automation, self-service deflection or AI triage can be built on a
  base where the ticket record does not reflect what actually happened.

---

## 7. What "solved" looks like

The end state, stated so it can be checked rather than asserted:

1. One ticket key survives the full lifecycle, whatever tier touches it.
2. Escalation cannot happen without a recorded reason — **except on a deliberate, accountable
   fast path for major incidents** (see `PLAN.md` §7).
3. Priority is derived from impact and urgency, not negotiated.
4. The SLA clock stops when the ball is in the customer's court, and the report is trusted
   enough to be read.
5. Every escalation with no matching KB article generates a candidate article.
6. Recurring incidents become problem records rather than repeated work.
7. First-time resolution at L1 is measurable, and moves.

**Baselines are deliberately absent.** Targets get set from the pilot's own measured baseline,
not from numbers imported from someone else's organisation (§8).

---

## 8. Honesty about the numbers

Any specific figure in this repo — first-time-resolution targets, SLA durations, ticket
volumes, per-ticket costs — is a **placeholder illustrating shape, not a benchmark**. None is
drawn from research on this organisation, because no measurement of this organisation exists
yet.

The correct sequence is: instrument first, measure the baseline through the pilot, then set
targets against it. A target imported from another company is worse than no target — it is
unfalsifiable and it invites argument about the number instead of the mechanism.

`CLAIMS.md` records every factual assertion in this repo with its verification status.

---

## 9. Non-goals

Naming what this does **not** fix prevents the design being judged for the wrong failures:

- **Not a staffing model.** It measures whether the tower is resourced correctly; it does not
  size it.
- **Not a CMDB or asset management programme.** It references services; it does not inventory
  them.
- **Not a fix for underlying platform instability.** It makes recurrence *visible* via problem
  records. Fixing the causes is other work.
- **Not full ITIL adoption.** Four issue types, not a certification programme.
- **Not a change-management or comms plan.** The technical build is 8 weeks (`PLAN.md` §12).
  Shifting how a live support team actually works takes considerably longer, and that effort is
  not scoped here.
