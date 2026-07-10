"""Explains *why* a node recompiled between two compiles -- the causal trace
behind epc.pipeline's recompile/reuse decision.

Not a CompilerPass or AnalysisPass: both operate on one IRGraph, and this
needs two (the previous compile's graph and the current one) to tell "own
properties changed" apart from "a dependency's hash changed, so mine did
too." epc.statestore's manifest only persists hashes, not full previous node
state, so this only works within one process holding both compiled IRGraphs
in memory (see examples/generate_explain_report.py) -- it is deliberately
not wired into the CLI's separate-process --manifest flow, where the
previous graph's properties genuinely aren't available to reconstruct.
Wiring that up is real future work (a State Store that persists more than
hashes, per the architecture doc's Checkpoint direction), not done here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ir import IRGraph


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


def explain_recompile(before: IRGraph, after: IRGraph, node_id: str) -> ChangeReason:
    after_node = after.nodes[node_id]

    if node_id not in before.nodes:
        return ChangeReason(node_id=node_id, is_new=True)

    before_node = before.nodes[node_id]
    own_changed = before_node.properties != after_node.properties
    diff: dict[str, tuple[Any, Any]] = {}
    if own_changed:
        keys = set(before_node.properties) | set(after_node.properties)
        diff = {
            key: (before_node.properties.get(key), after_node.properties.get(key))
            for key in keys
            if before_node.properties.get(key) != after_node.properties.get(key)
        }

    # ponytail: re-explains a shared dependency once per path that reaches it
    # (no memoization) -- fine at this scale, would matter on a graph with
    # heavy diamond fan-in.
    caused_by = [
        explain_recompile(before, after, dep_id)
        for dep_id in sorted(after_node.depends_on)
        if dep_id not in before.nodes or before.nodes[dep_id].hash != after.nodes[dep_id].hash
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
