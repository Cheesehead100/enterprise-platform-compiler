"""IR v1 edge types.

ponytail: only DependencyEdge is actually constructed today — IRGraph builds
one per `node.depends_on` entry (see graph.py), mirroring the node-level sets
the DAG builder (epc.dag) still reads directly for speed. PolicyEdge,
DataFlowEdge, and ExecutionEdge exist so the type taxonomy is frozen and a
future policy pass or data-lineage-aware optimizer has a real type to
construct — add call sites for them when such a pass exists, not before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Edge:
    kind: ClassVar[str] = "edge"
    source: str
    target: str


@dataclass(frozen=True)
class DependencyEdge(Edge):
    """`source` must exist before `target` can be planned — the DAG's edges."""

    kind: ClassVar[str] = "dependency"


@dataclass(frozen=True)
class PolicyEdge(Edge):
    """`target` is governed by policy node `source` (e.g. a PolicyNode scoping
    which nodes it applies to) — distinct from execution ordering."""

    kind: ClassVar[str] = "policy"


@dataclass(frozen=True)
class DataFlowEdge(Edge):
    """Data moves from `source` to `target` (e.g. storage -> pipeline) —
    relevant to lineage and cost/optimization passes even when there's no
    provisioning-order dependency between the two."""

    kind: ClassVar[str] = "data-flow"


@dataclass(frozen=True)
class ExecutionEdge(Edge):
    """An ordering constraint introduced by the scheduler (architecture doc §05)
    rather than derived from the spec itself — e.g. a rate-limit-driven
    sequencing between two otherwise-independent nodes."""

    kind: ClassVar[str] = "execution"
