"""Produces the real numbers behind the "why EPC beats a naive execution
engine" demo -- run this, don't hand-write the numbers it prints. Uses
tests/fixtures/parallel_demo.yaml, the same fixture tests/test_parallel_demo.py
asserts against, so the demo and the regression test can't drift apart.

    python examples/generate_demo_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epc.normalizer import normalize  # noqa: E402
from epc.parser import parse  # noqa: E402
from epc.passes import (  # noqa: E402
    BatchPlanner,
    CriticalPathPass,
    DependencySimplificationPass,
    GraphStatisticsPass,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "parallel_demo.yaml"


def edge_list(graph) -> list[list[str]]:
    return sorted([dep, node_id] for node_id, node in graph.nodes.items() for dep in node.depends_on)


def main() -> None:
    spec_yaml = FIXTURE_PATH.read_text()

    before = normalize(parse(spec_yaml))
    after = DependencySimplificationPass().run(normalize(parse(spec_yaml)))

    before_edges = edge_list(before)
    after_edges = edge_list(after)
    removed_edges = [e for e in before_edges if e not in after_edges]

    plan = BatchPlanner().plan(before)
    batches = [b.node_ids for b in plan.batches]

    critical_path = CriticalPathPass().run(before)
    stats = GraphStatisticsPass().run(before)

    naive_steps = len(before.nodes)
    batched_steps = len(batches)

    data = {
        "nodes": sorted(before.nodes),
        "edges_before": before_edges,
        "edges_after": after_edges,
        "edges_removed": removed_edges,
        "batches": batches,
        "naive_sequential_steps": naive_steps,
        "batched_steps": batched_steps,
        # naive_steps / batched_steps: how many fewer sequential scheduling
        # steps batching produces here. Not a wall-clock speedup claim --
        # actual provisioning time also depends on provider/API latency,
        # which this number says nothing about.
        "parallelism_factor": round(naive_steps / batched_steps, 2),
        "critical_path": {"length": critical_path.length, "path": critical_path.path},
        "graph_statistics": {
            "node_count": stats.node_count,
            "edge_count": stats.edge_count,
            "max_fan_in": stats.max_fan_in,
            "max_fan_out": stats.max_fan_out,
            "nodes_by_kind": stats.nodes_by_kind,
        },
    }
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
