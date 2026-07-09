"""Not a CompilerPass -- its output is an ExecutionPlan, not an IRGraph, so
forcing it into that interface would misrepresent what it does (see
epc.passes.base's module docstring). It's still a distinct, named,
independently-testable stage: "parallel batch detection" over the graph the
optimization passes produced.

Thin wrapper: epc.dag.topological_batches already computes exactly this;
this just gives the stage a name in the pass pipeline and returns the typed
ExecutionPlan (epc.ir.v1.graph) instead of a bare list of lists.
"""

from __future__ import annotations

from ..dag import topological_batches
from ..ir import ExecutionPlan, IRGraph, to_execution_plan


class BatchPlanner:
    def plan(self, graph: IRGraph) -> ExecutionPlan:
        return to_execution_plan(topological_batches(graph))
