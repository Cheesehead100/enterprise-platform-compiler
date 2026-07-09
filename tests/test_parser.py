import pytest

from epc.ast import Ref
from epc.errors import ParseError, SchemaError
from epc.parser import parse

MINIMAL = """
apiVersion: epc/v1
kind: PlatformSpec
metadata:
  name: example
spec:
  region: eastus2
  resources:
    - capability: storage
      name: dataLake
      properties:
        tier: Standard_LRS
        region: "ref:spec.region"
"""


def test_parses_metadata_and_spec_properties():
    ast = parse(MINIMAL)
    assert ast.name == "example"
    assert ast.spec_properties == {"region": "eastus2"}


def test_parses_resource_with_ref_property():
    ast = parse(MINIMAL)
    node = ast.resources[0]
    assert node.id == "storage.dataLake"
    assert node.properties["tier"] == "Standard_LRS"
    assert node.properties["region"] == Ref("spec.region")


def test_invalid_yaml_raises_parse_error():
    with pytest.raises(ParseError):
        parse("resources: [unterminated")


def test_missing_metadata_name_raises_schema_error():
    with pytest.raises(SchemaError):
        parse("metadata: {}\nspec: {resources: []}")


def test_resource_missing_capability_raises_schema_error():
    bad = """
metadata: {name: x}
spec:
  resources:
    - name: dataLake
"""
    with pytest.raises(SchemaError):
        parse(bad)
