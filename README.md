# Enterprise Platform Compiler

Open-source-first platform compiler: a `PlatformSpec` compiles through a real
pipeline (parse → AST → normalized IR → dependency graph) before any
provider — OpenTofu, Terraform Cloud, Vault, ServiceNow, whatever — is
called. Providers are the codegen backend; they are not the compiler.

Full architecture: see `docs/architecture.html` (design doc, not yet
committed here — currently lives in the design conversation as two
artifacts: the IaC Agent TDD and the Enterprise Platform Compiler
architecture v0.2).

## Compiler Explainability Contract

> For every compiler decision, `epc.explain` must be able to reconstruct the
> causal path from persisted compiler artifacts (the manifest — hash,
> properties, dependency edges — plus the current `IRGraph`) alone. **An
> explanation that disagrees with the decision it's explaining is a compiler
> defect**, not an edge case to note and move past.

This isn't aspirational. It's the rule that was already broken once: the
first version of `explain_recompile` correctly detected that removing a
dependency edge changed a node's hash (`ProviderLowering` recompiled it,
correctly), but the explanation walked only *current* dependencies asking
"did this one change," which structurally cannot see an edge that no longer
exists — so it reported `recompiled = False` for a node the pipeline had
just recompiled. Caught before shipping by reasoning through a suggested
test case, not by a user filing a bug. Fixed in `epc.explain`
(`removed_dependencies`/`added_dependencies` diffed against the manifest's
persisted `depends_on`, not inferred from a per-dependency hash walk); see
`tests/test_explain.py` and `tests/test_cascading_removal.py` for the
regression coverage, and `tests/test_determinism.py` for the two invariants
this contract also implies — compiling the same spec twice must produce
byte-identical manifests and plans, and every node in a true no-op
recompile must agree between the top-level `skipped` list and its own
`--explain` verdict.

