"""Analysis pass: counts, no mutation. Cheap enough to run on every compile
if a caller asks for it (via compile_spec's `analyses=` param or the CLI's
`--analyze` flag) — not run by default because nothing downstream consumes it
yet, same reasoning as critical_path.py.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import ClassVar

from ..ir import IRGraph
from .analysis import AnalysisPass, AnalysisResult


@dataclass
class GraphStatistics(AnalysisResult):
    node_count: int
    edge_count: int
    max_fan_in: int
    max_fan_out: int
    nodes_by_kind: dict[str, int] = field(default_factory=dict)


class GraphStatisticsPass(AnalysisPass):
    name: ClassVar[str] = "graph-statistics"

    def run(self, graph: IRGraph) -> GraphStatistics:
        nodes = graph.nodes.values()
        fan_in = [len(node.depends_on) for node in nodes] or [0]
        fan_out = [len(node.depended_on_by) for node in nodes] or [0]

        return GraphStatistics(
            node_count=len(graph.nodes),
            edge_count=sum(len(node.depends_on) for node in nodes),
            max_fan_in=max(fan_in),
            max_fan_out=max(fan_out),
            nodes_by_kind=dict(Counter(type(node).kind.value for node in nodes)),
        )
