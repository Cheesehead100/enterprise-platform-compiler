"""Stand-in for the architecture doc's State Store (§05) — just enough to prove
incremental compilation (§02) actually skips unchanged work. A real State Store
(Postgres, per the doc) is Phase 1.

ponytail: single JSON file, no locking — fine for one compiler process at a
time. Swap for the real State Store when concurrent/multi-instance compiles
need it.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_manifest(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_manifest(path: str, manifest: dict[str, str]) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True))
