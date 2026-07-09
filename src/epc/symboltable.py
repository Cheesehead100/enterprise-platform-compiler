"""Symbol table used by Resolve References (architecture doc §02).

An undefined reference is caught here, before any provider is called —
the compiler's equivalent of an undefined-variable linker error.
"""

from __future__ import annotations

from typing import Any

from .ast import ResourceNode
from .errors import UndefinedReferenceError


class SymbolTable:
    def __init__(self, spec_properties: dict[str, Any]):
        self._spec_properties = spec_properties
        self._nodes: dict[str, ResourceNode] = {}

    def register(self, node: ResourceNode) -> None:
        self._nodes[node.id] = node

    def node_exists(self, node_id: str) -> bool:
        return node_id in self._nodes

    def resolve(self, from_node_id: str, path: str) -> Any:
        """Resolve a Ref path: 'spec.<key>' looks up spec properties, anything else
        must be an existing node id (an implicit dependency edge, per §02)."""
        if path.startswith("spec."):
            key = path.removeprefix("spec.")
            if key not in self._spec_properties:
                raise UndefinedReferenceError(from_node_id, path)
            return self._spec_properties[key]

        if path not in self._nodes:
            raise UndefinedReferenceError(from_node_id, path)
        return path  # the referenced node id — caller adds it as a dependency edge
