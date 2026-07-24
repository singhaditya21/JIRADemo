#!/usr/bin/env python3
"""Fail if identifying content survives into something we publish.

The site is presented internally and is world-readable, and the repo behind it is public, so
neither may name whose Jira tenant or whose account is behind them. Two modes:

    python3 scripts/check_no_identity.py webapp/public/data webapp/dist   # artifact mode
    python3 scripts/check_no_identity.py --tracked                        # repo mode

Artifact mode scans the given paths — what CI is about to deploy. Repo mode scans every
git-TRACKED file, which is what a visitor to a public repo can actually read; it deliberately
ignores untracked and gitignored files, because a local un-anonymised bake sitting in
webapp/public/data is not published and flagging it is noise.

Two lessons are baked in, both learned the hard way:

  1. ARCHIVES. The first version scanned a fixed list of text extensions, so a tracked .pptx
     went unexamined for weeks — its title slide carried the real name and the real tenant and
     was downloadable unauthenticated. Office files are zip containers; this now opens them
     and scans the XML parts inside, naming the member that matched.

  2. NO IDENTIFIERS IN SOURCE. The first version hardcoded the owner's username and given name
     as a cleartext denylist, so the one file whose job was to stop the name being published
     was the only file at HEAD that published it. Identifiers are now DERIVED at runtime —
     from the git remote's owner and the names in git's own author metadata — or supplied via
     IDENTIFIERS. Nothing identifying is written down here.

    IDENTIFIERS="acme,jdoe" python3 scripts/check_no_identity.py webapp/public/data

Name matching is case-insensitive and substring-based. Tenant matching is a subdomain pattern,
so it catches ANY tenant rather than one known hostname, and a lone vendor domain in prose does
not trip it. Exit 0 = clean, 1 = something identifying survived.
"""

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

# A TENANT hostname identifies an organisation; the bare vendor domain identifies nobody. So
# this is a pattern, not a literal: `<tenant>.atlassian.net` reports, a lone `atlassian.net`
# (in prose, an assertion, or this file) does not. Written as a pattern for the second reason
# too — a literal example here would be the very leak the script exists to prevent.
TENANT_RE = re.compile(r"\b([a-z0-9][a-z0-9-]*)\.atlassian\.net", re.I)

# Tokens that turn up in author metadata but identify nobody.
NOISE = {"bot", "github", "actions", "none", "unknown", "root", "admin", "user", "runner"}

# Deliberate placeholder tenants — what the de-personalisation replaced the real host WITH.
# Flagging these would fail the build for doing the right thing. Any tenant NOT on this list
# reports, so the real one cannot hide here.
ALLOW_TENANTS = {"your-site", "your-tenant", "acme", "example", "tenant", "my-site", "demo"}

SCAN_EXT = {".json", ".js", ".jsx", ".css", ".html", ".map", ".txt", ".md", ".py", ".yml",
            ".yaml", ".svg", ".csv"}
# Office/OpenDocument files are zip containers. Scanning them as opaque bytes finds nothing —
# the text lives in compressed XML parts inside, so they have to be opened.
ARCHIVE_EXT = {".pptx", ".docx", ".xlsx", ".odp", ".odt", ".ods"}
SKIP_NAMES = {"bun.lock", "package-lock.json"}
# Local-only directories: never shipped, and .claude/settings.local.json legitimately holds
# machine-local credentials (gitignored, never committed — verified). Scanning them produces
# findings that are real but irrelevant to what gets published.
SKIP_DIRS = {".git", ".claude", "node_modules", ".pytest_cache", "__pycache__"}


