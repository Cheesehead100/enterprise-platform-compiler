from .analysis import AnalysisPass, AnalysisResult
from .base import CompilerPass
from .batch_planning import BatchPlanner
from .critical_path import CriticalPathPass, CriticalPathResult
from .dead_node_elimination import DeadNodeEliminationPass
from .dependency_simplification import DependencySimplificationPass
from .graph_statistics import GraphStatistics, GraphStatisticsPass
from .manager import PassManager
from .provider_lowering import LoweringResult, ProviderLowering
from .validation import ValidationPass

# Pass 1: Validation
# Pass 2: Dead Node Elimination
# Pass 3: Dependency Simplification
# Pass 4: Validation again -- cheap, and catches anything passes 2-3 broke
#         (e.g. a disabled node something else still depends on) before it
#         ever reaches batch planning or a provider.
#
# Policy Expansion has no slot here yet -- there's no policy engine to expand
# against (see epc.normalizer's identity-pass note). Adding a no-op
# PolicyPass class just to complete the picture would be exactly the kind of
# speculation IR v1's traits decision argued against: no consumer, no pass.
DEFAULT_PASSES: list[CompilerPass] = [
    ValidationPass(),
    DeadNodeEliminationPass(),
    DependencySimplificationPass(),
    ValidationPass(),
]

__all__ = [
    "CompilerPass",
    "PassManager",
    "ValidationPass",
    "DeadNodeEliminationPass",
    "DependencySimplificationPass",
    "BatchPlanner",
    "ProviderLowering",
    "LoweringResult",
    "DEFAULT_PASSES",
    "AnalysisPass",
    "AnalysisResult",
    "CriticalPathPass",
    "CriticalPathResult",
    "GraphStatisticsPass",
    "GraphStatistics",
]
