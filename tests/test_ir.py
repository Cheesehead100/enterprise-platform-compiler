"""Tests for the frozen IR v1 package itself -- independent of the compiler
frontend that normally produces an IRGraph (epc.normalizer). Proves the ABI
(serialization round-trip, version stamping, structural validation) holds on
its own, since providers and future frontends depend on exactly this shape.
"""

import pytest

from epc.ir import (
    IR_VERSION,
    NetworkNode,
    StorageNode,
    UnknownNodeKindError,
    UnsupportedIRVersionError,
    from_dict,
    node_class_for,
    to_dict,
    to_execution_plan,
    validate_graph,
)
from epc.ir.v1.graph import IRGraph


def _two_node_graph() -> IRGraph:
    storage = StorageNode(id="storage.dataLake", properties={"tier": "Standard_LRS"})
    network = NetworkNode(id="network.endpoint", depends_on={"storage.dataLake"})
    storage.depended_on_by.add("network.endpoint")
    return IRGraph(nodes={"storage.dataLake": storage, "network.endpoint": network})


def test_node_class_for_resolves_known_kinds():
    assert node_class_for("storage") is StorageNode
    assert node_class_for("network") is NetworkNode


def test_node_class_for_unknown_kind_raises():
    with pytest.raises(UnknownNodeKindError):
        node_class_for("quantum-flux-capacitor")


def test_capability_is_derived_from_the_node_type_not_a_separate_field():
    node = StorageNode(id="storage.x")
    assert node.capability == "storage"


def test_serializer_round_trip_preserves_shape():
    graph = _two_node_graph()
    graph.compute_hashes(["storage.dataLake", "network.endpoint"])

    restored = from_dict(to_dict(graph))

    assert set(restored.nodes) == set(graph.nodes)
    assert isinstance(restored.nodes["storage.dataLake"], StorageNode)
    assert isinstance(restored.nodes["network.endpoint"], NetworkNode)
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
