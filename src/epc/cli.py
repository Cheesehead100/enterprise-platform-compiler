"""Minimal CLI so the pipeline can be run by hand, not just by pytest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import build_registry, load_provider_config
from .parser import parse
from .passes import CriticalPathPass, GraphStatisticsPass
from .pipeline import compile_spec

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

    args = parser_.parse_args(argv)
    spec_yaml = Path(args.spec_file).read_text()
    ast = parse(spec_yaml)
    capabilities = {r.capability for r in ast.resources}
    provider_config = load_provider_config(args.providers) if args.providers else {}
    registry = build_registry(provider_config, capabilities)

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
