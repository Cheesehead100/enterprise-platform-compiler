"""Real "why was this node recompiled?" traces -- compiles
incremental_before.yaml then incremental_after.yaml through the actual
pipeline (same pair examples/generate_incremental_report.py uses) and
explains the causal chain behind each recompile decision.

    python examples/generate_explain_report.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "providers"))

from epc.explain import explain_recompile, previous_state_from_graph, render_trace  # noqa: E402
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

    previous = previous_state_from_graph(before.graph)
    for node_id in ("secret.dbPassword", "compute.appServer", "governance.catalog", "storage.archive", "network.vpc"):
        print(f"Why was {node_id} recompiled?" if node_id in after.plans else f"Why was {node_id} reused?")
        reason = explain_recompile(previous, after.graph, node_id)
        print(render_trace(reason))
        print()


if __name__ == "__main__":
    main()
