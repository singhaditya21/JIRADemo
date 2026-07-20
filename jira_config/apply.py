#!/usr/bin/env python3
"""Run the configurator end to end, in dependency order.

    python3 -m jira_config.apply [--only build] [--from priority] [--dry-run]

Every step is idempotent, so a full run against an already-built instance is the
normal case and should change nothing.

Deliberately NOT included:

  * fixtures.seed / fixtures.jsm_seed / fixtures.reset - those write issues. Demo
    data is not infrastructure, and reset.py deletes every issue in a project.
  * jsm_build / jsm_views - a separate project with its own guards and its own
    ordering. Running them by accident would write to the live ITSM project.

--dry-run is a real rehearsal of the whole pipeline: it is passed down to each
step, and every step routes its writes through jira_config.reconcile.Writer, so
the run logs the method and path of each write and issues none of them. It used
to only print the step list, which shared a name with the steps' genuine dry-run
flags and so read as a safety guarantee it did not provide. Use --list to get
the old behaviour of naming the steps without importing them.

One caveat worth stating plainly: a dry run reports what it would do against the
CURRENT instance. Later steps cannot see objects earlier steps only pretended to
create, so on a fresh instance the plan under-reports downstream work.
"""

import argparse

STEP_NAMES = ["build", "workflow", "issuetypes", "priority", "views"]


def load_steps():
    """Imported lazily so --dry-run and --help never touch the modules.

    jira_config.views still builds its FILTERS list at import time. That is
    network-free, so importing it is safe, but it is the reason this import sits
    inside a function rather than at module scope.
    """
    from jira_config import build, workflow, issuetypes, priority, views
    return {"build": build, "workflow": workflow, "issuetypes": issuetypes,
            "priority": priority, "views": views}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jira_config.apply")
    ap.add_argument("--only", action="append", choices=STEP_NAMES, default=None,
                    help="run just this step (repeatable)")
    ap.add_argument("--from", dest="start", choices=STEP_NAMES,
                    help="start at this step and run the rest")
    ap.add_argument("--dry-run", action="store_true",
                    help="run every step in rehearsal mode: log writes, issue none")
    ap.add_argument("--list", action="store_true", dest="list_only",
                    help="name the steps that would run, without importing them")
    args = ap.parse_args(argv)

    plan = list(STEP_NAMES)
    if args.start:
        plan = plan[STEP_NAMES.index(args.start):]
    if args.only:
        plan = [n for n in plan if n in set(args.only)]
    if not plan:
        raise SystemExit("nothing to run - --only and --from select no steps")

    if args.list_only:
        print("would run, in order:")
        for n in plan:
            print("  jira_config." + n)
        return

    step_argv = ["--dry-run"] if args.dry_run else []
    steps = load_steps()
    for n in plan:
        print("\n" + "=" * 60)
        print("== jira_config." + n + (" [DRY RUN]" if args.dry_run else ""))
        print("=" * 60)
        steps[n].main(step_argv)

    if args.dry_run:
        print("\nDRY RUN - no writes were applied.")


if __name__ == "__main__":
    main()
