"""Stage 8 — Generate DAG: topological batches + cycle detection (architecture doc §02).

ponytail: batches execute sequentially within epc.pipeline for now — real
parallel dispatch is Phase 1 (control plane / worker pool, architecture §05).
The batches themselves are already correct for that later scheduler to consume.
"""

from __future__ import annotations

from .errors import CycleError
from .ir import ResourceGraph


def topological_batches(graph: ResourceGraph) -> list[list[str]]:
    remaining = {node_id: set(node.depends_on) for node_id, node in graph.nodes.items()}
    batches: list[list[str]] = []

    while remaining:
        ready = sorted(node_id for node_id, deps in remaining.items() if not deps)
        if not ready:
            raise CycleError(_find_cycle(graph, list(remaining)))

        batches.append(ready)
        for node_id in ready:
            del remaining[node_id]
        for deps in remaining.values():
            deps.difference_update(ready)

    return batches


def _find_cycle(graph: ResourceGraph, candidates: list[str]) -> list[str]:
    """DFS from any still-blocked node to produce a human-readable cycle path."""
    visiting: set[str] = set()
    path: list[str] = []

    def dfs(node_id: str) -> list[str] | None:
        if node_id in visiting:
            return path[path.index(node_id) :] + [node_id]
        visiting.add(node_id)
        path.append(node_id)
        for dep_id in graph.nodes[node_id].depends_on:
            found = dfs(dep_id)
            if found:
                return found
        path.pop()
        visiting.discard(node_id)
        return None

    for start in candidates:
        cycle = dfs(start)
        if cycle:
            return cycle
    return candidates  # unreachable in practice, but keeps the error non-empty
