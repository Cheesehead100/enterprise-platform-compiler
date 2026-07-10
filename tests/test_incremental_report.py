"""Regression test for tests/fixtures/incremental_{before,after}.yaml -- the
same pair examples/generate_incremental_report.py compiles for the "What
Changed?" report. Backs the report's numbers with a real test, same pattern
as tests/test_parallel_demo.py.
"""

from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

BEFORE = open("tests/fixtures/incremental_before.yaml").read()
AFTER = open("tests/fixtures/incremental_after.yaml").read()


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("network", "storage", "secret", "compute", "governance"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def _compile_both(manifest_path: str):
    before = compile_spec(BEFORE, _registry(), manifest_path=manifest_path)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest_path)
    return before, after


def test_both_graphs_have_seven_nodes(tmp_path):
    before, after = _compile_both(str(tmp_path / "manifest.json"))
    assert len(before.graph.nodes) == 7
    assert len(after.graph.nodes) == 7


def test_archive_added_and_old_vnet_removed(tmp_path):
    before, after = _compile_both(str(tmp_path / "manifest.json"))
    added = set(after.graph.nodes) - set(before.graph.nodes)
    removed = set(before.graph.nodes) - set(after.graph.nodes)
    assert added == {"storage.archive"}
    assert removed == {"network.oldVnet"}


def test_changing_dbpassword_cascades_through_its_dependents_but_not_its_siblings(tmp_path):
    """The only edited property is dbPassword.rotation -- appServer and
    catalog recompile anyway because dbPassword's new hash propagates
    through them (IRGraph.compute_hashes), not because they were edited.
    bucket1/bucket2, which don't depend on dbPassword, are reused."""
    before, after = _compile_both(str(tmp_path / "manifest.json"))
    assert after.skipped == {"network.vpc", "storage.bucket1", "storage.bucket2"}
    assert set(after.plans) == {
        "secret.dbPassword",
        "compute.appServer",
        "governance.catalog",
        "storage.archive",
    }


def test_provider_lowering_counts_match_the_compiler_decision(tmp_path):
    _, after = _compile_both(str(tmp_path / "manifest.json"))
    assert len(after.plans) == 4
    assert len(after.skipped) == 3
