"""IRGraph <-> dict/JSON, with IR_VERSION embedded on every serialized graph —
the compiler's ABI has to be checkable by whatever reads it, not just by
whatever wrote it.
"""

from __future__ import annotations

import json
from typing import Any

from .graph import IRGraph
from .nodes import node_class_for
from .schema import IR_VERSION


class UnsupportedIRVersionError(ValueError):
    def __init__(self, found: str):
        self.found = found
        super().__init__(f"IR version '{found}' is not supported (this package handles '{IR_VERSION}')")


def to_dict(graph: IRGraph) -> dict[str, Any]:
    return {
        "ir_version": IR_VERSION,
        "nodes": [
            {
                "kind": node.capability,
                "id": node.id,
                "properties": node.properties,
                "depends_on": sorted(node.depends_on),
                "hash": node.hash,
            }
            for node in graph.nodes.values()
        ],
    }


def from_dict(data: dict[str, Any]) -> IRGraph:
    version = data.get("ir_version")
    if version != IR_VERSION:
        raise UnsupportedIRVersionError(str(version))

    nodes = {}
    for entry in data["nodes"]:
        node_cls = node_class_for(entry["kind"])
        nodes[entry["id"]] = node_cls(
            id=entry["id"],
            properties=entry.get("properties", {}),
            depends_on=set(entry.get("depends_on", [])),
            hash=entry.get("hash"),
        )

    for node in nodes.values():
        for dep_id in node.depends_on:
            nodes[dep_id].depended_on_by.add(node.id)

    return IRGraph(nodes=nodes)


def to_json(graph: IRGraph, **kwargs: Any) -> str:
    return json.dumps(to_dict(graph), sort_keys=True, **kwargs)


def from_json(data: str) -> IRGraph:
    return from_dict(json.loads(data))
