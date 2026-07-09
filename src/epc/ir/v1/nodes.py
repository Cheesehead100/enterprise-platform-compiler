"""IR v1 node types — the compiler's ABI.

Two separate axes, on purpose — this is IR v1's key structural decision:

- `kind` (NodeKind): a small, closed enum of infrastructure *primitives* --
  what shape of thing this is, structurally. The DAG, the scheduler, and
  optimization passes (dead-node elimination, resource coalescing, ...)
  reason about this. Frozen: adding a tenth kind is an IR v2 decision.
- `capability` (str): an open, growing vocabulary of *what this node does* --
  "monitoring", "gitops", "service-discovery", "governance", whatever a
  provider registry knows how to resolve. Providers dispatch on this.
  Extensible: adding "cost-optimizer" tomorrow touches zero types here.

Modeling every capability as its own node subclass doesn't scale to a
20-capability platform catalog (architecture doc §13). ServiceNode exists
specifically so monitoring/logging/catalog/service-discovery/artifact-
repository/gitops/cost/ai/event-bus/approval all share one structural shape
without forcing domain vocabulary into the type system. Anything whose
capability isn't in the known routing table (epc.capabilities, deliberately
outside this package -- see that module's docstring) falls back to
ExtensionNode rather than failing to compile.

ponytail: no per-kind trait system (managed/stateful/networked/observable...)
yet -- floated as a real idea for optimization passes to reason about, but
speculative until a pass actually needs it instead of matching on `kind`.
Add as an IR v1.1 field addition (traits: don't require a new node type)
when that pass exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


class NodeKind(str, Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    IDENTITY = "identity"
    SECRET = "secret"
    DATA_PLATFORM = "data-platform"
    SERVICE = "service"
    WORKFLOW = "workflow"
    POLICY = "policy"
    EXTENSION = "extension"  # forward-compat escape hatch


@dataclass
class IRNode:
    kind: ClassVar[NodeKind] = NodeKind.EXTENSION

    id: str
    capability: str
    properties: dict[str, Any] = field(default_factory=dict)
    depends_on: set[str] = field(default_factory=set)
    depended_on_by: set[str] = field(default_factory=set)
    hash: str | None = None  # set once dependency hashes are known — see IRGraph.compute_hashes


@dataclass
class ComputeNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.COMPUTE


@dataclass
class StorageNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.STORAGE


@dataclass
class NetworkNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.NETWORK


@dataclass
class IdentityNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.IDENTITY


@dataclass
class SecretNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.SECRET


@dataclass
class DataPlatformNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.DATA_PLATFORM


@dataclass
class ServiceNode(IRNode):
    """Deliberately broad: monitoring, logging, catalog, service-discovery,
    artifact-repository, gitops, cost, ai, event-bus, approval, and any other
    platform service that isn't an infrastructure primitive. `capability`
    tells these apart; `kind` doesn't need to."""

    kind: ClassVar[NodeKind] = NodeKind.SERVICE


@dataclass
class WorkflowNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.WORKFLOW


@dataclass
class PolicyNode(IRNode):
    kind: ClassVar[NodeKind] = NodeKind.POLICY


@dataclass
class ExtensionNode(IRNode):
    """The escape hatch. Any capability the routing table doesn't recognize
    lands here with kind=extension instead of failing to compile -- this is
    what keeps IR v1 frozen while the capability catalog keeps growing."""

    kind: ClassVar[NodeKind] = NodeKind.EXTENSION


NODE_CLASS_BY_KIND: dict[NodeKind, type[IRNode]] = {
    NodeKind.COMPUTE: ComputeNode,
    NodeKind.STORAGE: StorageNode,
    NodeKind.NETWORK: NetworkNode,
    NodeKind.IDENTITY: IdentityNode,
    NodeKind.SECRET: SecretNode,
    NodeKind.DATA_PLATFORM: DataPlatformNode,
    NodeKind.SERVICE: ServiceNode,
    NodeKind.WORKFLOW: WorkflowNode,
    NodeKind.POLICY: PolicyNode,
    NodeKind.EXTENSION: ExtensionNode,
}
