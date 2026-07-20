# Architecture

Five packages. The split exists so the **application** can outlive the **vendor**, and so
demo data can never reach production. If you are adding a file, §4 tells you where it goes.

## 1. The layers

| Package | What it is | Runs |
|---|---|---|
| `shared/` | The tower model, the Jira HTTP client, runtime field resolution. Imports **stdlib only**. | always |
| `jira_config/` | Infrastructure as code. Creates and reconciles projects, fields, workflows, filters, dashboards. | on change |
| `fixtures/` | Demo and test data. Generates tickets and drives them through transitions. | never in production |
| `app/` | The product — SLA engine and metrics. Stateless, read-mostly. | continuously |
| `tools/` | Repo hygiene. Not part of the system. | pre-commit |

Dependency direction is one-way and enforced by review:

```
tools/                     (stdlib only, imports nothing here)

app/  ──►  shared/         ◄── never the reverse
fixtures/  ──►  shared/, jira_config/
jira_config/  ──►  shared/
```

`shared/` imports nobody. `app/` imports `shared/` and nothing else.

## 2. The rule that matters

> **`app/` never imports `jira_config` and never reads build state.**

`app/` resolves custom-field ids **by name at runtime** through `shared/fields.py`, which
queries `/rest/api/3/field`. It does not read `jira_config/state/.build_state.json`.

This is not tidiness. It is what makes the metrics and SLA engine run against *any*
instance built to this design — including one built by hand in the UI, or by someone
else's automation, or a customer's existing project. Proven, not asserted: copy `app/` and
`shared/` into an empty directory where `jira_config/` does not exist on disk, and
`python3 -m app.cli sla --project OPS --dry-run` still returns the same 420 issues and
78.9% attainment (CLAIMS #65).

The corollary is that `jira_config/state/` is **write-only from the rest of the repo's
point of view**: `jira_config` writes it, `fixtures` reads it (it needs field ids to seed
with), and `app` must never touch it.

"Vendor-neutral" applies per module, not per package:

- **`shared/domain.py` is genuinely neutral** — towers, priority matrix, SLA targets and
  calendars, status lifecycles, field *names*. No Jira string appears in it. This is the
  module the rule is about, and the only one `app/` needs.
- **`shared/jira_client.py` and `shared/fields.py` are the Jira adapter.** They speak the
  wire format by definition. `fields.py` has to know custom-field type keys to break ties
  when two fields share a name — which is real on this instance, where `Urgency` exists
  twice.

So `jira_config/jira_schema.py` importing those type keys *from* `fields.py` is the
intended direction, not drift. One definition, so the duplicate-name tie-break cannot
silently disagree with what the builder creates.

## 3. Why the seams are where they are

**`fixtures/` is separate from `jira_config/` because they have different lifetimes.**
Config is declarative and idempotent — re-running it converges. Fixtures are generative and
destructive; `fixtures/reset.py` deletes every issue in the project. Putting them in one
package makes "run the build" ambiguous at exactly the moment you cannot afford ambiguity.

**`app/` is separate from `jira_config/` because they have different audiences.** Config is
run by whoever owns the instance, occasionally. The app is what the tower's manager looks
at, constantly. Coupling them means the reporting layer inherits the build layer's
assumptions — which is precisely how the SLA engine came to read a build artifact and stop
working anywhere else.

**`shared/domain.py` is separate from `jira_config/jira_schema.py` because one is the
design and the other is this instance's encoding of it.** Changing the towers is an edit to
`domain.py`. Changing how towers map onto a Jira select field is an edit to `jira_schema.py`.
Those change for different reasons, at different rates, and a port to another tracker keeps
the first and discards the second.

## 4. Where a new file goes

Ask in order; take the first yes.

1. **Does it create or reconcile something on the instance?** → `jira_config/`
   Give it `--dry-run` routed through `reconcile.Writer`, and make it idempotent. Every
   module here must be safe to re-run.
2. **Does it generate or destroy tickets?** → `fixtures/`
   It must be obvious from the package name that this never runs against real data.
3. **Does it read tickets and compute something a human reads?** → `app/`
   It may not import `jira_config` and may not read state. Resolve fields by name.
4. **Is it a fact about the tower that holds regardless of tracker?** → `shared/domain.py`
5. **Is it a Jira-specific id, key or wire constant?** → `jira_config/jira_schema.py`
   Exception: things `shared/fields.py` needs to do its job live in `fields.py`.
6. **Is it about the repo rather than the system?** → `tools/` (no `__init__.py`)

If the honest answer is "two of these", the file is doing two jobs. Split it.

## 5. Running things

Everything is a module. There are no `sys.path` hacks and no scripts to execute by path.

```bash
python3 -m jira_config.apply --dry-run     # rehearse the whole build
python3 -m app.cli metrics --project OPS   # the six scoreboard metrics
python3 -m app.cli sla --project OPS --dry-run
python3 tools/check_consistency.py         # before every commit
```

`--project` is **required** on `app.cli`. That is deliberate: it is the flag that lets the
same binary report on `OPS` and `ITSM` without either project's identity being compiled in.
