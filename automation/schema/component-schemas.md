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

### `jira.issue.field.changed`  ⚠️ partial
Top level round-trips as
`{"eventFilters":["<projectARI>"],"changeType":"ANY_CHANGE","fields":null,"actions":[]}`
but the **`fields`** item shape resolves server-side and 500s on every candidate tried
(`{"type":"NAME"|"ID","value":…}`, raw id, numeric id, `{"fieldId":…}`). `ANY_CHANGE`
with `fields:null` fires on *any* edit — usable, just not field-scoped. Field scoping
needs one UI capture.

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

### `jira.issue.outgoing.email`  ⚠️ partial
Top level round-trips as
`{"to":[],"cc":[],"bcc":[],"subject":"…","body":"…","mimeType":"text/html","convertLineBreaks":true}`
but the **`to`** recipient item shape resolves server-side and 500s on every candidate
tried (`{"type":"REPORTER"}`, `{"type":"FIELD","value":"reporter"}`, email strings, …).
Recipients need one UI capture.

### Other confirmed real action types (value shape not fully mapped)
- `jira.issue.assign` — `{"assignType":"SPECIFY_USER",…,"assignee":…}`

## Not yet mapped
- If / else block (branch/condition container) — needed for the 9-cell priority matrix.
- `jira.issue.field.changed` `fields[]`, `jira.issue.outgoing.email` `to[]` — server-resolved.
