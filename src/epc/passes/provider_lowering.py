"""The lowering stage: Generic IR -> Provider Lowering -> Provider IR ->
Provider Adapter -> Plan.

Not a CompilerPass -- it produces `Plan` objects and has side effects (a real
provider adapter shells out to a CLI), not an IRGraph (see epc.passes.base).

What "lowering" means is split deliberately across two places:

- *When* lowering happens, and for which nodes (skipping ones an incremental
  compile already covers) -- that's this class's job, and it's compiler
  orchestration: capability-agnostic, provider-agnostic.
- *How* a specific node's generic IR becomes that provider's Provider IR
  (e.g. TerraformCliProvider._lower turning a StorageNode into a
  terraform_data block) -- that stays inside each provider, on purpose.
  Only the provider knows its target shape (Terraform HCL vs. a Pulumi
  program vs. a Crossplane manifest), and keeping that logic out of this
  class is exactly what keeps provider-specific fields from leaking into the
  generic IR -- an IR node that grew a `terraform_workspace` field would be
  the smell this split exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import UnknownCapabilityError
from ..ir import ExecutionPlan, IRGraph
from ..provider import Plan, ProviderRegistry


@dataclass
class LoweringResult:
    plans: dict[str, Plan]
    skipped: set[str] = field(default_factory=set)


class ProviderLowering:
    def run(
        self,
        graph: IRGraph,
        execution_plan: ExecutionPlan,
        registry: ProviderRegistry,
        previous_manifest: dict[str, dict] | None = None,
    ) -> LoweringResult:
        previous_manifest = previous_manifest or {}
        plans: dict[str, Plan] = {}
        skipped: set[str] = set()

        for node_id in execution_plan.ordered_node_ids:
            node = graph.nodes[node_id]
            if previous_manifest.get(node_id, {}).get("hash") == node.hash:
                skipped.add(node_id)
                continue

            provider = registry.resolve(node.capability)
            if provider is None:
                raise UnknownCapabilityError(node_id, node.capability)

            validation = provider.validate(node)
            if not validation.ok:
                raise ValueError(f"{node_id}: {'; '.join(validation.errors)}")
            plans[node_id] = provider.plan(node)

        return LoweringResult(plans=plans, skipped=skipped)
