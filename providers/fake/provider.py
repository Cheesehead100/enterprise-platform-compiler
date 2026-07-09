"""A fake Provider (architecture doc §04 interface) used only to prove the
pipeline end-to-end without touching real infrastructure. Real providers
(OpenTofu, Vault, ...) are Phase 1 (architecture doc §20)."""

from __future__ import annotations

from typing import Any

from epc.ir import ResourceGraphNode
from epc.provider import Plan, Provider, ValidationResult


class FakeProvider(Provider):
    def __init__(self, name: str = "fake"):
        self.name = name
        self.applied: dict[str, Plan] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        pass

    def validate(self, node: ResourceGraphNode) -> ValidationResult:
        return ValidationResult(ok=True)

    def plan(self, node: ResourceGraphNode) -> Plan:
        return Plan(node_id=node.id, provider=self.name, diff={"create": node.properties})

    def apply(self, plan: Plan) -> dict[str, Any]:
        self.applied[plan.node_id] = plan
        return {"state": "applied", "node_id": plan.node_id}

    def destroy(self, node_id: str) -> None:
        self.applied.pop(node_id, None)

    def status(self, node_id: str) -> dict[str, Any]:
        return {"applied": node_id in self.applied}

    def health(self) -> bool:
        return True

    def rollback(self, checkpoint_id: str) -> None:
        pass
