"""Structural validation of an already-built IRGraph — independent of the
compiler frontend that produced it. epc.normalizer catches undefined
references while building the graph (compile-time, via the symbol table);
this exists for IR that arrives from somewhere else entirely — deserialized
from disk, received over the architecture doc §04 adapter API — and needs
its own structural check before anything trusts it.
"""

from __future__ import annotations

from .graph import IRGraph


def validate_graph(graph: IRGraph) -> list[str]:
    errors: list[str] = []

    for node_id, node in graph.nodes.items():
        for dep_id in node.depends_on:
            if dep_id not in graph.nodes:
                errors.append(f"{node_id}: dangling dependency '{dep_id}'")

        for dependent_id in node.depended_on_by:
            if dependent_id not in graph.nodes:
                errors.append(f"{node_id}: dangling dependent '{dependent_id}'")
            elif node_id not in graph.nodes[dependent_id].depends_on:
                errors.append(f"{node_id}: depended_on_by/depends_on out of sync with '{dependent_id}'")

    return errors
