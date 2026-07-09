"""Proves registry.resolve() actually branches on which provider is
registered per capability -- two genuinely different implementations (a fake
and a real CLI adapter) producing different Plan shapes from the same IR,
with zero changes to the pipeline, normalizer, or DAG code.
"""

import shutil

import pytest

from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider
from terraform_cli.provider import TerraformCliProvider

TERRAFORM_BINARY = "tofu" if shutil.which("tofu") else "terraform"
HAS_CLI = shutil.which(TERRAFORM_BINARY) is not None

SPEC = """
metadata: {name: swap-example}
spec:
  resources:
    - capability: storage
      name: dataLake
      properties:
        tier: Standard_LRS
    - capability: network
      name: privateEndpoint
      dependsOn: ["storage.dataLake"]
"""


def _fake_only_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("storage", FakeProvider(name="fake-storage"))
    registry.register("network", FakeProvider(name="fake-network"))
    return registry


@pytest.mark.skipif(not HAS_CLI, reason="no terraform/tofu binary on PATH")
def test_swapping_the_storage_provider_changes_only_that_nodes_plan():
    fake_result = compile_spec(SPEC, _fake_only_registry())

    tf_provider = TerraformCliProvider(binary=TERRAFORM_BINARY)
    tf_provider.initialize({})
    mixed_registry = ProviderRegistry()
    mixed_registry.register("storage", tf_provider)
    mixed_registry.register("network", FakeProvider(name="fake-network"))
    mixed_result = compile_spec(SPEC, mixed_registry)

    # same spec, same IR, same DAG batches -- only the resolved provider differs
    assert fake_result.batches == mixed_result.batches
    assert fake_result.plans["storage.dataLake"].provider == "fake-storage"
    assert mixed_result.plans["storage.dataLake"].provider == TERRAFORM_BINARY
    assert mixed_result.plans["storage.dataLake"].diff != fake_result.plans["storage.dataLake"].diff

    # network was never swapped -- still the fake provider in both compiles
    assert mixed_result.plans["network.privateEndpoint"].provider == "fake-network"
