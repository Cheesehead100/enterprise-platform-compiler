"""The optimization-pass contract: consumes IR, produces IR. Every pass in
this package is independently testable and independently constructible —
that's the point of the interface, not ceremony for its own sake.

Not every pipeline stage fits this shape, on purpose. Batch planning
produces an ExecutionPlan, not an IRGraph; provider lowering produces Plan
objects and has side effects (subprocess calls, in the terraform_cli case).
Forcing those into `run(graph) -> IRGraph` would be a lie the type system
tells — see epc.passes.batch_planning and epc.passes.provider_lowering for
how those stay honest about their actual input/output shape instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..ir import IRGraph


class CompilerPass(ABC):
    name: ClassVar[str]

    @abstractmethod
    def run(self, graph: IRGraph) -> IRGraph: ...
