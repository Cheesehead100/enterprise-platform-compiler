"""Pass 3: transitive reduction — drop a direct dependency edge (u -> v) when
v is already reachable from u through some other dependency. This never
changes scheduling: if u depends on both v and w, and w already depends on v
(transitively or directly), then u's earliest-ready batch is already gated by
w's batch, which is itself gated by v's -- the direct u -> v edge was
redundant for ordering purposes. It also never changes incremental-compilation
hashes: a change to v still changes w's hash, which still changes u's hash,
just through one fewer edge (see IRGraph.compute_hashes).

What it's for: a cleaner edge set going into serialization (epc.ir.v1.serializer)
and anything that renders the dependency graph later -- fewer redundant arrows
to look at, same actual ordering.
"""

from __future__ import annotations

from typing import ClassVar

from ..ir import IRGraph
from .base import CompilerPass


class DependencySimplificationPass(CompilerPass):
    name: ClassVar[str] = "dependency-simplification"

    def run(self, graph: IRGraph) -> IRGraph:
        for node in graph.nodes.values():
            redundant = {
                dep_id
                for dep_id in node.depends_on
                if any(self._reachable(graph, other, dep_id) for other in node.depends_on if other != dep_id)
            }
            for dep_id in redundant:
                node.depends_on.discard(dep_id)
                graph.nodes[dep_id].depended_on_by.discard(node.id)

        return graph

    @staticmethod
    def _reachable(graph: IRGraph, start: str, target: str) -> bool:
        stack = [start]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(graph.nodes[current].depends_on)
        return False
