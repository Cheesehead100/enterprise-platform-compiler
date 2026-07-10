"""Minimal CLI so the pipeline can be run by hand, not just by pytest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import build_registry, load_provider_config
from .explain import explain_recompile, previous_state_from_manifest, render_trace
from .normalizer import normalize
from .parser import parse
from .passes import CriticalPathPass, GraphStatisticsPass
from .pipeline import CompileResult, compile_spec
from .provider import ProviderRegistry
from .statestore import load_manifest

# providers/ lives alongside src/, not under it — not an installed dependency
# of epc itself, so it isn't on sys.path by default.
_PROVIDERS_DIR = Path(__file__).resolve().parents[2] / "providers"
if str(_PROVIDERS_DIR) not in sys.path:
    sys.path.insert(0, str(_PROVIDERS_DIR))


def main(argv: list[str] | None = None) -> int:
    parser_ = argparse.ArgumentParser(prog="epc")
    sub = parser_.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile", help="compile a PlatformSpec and print its DAG + plans")
    compile_cmd.add_argument("spec_file")
    compile_cmd.add_argument("--manifest", help="path to an incremental-compilation manifest file")
    compile_cmd.add_argument(
        "--providers",
        help="path to a providers.yaml config (architecture doc §15); "
        "capabilities not listed default to the fake provider",
    )
    compile_cmd.add_argument(
        "--analyze",
        action="store_true",
        help="run analysis passes (graph statistics, critical path) and print their results",
    )
    compile_cmd.add_argument(
        "--explain",
        metavar="NODE_ID",
        help="print a compiler reasoning trace for one node -- why it recompiled or was reused. "
        "Needs --manifest from a previous run to compare against; without one, everything is new.",
    )

    args = parser_.parse_args(argv)
    spec_yaml = Path(args.spec_file).read_text()
    ast = parse(spec_yaml)
    capabilities = {r.capability for r in ast.resources}
    provider_config = load_provider_config(args.providers) if args.providers else {}
    registry = build_registry(provider_config, capabilities)

    # read before compile_spec overwrites it with this run's own state
    previous_manifest = load_manifest(args.manifest) if (args.explain and args.manifest) else {}

    analyses = [GraphStatisticsPass(), CriticalPathPass()] if args.analyze else None
    result = compile_spec(spec_yaml, registry, manifest_path=args.manifest, analyses=analyses)

    for i, batch in enumerate(result.batches, start=1):
        print(f"batch {i}: {batch}")
    if result.skipped:
        print(f"skipped (unchanged): {sorted(result.skipped)}")
    for node_id, plan in result.plans.items():
        print(f"  {node_id} -> {plan.provider}: {json.dumps(plan.diff)}")
    for name, analysis in result.analyses.items():
        print(f"analysis[{name}]: {analysis}")

    if args.explain:
        print()
        _print_reasoning_trace(args.explain, spec_yaml, result, registry, previous_manifest)

    return 0


def _print_reasoning_trace(
    node_id: str,
    spec_yaml: str,
    result: CompileResult,
    registry: ProviderRegistry,
    previous_manifest: dict,
) -> None:
    print("Compiler Reasoning Trace")
    print()
    print("Target")
    print(f"  {node_id}")
    print()

    if node_id not in result.graph.nodes:
        print("Decision")
        print("  not in the compiled graph -- removed by Dead Node Elimination, or never declared")
        return

    node = result.graph.nodes[node_id]
    recompiled = node_id in result.plans
    print("Decision")
    print(f"  {'RECOMPILED' if recompiled else 'REUSED'}")
    print()

    # what Dependency Simplification did to this node specifically: compare
    # its edges before any pass ran against its edges in the compiled graph
    raw_graph = normalize(parse(spec_yaml))
    dep_edges_changed = node_id in raw_graph.nodes and raw_graph.nodes[node_id].depends_on != node.depends_on

    previous_state = previous_state_from_manifest(previous_manifest)
    reason = explain_recompile(previous_state, result.graph, node_id)
    if reason.is_new:
        incremental_note = "new node, no previous compile to compare against"
    elif reason.own_properties_changed:
        incremental_note = "own properties changed"
    elif reason.caused_by:
        incremental_note = f"dependency hash changed ({', '.join(c.node_id for c in reason.caused_by)})"
    else:
        incremental_note = "unchanged"

    batch_index = next((i for i, batch in enumerate(result.batches, start=1) if node_id in batch), None)
    provider = registry.resolve(node.capability)

    print("Pipeline stages")
    print("  [ok] Validation                 graph is structurally valid")
    print(
        f"  [{'!' if dep_edges_changed else '='}]  Dependency Simplification  "
        f"{'a redundant edge was removed for this node' if dep_edges_changed else 'no edges changed for this node'}"
    )
    print(f"  [{'!' if recompiled else '='}]  Incremental Analysis       {incremental_note}")
    print(f"  [->] Batch Planning             assigned to batch {batch_index}")
    if recompiled:
        provider_name = provider.name if provider else "unknown"
        print(f"  [->] Provider Lowering          {provider_name} provider selected, plan generated")
    else:
        print("  [x]  Provider Lowering          skipped (reused from previous compile)")
    print()

    print("Causal trace")
    for line in render_trace(reason).splitlines():
        print(f"  {line}")


if __name__ == "__main__":
    sys.exit(main())
