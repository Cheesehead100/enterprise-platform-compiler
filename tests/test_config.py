"""Config-driven provider resolution (architecture doc §15) -- proves
`python -m epc compile --providers ...` exercises real provider swapping,
not just the pipeline's own registry.resolve() (see test_provider_swap.py).
"""

import shutil

import pytest

from epc.config import UnknownProviderError, build_registry, load_provider_config
from fake.provider import FakeProvider

TERRAFORM_BINARY = "tofu" if shutil.which("tofu") else "terraform"
HAS_CLI = shutil.which(TERRAFORM_BINARY) is not None
PROVIDER_NAME = "opentofu" if TERRAFORM_BINARY == "tofu" else "terraform-cli"


def test_unlisted_capability_defaults_to_fake():
    registry = build_registry({}, {"storage"})
    assert isinstance(registry.resolve("storage"), FakeProvider)


def test_explicit_fake_config_is_honored():
    registry = build_registry({"storage": {"provider": "fake", "name": "fake-storage"}}, {"storage"})
    provider = registry.resolve("storage")
    assert isinstance(provider, FakeProvider)
    assert provider.name == "fake-storage"


def test_unknown_provider_name_raises():
    with pytest.raises(UnknownProviderError):
        build_registry({"storage": {"provider": "azure-storage-magic"}}, {"storage"})


@pytest.mark.skipif(not HAS_CLI, reason="no terraform/tofu binary on PATH")
def test_real_cli_provider_is_selected_and_initialized():
    from terraform_cli.provider import TerraformCliProvider

    registry = build_registry({"storage": {"provider": PROVIDER_NAME}}, {"storage"})
    provider = registry.resolve("storage")
    assert isinstance(provider, TerraformCliProvider)
    assert provider.health() is True  # initialize() already ran inside the factory


def test_load_provider_config_reads_the_providers_block(tmp_path):
    config_file = tmp_path / "providers.yaml"
    config_file.write_text("providers:\n  storage:\n    provider: fake\n")
    assert load_provider_config(str(config_file)) == {"storage": {"provider": "fake"}}


def test_load_provider_config_defaults_to_empty_when_block_missing(tmp_path):
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("not_providers: {}\n")
    assert load_provider_config(str(config_file)) == {}
