"""Analysis pass: finds the longest dependency chain (by node count) — the
path nothing on it can start earlier than, regardless of how much
parallelism exists elsewhere in the graph. Standard longest-path-in-a-DAG,
computed bottom-up with memoization: depth(node) = 1 + max(depth(dep) for dep
in node.depends_on).

Correctly ignores shorter redundant edges on its own: if a node has both a
direct dependency and a longer transitive one to the same ancestor, max()
already picks the longer route — so this gives the same answer whether or
not DependencySimplificationPass ran first (see test_critical_path.py).

ponytail: not wired into BatchPlanner yet — there's no concurrency-bounded
executor for a critical-path-aware schedule to actually help. epc.dag's plain
topological batching is already optimal when nothing limits how many nodes a
batch can run in parallel. Wire this in when a bounded worker pool
(architecture doc §05) makes *order within* a batch matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from ..errors import CycleError
from ..ir import IRGraph
from .analysis import AnalysisPass, AnalysisResult


@dataclass
class CriticalPathResult(AnalysisResult):
    length: int
    path: list[str] = field(default_factory=list)


class CriticalPathPass(AnalysisPass):
    name: ClassVar[str] = "critical-path"

    def run(self, graph: IRGraph) -> CriticalPathResult:
        if not graph.nodes:
            return CriticalPathResult(length=0, path=[])

        depth = self._depths(graph)
        end = max(depth, key=depth.get)
        return CriticalPathResult(length=depth[end], path=self._reconstruct(graph, depth, end))

    @staticmethod
    def _depths(graph: IRGraph) -> dict[str, int]:
        depth: dict[str, int] = {}
        visiting: set[str] = set()

        def compute(node_id: str) -> int:
            if node_id in depth:
                return depth[node_id]
            if node_id in visiting:
                raise CycleError([node_id])
            visiting.add(node_id)
            depth[node_id] = 1 + max((compute(dep) for dep in graph.nodes[node_id].depends_on), default=0)
            visiting.discard(node_id)
            return depth[node_id]

        for node_id in graph.nodes:
            compute(node_id)
        return depth

    @staticmethod
    def _reconstruct(graph: IRGraph, depth: dict[str, int], end: str) -> list[str]:
        path = [end]
        current = end
        while depth[current] > 1:
            current = next(dep for dep in graph.nodes[current].depends_on if depth[dep] == depth[current] - 1)
            path.append(current)
        path.reverse()
        return path
