import pytest

from epc.errors import CycleError
from epc.ir import IRGraph
from epc.normalizer import normalize
from epc.parser import parse
from epc.passes import CriticalPathPass, DependencySimplificationPass, GraphStatisticsPass

FIXTURE = open("tests/fixtures/data_platform.yaml").read()

CRITICAL_PATH = [
    "storage.dataLake",
    "network.privateEndpoint",
    "network.firewall",
    "compute.databricks",
    "governance.unityCatalog",
    "pipeline.pipelines",
]


def test_critical_path_finds_the_longest_chain():
    result = CriticalPathPass().run(normalize(parse(FIXTURE)))
    assert result.length == 6
    assert result.path == CRITICAL_PATH


def test_critical_path_is_unaffected_by_dependency_simplification():
    """max() over dependency depths already ignores a shorter redundant edge,
    so this must agree with the raw graph regardless of whether the
    transitive-reduction pass ran first."""
    raw = CriticalPathPass().run(normalize(parse(FIXTURE)))
    simplified = CriticalPathPass().run(DependencySimplificationPass().run(normalize(parse(FIXTURE))))
    assert raw == simplified


def test_critical_path_on_an_empty_graph():
    result = CriticalPathPass().run(IRGraph(nodes={}))
    assert result.length == 0
    assert result.path == []


def test_critical_path_detects_a_cycle():
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
    with pytest.raises(CycleError):
        CriticalPathPass().run(normalize(parse(bad)))


def test_graph_statistics_counts_nodes_edges_and_kinds():
    stats = GraphStatisticsPass().run(normalize(parse(FIXTURE)))
    assert stats.node_count == 6
    assert stats.nodes_by_kind == {"storage": 1, "network": 2, "compute": 1, "data-platform": 1, "workflow": 1}
    # unityCatalog depends on both databricks and dataLake before simplification runs
    assert stats.max_fan_in == 2
    assert stats.max_fan_out == 2


def test_graph_statistics_on_an_empty_graph():
    stats = GraphStatisticsPass().run(IRGraph(nodes={}))
    assert stats.node_count == 0
    assert stats.edge_count == 0
    assert stats.max_fan_in == 0
    assert stats.max_fan_out == 0