**A second, more serious violation — this one a decision bug, not just an
explanation bug — surfaced by stress-testing a rename** (`tests/fixtures`
has no rename tracking; a rename is legitimately "remove the old id, add a
new one"). `IRGraph.compute_hashes` folded a node's dependencies down to
*bare hash values* (`sorted(dep.hash for dep in depends_on)`). Two
structurally-identical-but-differently-named dependencies (same capability,
same properties — e.g. a secret renamed with its rotation policy
unchanged) hash identically, so a node "rewired" from the old id to the new
one hashed **the same before and after** — `ProviderLowering` would have
silently skipped a resource whose actual wiring changed, as long as the new
target happened to hash the same as the old one. This is the pipeline
producing a wrong *decision*, not a wrong explanation of a right one — the
more serious class. Fixed by hashing `(dep_id, dep_hash)` pairs instead of
bare hash values, so the payload differs whenever the dependency *set*
differs regardless of value collisions
(`tests/test_ir.py::test_a_node_hash_distinguishes_which_specific_dependency_it_points_at`,
`tests/test_rename_semantics.py`,
`tests/test_explanation_completeness.py::test_rename_agrees_for_every_node`).

**Explanation Completeness** (the general form of the contract above, not
just the property/dependency-edge cases that motivated it):
`tests/test_explanation_completeness.py` doesn't test one hand-picked node —
for every fixture pair, it iterates every node in the compiled graph and
asserts `(node_id in result.plans) == explain_recompile(...).recompiled`
holds for *all* of them. This is the test that would have caught the first
violation above without anyone having to think of "removed dependency" as a
specific scenario first — the discipline going forward is to prefer this
shape of test (agreement across every node) over one-node spot checks
whenever a fixture pair already exists.

**Graph Identity Invariant**, the general principle the hash-collision fix
above is one instance of:

> A node's identity (its id) is part of compiler semantics, not incidental
> to it. Two nodes with identical properties but different identities are
> not interchangeable — depending on one instead of the other is a real
> change, whether or not either node's own content differs.

The rename case (`tests/test_rename_semantics.py`) and a second, structurally
distinct case — swapping between two *already-coexisting*, identically-shaped
resources (`tests/test_dependency_swap.py`, `compute.app` switching from
`compute.primary` to `compute.replica`, both present and unchanged before and
after) — both had to be checked, not assumed identical, because they exercise
different code inside `explain_recompile`: a rename's new target is genuinely
new (`caused_by`'s `is_new` branch catches it), while a swap's new target
already exists with an unchanged hash (only the `added_dependencies`/
`removed_dependencies` set-difference path catches it). Both are confirmed
correct through the real pipeline, not just `explain`, with an explicit
precondition check that the swapped resources really do hash identically in
isolation — otherwise the test would pass for the wrong reason (a real
property difference) instead of proving graph identity is respected.

## Current scope: pass-manager compiler + frozen IR v1 + config-driven providers

Pipeline stages implemented:

1. **Parse** — YAML `PlatformSpec` → AST (`epc.ast`)
2. **Normalize + Resolve References** — AST → `IRGraph` (`epc.normalizer`,
   `epc.symboltable`); undefined references are compile errors
3. **Optimization passes** (`epc.passes`, see below) — a `PassManager` runs an
   ordered list of `CompilerPass`es, each consuming the previous one's output
   graph
4. **Batch planning** — topological batches, cycle detection (`epc.dag`,
   wrapped as `epc.passes.BatchPlanner`)
5. **Provider lowering, config-driven** (`epc.passes.ProviderLowering`) —
   each IR node is handed to whatever `Provider` is registered for its
   `capability`, resolved from a `providers:` YAML config (`epc.config`) — a
   capability not listed defaults to the fake provider. Two implementations
   exist:
   - `providers/fake` — echoes back a `Plan`, no external process
   - `providers/terraform_cli` — a real OpenTofu/Terraform CLI adapter.
     **`validate()` and `plan()` only — `apply()` is intentionally
     `NotImplementedError`.** Every IR node lowers to one `terraform_data`
     resource (built into the binary, no plugin download, no network, no
     credentials), so the adapter proves subprocess execution, JSON
     (de)serialization, error handling, and version detection against a
     real CLI with zero infrastructure risk. *How* a node becomes that
     provider's shape stays inside the provider (`TerraformCliProvider._lower`)
     — `ProviderLowering` only decides *when* to call it; see the module
     docstring for why that split is what keeps provider-specific fields out
     of the generic IR.

   `python -m epc compile spec.yaml --providers config.yaml` runs this for
   real — not just in tests. `tests/test_provider_swap.py` and
   `tests/test_cli.py` both prove `registry.resolve()` actually branches:
   same IR, same batches, only the resolved provider and its `Plan` differ.
6. **Incremental compilation** — pass `--manifest <path>` (or
   `manifest_path=` to `compile_spec`) and a node whose content hash matches
   the previous compile is skipped entirely (`ProviderLowering`, no
   `validate()`, no `plan()` call). A node's hash already folds in its
   resolved dependencies' hashes, so this alone is enough to detect "this
   node or anything upstream of it changed" (`epc.statestore`,
   `tests/test_incremental.py`)

### Optimization passes (`epc/passes/`)

```
epc/passes/
  base.py                        CompilerPass ABC: run(graph) -> IRGraph
  manager.py                     PassManager — runs an ordered pass list
  validation.py                  ValidationPass — wraps epc.ir.validate_graph
  dead_node_elimination.py       removes properties.enabled: false nodes
  dependency_simplification.py   transitive reduction of depends_on edges
  batch_planning.py              BatchPlanner — not a CompilerPass (produces
                                  an ExecutionPlan, not an IRGraph)
  provider_lowering.py           ProviderLowering — not a CompilerPass either
                                  (produces Plans, has side effects)
```

`DEFAULT_PASSES` (`epc/passes/__init__.py`): `[ValidationPass,
DeadNodeEliminationPass, DependencySimplificationPass, ValidationPass]` — the
second `ValidationPass` is a cheap self-check that catches anything the two
structural passes broke (e.g. disabling a node something else still depends
on) before batch planning or a provider ever sees the graph. There's no
`PolicyPass` in this list yet — no policy engine exists to expand against, so
a no-op class would be exactly the kind of speculation IR v1's traits
decision argued against: no consumer, no pass.

`BatchPlanner` and `ProviderLowering` deliberately aren't `CompilerPass`es —
their outputs (`ExecutionPlan`, `Plan` objects with real side effects) aren't
an `IRGraph`, and forcing them into that shape for symmetry would misrepresent
what they do. `epc/passes/base.py`'s docstring explains the split.

**Found, not just refactored:** `DependencySimplificationPass` revealed that
the architecture doc's own worked "fan-in" example — `unityCatalog`
depending directly on both `databricks` and `dataLake` — was never a genuine
fan-in. `dataLake` is already reachable via `databricks → firewall →
privateEndpoint → dataLake`, so that direct edge is provably redundant; the
pass correctly collapses it (`tests/test_passes.py`,
`tests/test_analysis.py`). That's a pass operating on graph semantics, not
syntax — the actual test of whether "optimization pass" is doing real work
or just relabeling.

### Analysis passes (`epc/passes/analysis.py` and friends)

Distinct from `CompilerPass` the same way LLVM/MLIR separate transformation
passes from analysis passes: an `AnalysisPass` observes an `IRGraph` and
returns an `AnalysisResult` — never mutates the graph, never changes what
compiles. Two exist:

- **`CriticalPathPass`** — longest dependency chain by node count, computed
  bottom-up with memoization (`depth(node) = 1 + max(depth(dep) for dep in
  node.depends_on)`). Correctly agrees with the result on a
  not-yet-simplified graph, since `max()` already ignores a shorter
  redundant edge on its own.
- **`GraphStatisticsPass`** — node/edge counts, per-kind breakdown, max
  fan-in/fan-out.

Neither runs by default — `compile_spec(..., analyses=[...])` or the CLI's
`--analyze` flag opt in. Nothing downstream consumes an analysis result yet
(no bounded worker pool for `CriticalPathPass` to help schedule against), so
running one unconditionally on every compile would be overhead with no
payoff — the same "no consumer, no default" reasoning `DEFAULT_PASSES`
already applies to a hypothetical `PolicyPass`.

```bash
python -m epc compile tests/fixtures/data_platform.yaml --analyze
```

### Demo: why this beats a naive execution engine

`tests/fixtures/parallel_demo.yaml` is built specifically to show what a
near-linear fixture like `data_platform.yaml` can't: real batch parallelism
(three independent nodes — `bucket1`, `bucket2`, `dbPassword` — share one
batch) and a genuine transitive-reduction case (`appServer`'s direct edge to
`vpc` is redundant once `bucket1`/`bucket2`/`dbPassword` already reach it).
`examples/generate_demo_data.py` computes the real numbers —
`naive_sequential_steps: 6` vs `batched_steps: 4`, one edge removed, a
4-hop critical path — and `tests/test_parallel_demo.py` asserts the same
numbers, so the demo and the regression test can't drift apart.

```bash
python examples/generate_demo_data.py
```

### Demo: "What changed?" — an incremental compilation report

`tests/fixtures/incremental_before.yaml` / `incremental_after.yaml` are the
same 7-node graph one commit apart: `dbPassword.rotation` changed 90 → 30,
`network.oldVnet` was removed, `storage.archive` was added.
`examples/generate_incremental_report.py` compiles both against the same
manifest file, through the real pipeline, and reports the compiler's
decision — not a cache-hit-rate number, which nodes it actually recompiled
and why. The interesting case: `appServer` and `catalog` were never edited,
but recompile anyway because `dbPassword`'s new hash propagates through them
(`IRGraph.compute_hashes`) — while `bucket1`/`bucket2`, siblings of
`dbPassword` that don't depend on it, are reused. `tests/test_incremental_report.py`
asserts all of this against the same two fixtures.

```bash
python examples/generate_incremental_report.py
```

### Demo: "Why was this recompiled?" — a compiler reasoning trace

`epc.explain.explain_recompile(previous, after, node_id)` walks the causal
chain behind a recompile decision: a node's own properties changed, a
dependency's hash changed (recurse into that dependency), or it's new. Not a
`CompilerPass` or `AnalysisPass` — both operate on one `IRGraph`, and this
needs a *previous* state to compare against.

**Works across two separate CLI invocations**, not just within one process:

```bash
python -m epc compile spec.yaml --manifest m.json                          # run 1
python -m epc compile spec.yaml --manifest m.json --explain compute.appServer  # run 2
```
```
Compiler Reasoning Trace

Target
  compute.appServer

Decision
  RECOMPILED

Pipeline stages
  [ok] Validation                 graph is structurally valid
  [=]  Dependency Simplification  no edges changed for this node
  [!]  Incremental Analysis       dependency hash changed (secret.dbPassword)
  [->] Batch Planning             assigned to batch 3
  [->] Provider Lowering          fake provider selected, plan generated

Causal trace
  compute.appServer  (depends on changed: secret.dbPassword)
    secret.dbPassword  (edited: rotation: 90 -> 30)
```

This required extending `epc.statestore`'s manifest from `{node_id: hash}`
to `{node_id: {hash, properties, depends_on}}` — not a new State Store
subsystem, fields persisted alongside the hash already being written. That's
enough for `PreviousNodeState` (`epc.explain`) to reconstruct "this node's
own properties changed" vs. "a dependency's hash changed" vs. "a dependency
edge was added or removed" from a manifest file alone, with no previous
`IRGraph` in memory. `previous_state_from_graph` (in-process, two compiled
graphs — what `examples/generate_explain_report.py` uses) and
`previous_state_from_manifest` (loaded from disk — what the CLI uses)
produce the identical `PreviousState` shape and are asserted equivalent in
`tests/test_explain.py`.

**A real bug this surfaced, caught before shipping rather than after:** the
first version only compared each *current* dependency's hash against its
previous hash — walking `node.depends_on` and asking "did this one change."
That misses a dependency edge being added or removed entirely: wiring
`compute.app` to an existing, otherwise-untouched `network.z` changes
`app`'s hash (its dependency-hash list is now longer) without changing
`z`'s hash at all, so the per-dependency walk never visits the actual cause
and reports `recompiled = False` — directly contradicting what the real
pipeline does (it correctly recompiles `app`, since `app`'s own hash
changed). Fixed by diffing the dependency *set* against the manifest's
persisted `depends_on`, not just re-checking each current dependency's hash.
`tests/test_explain.py` locks in both directions (edge added / edge
removed) plus a YAML-key-reorder case (properties are hashed with
`sort_keys=True`, so key order was never semantic, but wasn't previously
asserted).

The `Pipeline stages` block is assembled from facts the compiler already
computed for this compile — which batch the node landed in
(`ExecutionPlan`), whether `DependencySimplificationPass` changed its edges
(compared against a fresh `normalize()` of the same spec), which provider
was resolved (`ProviderRegistry`) — not a new instrumentation layer bolted
onto the passes themselves.

```bash
python examples/generate_explain_report.py   # in-process version, no CLI/manifest needed
```

### IR v1 — frozen and versioned (`epc/ir/v1/`)

The IR is the compiler's ABI: every provider, every future optimization
pass, and any future non-YAML frontend depends on this shape, so it's a
versioned package, not a module that happens to hold some dataclasses.

**Two separate axes per node, not one:**

- `kind` (`NodeKind`) — a small, closed enum of infrastructure *primitives*:
  `compute`, `storage`, `network`, `identity`, `secret`, `data-platform`,
  `service`, `workflow`, `policy`, `extension`. What the DAG, the scheduler,
  and optimization passes reason about. Frozen — a tenth kind is an IR v2
  decision.
- `capability` (`str`) — an open, growing vocabulary of *what the node does*:
  `"storage"`, `"monitoring"`, `"gitops"`, `"governance"`, whatever a
  provider registry knows how to resolve. What providers dispatch on.
  Extensible — adding a capability never touches a type.

`ServiceNode` is deliberately broad: monitoring, logging, catalog,
service-discovery, artifact-repository, gitops, cost, ai, event-bus, and
approval all share this one kind — modeling each as its own node subclass
doesn't scale to a 20-capability platform catalog. `ExtensionNode`
(`kind=extension`) is the escape hatch: a capability the routing table
doesn't recognize compiles fine anyway instead of failing, which is what
keeps IR v1 frozen while the capability catalog keeps growing. The
capability → kind routing table lives in `epc/capabilities.py`, deliberately
*outside* the `ir` package — it's compiler policy, not part of the frozen
ABI, and grows independently of it.

```
epc/ir/v1/
  nodes.py        NodeKind enum + IRNode base + 9 explicit kinds (Compute,
                   Storage, Network, Identity, Secret, DataPlatform, Service,
                   Workflow, Policy) + ExtensionNode — capability is a real,
                   open field, independent of which kind subclass it's on
  edges.py         Edge base + DependencyEdge (populated), PolicyEdge,
                   DataFlowEdge, ExecutionEdge (typed, not yet constructed —
                   add call sites when a pass needs to distinguish them)
  graph.py         IRGraph, ExecutionBatch, ExecutionPlan, Checkpoint
  schema.py        IR_VERSION = "1.0"
  serializer.py    to_dict/from_dict/to_json/from_json — kind and capability
                    persisted separately, IR_VERSION-stamped, rejects a
                    mismatched version rather than guessing
  validator.py     structural checks (dangling deps) independent of the
                   normalizer, for IR arriving from outside this process

epc/capabilities.py   CAPABILITY_KINDS routing table (open, hand-maintained
                       for now) + kind_for_capability/node_class_for —
                       intentionally outside epc.ir, see module docstring
```

`epc.ir` re-exports the current version's public API, so bumping the active
version later is a one-line change there instead of a repo-wide import
rewrite (`from epc.ir import StorageNode`, not `from epc.ir.v1.nodes import
StorageNode`, everywhere outside the `ir` package itself).

**What IR v1 freezes, and what stays deliberately open:**

| Frozen (an IR v2 decision to change) | Extensible (changes anytime) |
|---|---|
| Graph structure, node identity | Capability names |
| Dependency model | Provider names |
| Execution batches, checkpoints | Resource properties/attributes |
| Serialization shape, lifecycle semantics | Service taxonomy (what's a `ServiceNode`) |

Explicitly **not** in this repo yet, in roadmap order: a provider
compliance test suite every provider must pass (including capability
negotiation instead of relying solely on `NotImplementedError`), wiring
`CriticalPathPass` into a scheduler once a bounded worker pool exists to
make ordering-within-a-batch matter, pass metadata (`requires`/
`invalidates`, so a future `PassManager` can skip recomputing an analysis
nothing downstream touched — deliberately unbuilt until a second analysis
pass creates a real dependency to track), a provider-lowering *pipeline*
(generic IR → canonical provider IR → provider-specific IR, letting
optimization happen after lowering too — an EPC v2 idea, not a v1 gap),
further optimization passes (cost, security-review — the ones that will
likely need the traits system explicitly deferred in
`epc/ir/v1/nodes.py`), control plane (API/Scheduler/Queue/Worker), state
manager, reconciliation, event bus, multi-agent AI passes (the natural next
`CompilerPass`/`AnalysisPass` implementations — neither interface cares
whether `run()` is deterministic or calls an LLM), SDK/ecosystem tooling.
`apply()` stays disabled on every provider until its own phase explicitly
lifts that gate.

## Run the tests

```bash
pip install -e ".[dev]"
pytest
```

## Run the compiler by hand

```bash
# fake provider everywhere (default)
python -m epc compile tests/fixtures/data_platform.yaml

# real OpenTofu/Terraform CLI for storage, fake for everything else
python -m epc compile tests/fixtures/data_platform.yaml --providers examples/providers/mixed.yaml

# incremental compilation
python -m epc compile tests/fixtures/data_platform.yaml --manifest /tmp/epc-manifest.json
python -m epc compile tests/fixtures/data_platform.yaml --manifest /tmp/epc-manifest.json  # second run: everything skipped

# graph statistics + critical path
python -m epc compile tests/fixtures/data_platform.yaml --analyze
```

## Layout

```
src/epc/                     compiler frontend — parser, ast, symboltable, normalizer, dag, provider, capabilities, config, statestore, pipeline, cli
src/epc/ir/v1/                 frozen, versioned IR — nodes, edges, graph, schema, serializer, validator
src/epc/passes/                PassManager, CompilerPass implementations, BatchPlanner, ProviderLowering
providers/fake/               a fake Provider implementation, used by tests and as the CLI default
providers/terraform_cli/      real OpenTofu/Terraform CLI adapter — validate/plan only, apply disabled
examples/providers/           example `providers:` config files for --providers
examples/generate_demo_data.py  real before/after/critical-path/batching numbers for the demo fixture
tests/                        one module per pipeline stage, the IR package, capability routing, passes, analysis passes, the parallel-demo fixture, incremental compilation, provider swap, config resolution, and the CLI end to end
```
