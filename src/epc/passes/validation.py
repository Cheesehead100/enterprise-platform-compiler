"""Pass 1 (and re-run after structural passes, see epc.passes.DEFAULT_PASSES):
wraps epc.ir.validate_graph so structural corruption is a pass failure with a
clear message, not a mysterious downstream KeyError three stages later.
"""

from __future__ import annotations

from typing import ClassVar

from ..errors import GraphValidationError
from ..ir import IRGraph, validate_graph
from .base import CompilerPass


class ValidationPass(CompilerPass):
    name: ClassVar[str] = "validation"

    def run(self, graph: IRGraph) -> IRGraph:
        findings = validate_graph(graph)
        if findings:
            raise GraphValidationError(findings)
        return graph
