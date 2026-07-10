"""Distinct from tests/test_rename_semantics.py's rename case: there, the
new dependency was brand new (caught via caused_by's is_new branch). Here,
`database.primary` and `database.replica` BOTH already exist, unchanged,
before and after -- swapping which one `app` depends on can only be caught
via the added_dependencies/removed_dependencies set-difference path, since
neither endpoint's own hash changes. Confirms the graph-identity fix
(hashing (dep_id, dep_hash) pairs) generalizes to "swap between two
coexisting, identically-shaped resources," not just "rename to a new one."
"""

from epc.explain import explain_recompile, previous_state_from_graph
from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

BEFORE = """
metadata: {name: swap-example}
spec:
  resources:
    - capability: compute
      name: primary
      properties: {tier: Standard}
    - capability: compute
      name: replica
      properties: {tier: Standard}
    - capability: compute
      name: app
      dependsOn: ["compute.primary"]
"""

AFTER = BEFORE.replace('dependsOn: ["compute.primary"]', 'dependsOn: ["compute.replica"]')


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("compute", FakeProvider(name="fake-compute"))
    return registry


def test_primary_and_replica_are_hash_identical_in_isolation():
    """Precondition for the test below to mean anything -- if they didn't
    collide, the pipeline would trivially get this right for the wrong
    reason (a real property difference), not because graph identity works."""
    before = compile_spec(BEFORE, _registry())
    assert before.graph.nodes["compute.primary"].hash == before.graph.nodes["compute.replica"].hash


def test_pipeline_recompiles_app_when_swapped_to_an_equal_shaped_sibling(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    assert "compute.app" in after.plans
    assert "compute.app" not in after.skipped
    # primary/replica themselves are untouched by the swap -- only app's wiring changed
    assert "compute.primary" in after.skipped or "compute.primary" not in after.graph.nodes
    assert "compute.replica" in after.skipped


def test_explanation_names_the_swap_via_added_removed_not_caused_by(tmp_path):
    """Neither primary nor replica's own hash changes, so this must be
    caught by the set-difference path, not the per-dependency hash walk --
    a different code path than the rename case."""
    manifest = str(tmp_path / "manifest.json")
    before = compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    reason = explain_recompile(previous_state_from_graph(before.graph), after.graph, "compute.app")
    assert reason.recompiled is True
    assert reason.added_dependencies == ["compute.replica"]
    assert reason.removed_dependencies == ["compute.primary"]
    assert reason.caused_by == []  # neither endpoint's own hash changed
