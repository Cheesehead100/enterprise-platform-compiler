"""The general form of the invariant tests/test_explain.py's individual
cases each proved once: for EVERY node in a compile, not just the ones a
test happened to pick, the pipeline's decision (result.plans vs.
result.skipped) and explain_recompile's verdict must agree. This is what
would have caught the removed-dependency bug automatically, without anyone
having to think of that specific scenario first.

  RECOMPILE decision  <=>  explain_recompile(...).recompiled is True
  SKIP decision       <=>  explain_recompile(...).recompiled is False
"""

from epc.explain import explain_recompile, previous_state_from_graph
from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider


def _registry(*capabilities: str) -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in capabilities:
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def _assert_every_node_agrees(before_yaml: str, after_yaml: str, capabilities: tuple[str, ...], tmp_path) -> None:
    manifest = str(tmp_path / "manifest.json")
    before = compile_spec(before_yaml, _registry(*capabilities), manifest_path=manifest)
    after = compile_spec(after_yaml, _registry(*capabilities), manifest_path=manifest)
    previous = previous_state_from_graph(before.graph)

    for node_id in after.graph.nodes:
        decision_recompiled = node_id in after.plans
        assert node_id in after.plans or node_id in after.skipped, f"{node_id}: neither planned nor skipped"

        explanation_recompiled = explain_recompile(previous, after.graph, node_id).recompiled
        assert decision_recompiled == explanation_recompiled, (
            f"{node_id}: pipeline decided "
            f"{'RECOMPILE' if decision_recompiled else 'SKIP'} but explain_recompile said "
            f"recompiled={explanation_recompiled}"
        )


def test_incremental_fixture_pair_agrees_for_every_node(tmp_path):
    before = open("tests/fixtures/incremental_before.yaml").read()
    after = open("tests/fixtures/incremental_after.yaml").read()
    _assert_every_node_agrees(before, after, ("network", "storage", "secret", "compute", "governance"), tmp_path)


def test_parallel_demo_no_op_recompile_agrees_for_every_node(tmp_path):
    spec = open("tests/fixtures/parallel_demo.yaml").read()
    _assert_every_node_agrees(spec, spec, ("network", "storage", "secret", "compute", "governance"), tmp_path)


def test_cascading_removal_agrees_for_every_remaining_node(tmp_path):
    before = """
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
    after = """
metadata: {name: cascade-example}
spec:
  resources:
    - capability: compute
      name: service
    - capability: compute
      name: frontend
      dependsOn: ["compute.service"]
"""
    _assert_every_node_agrees(before, after, ("compute",), tmp_path)


def test_rename_agrees_for_every_node(tmp_path):
    before = """
metadata: {name: rename-example}
spec:
  resources:
    - capability: secret
      name: dbPassword
      properties: {rotation: 90}
    - capability: compute
      name: appServer
      dependsOn: ["secret.dbPassword"]
"""
    after = """
metadata: {name: rename-example}
spec:
  resources:
    - capability: secret
      name: databasePassword
      properties: {rotation: 90}
    - capability: compute
      name: appServer
      dependsOn: ["secret.databasePassword"]
"""
    _assert_every_node_agrees(before, after, ("secret", "compute"), tmp_path)
