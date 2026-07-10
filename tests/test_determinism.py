"""Two invariants the "no compiler decision without an explanation that
agrees with it" contract (README) depends on:

- compiling the same spec twice, cold, must produce byte-identical manifests
  and identical plans -- otherwise "why did it decide X" has no stable
  answer to give
- a true no-op recompile (identical spec, existing manifest) must mark
  every node reused, and --explain on every one of them must agree with
  that, not just some of them
"""

import json

from epc.cli import main
from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

FIXTURE = open("tests/fixtures/parallel_demo.yaml").read()


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("network", "storage", "secret", "compute", "governance"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def test_two_cold_compiles_produce_byte_identical_manifests(tmp_path):
    manifest_a = tmp_path / "a.json"
    manifest_b = tmp_path / "b.json"
    compile_spec(FIXTURE, _registry(), manifest_path=str(manifest_a))
    compile_spec(FIXTURE, _registry(), manifest_path=str(manifest_b))

    assert manifest_a.read_text() == manifest_b.read_text()
    # sanity: not comparing two empty files
    assert json.loads(manifest_a.read_text())


def test_two_cold_compiles_produce_identical_plans():
    result_a = compile_spec(FIXTURE, _registry())
    result_b = compile_spec(FIXTURE, _registry())

    assert {n: p.diff for n, p in result_a.plans.items()} == {n: p.diff for n, p in result_b.plans.items()}
    assert set(result_a.plans) == set(result_b.plans)


def test_every_node_in_a_true_no_op_recompile_is_consistently_reused(tmp_path, capsys):
    """Compile once, then again with nothing changed -- the top-level
    'skipped (unchanged)' list and --explain's per-node verdict must agree
    for every single node, not just the one this feature was built around."""
    manifest = str(tmp_path / "manifest.json")
    main(["compile", "tests/fixtures/parallel_demo.yaml", "--manifest", manifest])
    capsys.readouterr()

    main(["compile", "tests/fixtures/parallel_demo.yaml", "--manifest", manifest])
    out = capsys.readouterr().out
    skipped_line = next(line for line in out.splitlines() if line.startswith("skipped (unchanged):"))
    all_node_ids = ["network.vpc", "storage.bucket1", "storage.bucket2", "secret.dbPassword", "compute.appServer", "governance.catalog"]
    assert all(node_id in skipped_line for node_id in all_node_ids)

    for node_id in all_node_ids:
        main(["compile", "tests/fixtures/parallel_demo.yaml", "--manifest", manifest, "--explain", node_id])
        explain_out = capsys.readouterr().out
        assert "Decision\n  REUSED" in explain_out, f"{node_id} disagreed with the top-level skipped list"
