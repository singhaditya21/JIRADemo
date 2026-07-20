# L1/L2 Support Tower on Jira

Design and build approach for an L1/L2 IT support tower ticket management system on Jira Service Management, plus the demo materials that present it.

## Contents

| File | What it is |
|---|---|
| [demo.html](demo.html) | The presentation page — the design, scoreboard and delivery plan. Sections tagged `CORE` (~10 min spine) or `DEEP DIVE` (optional depth). Self-contained; works offline. |
| [BRIEF.md](BRIEF.md) | One-page written brief. The same argument in prose, for reading ahead. |
| [PLAN.md](PLAN.md) | Full technical design — field schema, status model, SLA targets, priority matrix, permission scheme, automation rules, build phases. |
| [LIVEDEMO.md](LIVEDEMO.md) | How to build a live, clickable demo: what is scriptable, seed-data strategy, run sheet, fallbacks. |

## The design in three lines

**Tier is a workflow state. Tower is a field. It is one project.** Escalation is a transition that flips `Support Tier` and reassigns — same ticket key, same continuous SLA clock, one audit trail. Splitting L1 and L2 into separate projects breaks all three, which is why ping-pong stays invisible and L1's contribution can't be measured.

The mechanism that makes it work is a **workflow validator** on `In Progress L1 → Escalated to L2` requiring Escalation Reason, Troubleshooting Performed and KB Article Checked. It enforces in configuration what policy cannot, and generates the escalation-rate-per-analyst data that tells you whether L1 is functioning.

## Instance state as of 2026-07-20

Verified against `singhaditya21.atlassian.net`:

- Only `jira-software` is licensed. **Jira Service Management is not provisioned** — `/rest/servicedeskapi/*` returns 403, so SLAs, queues, request types, approvals and the customer portal are unavailable. Provisioning JSM (free tier: 3 agents, full SLA engine) is the first blocker.
- Structural config *is* REST-scriptable (fields, screens, statuses, workflows, schemes, permissions all return 200).
- Automation rules are **not** — no public Cloud REST API. Version-controlled via Automation's JSON export/import instead.

## Credentials

No credentials in this repo. Scripts read `JIRA_SITE`, `JIRA_EMAIL` and `JIRA_TOKEN` from the environment. `.claude/settings.local.json` is gitignored because Claude Code can record command history there, including tokens.
