"""Minimal CLI so the pipeline can be run by hand, not just by pytest.

ponytail: registers a FakeProvider for every capability found in the spec —
real provider selection via a `providers:` config block (architecture doc §15)
is Phase 1, once a real provider exists to select.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parser import parse
from .pipeline import compile_spec
from .provider import ProviderRegistry


def _fake_registry(spec_yaml: str) -> ProviderRegistry:
    # providers/ lives alongside src/, not under it — not an installed
    # dependency of epc itself, so it isn't on sys.path by default.
    providers_dir = Path(__file__).resolve().parents[2] / "providers"
    if str(providers_dir) not in sys.path:
        sys.path.insert(0, str(providers_dir))
    from fake.provider import FakeProvider

    ast = parse(spec_yaml)
    registry = ProviderRegistry()
    for capability in {r.capability for r in ast.resources}:
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def main(argv: list[str] | None = None) -> int:
    parser_ = argparse.ArgumentParser(prog="epc")
    sub = parser_.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile", help="compile a PlatformSpec and print its DAG + plans")
    compile_cmd.add_argument("spec_file")
    compile_cmd.add_argument("--manifest", help="path to an incremental-compilation manifest file")

    args = parser_.parse_args(argv)
    spec_yaml = Path(args.spec_file).read_text()
    registry = _fake_registry(spec_yaml)

    result = compile_spec(spec_yaml, registry, manifest_path=args.manifest)

    for i, batch in enumerate(result.batches, start=1):
        print(f"batch {i}: {batch}")
    if result.skipped:
        print(f"skipped (unchanged): {sorted(result.skipped)}")
    for node_id, plan in result.plans.items():
        print(f"  {node_id} -> {plan.provider}: {json.dumps(plan.diff)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
