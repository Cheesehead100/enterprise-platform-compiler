"""Runs against a real terraform/tofu binary -- see providers/terraform_cli's
module docstring for why this touches zero external infrastructure.
"""

import shutil

import pytest

from epc.ir import StorageNode
from terraform_cli.provider import CliNotFoundError, TerraformCliProvider

TERRAFORM_BINARY = "tofu" if shutil.which("tofu") else "terraform"
HAS_CLI = shutil.which(TERRAFORM_BINARY) is not None

pytestmark = pytest.mark.skipif(not HAS_CLI, reason="no terraform/tofu binary on PATH")


def _node() -> StorageNode:
    return StorageNode(id="storage.dataLake", properties={"tier": "Standard_LRS"})


def test_initialize_detects_a_supported_version():
    provider = TerraformCliProvider(binary=TERRAFORM_BINARY)
    provider.initialize({})  # must not raise
    assert provider.health() is True


def test_validate_accepts_a_valid_node():
    result = TerraformCliProvider(binary=TERRAFORM_BINARY).validate(_node())
    assert result.ok is True
    assert result.errors == []


def test_plan_reports_a_create_action():
    plan = TerraformCliProvider(binary=TERRAFORM_BINARY).plan(_node())
    assert plan.provider == TERRAFORM_BINARY
    assert "create" in plan.diff["actions"]
    assert plan.diff["resource_changes"][0]["address"] == "terraform_data.storage_dataLake"


def test_apply_destroy_status_rollback_are_intentionally_disabled():
    provider = TerraformCliProvider(binary=TERRAFORM_BINARY)
    with pytest.raises(NotImplementedError):
        provider.apply(plan=None)
    with pytest.raises(NotImplementedError):
        provider.destroy(node_id="storage.dataLake")
    with pytest.raises(NotImplementedError):
        provider.status(node_id="storage.dataLake")
    with pytest.raises(NotImplementedError):
        provider.rollback(checkpoint_id="whatever")


def test_missing_binary_fails_health_and_initialize():
    provider = TerraformCliProvider(binary="epc-nonexistent-cli-xyz")
    assert provider.health() is False
    with pytest.raises(CliNotFoundError):
        provider.initialize({})
