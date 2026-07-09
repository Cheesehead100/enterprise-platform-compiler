"""Compile-time errors, one per pipeline stage that can fail (architecture doc §03)."""


class CompileError(Exception):
    """Base class for every error the pipeline can raise before a provider is touched."""


class ParseError(CompileError):
    """Stage 1 — malformed PlatformSpec YAML."""


class SchemaError(CompileError):
    """Stage 2 — spec parses but violates the minimal PlatformSpec shape."""


class UndefinedReferenceError(CompileError):
    """Stage 5 — a `ref:` points at a node or spec field that doesn't exist. The linker error."""

    def __init__(self, node_id: str, ref_path: str):
        self.node_id = node_id
        self.ref_path = ref_path
        super().__init__(f"{node_id}: undefined reference '{ref_path}'")


class CycleError(CompileError):
    """Stage 8 — the dependency graph is not acyclic."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"dependency cycle: {' -> '.join(cycle)}")


class UnknownCapabilityError(CompileError):
    """Stage 9 — no provider is registered for a node's capability."""

    def __init__(self, node_id: str, capability: str):
        self.node_id = node_id
        self.capability = capability
        super().__init__(f"{node_id}: no provider registered for capability '{capability}'")
