#!/usr/bin/env python3
"""Fail if the published artifact carries the hosting organisation's identity.

The site is presented internally and is world-readable, so the deployed JSON and bundle must
not name whose Jira tenant or whose account is behind it. Two fields used to leak it into
every record: `url` (https://<tenant>.atlassian.net/browse/KEY) and the model's `site`.
`DEMO_ANONYMISE=1` strips both at bake time — this script is what proves it actually worked,
so the guarantee is a check that runs rather than something someone remembered to look at.

    python3 scripts/check_no_identity.py webapp/public/data webapp/dist
    IDENTIFIERS="acme,jdoe" python3 scripts/check_no_identity.py webapp/public/data

Identifiers default to the current host's; override with IDENTIFIERS (comma-separated) when
the demo moves. Matching is case-insensitive and substring-based, so `atlassian.net` catches
any tenant, not just the known one.

Exit 0 = clean, 1 = something identifying survived (with the file and a redacted excerpt).
"""

import os
import sys
from pathlib import Path

# Substrings that must not appear in a published artifact. `atlassian.net` is deliberately
# generic: it catches ANY tenant hostname, so a future re-point cannot silently reintroduce
# the leak under a different name.
DEFAULT_IDENTIFIERS = ["singhaditya21", "aditya", "atlassian.net"]

# Extensions worth scanning. Binary/lockfiles are skipped — they carry no tenant strings and
# only produce noise.
SCAN_EXT = {".json", ".js", ".css", ".html", ".map", ".txt", ".md"}
SKIP_NAMES = {"bun.lock", "package-lock.json"}
# Local-only directories: never shipped, and .claude/settings.local.json legitimately holds
# machine-local credentials (gitignored, never committed — verified). Scanning them produces
# findings that are real but irrelevant to what gets published.
SKIP_DIRS = {".git", ".claude", "node_modules", ".pytest_cache", "__pycache__"}


def identifiers():
    raw = os.environ.get("IDENTIFIERS")
    if raw:
        return [x.strip().lower() for x in raw.split(",") if x.strip()]
    return DEFAULT_IDENTIFIERS


def scan(paths, ids):
    hits = []
    for root in paths:
        p = Path(root)
        if not p.exists():
            print("  (skip, not present: %s)" % root)
            continue
        files = ([p] if p.is_file() else
                 [f for f in p.rglob("*")
                  if f.is_file() and not SKIP_DIRS & set(f.parts)])
        for f in files:
            if f.suffix.lower() not in SCAN_EXT or f.name in SKIP_NAMES:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            low = text.lower()
            for ident in ids:
                idx = low.find(ident)
                if idx != -1:
                    excerpt = text[max(0, idx - 40):idx + 60].replace("\n", " ")
                    hits.append((str(f), ident, excerpt))
    return hits


def main(argv):
    paths = argv[1:] or ["webapp/public/data"]
    ids = identifiers()
    print("scanning %s for: %s" % (", ".join(paths), ", ".join(ids)))
    hits = scan(paths, ids)
    if not hits:
        print("CLEAN — no identifying string found in the published artifact.")
        return 0
    print("\nFAIL — %d identifying string(s) survived into the artifact:\n" % len(hits))
    seen = set()
    for path, ident, excerpt in hits:
        key = (path, ident)
        if key in seen:          # one line per file+identifier, not per occurrence
            continue
        seen.add(key)
        print("  %s\n    matched %r near: …%s…\n" % (path, ident, excerpt))
    print("Set DEMO_ANONYMISE=1 on the bake, or add the string to IDENTIFIERS if it is "
          "genuinely not identifying.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
