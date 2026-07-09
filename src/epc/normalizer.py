"""Stages 3-5 — Normalize, Resolve References (architecture doc §03).

ponytail: Expand (macro/workload-type expansion, stage 4) and Policy (stage 6)
are identity passes for now — no workload-type macros or OPA integration exist
yet. Add Expand when a second workload shorthand (beyond explicit resource
lists) is needed; add Policy when a real policy engine is wired in.
"""

from __future__ import annotations

from .ast import PlatformSpecAST, Ref
from .ir import IRGraph, IRNode, node_class_for
from .symboltable import SymbolTable


def normalize(ast: PlatformSpecAST) -> IRGraph:
    symbols = SymbolTable(ast.spec_properties)
    for resource in ast.resources:
        symbols.register(resource)

    graph_nodes: dict[str, IRNode] = {}
    for resource in ast.resources:
        depends_on = set(resource.depends_on)
        for dep_id in resource.depends_on:
            symbols.resolve(resource.id, dep_id)  # raises UndefinedReferenceError if missing

        resolved_properties: dict = {}
        for key, value in resource.properties.items():
            if isinstance(value, Ref):
                resolved = symbols.resolve(resource.id, value.path)
                if not value.path.startswith("spec."):
                    depends_on.add(resolved)  # a property ref is an implicit dependency edge
                    resolved_properties[key] = f"${{{value.path}}}"  # placeholder until codegen has real outputs
                else:
                    resolved_properties[key] = resolved
            else:
                resolved_properties[key] = value

        node_cls = node_class_for(resource.capability)  # raises UnknownNodeKindError if not a known IR node kind
        graph_nodes[resource.id] = node_cls(
            id=resource.id,
            properties=resolved_properties,
            depends_on=depends_on,
        )

    for node in graph_nodes.values():
        for dep_id in node.depends_on:
            graph_nodes[dep_id].depended_on_by.add(node.id)

    return IRGraph(nodes=graph_nodes)
