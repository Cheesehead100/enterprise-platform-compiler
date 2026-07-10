"""Transitive reasoning through a removed node, end to end through the real
pipeline: database -> service -> frontend. database is deleted; service's
edge to it is removed (service stays); frontend's edge to service is
untouched. Complements test_explain.py's property-driven cascade
(dbPassword -> appServer -> catalog) with a removal-driven one -- the two
together prove explain_recompile's caused_by mechanism doesn't care which
kind of change triggered the hash difference it's walking.
"""

import pytest

from epc.explain import explain_recompile, previous_state_from_graph
from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

BEFORE = """
metadata: {name: cascade-example}
spec:
  resources:
    - capability: compute
      name: database
    - capability: compute
      name: service
      dependsOn: ["compute.database"]
    - capability: compute
      name: frontend
      dependsOn: ["compute.service"]
"""

# database removed entirely; service no longer depends on it; frontend's
# edge to service is untouched
AFTER = """
metadata: {name: cascade-example}
spec:
  resources:
    - capability: compute
      name: service
    - capability: compute
      name: frontend
      dependsOn: ["compute.service"]
"""


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("compute", FakeProvider(name="fake-compute"))
    return registry


def test_database_is_gone_service_and_frontend_both_recompile(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    assert "compute.database" not in after.graph.nodes
    assert set(after.plans) == {"compute.service", "compute.frontend"}
    assert after.skipped == set()


def test_service_reports_the_removed_dependency_by_name(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    before = compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    reason = explain_recompile(previous_state_from_graph(before.graph), after.graph, "compute.service")
    assert reason.recompiled is True
    assert reason.removed_dependencies == ["compute.database"]
    assert reason.own_properties_changed is False


def test_frontend_cascades_through_service_even_though_its_own_edge_never_changed(tmp_path):
    """frontend's depends_on = {service} is identical before and after --
    it recompiles solely because service's hash changed underneath it."""
    manifest = str(tmp_path / "manifest.json")
    before = compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    assert before.graph.nodes["compute.frontend"].depends_on == after.graph.nodes["compute.frontend"].depends_on

    reason = explain_recompile(previous_state_from_graph(before.graph), after.graph, "compute.frontend")
    assert reason.recompiled is True
    assert reason.added_dependencies == []
    assert reason.removed_dependencies == []
    assert [c.node_id for c in reason.caused_by] == ["compute.service"]
    assert reason.caused_by[0].removed_dependencies == ["compute.database"]


def test_explaining_a_removed_node_directly_raises_a_clear_error(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    before = compile_spec(BEFORE, _registry(), manifest_path=manifest)
    after = compile_spec(AFTER, _registry(), manifest_path=manifest)

    with pytest.raises(KeyError, match="compute.database"):
        explain_recompile(previous_state_from_graph(before.graph), after.graph, "compute.database")
