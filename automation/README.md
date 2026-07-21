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


## Update 2026-07-20 — the API is reachable after all

The public `/rest/api/3/automation/rules` returns 404, but the Automation UI drives an
**internal** API that the token *can* reach:

```
POST /gateway/api/automation/internal-api/jira/{cloudId}/pro/rest/{projectId}/rules   # list  -> 200
POST /gateway/api/automation/internal-api/jira/{cloudId}/pro/rest/{projectId}/rule    # create -> exists (400 on bad body)
```

The create envelope is known (CLAIMS #77):

```json
{ "ruleConfigBean": {
    "name": "...", "state": "ENABLED|DISABLED",
    "authorAccountId": "<accountId>",
    "trigger": { "component": "TRIGGER", "type": "<type>", "value": null, "children": [] },
    "components": [ /* conditions and actions */ ] } }
```

**What is still missing:** the exact `type` strings and `value` schemas for each trigger,
condition and action. Those were **not** reverse-engineered and are **not** guessed here
(CLAIMS #78). The reliable way to get them is to build ONE rule by hand in the UI, then
`GET` it back over the internal API — the same technique that corrected the "validator is
UI-only" mistake (CLAIMS #8). Once one real rule is captured, the six recipe files below can
be turned into real create payloads and posted.

The `rule-N-*.json` files remain **specifications**, not verified exports.


## Update 2026-07-20 (later) — verified triggers, and the one manual step that unblocks the rest

Verified without guessing (CLAIMS #87-90):

- **Trigger types** (from `ruleTemplates`): `jira.issue.field.changed`,
  `jira.issue.event.trigger:transitioned`, `jira.jql.scheduled`,
  `jira.issue.event.trigger:created`, `jira.manual.trigger.issue`.
- **`jira.issue.comment`** is a confirmed action type.
- **Component value schemas are NOT obtainable over the API** — no descriptor endpoint
  exists, and the create endpoint's error channel is too noisy to walk. They live in the
  UI bundle.
- The new **Flows builder cannot be driven by the automation tooling** (it never idles).

### The unblock — 2 minutes of human clicking, then fully scripted

1. In the UI, build **one** rule that uses the components the seven need — e.g. trigger
   *Issue transitioned* → action *Edit issue field* + *Add comment* — and save it.
2. Then it can be read back over the proven internal endpoint:
   `GET /gateway/api/automation/internal-api/jira/{cloudId}/pro/rest/10034/rule/{id}`
   which returns the canonical `ruleConfigBean` with real `value` schemas.
3. With one real example per component, the six recipe files below become real create
   payloads and are POSTed **disabled** (so they never rewrite the 420 seeded tickets),
   then enabled deliberately at go-live.

The `rule-N-*.json` files remain **specifications**, not verified exports, until step 1 is done.
