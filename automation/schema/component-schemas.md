# Automation component schemas (discovered)

How these were obtained: there is **no** first-party component-metadata endpoint
(`pluggableComponents` returns only third-party connectors; `pagecontext` is empty; the
81 `ruleTemplates` name trigger *types* but carry no component *values*). The Flows
builder UI is the documented source, but it freezes the CDP-driven renderer on save, so
UI capture is unreliable.

What works instead: **empirical round-trip against the internal API.** POST a rule with a
candidate component `value`, `GET` it back, and read the *canonical stored shape* the
server normalises to — then `DELETE` the probe. A 400 names the required fields; a 500
means the shape was recognised but a value failed server-side resolution; an unknown key
is silently stripped (round-trips to `{}`/`null`). Every shape below was confirmed to
round-trip intact. See `probe` in the session scratch — the method is reproducible.

## Triggers

### `jira.issue.event.trigger:transitioned`  (had already)
```json
{"eventFilters":["<projectARI>"],"fromStatus":[{"type":"NAME","value":"…"}],
 "toStatus":[{"type":"NAME","value":"…"}],"eventKey":"jira:issue_updated","issueEvent":"issue_generic"}
```

### `jira.jql.scheduled`  ✅ verified
```json
{"schedule":{"cronExpression":"0 0 2 ? * *","method":null,"rate":0,"rateInterval":0,"rRule":null},
 "jql":"project = OPS AND …","executionMode":"jql","onlyUpdatedIssues":false}
```
- `schedule.cronExpression` (Quartz: sec min hour day-of-month month day-of-week) drives it.
  `rate`/`rateInterval` are the interval alternative; leave 0 when using cron.
- `executionMode:"jql"` + a `jql` runs the actions once per matching work item.

### `jira.issue.event.trigger:updated`  ✅ verified (enables)
```json
{"eventFilters":["<projectARI>"],"eventKey":"jira:issue_updated","issueEvent":"issue_generic"}
```
Fires on any edit to a work item. This is what the priority-derivation rule uses to
re-derive on Impact/Urgency changes, since `jira.issue.field.changed` (below) cannot be
enabled over the API.

### `jira.issue.field.changed`  🔴 cannot be enabled over the API
Round-trips *disabled* as
`{"eventFilters":["<projectARI>"],"changeType":"ANY_CHANGE","fields":null,"actions":[]}`,
but **ENABLED validation 500s on every variant** — field-scoped or not (`fields:null`
included). And the per-field `fields[]` item shape 500s on every candidate
(`{"type":"NAME"|"ID","value":…}`, raw id, numeric id, `{"fieldId":…}`) because it resolves
the field server-side. So this trigger is UI-only; the design's "field value changed on
Impact/Urgency" is served instead by the generic `…:updated` trigger above + value
conditions.

## Actions

### `jira.issue.edit`  (had already)
```json
{"operations":[{"field":{"type":"NAME","value":"Support Tier"},
   "fieldType":"com.atlassian.jira.plugin.system.customfieldtypes:select",
   "type":"SET","value":{"type":"NAME","value":"L2"}}],
 "advancedFields":null,"sendNotifications":false}
```

### `jira.issue.comment`  ✅ verified
```json
{"comment":"plain text","publicComment":false,"commentVisibility":null,
 "sendNotifications":true,"addCommentOnce":false}
```
`comment` is a **plain string** (ADF 500s). `addCommentOnce:true` de-dupes.

### `jira.issue.transition`  ✅ verified
```json
{"operations":[],"advancedFields":null,"sendNotifications":false,
 "destinationStatus":{"type":"NAME","value":"Closed"},"transitionMatch":null}
```
`destinationStatus` takes a `{"type":"NAME","value":…}` status ref; `operations` can carry
field edits performed during the transition (same shape as `jira.issue.edit`).

### `jira.issue.assign`  ✅ verified (enables)
```json
{"assignType":"SPECIFY_USER","smartValue":null,"itsmOpsOncall":null,"jql":null,
 "issueToCopy":null,"fieldToCopy":null,"listAssignMethod":null,
 "assignee":{"type":"ID","value":"<accountId>"},
 "restrictedToGroup":null,"group":null,"role":null}
```
`assignee` takes `{"type":"ID","value":"<accountId>"}` (a bare string or `type:"ACCOUNT_ID"`
both 500). Assigning fires Jira's own notification-scheme email to the new assignee — which
is how the major-incident rule "notifies" the MIM without the outgoing-email recipient shape.

### `jira.issue.outgoing.email`  🔴 recipient shape is UI-only
Top level round-trips as
`{"to":[],"cc":[],"bcc":[],"subject":"…","body":"…","mimeType":"text/html","convertLineBreaks":true}`
but the **`to`** recipient item resolves server-side and 500s on every candidate tried
(`{"type":"REPORTER"}`, `{"type":"FIELD","value":"reporter"}`, email strings, …). So the
major-incident rule uses `jira.issue.assign` (above) for its notification instead of email.

## Conditions and branching  ✅ verified
- `jira.condition.container.block` (component `CONDITION`, value `{}`) is an IF block: its
  `children` (conditions + actions) run only when its conditions match. Sibling blocks
  evaluate independently, so a list of them is a branch matrix (this is the 9-cell priority
  matrix).
- `jira.issue.condition` (field-value comparison):
  ```json
  {"selectedField":{"type":"NAME","value":"Impact"},
   "selectedFieldType":"<field-type-key>","comparison":"EQUALS",
   "compareValue":{"type":"NAME","value":"High"}}
  ```
  **Enable asymmetry:** a *select* custom field compares by `{"type":"NAME"}`, but the
  *system Priority* field compares by `{"type":"ID","value":"<priorityId>"}`.

## Still UI-only (server-resolved, 500 on every constructed value)
- `jira.issue.field.changed` — cannot be enabled at all over the API (see above); the
  `…:updated` trigger is the enable-able substitute.
- `jira.issue.outgoing.email` `to[]` recipients — `jira.issue.assign` is the substitute used.
