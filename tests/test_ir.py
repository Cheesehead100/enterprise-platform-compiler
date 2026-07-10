"""Tests for the frozen IR v1 package itself -- independent of the compiler
frontend that normally produces an IRGraph (epc.normalizer). Proves the ABI
(serialization round-trip, version stamping, structural validation) holds on
its own, since providers and future frontends depend on exactly this shape.
"""

import pytest

from epc.ir import (
    IR_VERSION,
    NetworkNode,
    NodeKind,
    ServiceNode,
    StorageNode,
    UnsupportedIRVersionError,
    from_dict,
    to_dict,
    to_execution_plan,
    validate_graph,
)
from epc.ir.v1.graph import IRGraph


def _two_node_graph() -> IRGraph:
    storage = StorageNode(id="storage.dataLake", capability="storage", properties={"tier": "Standard_LRS"})
    network = NetworkNode(id="network.endpoint", capability="network", depends_on={"storage.dataLake"})
    storage.depended_on_by.add("network.endpoint")
    return IRGraph(nodes={"storage.dataLake": storage, "network.endpoint": network})


def test_kind_is_a_closed_structural_axis_separate_from_capability():
    node = StorageNode(id="storage.x", capability="storage")
    assert type(node).kind == NodeKind.STORAGE
    assert node.capability == "storage"


def test_service_node_lets_unrelated_capabilities_share_one_kind():
    """monitoring and gitops are structurally the same shape (a platform
    service) even though they're unrelated domains -- ServiceNode exists so
    that doesn't require two node types."""
    monitoring = ServiceNode(id="service.prom", capability="monitoring")
    gitops = ServiceNode(id="service.argocd", capability="gitops")
    assert type(monitoring) is type(gitops) is ServiceNode
    assert monitoring.capability != gitops.capability


def test_serializer_round_trip_preserves_kind_and_capability_separately():
    graph = _two_node_graph()
    graph.compute_hashes(["storage.dataLake", "network.endpoint"])

    restored = from_dict(to_dict(graph))

    assert set(restored.nodes) == set(graph.nodes)
    assert isinstance(restored.nodes["storage.dataLake"], StorageNode)
    assert isinstance(restored.nodes["network.endpoint"], NetworkNode)
    assert restored.nodes["storage.dataLake"].capability == "storage"
    assert restored.nodes["storage.dataLake"].properties == {"tier": "Standard_LRS"}
    assert restored.nodes["network.endpoint"].depends_on == {"storage.dataLake"}
    assert restored.nodes["storage.dataLake"].depended_on_by == {"network.endpoint"}
    assert restored.nodes["storage.dataLake"].hash == graph.nodes["storage.dataLake"].hash


def test_serializer_embeds_ir_version():
    assert to_dict(_two_node_graph())["ir_version"] == IR_VERSION


def test_from_dict_rejects_unsupported_version():
    payload = to_dict(_two_node_graph())
    payload["ir_version"] = "0.9"
    with pytest.raises(UnsupportedIRVersionError):
        from_dict(payload)


def test_validator_accepts_a_consistent_graph():
    assert validate_graph(_two_node_graph()) == []


def test_validator_catches_a_dangling_dependency():
    graph = _two_node_graph()
    graph.nodes["network.endpoint"].depends_on.add("storage.doesNotExist")
    errors = validate_graph(graph)
    assert any("dangling dependency" in e for e in errors)


def test_to_execution_plan_wraps_batches_with_ordering_preserved():
    plan = to_execution_plan([["storage.dataLake"], ["network.endpoint"]])
    assert [b.node_ids for b in plan.batches] == [["storage.dataLake"], ["network.endpoint"]]
    assert plan.ordered_node_ids == ["storage.dataLake", "network.endpoint"]


def test_a_node_hash_distinguishes_which_specific_dependency_it_points_at():
    """Regression: two structurally-identical dependencies (same capability,
    same properties) must NOT make a parent's hash blind to which one it
    actually depends on. The hash payload used to fold dependencies down to
    bare hash *values* (sorted(dep.hash for dep in depends_on)) -- two
    same-shaped-but-differently-named dependencies collide, so a node
    "rewired" from one to the other hashed identically before and after,
    which would make ProviderLowering silently skip a real change."""
    old_secret = StorageNode(id="storage.old", capability="storage", properties={"tier": "Standard_LRS"})
    new_secret = StorageNode(id="storage.new", capability="storage", properties={"tier": "Standard_LRS"})

    pointing_at_old = NetworkNode(id="network.consumer", capability="network", depends_on={"storage.old"})
    graph_a = IRGraph(nodes={"storage.old": old_secret, "network.consumer": pointing_at_old})
    graph_a.compute_hashes(["storage.old", "network.consumer"])

    pointing_at_new = NetworkNode(id="network.consumer", capability="network", depends_on={"storage.new"})
    graph_b = IRGraph(nodes={"storage.new": new_secret, "network.consumer": pointing_at_new})
    graph_b.compute_hashes(["storage.new", "network.consumer"])

    # the two dependencies really are hash-identical in isolation -- that's
    # the precondition for this bug, not a mistake in the fixture
    assert graph_a.nodes["storage.old"].hash == graph_b.nodes["storage.new"].hash

    assert graph_a.nodes["network.consumer"].hash != graph_b.nodes["network.consumer"].hash
