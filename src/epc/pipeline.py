"""Orchestrates stages 1-9 (architecture doc §03) against a ProviderRegistry.

Stops at `plan()` — stage 10 (Execution / apply) is out of scope for the
compiler-frontend-only phase (architecture doc §20 Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dag import topological_batches
from .errors import UnknownCapabilityError
from .ir import IRGraph
from .normalizer import normalize
from .parser import parse
from .provider import Plan, ProviderRegistry
from .statestore import load_manifest, save_manifest


@dataclass
class CompileResult:
    graph: IRGraph
    batches: list[list[str]]
    plans: dict[str, Plan]
    skipped: set[str] = field(default_factory=set)


def compile_spec(spec_yaml: str, registry: ProviderRegistry, manifest_path: str | None = None) -> CompileResult:
    """If `manifest_path` is given, this is an incremental compile (architecture
    doc §02): a node whose hash matches the previous manifest is skipped
    entirely — no validate(), no plan() call. A node's hash already includes
    its resolved dependencies' hashes (see IRGraph.compute_hashes), so
    comparing top-level hashes is sufficient to catch "this node or anything
    upstream of it changed" without any separate dependent-propagation step.
    """
    ast = parse(spec_yaml)
    graph = normalize(ast)
    batches = topological_batches(graph)
    graph.compute_hashes([node_id for batch in batches for node_id in batch])

    previous_manifest = load_manifest(manifest_path) if manifest_path else {}

    plans: dict[str, Plan] = {}
    skipped: set[str] = set()
    for batch in batches:
        for node_id in batch:
            node = graph.nodes[node_id]
            if manifest_path and previous_manifest.get(node_id) == node.hash:
                skipped.add(node_id)
                continue
            provider = registry.resolve(node.capability)
            if provider is None:
                raise UnknownCapabilityError(node_id, node.capability)
            validation = provider.validate(node)
            if not validation.ok:
                raise ValueError(f"{node_id}: {'; '.join(validation.errors)}")
            plans[node_id] = provider.plan(node)

    if manifest_path:
        save_manifest(manifest_path, {node_id: node.hash for node_id, node in graph.nodes.items()})

    return CompileResult(graph=graph, batches=batches, plans=plans, skipped=skipped)
