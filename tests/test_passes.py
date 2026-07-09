import pytest

from epc.dag import topological_batches
from epc.errors import GraphValidationError, UnknownCapabilityError
from epc.normalizer import normalize
from epc.parser import parse
from epc.passes import (
    DEFAULT_PASSES,
    BatchPlanner,
    DeadNodeEliminationPass,
    DependencySimplificationPass,
    PassManager,
    ProviderLowering,
    ValidationPass,
)
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

FIXTURE = open("tests/fixtures/data_platform.yaml").read()


def test_pass_manager_runs_passes_in_order_each_consuming_the_previous_output():
    order: list[str] = []

    class RecordingPass:
        def __init__(self, label: str):
            self.label = label

        def run(self, graph):
            order.append(self.label)
            return graph

    PassManager([RecordingPass("a"), RecordingPass("b"), RecordingPass("c")]).run(normalize(parse(FIXTURE)))
    assert order == ["a", "b", "c"]


def test_validation_pass_accepts_a_clean_graph():
    graph = normalize(parse(FIXTURE))
    assert ValidationPass().run(graph) is graph


def test_validation_pass_raises_on_a_dangling_dependency():
    graph = normalize(parse(FIXTURE))
    graph.nodes["storage.dataLake"].depends_on.add("storage.doesNotExist")
    with pytest.raises(GraphValidationError):
        ValidationPass().run(graph)


def test_dead_node_elimination_removes_disabled_nodes_and_keeps_the_rest():
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: unused
      properties:
        enabled: false
    - capability: network
      name: standalone
"""
    graph = DeadNodeEliminationPass().run(normalize(parse(spec)))
    assert "storage.unused" not in graph.nodes
    assert "network.standalone" in graph.nodes


def test_dead_node_elimination_leaves_a_dangling_reference_for_validation_to_catch():
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: dataLake
      properties:
        enabled: false
    - capability: network
      name: endpoint
      dependsOn: ["storage.dataLake"]
"""
    graph = DeadNodeEliminationPass().run(normalize(parse(spec)))
    assert "storage.dataLake" not in graph.nodes
    assert "storage.dataLake" in graph.nodes["network.endpoint"].depends_on  # left dangling on purpose
    with pytest.raises(GraphValidationError):
        ValidationPass().run(graph)


def test_default_passes_surface_a_disabled_still_needed_dependency_as_a_clear_error():
    """End-to-end through the real pipeline order: disabling a node something
    else still depends on fails loudly instead of silently compiling a broken graph."""
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: dataLake
      properties:
        enabled: false
    - capability: network
      name: endpoint
      dependsOn: ["storage.dataLake"]
"""
    with pytest.raises(GraphValidationError):
        PassManager(DEFAULT_PASSES).run(normalize(parse(spec)))


def test_dependency_simplification_removes_a_transitively_implied_edge():
    # unityCatalog -> dataLake is implied by unityCatalog -> databricks ->
    # firewall -> privateEndpoint -> dataLake
    graph = DependencySimplificationPass().run(normalize(parse(FIXTURE)))
    assert graph.nodes["governance.unityCatalog"].depends_on == {"compute.databricks"}


def test_dependency_simplification_does_not_change_scheduling():
    before = topological_batches(normalize(parse(FIXTURE)))
    after_graph = DependencySimplificationPass().run(normalize(parse(FIXTURE)))
    after = topological_batches(after_graph)
    assert before == after


def test_batch_planner_wraps_topological_batches():
    plan = BatchPlanner().plan(normalize(parse(FIXTURE)))
    assert plan.batches[0].node_ids == ["storage.dataLake"]
    assert plan.ordered_node_ids[-1] == "pipeline.pipelines"


def _full_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("storage", "network", "compute", "governance", "pipeline"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def test_provider_lowering_dispatches_per_capability_and_honors_manifest_skips():
    graph = normalize(parse(FIXTURE))
    execution_plan = BatchPlanner().plan(graph)
    graph.compute_hashes(execution_plan.ordered_node_ids)

    previous_manifest = {"storage.dataLake": graph.nodes["storage.dataLake"].hash}
    result = ProviderLowering().run(graph, execution_plan, _full_registry(), previous_manifest)

    assert result.skipped == {"storage.dataLake"}
    assert "network.privateEndpoint" in result.plans
    assert "storage.dataLake" not in result.plans


def test_provider_lowering_raises_for_a_missing_provider():
    graph = normalize(parse(FIXTURE))
    execution_plan = BatchPlanner().plan(graph)
    graph.compute_hashes(execution_plan.ordered_node_ids)

    registry = ProviderRegistry()
    registry.register("storage", FakeProvider())  # "network" etc. deliberately unregistered

    with pytest.raises(UnknownCapabilityError):
        ProviderLowering().run(graph, execution_plan, registry)
