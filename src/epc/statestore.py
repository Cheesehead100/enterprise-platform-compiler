"""Stand-in for the architecture doc's State Store (§05) — enough to prove
incremental compilation (§02) actually skips unchanged work, and enough for
epc.explain to reconstruct *why* a node's hash changed across two separate
CLI invocations. Manifest entries are `{node_id: {"hash": ..., "properties": ...}}`
— properties are stored alongside the hash specifically so a later compile
can tell "this node's own properties changed" apart from "a dependency's
hash changed," without needing the full previous IRGraph in memory.

ponytail: single JSON file, no locking — fine for one compiler process at a
time. Swap for the real State Store when concurrent/multi-instance compiles
need it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_manifest(path: str) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_manifest(path: str, manifest: dict[str, dict[str, Any]]) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True))
