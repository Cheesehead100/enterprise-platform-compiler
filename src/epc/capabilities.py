"""The default capability -> NodeKind routing table.

Deliberately *not* part of epc.ir: the IR package freezes structural types
(NodeKind, the node classes); this module is compiler policy about which
open-ended capability string maps to which structural kind, and that mapping
is allowed to grow anytime without touching the frozen ABI. An unrecognized
capability isn't a compile error -- it resolves to NodeKind.EXTENSION
(epc.ir.ExtensionNode) so the compiler stays functional on a capability that
doesn't have a dedicated routing entry yet.

ponytail: a hardcoded dict, populated by hand. "Validated by the compiler
configuration or plugin registry" (as opposed to baked into this module) is
the real end state -- swap CAPABILITY_KINDS for a config-driven or
registry-driven lookup when a second consumer (not just this compiler) needs
to influence the mapping, e.g. a community provider registering a capability
this table has never heard of.
"""

from __future__ import annotations

from .ir import NODE_CLASS_BY_KIND, IRNode, NodeKind

CAPABILITY_KINDS: dict[str, NodeKind] = {
    # infrastructure primitives
    "compute": NodeKind.COMPUTE,
    "storage": NodeKind.STORAGE,
    "network": NodeKind.NETWORK,
    "identity": NodeKind.IDENTITY,
    "secret": NodeKind.SECRET,
    "data-platform": NodeKind.DATA_PLATFORM,
    "governance": NodeKind.DATA_PLATFORM,  # domain name kept as-is; see module docstring
    "policy": NodeKind.POLICY,
    # orchestration
    "workflow": NodeKind.WORKFLOW,
    "pipeline": NodeKind.WORKFLOW,
    # platform services -- all ServiceNode, capability is what tells them apart
    "monitoring": NodeKind.SERVICE,
    "logging": NodeKind.SERVICE,
    "catalog": NodeKind.SERVICE,
    "service-discovery": NodeKind.SERVICE,
    "artifact-repository": NodeKind.SERVICE,
    "gitops": NodeKind.SERVICE,
    "cost": NodeKind.SERVICE,
    "ai": NodeKind.SERVICE,
    "event-bus": NodeKind.SERVICE,
    "approval": NodeKind.SERVICE,
}


def kind_for_capability(capability: str) -> NodeKind:
    return CAPABILITY_KINDS.get(capability, NodeKind.EXTENSION)


def node_class_for(capability: str) -> type[IRNode]:
    return NODE_CLASS_BY_KIND[kind_for_capability(capability)]
