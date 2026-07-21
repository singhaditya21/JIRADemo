"""Off-target alerting straight from the baked scoreboard — the tower telling an
operator it is breaching, without anyone opening the dashboard.

Every figure and verdict is already computed by app/analytics.py and frozen into the
baked ``{project}-{days}.json`` files (the same numbers the dashboard shows). This module
does NOT recompute anything and does NOT touch Jira — it reads those files and reports
every scoreboard KPI whose verdict is "GAP", worst-first by how far it misses.

It runs in CI right after the bake (see .github/workflows/pages.yml): the breaches are
written to the GitHub Actions job summary, so a scheduled run surfaces "Resolution SLA is
78.8% against a >=95% target" in the run's summary page — no browser, no token, no polling.

Deliberately warn-only by default: on this demo a GAP is the expected story, not a build
failure. Pass --fail-on-breach to make CI exit non-zero (for a real deployment that wants
a red build when the desk goes off-target).

Pure stdlib, reads only the public baked JSON — so it can run anywhere with zero secrets.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# Human labels for the scoreboard keys — must match the dashboard's KPI strip so CI and
# the UI say the same thing about the same number.
LABELS = {
    "ftr_pct": "First-time resolution",
    "escalation_pct": "Escalation rate",
    "reopen_pct": "Reopen rate",
    "sla_pct": "Resolution SLA",
    "response_pct": "Response SLA",
    "aged_14d": "Aged > 14 days",
}
# KPIs measured in points (%) vs. a raw count — governs how the gap is phrased.
PCT_KEYS = {"ftr_pct", "escalation_pct", "reopen_pct", "sla_pct", "response_pct"}


def _fmt_value(key, v):
    if v is None:
        return "—"
    return f"{v:.1f}%" if key in PCT_KEYS else f"{v:g}"


def evaluate(model):
    """Every GAP in a baked model, worst-first. Returns a list of breach dicts.

    Reuses the verdict already baked by app/analytics.py — no threshold logic is
    duplicated here, so CI can never disagree with the dashboard.
    """
    breaches = []
    for key, m in (model.get("scoreboard") or {}).items():
        if m.get("verdict") != "GAP":
            continue
        value, target = m.get("value"), m.get("target")
        direction = m.get("direction")
        gap = None if value is None or target is None else abs(value - target)
        breaches.append({
            "key": key,
            "label": LABELS.get(key, key),
            "value": value,
            "target": target,
            "direction": direction,
            "arrow": "≥" if direction == "ge" else "≤" if direction == "le" else "",
            "gap": gap,
            "unit": "%" if key in PCT_KEYS else "",
        })
    # Worst-first. Count-based gaps (aged) can't be compared to point gaps directly, so
    # rank percentage breaches by point-gap and push count breaches to the end.
    breaches.sort(key=lambda b: (b["key"] not in PCT_KEYS, -(b["gap"] or 0)))
    return breaches


def _breach_line(project, window_label, b):
    tail = ""
    if b["gap"] is not None and b["key"] in PCT_KEYS:
        tail = f" — {b['gap']:.1f} pts short"
    elif b["key"] == "aged_14d" and b["value"]:
        tail = f" — {int(b['value'])} tickets"
    return (f"**{project}** · {b['label']} is {_fmt_value(b['key'], b['value'])} "
            f"against a {b['arrow']}{b['target']}{b['unit']} target{tail} "
            f"_({window_label})_")


def summarize(reports):
    """Markdown summary for the GitHub Actions job summary. `reports` is a list of
    (project, window_label, [breaches], [warnings])."""
    total = sum(len(b) for _, _, b, _ in reports)
    out = ["## L1/L2 Control Tower — off-target alerts", ""]
    if total == 0:
        out.append("✅ Every scoreboard KPI is on target across all baked windows.")
    else:
        out.append(f"⚠️ {total} scoreboard KPI(s) breaching target:")
        out.append("")
        for project, window_label, breaches, _ in reports:
            for b in breaches:
                out.append(f"- {_breach_line(project, window_label, b)}")
    warned = [(p, w) for p, w, _, warns in reports for w2 in warns for w in [w2]]
    if warned:
        out.append("")
        out.append("<details><summary>Data warnings</summary>")
        out.append("")
        seen = set()
        for project, _, _, warns in reports:
            for w in warns:
                if w in seen:
                    continue
                seen.add(w)
                out.append(f"- **{project}**: {w}")
        out.append("")
        out.append("</details>")
    return "\n".join(out) + "\n"


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def collect(data_dir, days):
    """Read every ``{project}-{days}.json`` in `data_dir` and evaluate it."""
    reports = []
    for path in sorted(glob.glob(os.path.join(data_dir, f"*-{days}.json"))):
        model = _load(path)
        # skip anything that isn't a baked tower model (e.g. records files)
        if "scoreboard" not in model:
            continue
        project = model.get("project") or os.path.basename(path).split("-")[0]
        reports.append((project,
                        model.get("window_label", f"{days} days"),
                        evaluate(model),
                        model.get("warnings", []) or []))
    return reports


def main(argv=None):
    ap = argparse.ArgumentParser(description="Report off-target KPIs from the baked scoreboard.")
    ap.add_argument("--data-dir", default="webapp/public/data",
                    help="directory holding the baked {project}-{days}.json files")
    ap.add_argument("--days", type=int, default=90,
                    help="which window to alert on (default 90, the dashboard default)")
    ap.add_argument("--fail-on-breach", action="store_true",
                    help="exit non-zero if any KPI is breaching (default: warn only)")
    args = ap.parse_args(argv)

    reports = collect(args.data_dir, args.days)
    md = summarize(reports)
    print(md)

    # In GitHub Actions, also append to the run's job summary page.
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as fh:
            fh.write(md)

    total = sum(len(b) for _, _, b, _ in reports)
    if args.fail_on_breach and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
