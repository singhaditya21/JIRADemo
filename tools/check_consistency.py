#!/usr/bin/env python3
"""Guard against stale claims drifting back into the deliverables.

Four artifacts state the same argument, so a correction made in one can be silently
contradicted by another. That has already happened once: the scriptability claim was
fixed in PLAN.md and BRIEF.md while the deck still shipped the old version, because the
deck had been generated from BRIEF.md before the fix.

Run before every commit:  python3 tools/check_consistency.py
"""

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# CLAIMS.md is deliberately absent: it is the register itself, so it quotes
# retracted text verbatim and would false-positive on R1 and R2 forever.
DOCS = ["PROBLEM.md", "PLAN.md", "BRIEF.md", "LIVEDEMO.md", "README.md", "demo.html",
        "CONTROL-TOWER.md", "DEMO-TOMORROW.md",
        "PILOT.md", "ROLLOUT.md", "SCHEMA.md", "automation/README.md",
        "ARCHITECTURE.md"]
DECK = "L1-L2-Tower-Demo.pptx"

# Retracted claims. Any reappearance is a regression — see CLAIMS.md.
BANNED = [
    (r"phases?\s*2[-–—]6\s*are\s*(all\s*)?rest",
     "R1: 'Phases 2-6 are REST-scriptable' — false, automation rules have no Cloud REST API"),
    (r"queues and automation rules are all reachable",
     "R1: claims automation rules are reachable over REST"),
    (r"\$55,000|\$42,500|\$12,500 a month|about \$150(,000|k)",
     "R2: retracted ROI model — arithmetic contradicted the workflow (L1 cost omitted)"),
    (r"600\s*[x×]\s*\$75",
     "R2: retracted cost line — escalated tickets incur L1 cost too"),
]

# Claims that must appear wherever the related topic is discussed.
REQUIRED = [
    ("escalation gate", r"escalat\w* gate|escalate to l2",
     r"major incident|fast path|fast-path",
     "discusses the escalation gate but never mentions the P1 fast path"),
    ("scriptability", r"rest[- ]scriptable|rest api|rest-api",
     r"404|no public (cloud )?rest api|exported json|export/import",
     "claims REST scriptability without the automation-rules exception"),
]


def deck_text(path):
    """Extract slide text without requiring python-pptx."""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "ignore")
                out.extend(re.findall(r"<a:t>([^<]*)</a:t>", xml))
    return " ".join(out)


def main():
    sources = {}
    for d in DOCS:
        p = ROOT / d
        if p.exists():
            sources[d] = p.read_text(encoding="utf-8")
    deck = ROOT / DECK
    if deck.exists():
        sources[DECK] = deck_text(deck)

    failures = []

    for name, text in sources.items():
        low = text.lower()
        for pattern, why in BANNED:
            if re.search(pattern, low):
                failures.append(f"{name}: RETRACTED CLAIM PRESENT — {why}")
        for topic, trigger, needed, why in REQUIRED:
            if re.search(trigger, low) and not re.search(needed, low):
                failures.append(f"{name}: {why}")

    print(f"checked {len(sources)} artifacts: {', '.join(sources)}")
    if failures:
        print(f"\n{len(failures)} problem(s):\n")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nSee CLAIMS.md before changing any of these.")
        return 1
    print("\n✓ no retracted claims present; required caveats accompany every claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
