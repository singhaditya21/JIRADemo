"""Infrastructure as code for the Jira instance.

Declarative and idempotent: every module here reads the live instance, diffs it
against the declared schema, and writes only the difference. Safe to re-run.

The build artifacts live in state/ and are written by this package only. The
application layer (app/) must never read them - it resolves what it needs from
the live instance at runtime.
"""

import json
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / "state"
BUILD_STATE = STATE_DIR / ".build_state.json"
JSM_STATE = STATE_DIR / ".jsm_state.json"
SFC_STATE = STATE_DIR / ".sfc_state.json"


def read_state(path):
    """Current state, or {} if the build has never run. Never raises on absence."""
    return json.loads(path.read_text()) if path.exists() else {}


def merge_state(path, values, keys, dry=False):
    """Write only `keys` from `values`, merged over what is on disk right now.

    Each step owns a named subset of the artifact. Round-tripping the whole dict
    lets a step rewrite keys it never computed from a stale in-memory copy — that
    is how workflow_created was seen flipping true -> false during an unrelated
    build. Re-reading immediately before the write keeps every step authoritative
    for its own keys and silent about everyone else's.

    A dry run writes nothing: a rehearsal that mutates the artifact is not one.
    """
    if dry:
        return False
    on_disk = read_state(path)
    for k in keys:
        if k in values:
            on_disk[k] = values[k]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(on_disk, indent=2))
    return True