def _run(*args):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _derived():
    """Identifiers inferred from the repo itself, so none are hardcoded here.

    Two sources: the owner segment of the git remote (the account that hosts the repo, and
    therefore the Pages subdomain), and the display names in git author metadata — which is
    where the real full name lives and is exactly what must not appear in published content."""
    found = set()

    remote = _run("git", "remote", "get-url", "origin").strip()
    if remote:                                    # git@host:OWNER/repo.git or https://host/OWNER/repo
        m = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?$", remote)
        if m:
            found.add(m.group(1))

    for name in set(_run("git", "log", "--format=%an").split("\n")):
        name = name.strip()
        if not name or "[bot]" in name:
            continue
        found.add(name)                           # the full display name, e.g. "Jane Roe"
        for tok in re.split(r"[^A-Za-z0-9]+", name):
            if len(tok) >= 4 and tok.lower() not in NOISE:
                found.add(tok)                    # and each part, to catch it inside a URL

    return {f.lower() for f in found if f.lower() not in NOISE}


def identifiers():
    raw = os.environ.get("IDENTIFIERS")
    if raw:
        return sorted({x.strip().lower() for x in raw.split(",") if x.strip()})
    return sorted(_derived())


def _archive_texts(path):
    """(member_name, text) for each part of an Office/OpenDocument file."""
    try:
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                try:
                    yield member, z.read(member).decode("utf-8", errors="ignore")
                except (OSError, zipfile.BadZipFile, RuntimeError):
                    continue
    except (OSError, zipfile.BadZipFile):
        return


def _texts(path):
    """(label, text) pairs to scan for one file. An archive yields one pair per member."""
    ext = path.suffix.lower()
    if ext in ARCHIVE_EXT:
        for member, text in _archive_texts(path):
            yield "%s :: %s" % (path, member), text
    elif ext in SCAN_EXT and path.name not in SKIP_NAMES:
        try:
            yield str(path), path.read_text(errors="ignore")
        except OSError:
            return


def tracked_files():
    out = _run("git", "ls-files", "-z")
    if not out:
        print("  (not a git repo, or no tracked files)")
        return []
    return [Path(p) for p in out.split("\0") if p and Path(p).is_file()]


def candidates(paths):
    for root in paths:
        p = Path(root)
        if not p.exists():
            print("  (skip, not present: %s)" % root)
            continue
        if p.is_file():
            yield p
            continue
        for f in p.rglob("*"):
            if f.is_file() and not SKIP_DIRS & set(f.parts):
                yield f


def _excerpt(text, idx, length):
    return text[max(0, idx - 40):idx + length + 20].replace("\n", " ")


def scan(files, ids):
    hits = []
    for f in files:
        if SKIP_DIRS & set(f.parts):
            continue
        for label, text in _texts(f):
            low = text.lower()

            for ident in ids:                    # derived names / owner login
                idx = low.find(ident)
                if idx != -1:
                    hits.append((label, ident, _excerpt(text, idx, len(ident))))

            for m in TENANT_RE.finditer(text):   # <tenant>.atlassian.net, placeholders aside
                if m.group(1).lower() in ALLOW_TENANTS:
                    continue
                hits.append((label, m.group(0), _excerpt(text, m.start(), len(m.group(0)))))
                break                            # one tenant hit per file is enough to fail
    return hits


def main(argv):
    args = argv[1:]
    repo_mode = "--tracked" in args
    paths = [a for a in args if not a.startswith("-")] or ["webapp/public/data"]
    ids = identifiers()
    if not ids:
        print("no identifiers to check for — set IDENTIFIERS or run inside a git repo")
        return 1

    files = tracked_files() if repo_mode else list(candidates(paths))
    where = "every git-tracked file" if repo_mode else ", ".join(paths)
    print("scanning %s for %d identifier(s), archives included" % (where, len(ids)))

    hits = scan(files, ids)
    if not hits:
        print("CLEAN — no identifying string found (%d file(s) examined)." % len(files))
        return 0

    print("\nFAIL — %d identifying string(s) survived:\n" % len(hits))
    seen = set()
    for label, ident, excerpt in hits:
        key = (label, ident)
        if key in seen:          # one line per file+identifier, not per occurrence
            continue
        seen.add(key)
        print("  %s\n    matched %r near: …%s…\n" % (label, ident, excerpt))
    print("Set DEMO_ANONYMISE=1 on the bake, scrub the file, or add the string to "
          "IDENTIFIERS if it is genuinely not identifying.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
