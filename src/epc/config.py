"""Config-driven provider resolution (architecture doc §15) -- the piece that
lets `python -m epc compile` exercise the real registry instead of always
defaulting to the fake provider. A capability not mentioned in the config
defaults to `fake`, matching the "sane default, explicit opt-in for anything
else" pattern used throughout this repo (e.g. epc.pipeline's manifest_path).

ponytail: PROVIDER_FACTORIES is a hardcoded dict of the two providers that
exist. Real plugin discovery (manifests, OCI index, trust tiers -- architecture
doc §09) replaces this once there's a third provider author who isn't us.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from .provider import Provider, ProviderRegistry


class UnknownProviderError(ValueError):
    def __init__(self, capability: str, provider_name: str):
        known = ", ".join(sorted(PROVIDER_FACTORIES))
        super().__init__(f"{capability}: unknown provider '{provider_name}' — known providers: {known}")


def _fake_factory(cfg: dict[str, Any]) -> Provider:
    from fake.provider import FakeProvider

    return FakeProvider(name=cfg.get("name", "fake"))


def _terraform_cli_factory(default_binary: str) -> Callable[[dict[str, Any]], Provider]:
    def factory(cfg: dict[str, Any]) -> Provider:
        from terraform_cli.provider import TerraformCliProvider

        provider = TerraformCliProvider(binary=cfg.get("binary", default_binary))
        provider.initialize(cfg)
        return provider

    return factory


PROVIDER_FACTORIES: dict[str, Callable[[dict[str, Any]], Provider]] = {
    "fake": _fake_factory,
    "opentofu": _terraform_cli_factory("tofu"),
    "terraform-cli": _terraform_cli_factory("terraform"),
}


def load_provider_config(path: str) -> dict[str, dict[str, Any]]:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    return doc.get("providers") or {}


def build_registry(provider_config: dict[str, dict[str, Any]], capabilities: set[str]) -> ProviderRegistry:
    registry = ProviderRegistry()
    for capability in capabilities:
        entry = provider_config.get(capability, {"provider": "fake"})
        provider_name = entry.get("provider", "fake")
        factory = PROVIDER_FACTORIES.get(provider_name)
        if factory is None:
            raise UnknownProviderError(capability, provider_name)
        registry.register(capability, factory(entry))
    return registry
