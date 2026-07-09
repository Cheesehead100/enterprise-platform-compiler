# Enterprise Platform Compiler

Open-source-first platform compiler: a `PlatformSpec` compiles through a real
pipeline (parse → AST → normalized IR → dependency graph) before any
provider — OpenTofu, Terraform Cloud, Vault, ServiceNow, whatever — is
called. Providers are the codegen backend; they are not the compiler.

Full architecture: see `docs/architecture.html` (design doc, not yet
committed here — currently lives in the design conversation as two
artifacts: the IaC Agent TDD and the Enterprise Platform Compiler
architecture v0.2).

## Current scope: compiler frontend + one real provider

Pipeline stages implemented:

1. **Parse** — YAML `PlatformSpec` → AST (`epc.ast`)
2. **Normalize + Resolve References** — AST → `ResourceGraph`, an IR of
   typed nodes and typed edges; undefined references are compile errors
   (`epc.normalizer`, `epc.symboltable`)
3. **Generate DAG** — topological batches, cycle detection
   (`epc.dag`)
4. **Provider dispatch** — each IR node is handed to whatever `Provider` is
   registered for its `capability`. Two implementations exist:
   - `providers/fake` — echoes back a `Plan`, no external process, used by
     most tests and the CLI default
   - `providers/terraform_cli` — a real OpenTofu/Terraform CLI adapter.
     **`validate()` and `plan()` only — `apply()` is intentionally
     `NotImplementedError`.** Every IR node lowers to one `terraform_data`
     resource (built into the binary, no plugin download, no network, no
     credentials) so the adapter proves subprocess execution, JSON
     (de)serialization, error handling, and version detection against a
     real CLI with zero infrastructure risk. `tests/test_provider_swap.py`
     registers this alongside the fake provider for two different
     capabilities in the *same* compile to prove `registry.resolve()`
     actually branches — same IR, same DAG, only the resolved provider
     differs.
5. **Incremental compilation** — pass `--manifest <path>` (or
   `manifest_path=` to `compile_spec`) and a node whose content hash matches
   the previous compile is skipped entirely: no `validate()`, no `plan()`
   call. A node's hash already folds in its dependencies' hashes, so this
   alone is enough to detect "this node or anything upstream of it changed"
   (`epc.statestore`, `tests/test_incremental.py`)

Explicitly **not** in this repo yet, in roadmap order: a provider
compliance test suite every provider must pass, a frozen/versioned IR
schema, real optimizer passes, control plane (API/Scheduler/Queue/Worker),
state manager, reconciliation, event bus, multi-agent AI passes, SDK/
ecosystem tooling. `apply()` stays disabled on every provider until its own
phase explicitly lifts that gate.

## Run the tests

```bash
pip install -e ".[dev]"
pytest
```

## Run the compiler by hand

```bash
python -m epc compile tests/fixtures/data_platform.yaml
python -m epc compile tests/fixtures/data_platform.yaml --manifest /tmp/epc-manifest.json
python -m epc compile tests/fixtures/data_platform.yaml --manifest /tmp/epc-manifest.json  # second run: everything skipped
```

The CLI always uses the fake provider (see `epc.cli`). The real
`terraform_cli` provider is exercised only by its own tests so far — it
isn't wired into `--provider` config selection yet (that's the control
plane / config-driven provider resolution work, still ahead).

## Layout

```
src/epc/                     compiler frontend — parser, ast, symboltable, normalizer, dag, provider, statestore, pipeline, cli
providers/fake/               a fake Provider implementation, used by tests and the CLI
providers/terraform_cli/      real OpenTofu/Terraform CLI adapter — validate/plan only, apply disabled
tests/                        one test module per pipeline stage, plus incremental compilation, provider swap, and the real CLI adapter
```
