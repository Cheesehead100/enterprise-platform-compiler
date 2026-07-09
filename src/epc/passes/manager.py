"""Runs a fixed, ordered list of CompilerPass instances, each consuming the
previous one's output graph. Deliberately not more than this yet — plugin-
contributed passes (a community pass registering itself) are a real future
extension of this class, not a reason to build a registry today for zero
current registrants.
"""

from __future__ import annotations

from ..ir import IRGraph
from .base import CompilerPass


class PassManager:
    def __init__(self, passes: list[CompilerPass]):
        self.passes = passes

    def run(self, graph: IRGraph) -> IRGraph:
        for compiler_pass in self.passes:
            graph = compiler_pass.run(graph)
        return graph
