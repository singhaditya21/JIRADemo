# L1/L2 Support Tower on Jira

Design and build approach for an L1/L2 IT support tower ticket management system on Jira Service Management, plus the demo materials that present it.

## Contents

| File | What it is |
|---|---|
| [PROBLEM.md](PROBLEM.md) | **Start here.** Why these towers degrade — ten symptoms, five structural root causes, why the problem survives years of effort, and what "solved" means. |
| [PLAN.md](PLAN.md) | Full technical design — field schema, status model, escalation gate and major-incident fast path, SLA targets, priority matrix, permissions, build phases. |
| [demo.html](demo.html) | The presentation page. Sections tagged `CORE` (~10 min spine) or `DEEP DIVE`. Self-contained; works offline. |
| `L1-L2-Tower-Demo.pptx` | 18-slide deck — 10-slide core spine plus appendix A-1 to A-8. |
| [BRIEF.md](BRIEF.md) | One-page written brief, for reading ahead. |
| [LIVEDEMO.md](LIVEDEMO.md) | How to build a live, clickable demo: what is scriptable, seed-data strategy, run sheet, fallbacks. |
| [CLAIMS.md](CLAIMS.md) | **Every factual assertion with its verification status.** Nothing enters a deliverable without a row here. |
| `scripts/check_consistency.py` | Guards against retracted claims drifting back in. Run before every commit. |

## Working rules

Four artifacts state one argument, so corrections drift. Two mechanisms prevent it:

1. **[CLAIMS.md](CLAIMS.md) is the source of truth for facts.** Claims are `VERIFIED`, `UNVERIFIED`, `PLACEHOLDER` or `RETRACTED`. A claim not in the register does not belong in a deliverable.
2. **`python3 scripts/check_consistency.py` before committing.** It scans all six documents *and the deck* for retracted claims and for claims missing their required caveat.

Both exist because a claim was once asserted in four places before being checked, and shipped wrong — recorded as R1 in the register.

## The design in three lines

**Tier is a workflow state. Tower is a field. It is one project.** Escalation is a transition that flips `Support Tier` and reassigns — same ticket key, same continuous SLA clock, one audit trail. Splitting L1 and L2 into separate projects breaks all three, which is why ping-pong stays invisible and L1's contribution can't be measured.

The mechanism that makes it work is a **workflow validator** on `In Progress L1 → Escalated to L2` requiring Escalation Reason, Troubleshooting Performed and KB Article Checked. It enforces in configuration what policy cannot, and generates the escalation-rate-per-analyst data that tells you whether L1 is functioning.

The gate is **not** universal: a second transition, `Escalate — major incident`, carries no validators and is restricted to the Major Incident Manager role, because gating a P1 trades outage minutes for paperwork. A validator on `Resolved → Closed` requires the same three fields on every ticket, so majors pay the gate on the way out rather than skipping it.

**There is deliberately no ROI model.** Every cost input would be invented. The pilot measures a real baseline in two weeks; anything before that is decoration.

## Instance state as of 2026-07-20

Verified against `singhaditya21.atlassian.net`:

- Only `jira-software` is licensed. **Jira Service Management is not provisioned** — `/rest/servicedeskapi/*` returns 403, so SLAs, queues, request types, approvals and the customer portal are unavailable. Provisioning JSM (free tier: 3 agents, full SLA engine) is the first blocker.
- Structural config *is* REST-scriptable (fields, screens, statuses, workflows, schemes, permissions all return 200).
- Automation rules are **not** — no public Cloud REST API. Version-controlled via Automation's JSON export/import instead.

## Credentials

No credentials in this repo. Scripts read `JIRA_SITE`, `JIRA_EMAIL` and `JIRA_TOKEN` from the environment. `.claude/settings.local.json` is gitignored because Claude Code can record command history there, including tokens.
