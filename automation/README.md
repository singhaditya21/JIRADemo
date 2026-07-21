# Automation rules

**All seven rules are live on `singhaditya21.atlassian.net` (project OPS) and ENABLED**
(verified 2026-07-21, `CLAIMS.md` #101). They are created and reconciled by
[`build_rules.py`](build_rules.py); run it to rebuild them on any instance.

```bash
source your-env-file                 # JIRA_SITE, JIRA_EMAIL, JIRA_TOKEN
python3 automation/build_rules.py --dry-run
python3 automation/build_rules.py                 # idempotent: skips rules that already exist
python3 automation/build_rules.py --state DISABLED # build them off (e.g. to inspect before enabling)
```

| # | Rule | Trigger | What it does |
|---|---|---|---|
| 1 | Derive priority from Impact × Urgency | work item **updated** | Re-derives Priority from the 3×3 matrix on every edit (9 branches, gated on Impact **and** Urgency) |
| 2 | Reopen handling | Resolved → Triage | Sets Reopened = Yes, Support Tier = L1 |
| 3 | Major incident alert | work item created, Priority = P1 - Critical | **Assigns to the Major Incident Manager** (fires Jira's assignment notification) + posts a bridge/comms comment |
| 4 | SLA breach warning | scheduled, daily 08:00 | Comments on open P1/P2 tickets that have gone quiet |
| 5 | SLA pause on Pending | → Pending Customer / Pending Vendor | Sets Resolution SLA = Paused |
| 6 | Route on escalation | → Escalated to L2 | Sets Support Tier = L2 |
| 7 | Auto-close resolved tickets | scheduled, daily 02:00 | Transitions week-old Resolved tickets to Closed |

## How they were built — no public API, no working UI capture, so: round-trip discovery

Jira Cloud exposes **no public REST API** for automation (`/rest/api/3/automation/rules`
→ 404). The Automation UI drives an **internal** API the token *can* reach:

```
POST .../pro/rest/{projectId}/rules   # list
POST .../pro/rest/{projectId}/rule    # create  (needs the FULL rule wrapper, not a minimal envelope)
```

The hard part was the component **value schemas**. The documented source is the Flows
builder, but it freezes the CDP-driven renderer on save, so click-through capture is
unreliable. They were instead discovered by **empirical round-trip**: POST a rule with a
candidate `value`, `GET` it back to read the canonical shape the server normalises to,
then `DELETE` the probe. Every shape is written down in
[`schema/component-schemas.md`](schema/component-schemas.md); the real captured wrapper is
[`schema/example-transition-edit.rule.json`](schema/example-transition-edit.rule.json).

Two gotchas worth knowing:

- **ENABLED validation is stricter than DISABLED.** A rule round-trips fine while disabled
  but is rejected on enable unless the entity references resolve: the created trigger needs
  `eventKey`/`issueEvent` populated, the scheduled trigger needs `schedule.method:"CRON"`,
  a **priority** condition compares by **ID** while a **select** field compares by **NAME**.
- **Two component types stayed UI-only, so two rules use enable-able equivalents.** The
  `jira.issue.field.changed` trigger cannot be *enabled* over the API (it 500s on every
  value, field-scoped or not), and the outgoing-email `to[]` recipient shape 500s on every
  value too. So rule 1 uses the generic **`…:updated`** trigger (re-derives Priority on any
  edit — same net effect as field-changed on Impact/Urgency, since the matrix conditions
  gate each branch), and rule 3 **assigns the P1 to the Major Incident Manager**, which
  fires Jira's own assignment notification to that person. Both are faithful equivalents,
  not weaker stand-ins. To use the literal field-changed trigger or a Send-email action
  instead, build that one component in the UI.

## Enable safety and snapshot drift

The five event-triggered rules (1, 2, 3, 5, 6) only fire on *future* events, so enabling
them never touched existing tickets (OPS is still 420/171, verified). The two **scheduled**
rules (4, 7) act on the data when they run, and their `updated <= -Nd` windows are
*relative*, so what they match **grows as the static seed ages** (`CLAIMS.md` #110):

- **SLA breach warning** (daily 08:00) matched 0 rows when authored but ~a day later matches
  the open P1/P2 tickets that have gone quiet (9, after excluding paused Pending statuses);
  its next run comments on those.
- **Auto-close** (daily 02:00) still matches 0 (no Resolved ticket is a week stale yet) and
  will close them on a rolling 7-day basis.

This forward drift is the authorised behaviour of enabling these rules. To restore a clean,
inert snapshot before a demo, re-run the seed (`python3 -m fixtures.reset` + reseed) — it
resets every `updated` to today, which empties both windows again.

## The `rule-N-*.json` files

These remain human-readable **specifications** (trigger → conditions → actions, in order),
kept for review and for building the rules by hand. `build_rules.py` is the source of
truth for what is actually on the instance; the specs are documentation.

## Field IDs

Live on `singhaditya21.atlassian.net` — full list in [SCHEMA.md](../SCHEMA.md).

| Field | ID |
|---|---|
| Tower | `customfield_10042` |
| Support Tier | `customfield_10043` |
| Impact | `customfield_10004` |
| Urgency | `customfield_10044` |
| Response SLA | `customfield_10050` |
| Resolution SLA | `customfield_10051` |
| Reopened | `customfield_10052` |
| Reported At | `customfield_10057` |
| Resolved At | `customfield_10060` |
