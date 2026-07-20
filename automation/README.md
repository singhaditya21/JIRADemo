# Automation rules

Jira Cloud exposes **no public REST API for automation rules** —
`/rest/api/3/automation/rules` returns 404 (verified 2026-07-20, `CLAIMS.md` #6).
They are built in the rule builder and version-controlled through Automation's own
JSON export/import.

## What these files are

`rule-1` … `rule-7` are **specifications**, not verified Jira exports. Each maps
one-to-one onto the rule builder: trigger, conditions, actions, in order.

**They have not been round-tripped through Jira's import.** Authoring a file that
claims to be a Jira export without ever having exported one would be guessing at a
format, and a file that fails on import is worse than no file. The honest workflow:

1. Build the rule in the UI from the spec (each takes a few minutes).
2. **Export it from Automation** — Project settings → Automation → ⋯ → Export.
3. Commit the real export here, replacing the spec.

After step 3 this directory becomes genuinely reusable across environments. Until
then it is precise documentation, and labelled as such.

## Build order

Rules **5 and 6 first.** Rule 5 (SLA pause) is what makes the attainment report
defensible; without it every ticket waiting on a customer reads as a failure.
Rule 6 (reopen handling) is what makes first-time resolution honest; without it a
premature close reappears as a new ticket and flatters the number.

The other five improve the tower. Those two are what make its measurements true.

| # | Rule | Build order | Why |
|---|---|---|---|
| 5 | SLA pause and resume | **1st** | Makes SLA attainment trustworthy |
| 6 | Reopen handling | **2nd** | Makes first-time resolution honest |
| 1 | Derive priority | 3rd | Ends priority inflation |
| 2 | Route on escalation | 4th | Ticket lands in a tower queue, not on a person |
| 3 | Major incident alert | 5th | A P1 that waits in a queue is not a P1 |
| 4 | SLA breach warning at 75% | 6th | Warn while it can still be saved |
| 7 | Auto-close after resolution | 7th | Stops Resolved becoming a second backlog |

## Field IDs

Referenced by these specs, live on `singhaditya21.atlassian.net` — full list in
[SCHEMA.md](../SCHEMA.md).

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
