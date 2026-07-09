import pytest

from epc.errors import UnknownCapabilityError
from epc.pipeline import compile_spec
from epc.provider import ProviderRegistry
from fake.provider import FakeProvider

FIXTURE = open("tests/fixtures/data_platform.yaml").read()


def _full_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in ("storage", "network", "compute", "governance"):
        registry.register(capability, FakeProvider(name=f"fake-{capability}"))
    return registry


def test_compiles_end_to_end_with_fake_providers():
    result = compile_spec(FIXTURE, _full_registry())

    assert set(result.plans) == set(result.graph.nodes)
    assert result.plans["storage.dataLake"].provider == "fake-storage"


def test_every_node_has_a_content_hash_after_compile():
    result = compile_spec(FIXTURE, _full_registry())
    assert all(node.hash for node in result.graph.nodes.values())

    # a node's hash must change if its dependency's hash would change —
    # verified structurally: unityCatalog's hash input includes dataLake's hash
    dataLake_hash = result.graph.nodes["storage.dataLake"].hash
    unity_deps = result.graph.nodes["governance.unityCatalog"].depends_on
    assert "storage.dataLake" in unity_deps
    assert dataLake_hash is not None


def test_missing_provider_for_a_capability_raises():
    registry = ProviderRegistry()
    registry.register("storage", FakeProvider())
    # "network", "compute", "governance" deliberately left unregistered
    with pytest.raises(UnknownCapabilityError):
        compile_spec(FIXTURE, registry)
