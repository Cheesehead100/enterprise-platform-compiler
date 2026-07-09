# Enterprise Platform Compiler

Open-source-first platform compiler: a `PlatformSpec` compiles through a real
pipeline (parse → AST → normalized IR → dependency graph) before any
provider — OpenTofu, Terraform Cloud, Vault, ServiceNow, whatever — is
called. Providers are the codegen backend; they are not the compiler.

Full architecture: see `docs/architecture.html` (design doc, not yet
committed here — currently lives in the design conversation as two
artifacts: the IaC Agent TDD and the Enterprise Platform Compiler
architecture v0.2).

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
negotiation instead of relying solely on `NotImplementedError`), further
optimization passes (cost, security-review, parallel-scheduling-aware
passes — the ones that will likely need the traits system explicitly
deferred in `epc/ir/v1/nodes.py`), control plane (API/Scheduler/Queue/
Worker), state manager, reconciliation, event bus, multi-agent AI passes
(the natural next `CompilerPass` implementations — `CompilerPass` doesn't
care whether `run()` is deterministic or calls an LLM), SDK/ecosystem
tooling. `apply()` stays disabled on every provider until its own phase
explicitly lifts that gate.

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
```

## Layout

```
src/epc/                     compiler frontend — parser, ast, symboltable, normalizer, dag, provider, capabilities, config, statestore, pipeline, cli
src/epc/ir/v1/                 frozen, versioned IR — nodes, edges, graph, schema, serializer, validator
src/epc/passes/                PassManager, CompilerPass implementations, BatchPlanner, ProviderLowering
providers/fake/               a fake Provider implementation, used by tests and as the CLI default
providers/terraform_cli/      real OpenTofu/Terraform CLI adapter — validate/plan only, apply disabled
examples/providers/           example `providers:` config files for --providers
tests/                        one module per pipeline stage, the IR package, capability routing, passes, incremental compilation, provider swap, config resolution, and the CLI end to end
```
