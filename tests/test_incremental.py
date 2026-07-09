"""Proves architecture doc §02's incremental-compilation claim: changing one
node only recompiles that node and its dependents — an unrelated branch is
skipped entirely, not just cheaply recomputed.
"""

from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

V1 = """
metadata: {name: incremental-example}
spec:
  resources:
    - capability: storage
      name: dataLake
      properties:
        tier: Standard_LRS
    - capability: network
      name: privateEndpoint
      dependsOn: ["storage.dataLake"]
    - capability: secrets
      name: dbSecret
      properties:
        rotation: 90
"""

V2 = V1.replace("Standard_LRS", "Standard_GRS")

ALL_NODES = {"storage.dataLake", "network.privateEndpoint", "secrets.dbSecret"}


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("storage", "network", "secrets"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def test_first_compile_recomputes_every_node(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    result = compile_spec(V1, _registry(), manifest_path=manifest)
    assert result.skipped == set()
    assert set(result.plans) == ALL_NODES


def test_second_identical_compile_skips_everything(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    compile_spec(V1, _registry(), manifest_path=manifest)
    result = compile_spec(V1, _registry(), manifest_path=manifest)
    assert result.plans == {}
    assert result.skipped == ALL_NODES


def test_changing_one_node_only_recompiles_its_subtree(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    compile_spec(V1, _registry(), manifest_path=manifest)
    result = compile_spec(V2, _registry(), manifest_path=manifest)

    # dataLake changed directly; privateEndpoint is downstream of it, so its
    # hash changes too even though its own properties didn't -- both recompile.
    assert set(result.plans) == {"storage.dataLake", "network.privateEndpoint"}
    # dbSecret has no relation to storage.dataLake -- must be skipped, not
    # regenerated, matching the doc's "don't regenerate networking/IAM/KeyVault"
    # incremental-compilation claim.
    assert result.skipped == {"secrets.dbSecret"}


def test_no_manifest_path_means_no_incremental_behavior(tmp_path):
    """Backward-compat: omitting manifest_path recompiles everything, always —
    the existing non-incremental tests rely on this."""
    result = compile_spec(V1, _registry())
    assert result.skipped == set()
    assert set(result.plans) == ALL_NODES
