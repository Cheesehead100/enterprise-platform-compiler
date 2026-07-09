"""IR v1 node types — the compiler's ABI. Every provider, every optimization
pass, every future language frontend depends on this shape, so it's an
explicit versioned type per node kind rather than one generic bag of
properties with a string tag: a pass or provider can `isinstance()`-match
instead of parsing a string, and kind-specific typed fields (e.g. a future
`StorageNode.encryption_at_rest: bool`) can be added later without breaking
anything already matching on the type.

All eight kinds share the same structural fields today — that's fine. The
*type* is what IR v1 freezes; the field set can still grow per-kind in a
later minor version without invalidating anything holding a `StorageNode`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class IRNode:
    kind: ClassVar[str] = "node"

    id: str
    properties: dict[str, Any] = field(default_factory=dict)
    depends_on: set[str] = field(default_factory=set)
    depended_on_by: set[str] = field(default_factory=set)
    hash: str | None = None  # set once dependency hashes are known — see IRGraph.compute_hashes

    @property
    def capability(self) -> str:
        """capability and IR node kind are 1:1 today — ponytail: split them into
        separate fields if/when two different capabilities legitimately need to
        share one node kind (e.g. object-storage vs. block-storage, both
        StorageNode). Until then this is the single source of truth, not a
        second field that could drift from the type."""
        return type(self).kind


@dataclass
class ComputeNode(IRNode):
    kind: ClassVar[str] = "compute"


@dataclass
class StorageNode(IRNode):
    kind: ClassVar[str] = "storage"


@dataclass
class SecretNode(IRNode):
    kind: ClassVar[str] = "secret"


@dataclass
class IdentityNode(IRNode):
    kind: ClassVar[str] = "identity"


@dataclass
class NetworkNode(IRNode):
    kind: ClassVar[str] = "network"


@dataclass
class PolicyNode(IRNode):
    kind: ClassVar[str] = "policy"


@dataclass
class PipelineNode(IRNode):
    kind: ClassVar[str] = "pipeline"


@dataclass
class DataPlatformNode(IRNode):
    kind: ClassVar[str] = "data-platform"


NODE_TYPES: dict[str, type[IRNode]] = {
    cls.kind: cls
    for cls in (
        ComputeNode,
        StorageNode,
        SecretNode,
        IdentityNode,
        NetworkNode,
        PolicyNode,
        PipelineNode,
        DataPlatformNode,
    )
}


class UnknownNodeKindError(ValueError):
    def __init__(self, capability: str):
        self.capability = capability
        known = ", ".join(sorted(NODE_TYPES))
        super().__init__(f"unknown IR node kind '{capability}' — known kinds: {known}")


def node_class_for(capability: str) -> type[IRNode]:
    try:
        return NODE_TYPES[capability]
    except KeyError as exc:
        raise UnknownNodeKindError(capability) from exc
