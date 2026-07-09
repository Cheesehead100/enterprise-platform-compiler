# Enterprise Platform Compiler

Open-source-first platform compiler: a `PlatformSpec` compiles through a real
pipeline (parse → AST → normalized IR → dependency graph) before any
provider — OpenTofu, Terraform Cloud, Vault, ServiceNow, whatever — is
called. Providers are the codegen backend; they are not the compiler.

Full architecture: see `docs/architecture.html` (design doc, not yet
committed here — currently lives in the design conversation as two
artifacts: the IaC Agent TDD and the Enterprise Platform Compiler
architecture v0.2).

## Current scope: frozen IR v1 + config-driven provider resolution

Pipeline stages implemented:

1. **Parse** — YAML `PlatformSpec` → AST (`epc.ast`)
2. **Normalize + Resolve References** — AST → `IRGraph` (`epc.normalizer`,
   `epc.symboltable`); undefined references are compile errors
3. **Generate DAG** — topological batches, cycle detection (`epc.dag`)
4. **Provider dispatch, config-driven** — each IR node is handed to whatever
   `Provider` is registered for its `capability`, resolved from a
   `providers:` YAML config (`epc.config`) — a capability not listed
   defaults to the fake provider. Two implementations exist:
   - `providers/fake` — echoes back a `Plan`, no external process
   - `providers/terraform_cli` — a real OpenTofu/Terraform CLI adapter.
     **`validate()` and `plan()` only — `apply()` is intentionally
     `NotImplementedError`.** Every IR node lowers to one `terraform_data`
     resource (built into the binary, no plugin download, no network, no
     credentials), so the adapter proves subprocess execution, JSON
     (de)serialization, error handling, and version detection against a
     real CLI with zero infrastructure risk.

   `python -m epc compile spec.yaml --providers config.yaml` runs this for
   real — not just in tests. `tests/test_provider_swap.py` and
   `tests/test_cli.py` both prove `registry.resolve()` actually branches:
   same IR, same DAG, only the resolved provider and its `Plan` differ.
5. **Incremental compilation** — pass `--manifest <path>` (or
   `manifest_path=` to `compile_spec`) and a node whose content hash matches
   the previous compile is skipped entirely: no `validate()`, no `plan()`
   call. A node's hash already folds in its dependencies' hashes, so this
   alone is enough to detect "this node or anything upstream of it changed"
   (`epc.statestore`, `tests/test_incremental.py`)

### IR v1 — frozen and versioned (`epc/ir/v1/`)

The IR is the compiler's ABI: every provider, every future optimization
pass, and any future non-YAML frontend depends on this shape, so it's a
versioned package, not a module that happens to hold some dataclasses.

```
epc/ir/v1/
  nodes.py        IRNode base + 8 explicit kinds (ComputeNode, StorageNode,
                   SecretNode, IdentityNode, NetworkNode, PolicyNode,
                   PipelineNode, DataPlatformNode) — capability is derived
                   from the node's type, not a separate field that could drift
  edges.py         Edge base + DependencyEdge (populated), PolicyEdge,
                   DataFlowEdge, ExecutionEdge (typed, not yet constructed —
                   add call sites when a pass needs to distinguish them)
  graph.py         IRGraph, ExecutionBatch, ExecutionPlan, Checkpoint
  schema.py        IR_VERSION = "1.0"
  serializer.py    to_dict/from_dict/to_json/from_json, IR_VERSION-stamped,
                   rejects a mismatched version rather than guessing
  validator.py     structural checks (dangling deps) independent of the
                   normalizer, for IR arriving from outside this process
```

`epc.ir` re-exports the current version's public API, so bumping the active
version later is a one-line change there instead of a repo-wide import
rewrite (`from epc.ir import StorageNode`, not `from epc.ir.v1.nodes import
StorageNode`, everywhere outside the `ir` package itself).

Explicitly **not** in this repo yet, in roadmap order: a provider
compliance test suite every provider must pass (including capability
negotiation instead of relying solely on `NotImplementedError`), real
optimizer passes, control plane (API/Scheduler/Queue/Worker), state manager,
reconciliation, event bus, multi-agent AI passes, SDK/ecosystem tooling.
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
```

## Layout

```
src/epc/                     compiler frontend — parser, ast, symboltable, normalizer, dag, provider, config, statestore, pipeline, cli
src/epc/ir/v1/                 frozen, versioned IR — nodes, edges, graph, schema, serializer, validator
providers/fake/               a fake Provider implementation, used by tests and as the CLI default
providers/terraform_cli/      real OpenTofu/Terraform CLI adapter — validate/plan only, apply disabled
examples/providers/           example `providers:` config files for --providers
tests/                        one module per pipeline stage, the IR package, incremental compilation, provider swap, config resolution, and the CLI end to end
```
