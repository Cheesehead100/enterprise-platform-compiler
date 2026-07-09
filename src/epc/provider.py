"""The Provider contract (architecture doc §04) and a minimal in-process registry.

ponytail: registry is a flat dict, populated by hand in tests/pipeline callers —
the real plugin discovery (manifests, OCI index, trust tiers) is architecture §09,
Phase 1+. This is just enough to prove capability -> provider resolution works.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .ir import IRNode


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class Plan:
    node_id: str
    provider: str
    diff: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Every implementation — fake or real — satisfies this, regardless of capability."""

    name: str

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None: ...

    @abstractmethod
    def validate(self, node: IRNode) -> ValidationResult: ...

    @abstractmethod
    def plan(self, node: IRNode) -> Plan: ...

    @abstractmethod
    def apply(self, plan: Plan) -> dict[str, Any]: ...

    @abstractmethod
    def destroy(self, node_id: str) -> None: ...

    @abstractmethod
    def status(self, node_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def health(self) -> bool: ...

    @abstractmethod
    def rollback(self, checkpoint_id: str) -> None: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, capability: str, provider: Provider) -> None:
        self._providers[capability] = provider

    def resolve(self, capability: str) -> Provider | None:
        return self._providers.get(capability)
