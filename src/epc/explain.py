"""Explains *why* a node recompiled between two compiles -- the causal trace
behind epc.pipeline's recompile/reuse decision.

Not a CompilerPass or AnalysisPass: both operate on one IRGraph, and this
needs a *previous* state to compare the current graph against, to tell "own
properties changed" apart from "a dependency's hash changed, so mine did
too" apart from "the dependency edges themselves changed." That previous
state can come from two places, both producing the same PreviousState shape:

- an in-memory IRGraph from an earlier compile in the same process
  (previous_state_from_graph -- what examples/generate_explain_report.py uses)
- a manifest loaded from disk (previous_state_from_manifest -- what
  epc.cli's --explain flag uses, across two separate `epc compile`
  invocations)

epc.statestore persists {hash, properties, depends_on} per node specifically
so the manifest-backed path works without needing the full previous IRGraph
in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ir import IRGraph


@dataclass
class PreviousNodeState:
    hash: str
    properties: dict[str, Any]
    depends_on: set[str] = field(default_factory=set)


PreviousState = dict[str, PreviousNodeState]


def previous_state_from_graph(graph: IRGraph) -> PreviousState:
    return {
        node_id: PreviousNodeState(hash=node.hash, properties=node.properties, depends_on=set(node.depends_on))
        for node_id, node in graph.nodes.items()
    }


def previous_state_from_manifest(manifest: dict[str, dict[str, Any]]) -> PreviousState:
    return {
        node_id: PreviousNodeState(
            hash=entry["hash"],
            properties=entry.get("properties", {}),
            depends_on=set(entry.get("depends_on", [])),
        )
        for node_id, entry in manifest.items()
    }


@dataclass
class ChangeReason:
    node_id: str
    is_new: bool = False
    own_properties_changed: bool = False
    property_diff: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    added_dependencies: list[str] = field(default_factory=list)
    removed_dependencies: list[str] = field(default_factory=list)
    caused_by: list["ChangeReason"] = field(default_factory=list)

    @property
    def recompiled(self) -> bool:
        return (
            self.is_new
            or self.own_properties_changed
            or bool(self.caused_by)
            or bool(self.added_dependencies)
            or bool(self.removed_dependencies)
        )


def explain_recompile(previous: PreviousState, after: IRGraph, node_id: str) -> ChangeReason:
    if node_id not in after.nodes:
        raise KeyError(
            f"{node_id!r} is not in the current compiled graph -- it was removed (or never declared), "
            "so there is no recompile decision to explain. Check epc.explain.previous_state_from_manifest's "
            "keys, or the removed_dependencies of whatever node used to depend on it, instead."
        )
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

    current_deps = set(after_node.depends_on)
    # A dependency EDGE can be added or removed without either endpoint's own
    # hash changing (e.g. wiring a node to an existing, untouched neighbor) --
    # that must be checked as a set difference, not discovered by walking
    # current_deps and asking "did this one's hash change," which silently
    # misses edges that no longer exist at all.
    added_deps = sorted(current_deps - prev.depends_on)
    removed_deps = sorted(prev.depends_on - current_deps)

    # ponytail: re-explains a shared dependency once per path that reaches it
    # (no memoization) -- fine at this scale, would matter on a graph with
    # heavy diamond fan-in.
    caused_by = [
        explain_recompile(previous, after, dep_id)
        for dep_id in sorted(current_deps)
        if dep_id not in previous or previous[dep_id].hash != after.nodes[dep_id].hash
    ]

    return ChangeReason(
        node_id=node_id,
        own_properties_changed=own_changed,
        property_diff=diff,
        added_dependencies=added_deps,
        removed_dependencies=removed_deps,
        caused_by=caused_by,
    )


def render_trace(reason: ChangeReason, indent: int = 0) -> str:
    pad = "  " * indent
    if reason.is_new:
        line = f"{pad}{reason.node_id}  (new node)"
    elif reason.own_properties_changed:
        diff_str = ", ".join(f"{key}: {b!r} -> {a!r}" for key, (b, a) in reason.property_diff.items())
        line = f"{pad}{reason.node_id}  (edited: {diff_str})"
    elif reason.caused_by or reason.added_dependencies or reason.removed_dependencies:
        parts = []
        if reason.caused_by:
            parts.append(f"depends on changed: {', '.join(c.node_id for c in reason.caused_by)}")
        if reason.added_dependencies:
            parts.append(f"added dependency: {', '.join(reason.added_dependencies)}")
        if reason.removed_dependencies:
            parts.append(f"removed dependency: {', '.join(reason.removed_dependencies)}")
        line = f"{pad}{reason.node_id}  ({'; '.join(parts)})"
    else:
        line = f"{pad}{reason.node_id}  (unchanged)"

    lines = [line]
    for cause in reason.caused_by:
        lines.append(render_trace(cause, indent + 1))
    return "\n".join(lines)
