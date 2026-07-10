"""IRGraph — the normalized resource graph — plus the typed shapes for
scheduling and checkpointing (architecture doc §02/§05).

Cloud- and tool-agnostic on purpose: nothing here mentions OpenTofu, Pulumi,
or any other backend. That's what makes this the artifact every downstream
stage — optimizer, DAG builder, provider codegen, AI passes — reasons about
instead of the original YAML.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .edges import DependencyEdge, Edge
from .nodes import IRNode


@dataclass
class IRGraph:
    nodes: dict[str, IRNode]

    def edges(self) -> list[Edge]:
        """DependencyEdge view of every node.depends_on entry. epc.dag still
        reads node.depends_on directly for the actual scheduling algorithm —
        this is the typed form for introspection/serialization (epc.ir.v1.serializer)."""
        return [
            DependencyEdge(source=dep_id, target=node.id)
            for node in self.nodes.values()
            for dep_id in sorted(node.depends_on)
        ]

    def compute_hashes(self, order: list[str]) -> None:
        """Content-hash each node, including its already-computed dependency hashes,
        so a change anywhere upstream changes every downstream hash too.

        `order` must be a topological order (see epc.dag.topological_batches) —
        a node's dependencies must be hashed before the node itself.

        The `deps` payload is `(dep_id, dep_hash)` pairs, not bare hash values.
        Two structurally-identical-but-differently-named dependencies (e.g. a
        renamed secret with unchanged properties) produce the same hash value,
        so hashing only the *values* makes a node's hash blind to which
        specific node it actually depends on -- a real decision-correctness
        bug, not just a cosmetic one: ProviderLowering would silently SKIP a
        node whose wiring changed to point at a different resource, as long
        as that resource happened to hash the same. Pairing each hash with
        its dependency id closes that: the payload differs whenever the
        dependency SET differs, regardless of whether the values collide.
        """
        for node_id in order:
            node = self.nodes[node_id]
            dep_hashes = sorted((dep, self.nodes[dep].hash) for dep in node.depends_on)
            payload = json.dumps(
                {"capability": node.capability, "properties": node.properties, "deps": dep_hashes},
                sort_keys=True,
                default=str,
            )
            node.hash = hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class ExecutionBatch:
    """One topological batch — every node in it has all its dependencies
    already satisfied and can run in parallel with the rest of the batch."""

    index: int
    node_ids: list[str]


@dataclass
class ExecutionPlan:
    """The typed form of what epc.dag.topological_batches computes. epc.pipeline
    still consumes the raw `list[list[str]]` batches directly (see
    epc.ir.v1.graph.to_execution_plan for the conversion) — kept separate so
    changing this shape doesn't ripple through the dispatch loop until a real
    consumer (the control plane's Scheduler, architecture doc §05) needs it."""

    batches: list[ExecutionBatch]

    @property
    def ordered_node_ids(self) -> list[str]:
        return [node_id for batch in self.batches for node_id in batch.node_ids]


def to_execution_plan(batches: list[list[str]]) -> ExecutionPlan:
    return ExecutionPlan(batches=[ExecutionBatch(index=i, node_ids=b) for i, b in enumerate(batches)])


@dataclass
class Checkpoint:
    """A named, point-in-time snapshot of a graph's node hashes — the typed
    shape of what epc.statestore's JSON manifest already captures ad hoc.

    ponytail: not yet wired into epc.pipeline (compile_spec still reads/writes
    the raw manifest dict via epc.statestore) — this is the shape that
    manifest will migrate to once a real State Store (architecture doc §05)
    replaces the single JSON file.
    """

    id: str
    node_hashes: dict[str, str]
