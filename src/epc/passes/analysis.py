"""AnalysisPass: observes the graph, never mutates it. Distinct from
CompilerPass on purpose -- the same split LLVM/MLIR make between
transformation passes and analysis passes. Forcing an analysis to return an
IRGraph would either lose its actual output (a critical path, a node count)
or force callers to smuggle it in as a graph annotation. The only shared
contract across analyses is "doesn't change what compiles" -- each defines
its own AnalysisResult shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from ..ir import IRGraph


@dataclass
class AnalysisResult:
    """Marker base -- each analysis pass defines its own result shape."""


class AnalysisPass(ABC):
    name: ClassVar[str]

    @abstractmethod
    def run(self, graph: IRGraph) -> AnalysisResult: ...
