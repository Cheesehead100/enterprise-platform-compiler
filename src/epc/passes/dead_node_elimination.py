"""Pass 2: removes nodes explicitly disabled via `properties.enabled: false` —
the same conditional-resource pattern as Terraform's `count = 0`. This is the
concrete, needed-today form of "dead node elimination": every other node in a
freshly-parsed spec is something the author asked to exist, so removing
anything else would be deleting requested infrastructure, not dead code.

Deliberately does *not* cascade: if a still-enabled node depends on something
this pass just removed, that's left as a dangling reference on purpose —
epc.passes.ValidationPass (run immediately after, see epc.passes.DEFAULT_PASSES)
catches it and reports exactly which node still needs the thing that got
disabled, rather than silently producing a broken graph.
"""

from __future__ import annotations

from typing import ClassVar

from ..ir import IRGraph
from .base import CompilerPass


class DeadNodeEliminationPass(CompilerPass):
    name: ClassVar[str] = "dead-node-elimination"

    def run(self, graph: IRGraph) -> IRGraph:
        disabled = [node_id for node_id, node in graph.nodes.items() if node.properties.get("enabled") is False]

        for node_id in disabled:
            node = graph.nodes.pop(node_id)
            for dep_id in node.depends_on:
                if dep_id in graph.nodes:
                    graph.nodes[dep_id].depended_on_by.discard(node_id)

        return graph
