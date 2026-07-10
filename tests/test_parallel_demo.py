"""Regression test for tests/fixtures/parallel_demo.yaml -- the same fixture
examples/generate_demo_data.py uses to produce the "why EPC's compiler
architecture beats a naive engine" demo. Backing the demo's numbers with a
real test means they can't silently drift from what the compiler actually
does.
"""

from epc.normalizer import normalize
from epc.parser import parse
from epc.passes import BatchPlanner, CriticalPathPass, DependencySimplificationPass

FIXTURE = open("tests/fixtures/parallel_demo.yaml").read()


def test_raw_graph_has_the_redundant_edge():
    graph = normalize(parse(FIXTURE))
    assert graph.nodes["compute.appServer"].depends_on == {
        "storage.bucket1",
        "storage.bucket2",
        "secret.dbPassword",
        "network.vpc",
    }


def test_simplification_removes_exactly_the_redundant_edge():
    graph = DependencySimplificationPass().run(normalize(parse(FIXTURE)))
    assert graph.nodes["compute.appServer"].depends_on == {
        "storage.bucket1",
        "storage.bucket2",
        "secret.dbPassword",
    }


def test_batching_gives_three_way_parallelism_in_batch_two():
    plan = BatchPlanner().plan(normalize(parse(FIXTURE)))
    batches = [b.node_ids for b in plan.batches]
    assert batches == [
        ["network.vpc"],
        ["secret.dbPassword", "storage.bucket1", "storage.bucket2"],
        ["compute.appServer"],
        ["governance.catalog"],
    ]


def test_naive_sequential_would_take_six_steps_batched_takes_four():
    graph = normalize(parse(FIXTURE))
    plan = BatchPlanner().plan(graph)
    naive_steps = len(graph.nodes)
    batched_steps = len(plan.batches)
    assert naive_steps == 6
    assert batched_steps == 4
    assert round(naive_steps / batched_steps, 2) == 1.5


def test_critical_path_is_four_hops():
    result = CriticalPathPass().run(normalize(parse(FIXTURE)))
    assert result.length == 4
    assert result.path[0] == "network.vpc"
    assert result.path[-1] == "governance.catalog"
    assert result.path[-2] == "compute.appServer"
