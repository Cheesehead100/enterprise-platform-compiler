"""Orchestrates the full pipeline (architecture doc §03) against a
ProviderRegistry: parse -> normalize -> optimization passes -> [analysis
passes] -> batch planning -> incremental diff -> provider lowering.

Stops at `plan()` — stage 10 (Execution / apply) is out of scope for the
compiler-frontend-only phase (architecture doc §20 Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ir import IRGraph
from .normalizer import normalize
from .parser import parse
from .passes import DEFAULT_PASSES, AnalysisPass, AnalysisResult, BatchPlanner, PassManager, ProviderLowering
from .provider import Plan, ProviderRegistry
from .statestore import load_manifest, save_manifest


@dataclass
class CompileResult:
    graph: IRGraph
    batches: list[list[str]]
    plans: dict[str, Plan]
    skipped: set[str] = field(default_factory=set)
    analyses: dict[str, AnalysisResult] = field(default_factory=dict)


def compile_spec(
    spec_yaml: str,
    registry: ProviderRegistry,
    manifest_path: str | None = None,
    analyses: list[AnalysisPass] | None = None,
) -> CompileResult:
    """If `manifest_path` is given, this is an incremental compile (architecture
    doc §02): a node whose hash matches the previous manifest is skipped
    entirely — no validate(), no plan() call. A node's hash already includes
    its resolved dependencies' hashes (see IRGraph.compute_hashes), so
    comparing top-level hashes is sufficient to catch "this node or anything
    upstream of it changed" without any separate dependent-propagation step.

    `analyses`, if given, run after optimization and before batch planning —
    observe-only (epc.passes.AnalysisPass), never change what compiles. Not
    run by default: nothing downstream consumes an analysis result yet, so
    computing one unconditionally on every compile would be pure overhead
    for the common caller.
    """
    graph = normalize(parse(spec_yaml))
    graph = PassManager(DEFAULT_PASSES).run(graph)

    analysis_results = {a.name: a.run(graph) for a in (analyses or [])}

    execution_plan = BatchPlanner().plan(graph)
    graph.compute_hashes(execution_plan.ordered_node_ids)

    previous_manifest = load_manifest(manifest_path) if manifest_path else {}
    lowering = ProviderLowering().run(graph, execution_plan, registry, previous_manifest)

    if manifest_path:
        save_manifest(manifest_path, {node_id: node.hash for node_id, node in graph.nodes.items()})

    return CompileResult(
        graph=graph,
        batches=[batch.node_ids for batch in execution_plan.batches],
        plans=lowering.plans,
        skipped=lowering.skipped,
        analyses=analysis_results,
    )
