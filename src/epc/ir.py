"""Normalized IR — the resource graph (architecture doc §02 'Normalized IR').

Cloud- and tool-agnostic on purpose: nothing here mentions OpenTofu, Pulumi,
or any other backend. That's what makes this the artifact every downstream
stage — optimizer, DAG builder, provider codegen, AI passes — reasons about
instead of the original YAML.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceGraphNode:
    id: str
    capability: str
    properties: dict[str, Any] = field(default_factory=dict)
    depends_on: set[str] = field(default_factory=set)
    depended_on_by: set[str] = field(default_factory=set)
    hash: str | None = None  # set once dependency hashes are known — see ResourceGraph.compute_hashes


@dataclass
class ResourceGraph:
    nodes: dict[str, ResourceGraphNode]

    def compute_hashes(self, order: list[str]) -> None:
        """Content-hash each node, including its already-computed dependency hashes,
        so a change anywhere upstream changes every downstream hash too.

        `order` must be a topological order (see epc.dag.topological_batches) —
        a node's dependencies must be hashed before the node itself.

        ponytail: hash is computed but nothing diffs it against a stored manifest
        yet — that's incremental compilation (architecture doc §02), Phase 1.
        """
        for node_id in order:
            node = self.nodes[node_id]
            dep_hashes = sorted(self.nodes[dep].hash for dep in node.depends_on)
            payload = json.dumps(
                {"capability": node.capability, "properties": node.properties, "deps": dep_hashes},
                sort_keys=True,
                default=str,
            )
            node.hash = hashlib.sha256(payload.encode()).hexdigest()
