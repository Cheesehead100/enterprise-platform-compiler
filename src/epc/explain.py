"""Explains *why* a node recompiled between two compiles -- the causal trace
behind epc.pipeline's recompile/reuse decision.

Not a CompilerPass or AnalysisPass: both operate on one IRGraph, and this
needs a *previous* state to compare the current graph against, to tell "own
properties changed" apart from "a dependency's hash changed, so mine did
too." That previous state can come from two places, both producing the same
PreviousState shape:

- an in-memory IRGraph from an earlier compile in the same process
  (previous_state_from_graph -- what examples/generate_explain_report.py uses)
- a manifest loaded from disk (previous_state_from_manifest -- what
  epc.cli's --explain flag uses, across two separate `epc compile`
  invocations)

epc.statestore persists {hash, properties} per node specifically so the
manifest-backed path works without needing the full previous IRGraph in
memory -- explaining a recompile across CLI invocations doesn't require any
richer State Store than what already exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ir import IRGraph


@dataclass
class PreviousNodeState:
    hash: str
    properties: dict[str, Any]


PreviousState = dict[str, PreviousNodeState]


def previous_state_from_graph(graph: IRGraph) -> PreviousState:
    return {node_id: PreviousNodeState(hash=node.hash, properties=node.properties) for node_id, node in graph.nodes.items()}


def previous_state_from_manifest(manifest: dict[str, dict[str, Any]]) -> PreviousState:
    return {
        node_id: PreviousNodeState(hash=entry["hash"], properties=entry.get("properties", {}))
        for node_id, entry in manifest.items()
    }


@dataclass
class ChangeReason:
    node_id: str
    is_new: bool = False
    own_properties_changed: bool = False
    property_diff: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    caused_by: list["ChangeReason"] = field(default_factory=list)

    @property
    def recompiled(self) -> bool:
        return self.is_new or self.own_properties_changed or bool(self.caused_by)


def explain_recompile(previous: PreviousState, after: IRGraph, node_id: str) -> ChangeReason:
    after_node = after.nodes[node_id]

    if node_id not in previous:
        return ChangeReason(node_id=node_id, is_new=True)

    prev = previous[node_id]
    own_changed = prev.properties != after_node.properties
    diff: dict[str, tuple[Any, Any]] = {}
    if own_changed:
        keys = set(prev.properties) | set(after_node.properties)
        diff = {
            key: (prev.properties.get(key), after_node.properties.get(key))
            for key in keys
            if prev.properties.get(key) != after_node.properties.get(key)
        }

    # ponytail: re-explains a shared dependency once per path that reaches it
    # (no memoization) -- fine at this scale, would matter on a graph with
    # heavy diamond fan-in.
    caused_by = [
        explain_recompile(previous, after, dep_id)
        for dep_id in sorted(after_node.depends_on)
        if dep_id not in previous or previous[dep_id].hash != after.nodes[dep_id].hash
    ]

    return ChangeReason(node_id=node_id, own_properties_changed=own_changed, property_diff=diff, caused_by=caused_by)


def render_trace(reason: ChangeReason, indent: int = 0) -> str:
    pad = "  " * indent
    if reason.is_new:
        line = f"{pad}{reason.node_id}  (new node)"
    elif reason.own_properties_changed:
        diff_str = ", ".join(f"{key}: {b!r} -> {a!r}" for key, (b, a) in reason.property_diff.items())
        line = f"{pad}{reason.node_id}  (edited: {diff_str})"
    elif reason.caused_by:
        deps = ", ".join(c.node_id for c in reason.caused_by)
        line = f"{pad}{reason.node_id}  (depends on changed: {deps})"
    else:
        line = f"{pad}{reason.node_id}  (unchanged)"

    lines = [line]
    for cause in reason.caused_by:
        lines.append(render_trace(cause, indent + 1))
    return "\n".join(lines)
