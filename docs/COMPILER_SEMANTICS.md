# Compiler Semantics

This is the settled reference: the rules a contributor needs to hold in
their head before touching `epc.ir`, `epc.explain`, `epc.statestore`, or
`epc.passes.ProviderLowering`, so the next change doesn't quietly break an
invariant three files away from where it's enforced.

It is not the story of how these rules were discovered. That story —
commit-by-commit, each rule earned by a real bug found through stress
testing — lives in the README's [Compiler Explainability
Contract](../README.md#compiler-explainability-contract) section. Read that
for *why*; read this for *what's true*.

**Every claim below cites a real test.** If a rule here can't be traced to a
test that would fail without it, it's a hope, not a rule — fix the doc or
write the test, don't leave the gap.

## 1. Node identity rules

- A node's identity is its `id` — `f"{capability}.{name}"` — not its
  content. `capability` is itself derived from the node's Python type
  (`type(node).kind`), never a separate field that could drift from it
  (`epc/ir/v1/nodes.py`).
- Two nodes with identical `capability` and `properties` but different `id`s
  are **not interchangeable**. Depending on one instead of the other is a
  real, hashable change, even though nothing about either node's own
  content differs.
  (`tests/test_ir.py::test_a_node_hash_distinguishes_which_specific_dependency_it_points_at`,
  `tests/test_dependency_swap.py`)
- There is no rename tracking. A rename is, structurally, "remove the old
  id, add a new one" — nothing infers that the new node is "the same
  resource" as the old one, and nothing should: EPC has no signal that would
  justify that inference. (`tests/test_rename_semantics.py`)
- There is no namespace/path concept distinct from `capability.name`. "Same
  name, different path" is not a case this model can express yet — it would
  require a new identity axis (namespace → capability → instance) that
  doesn't exist because nothing has needed it. Don't add it speculatively;
  add it when a second capability genuinely needs to disambiguate by more
  than `capability.name`.

## 2. Hash construction rules

- `IRGraph.compute_hashes` (`epc/ir/v1/graph.py`): a node's hash is
  `sha256(json({capability, properties, deps}, sort_keys=True))`, where
  `deps` is the **sorted list of `(dependency_id, dependency_hash)` pairs**
  for everything in `depends_on`.
- `deps` must pair each hash with its dependency's id. Hashing bare hash
  *values* (no id) makes a node's hash blind to *which* dependency produced
  each value — two differently-identified, identically-shaped dependencies
  collide, and a node "rewired" from one to the other hashes the same
  before and after. This was a real bug, not a hypothetical: see rule 1's
  second bullet. Fixed in commit `5ff5a39`.
- `properties` dicts are hashed with `sort_keys=True`. Key order in the
  source YAML is never semantic.
  (`tests/test_explain.py::test_reordering_yaml_keys_does_not_change_the_hash`)
- Hashing must proceed in topological order — a node's dependencies must
  already have `.hash` set before the node itself is hashed
  (`epc.dag.topological_batches` / `epc.passes.BatchPlanner` produce that
  order; `IRGraph.compute_hashes`'s docstring states the precondition).

## 3. Manifest evidence model

- `epc.statestore` persists, per node: `{hash, properties, depends_on}`.
  Not a State Store in the architecture doc's sense (no history, no
  concurrent-writer story) — just enough evidence artifacts to reconstruct
  *why* a hash changed without holding the previous `IRGraph` in memory.
- The manifest's shape grew by necessity, each addition closing a real gap,
  not added speculatively:
  1. `{hash}` — enough to decide recompile vs. reuse (`ProviderLowering`),
     not enough to explain the decision.
  2. `+ properties` — enough to tell "this node's own properties changed"
     apart from "a dependency changed," not enough to see a dependency
     *edge* being added or removed.
  3. `+ depends_on` — closes that: a dependency set can be diffed directly
     against what the manifest recorded, instead of inferred from
     per-dependency hash comparisons that structurally can't see an edge
     that no longer exists.
- Two ways to build the in-memory `PreviousState` (`epc.explain`), asserted
  equivalent: `previous_state_from_graph` (same process, two compiled
  graphs — what `examples/generate_explain_report.py` uses) and
  `previous_state_from_manifest` (loaded from disk — what `epc.cli`'s
  `--explain` flag uses, across two separate process invocations).
  (`tests/test_explain.py::test_previous_state_from_manifest_matches_previous_state_from_graph`)

## 4. Decision / explanation contract

> For every compiler decision, `epc.explain` must be able to reconstruct the
> causal path from persisted compiler artifacts alone. An explanation that
> disagrees with the decision it's explaining is a compiler defect.

Concretely:

- **Decision**: `node_id in CompileResult.plans` (recompiled) or
  `node_id in CompileResult.skipped` (reused) — computed by
  `ProviderLowering` from a single hash comparison against the manifest.
- **Explanation**: `explain_recompile(previous, after, node_id).recompiled`
  — computed independently, from the same persisted evidence
  (`previous_state_from_manifest` or `previous_state_from_graph`) plus the
  current `IRGraph`.
- **Invariant**: these must agree, for every node, not just the ones a given
  test happens to check. `tests/test_explanation_completeness.py` asserts
  this across every node in every fixture pair it runs — the general form,
  not a per-scenario spot check.

Both branches read the *same* evidence and are required to agree by
construction. The explanation is not a summary produced after the decision;
it's an independent computation over identical inputs.

## 5. Valid IRGraph assumptions

Everything downstream of `normalize()` — `epc.passes`, `epc.explain`,
`epc.dag` — assumes these hold, and is not re-validated on every call. They
are enforced exactly once, at the boundary:

- Every `depends_on` entry resolves to another node **within the same
  graph**. Enforced by `epc.symboltable.SymbolTable.resolve()` during
  `normalize()`. (`tests/test_missing_evidence.py::test_normalize_path_is_structurally_immune_to_this`)
- The graph is acyclic. Enforced by `epc.dag.topological_batches`.
  (`tests/test_dag.py::test_cycle_is_detected`)
- An unrecognized `capability` string is **not** a validation failure — it
  resolves to `ExtensionNode` (`kind=extension`) via `epc.capabilities`, on
  purpose (`epc.ir.v1.nodes`'s module docstring; the IR-v1-freeze design
  decision). Don't add an "unknown capability" failure mode; that would be
  reintroducing the ceiling this was built to remove.

A hand-constructed or otherwise corrupted `IRGraph` that violates the first
two assumptions is **out of contract** for any post-normalize consumer.
Public functions that might receive one anyway (`epc.explain.explain_recompile`)
must fail loudly and specifically when they detect it — see §6.

## 6. Failure modes

| Condition | Detected by | Raises |
|---|---|---|
| `dependsOn` targets an undeclared resource | `normalize()` / `SymbolTable.resolve()` | `UndefinedReferenceError` |
| Dependency cycle | `epc.dag.topological_batches` | `CycleError` |
| A node's `depends_on` references an id absent from the graph it's queried against (only reachable via a hand-built/corrupted `IRGraph` — the real compile path can't produce this) | `epc.explain.explain_recompile` | `KeyError`, missing id named explicitly |
| A disabled node (`properties.enabled: false`) is still depended on by an enabled node | `DeadNodeEliminationPass` + the second `ValidationPass` in `DEFAULT_PASSES` | `GraphValidationError` |
| No provider registered for a node's capability | `ProviderLowering` | `UnknownCapabilityError` |
| Deserializing IR at an unsupported version | `epc.ir.v1.serializer.from_dict` | `UnsupportedIRVersionError` |
| Querying `explain_recompile` for a node absent from the *current* graph (removed, or never declared) | `epc.explain.explain_recompile` | `KeyError`, with a pointer to check `removed_dependencies` on whatever depended on it instead |

Every row is deliberate: fail specifically, at the earliest point the
violation is knowable, with enough context to say what's wrong — never
silently coerce an invalid state into a plausible-looking valid one.

## 7. Invariants

Four, in the order they were established. Each has a one-line statement, a
test that enforces the general form (not just the scenario that motivated
it), and — critically — a real historical violation, because an invariant
with no violation behind it is a guess about what might go wrong, not a
documented fact about what did.

| Invariant | Statement | General test | Violation that motivated it |
|---|---|---|---|
| **Compiler Explainability Contract** | Decision and explanation must agree, always. | `tests/test_explanation_completeness.py` | Removed-dependency case reported `recompiled=False` for a node the pipeline had just recompiled (commit `6185cc4`). |
| **Explanation Completeness** | Every node's decision/explanation agreement holds individually — not just for one hand-picked node per fixture. | `tests/test_explanation_completeness.py` | Same commit; this is the generalized form of the test that would have caught it without anyone naming "removed dependency" first. |
| **Graph Identity Invariant** | A node's id is part of compiler semantics. Identical content at different ids is not interchangeable. | `tests/test_rename_semantics.py`, `tests/test_dependency_swap.py` | `IRGraph.compute_hashes` hashed bare dependency-hash values; a rewired dependency with an unchanged-hash target produced the same parent hash before and after (commit `5ff5a39`) — a wrong pipeline *decision*, not just a wrong explanation. |
| **Evidence Closure Invariant** | Every compiler decision must be derivable from evidence contained in the current `IRGraph` and the persisted manifest. Missing evidence is an error condition, never an implicit assumption (e.g. "absent means deleted"). | `tests/test_missing_evidence.py` | `explain_recompile` raised an unexplained `KeyError` when handed a graph with a dangling internal reference, instead of naming what evidence was missing (commit `2625247`). |

## Keeping this document honest

This file is not exempt from the rule it describes: every claim here must
be derivable from something the compiler actually does, checked by
something that actually runs. When a future change touches `epc.ir`,
`epc.explain`, or `epc.statestore`, the obligation is symmetric — update
whichever of {code, test, this document} has fallen out of sync with the
other two, and prefer discovering that via a failing test over discovering
it via a stale sentence here.
