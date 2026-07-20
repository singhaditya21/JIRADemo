#!/usr/bin/env python3
"""Entry point for the application layer.

    python3 -m app.cli metrics --project OPS [--days 90] [--by-tower] [--json out.json]
    python3 -m app.cli sla     --project OPS [--dry-run] [--workers 4]

Both subcommands take --project, which may also come from the JIRA_PROJECT
environment variable. Neither knows what "OPS" is until you tell it - that is
what makes them runnable against a second instance.
"""

import argparse

from app import metrics, sla_engine


def build_parser():
    ap = argparse.ArgumentParser(prog="app.cli", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command")
    metrics.add_arguments(
        sub.add_parser("metrics", help="the six scoreboard metrics")
    ).set_defaults(_run=metrics.run)
    sla_engine.add_arguments(
        sub.add_parser("sla", help="recompute SLA state from the timeline")
    ).set_defaults(_run=sla_engine.run)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "_run", None):
        ap.print_help()
        raise SystemExit(2)
    args._run(args)


if __name__ == "__main__":
    main()
