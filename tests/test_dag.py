import pytest

from epc.dag import topological_batches
from epc.errors import CycleError
from epc.normalizer import normalize
from epc.parser import parse

FIXTURE = open("tests/fixtures/data_platform.yaml").read()


def test_batches_match_architecture_doc_worked_example():
    """Mirrors the exact batch table in architecture doc §02 — including the
    fan-in at batch 5, which a linear script gets wrong first."""
    graph = normalize(parse(FIXTURE))
    batches = topological_batches(graph)

    assert batches == [
        ["storage.dataLake"],
        ["network.privateEndpoint"],
        ["network.firewall"],
        ["compute.databricks"],
        ["governance.unityCatalog"],
        ["pipeline.pipelines"],
    ]


def test_cycle_is_detected():
    bad = """
metadata: {name: x}
spec:
  resources:
    - capability: network
      name: one
      dependsOn: ["compute.two"]
    - capability: compute
      name: two
      dependsOn: ["network.one"]
"""
    graph = normalize(parse(bad))
    with pytest.raises(CycleError):
        topological_batches(graph)


def test_independent_nodes_share_a_batch():
    two_roots = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: a
    - capability: storage
      name: b
"""
    graph = normalize(parse(two_roots))
    batches = topological_batches(graph)
    assert batches == [["storage.a", "storage.b"]]
