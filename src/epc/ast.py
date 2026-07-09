"""AST — output of Parse, input to Normalize (architecture doc §02 'AST — what Parse produces').

Deliberately dumb: no reference resolution, no dependency inference happens here.
That's the Normalizer's job (epc.normalizer), kept separate so each stage stays
independently testable, per the architecture doc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Ref:
    """An unresolved reference, e.g. Ref("spec.region") or Ref("network.firewall")."""

    path: str


@dataclass
class ResourceNode:
    capability: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.capability}.{self.name}"


@dataclass
class PlatformSpecAST:
    name: str
    spec_properties: dict[str, Any]
    resources: list[ResourceNode]
