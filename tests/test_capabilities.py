"""The escape hatch this round's redesign exists for: a capability the
routing table doesn't know about must not fail to compile -- it should land
on ExtensionNode (kind=extension) and flow through the rest of the pipeline
like any other node.
"""

from epc.capabilities import kind_for_capability, node_class_for
from epc.ir import (
    DataPlatformNode,
    ExtensionNode,
    NodeKind,
    ServiceNode,
    WorkflowNode,
)
from epc.normalizer import normalize
from epc.parser import parse


def test_known_capabilities_resolve_to_their_documented_kind():
    assert kind_for_capability("storage") == NodeKind.STORAGE
    assert kind_for_capability("governance") == NodeKind.DATA_PLATFORM
    assert kind_for_capability("pipeline") == NodeKind.WORKFLOW
    for service_capability in ("monitoring", "gitops", "service-discovery", "artifact-repository", "cost", "ai"):
        assert kind_for_capability(service_capability) == NodeKind.SERVICE


def test_unknown_capability_falls_back_to_extension_not_an_error():
    assert kind_for_capability("some-future-capability-nobody-registered-yet") == NodeKind.EXTENSION
    assert node_class_for("some-future-capability-nobody-registered-yet") is ExtensionNode


def test_governance_keeps_its_own_capability_name_while_resolving_to_data_platform_kind():
    """The specific regression this module guards against: a domain-meaningful
    capability name ("governance") must not be forced to rename itself just
    to fit the IR's structural vocabulary ("data-platform")."""
    assert node_class_for("governance") is DataPlatformNode


def test_normalizer_compiles_an_unrecognized_capability_without_raising():
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: quantum-flux-capacitor
      name: thing
"""
    graph = normalize(parse(spec))
    node = graph.nodes["quantum-flux-capacitor.thing"]
    assert isinstance(node, ExtensionNode)
    assert node.capability == "quantum-flux-capacitor"


def test_normalizer_routes_service_and_workflow_capabilities_correctly():
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: monitoring
      name: prometheus
    - capability: pipeline
      name: nightly
"""
    graph = normalize(parse(spec))
    assert isinstance(graph.nodes["monitoring.prometheus"], ServiceNode)
    assert isinstance(graph.nodes["pipeline.nightly"], WorkflowNode)
