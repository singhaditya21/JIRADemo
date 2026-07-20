# Demo tomorrow — what to do tonight

> **Updated 2026-07-20, later the same day.** The JSM rebuild happened anyway — the `ITSM`
> project now exists, fully seeded, with a portal, 19 agent queues and a working dashboard.
> **The decision below is unchanged: still demo `OPS`.** The reason is now stronger, not
> weaker — the `Escalated` status does not exist in `ITSM`'s Incident workflow, so an
> escalated `ITSM` Incident's History contradicts its own fields. `ITSM` is the
> "what's next" slide and worth 60 live seconds. See **[CONTROL-TOWER.md](CONTROL-TOWER.md)**
> for both projects side by side and for what not to open in either.
>
> **Both earlier warnings are now resolved.** The `OPS` dashboard's 12 gadgets are bound to
> real filters (CLAIMS #53) and all 358 Closed tickets carry a proper resolution (CLAIMS #54).
> Step 7 of the run sheet works as written. A third reported defect — stale at-risk filter
> thresholds — turned out to be a false alarm and no change was made (CLAIMS #55).

**Decision: demo `OPS`.** JSM is provisioned and is the right long-term home, but the
run sheet's centrepiece — escalate, key stays the same, open History — works on 156 `OPS`
tickets and only 18 in `ITSM`. Migration is your "what's next" slide.

Environment verified `GOOD` on 2026-07-20: 420 tickets, 171 escalated with complete gate
evidence, SLA computed, 20 filters live.

---

## Tonight — about 2 hours

| | Task | Time | Why it matters |
|---|---|---|---|
| 1 | Escalation gate validator | 30 min | **The demo centrepiece.** Without it, step 3 of the run sheet does not work |
| 2 | Major Incident Manager role + fast path | 15 min | Answers the hardest question you will get |
| 3 | Automation rules 5 and 6 | 30 min | Rule 5 makes the SLA number quotable |
| 4 | Verify | 10 min | One command |
| 5 | Rehearse once, record it | 30 min | The fallback you will be glad you have |

If you only have one hour, do **1 and 2**. Everything else has a workaround; those two
are the argument.

> Menu labels shift between Jira versions. The navigation below is accurate as of now,
> but if a label differs, the shape of the task is still what is described.

---

## 1. The escalation gate validator (30 min)

**Settings (gear) → Issues → Workflows →** find `OPS L1-L2 Support Workflow` **→ Edit**

1. Select the **`Escalate to L2`** transition
2. Open **Validators → Add validator → Field Required Validator**
3. Add all three:
   - `Escalation Reason`
   - `Troubleshooting Performed`
   - `KB Article Checked`
4. Set the error message to something a human would write:
   *"Record what you tried before escalating to L2."*
5. **Publish the draft.** Jira edits in-use workflows as a draft — unpublished changes
   do nothing, and this is the single easiest way to arrive tomorrow with a gate that
   silently is not there.

**Verify by hand:** open any ticket in `In Progress L1`, try `Escalate to L2`, leave the
fields blank. It must refuse. If it lets you through, the draft did not publish.

---

## 2. Major Incident Manager role and the fast path (15 min)

**Settings → Issues → Project roles → Add project role** → `Major Incident Manager`

Then **Project settings → People** on `OPS` → add yourself to that role.

Back in the workflow editor:

1. Select the **`Escalate - major incident`** transition
2. **Conditions → Add condition → User Is In Project Role → Major Incident Manager**
3. Leave validators **empty** — that is the entire point
4. Publish

**Why this matters more than it looks.** "What about a P1?" is the first question a
real operator asks, and it is a good question: forcing a write-up during an outage
trades downtime for paperwork. Having the answer already built, with the capture merely
deferred to closure, is the strongest thirty seconds available to you.

---

## 3. Automation rules 5 and 6 (30 min)

**Project settings → Automation → Create rule.** Full specs in `automation/`.

**Rule 5 — SLA pause/resume.** Trigger: issue transitioned. Condition: status is
`Pending Customer` or `Pending Vendor`. Action: set `Resolution SLA` = `Paused`. Add the
inverse branch to set it back to `In progress` on exit.
*Build this one first — it is what makes the attainment figure defensible.*

**Rule 6 — reopen handling.** Trigger: issue transitioned from `Resolved` to `Triage`.
Action: set `Reopened` = `Yes`, set `Support Tier` = `L1`, notify.
*This is what keeps first-time resolution honest.*

Skip rules 1, 2, 3, 4 and 7 tonight. They improve the tower; these two make its numbers
true.

---

## 4. Verify (10 min)

```bash
source your-env-file
python3 -m app.cli sla --project OPS --dry-run    # SLA still computes cleanly
python3 -m app.cli metrics --project OPS --days 90  # the six metrics
```

Expected: 420 issues, resolution attainment ~78.9%, response ~96.6%, FTR 61.8%.
If those have drifted, something changed — investigate before you present, not during.

---

## 5. The run sheet — 12 minutes

1. **Open a ticket from the [L1 queue].** Point at the key. It will not change. That is
   the whole thesis.
2. **Show Impact and Urgency — not Priority.** Priority is derived from the matrix.
   Nobody argues their way to a P1.
3. **Try to escalate without troubleshooting. It refuses.** *This is the demo.* Show the
   three required fields.
4. **Fill them in and escalate properly.** Same key. Same clock. Open **History** — the
   full trail is there: `Triage → In Progress L1 → Escalated to L2 → In Progress L2 →
   Resolved → Closed`.
5. **Show the major-incident fast path**, then the `Resolved → Closed` validator that
   still demands the same three fields. Nothing is lost, only deferred.
6. **Move a ticket to Pending Customer.** The clock pauses. This is why the SLA report is
   trustworthy.
7. **Open the dashboard.** FTR 61.8%, reopen 4.3%, and the pairing: closing early lifts
   one and wrecks the other, so neither can be gamed alone.
8. **Close on the numbers you did not invent** — 46% of escalations found no KB article.
   That is L1's ceiling, measured, and the largest lever in the design.

If you get four minutes instead of twelve: **1, 3, 4, 7.**

---

## 6. Fallbacks

- **A — live Jira.** The real thing.
- **B — the recording.** Make it after tonight's rehearsal, while the environment is
  known-good. This is the one people skip and regret.
- **C — [demo.html](demo.html).** Works with no network and no Jira.

---

## 7. If you are asked what is not built

Answer plainly. It lands better than deflecting.

**"Why not Service Management?"** — It is provisioned as of today. The tower runs on Jira
Software, with SLA state carried in fields rather than the native engine. Migrating to a
service project is the next step and buys the customer portal, approvals and unlicensed
requesters — that last one is the structural argument, because on Jira Software every
person who needs to see a ticket needs a paid seat.

**"Is the SLA real?"** — Yes, computed from timestamps, not seeded: elapsed from
`Reported At` to resolution, minus paused time, on the calendar each priority is governed
by. P1/P2 on 24×7, P3/P4 on business hours. Building it caught a genuine error —
measuring a business-hours target on a 24×7 clock had understated attainment by 17 points.

**"Where did the targets come from?"** — They are placeholders, deliberately. No
measurement of a real organisation exists yet. The pilot sets targets from a measured
baseline; a target imported from another company is unfalsifiable.

**"Are the towers real?"** — No, they are a generic infrastructure split. Replacing them
is one edit and a reseed.

**"How much of this is automated?"** — Structure is scripted end to end and reproducible.
The gate validator and automation rules are UI, because Jira Cloud exposes no REST API
for either. Automation rules version-control through JSON export/import.

---

## 8. Do not do this tonight

- Do not run `fixtures/reset.py` unless you also reseed and re-run `app/sla_engine.py`. The demo state
  is currently verified good.
- Do not rebuild in JSM.
- Do not add the remaining five automation rules. Nothing in the run sheet needs them.
