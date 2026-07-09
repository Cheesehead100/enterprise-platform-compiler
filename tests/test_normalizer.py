import pytest

from epc.errors import UndefinedReferenceError
from epc.normalizer import normalize
from epc.parser import parse

FIXTURE = open("tests/fixtures/data_platform.yaml").read()


def test_normalize_resolves_spec_ref():
    graph = normalize(parse(FIXTURE))
    assert graph.nodes["storage.dataLake"].properties["region"] == "eastus2"


def test_normalize_builds_depended_on_by():
    graph = normalize(parse(FIXTURE))
    # unityCatalog depends directly on both databricks AND dataLake (the fan-in)
    assert "governance.unityCatalog" in graph.nodes["storage.dataLake"].depended_on_by
    assert "governance.unityCatalog" in graph.nodes["compute.databricks"].depended_on_by


def test_undefined_dependency_raises():
    bad = """
metadata: {name: x}
spec:
  resources:
    - capability: network
      name: firewall
      dependsOn: ["storage.doesNotExist"]
"""
    with pytest.raises(UndefinedReferenceError):
        normalize(parse(bad))


def test_undefined_spec_ref_raises():
    bad = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: dataLake
      properties:
        region: "ref:spec.doesNotExist"
"""
    with pytest.raises(UndefinedReferenceError):
        normalize(parse(bad))
