"""Orchestrates stages 1-9 (architecture doc §03) against a ProviderRegistry.

Stops at `plan()` — stage 10 (Execution / apply) is out of scope for the
compiler-frontend-only phase (architecture doc §20 Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass

from .dag import topological_batches
from .errors import UnknownCapabilityError
from .ir import ResourceGraph
from .normalizer import normalize
from .parser import parse
from .provider import Plan, ProviderRegistry


@dataclass
class CompileResult:
    graph: ResourceGraph
    batches: list[list[str]]
    plans: dict[str, Plan]


def compile_spec(spec_yaml: str, registry: ProviderRegistry) -> CompileResult:
    ast = parse(spec_yaml)
    graph = normalize(ast)
    batches = topological_batches(graph)
    graph.compute_hashes([node_id for batch in batches for node_id in batch])

    plans: dict[str, Plan] = {}
    for batch in batches:
        for node_id in batch:
            node = graph.nodes[node_id]
            provider = registry.resolve(node.capability)
            if provider is None:
                raise UnknownCapabilityError(node_id, node.capability)
            validation = provider.validate(node)
            if not validation.ok:
                raise ValueError(f"{node_id}: {'; '.join(validation.errors)}")
            plans[node_id] = provider.plan(node)

    return CompileResult(graph=graph, batches=batches, plans=plans)
