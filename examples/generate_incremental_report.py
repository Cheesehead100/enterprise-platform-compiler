"""Real incremental-compilation numbers -- compiles incremental_before.yaml,
then incremental_after.yaml against the same manifest file, through the
actual pipeline (epc.pipeline.compile_spec), and reports what the compiler
decided: what it recompiled, what it reused, and why. Not a cache-hit-rate
metric -- the compiler's own reasoning about a real change.

    python examples/generate_incremental_report.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "providers"))

from epc.pipeline import compile_spec  # noqa: E402
from epc.provider import ProviderRegistry  # noqa: E402
from fake.provider import FakeProvider  # noqa: E402

FIXTURES = _ROOT / "tests" / "fixtures"


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("network", "storage", "secret", "compute", "governance"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def main() -> None:
    before_yaml = (FIXTURES / "incremental_before.yaml").read_text()
    after_yaml = (FIXTURES / "incremental_after.yaml").read_text()

    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = str(Path(tmp) / "manifest.json")
        before = compile_spec(before_yaml, _registry(), manifest_path=manifest_path)
        after = compile_spec(after_yaml, _registry(), manifest_path=manifest_path)

    before_ids = set(before.graph.nodes)
    after_ids = set(after.graph.nodes)

    data = {
        "previous_graph_nodes": len(before_ids),
        "current_graph_nodes": len(after_ids),
        "input_changes": {
            "added": sorted(after_ids - before_ids),
            "removed": sorted(before_ids - after_ids),
        },
        "compiler_decision": {
            "recompiled": sorted(after.plans),
            "reused": sorted(after.skipped),
        },
        "provider_lowering": {
            "generated_plans": len(after.plans),
            "skipped_lowering": len(after.skipped),
        },
    }
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
