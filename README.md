# Enterprise Platform Compiler

Open-source-first platform compiler: a `PlatformSpec` compiles through a real
pipeline (parse → AST → normalized IR → dependency graph) before any
provider — OpenTofu, Terraform Cloud, Vault, ServiceNow, whatever — is
called. Providers are the codegen backend; they are not the compiler.

Full architecture: see `docs/architecture.html` (design doc, not yet
committed here — currently lives in the design conversation as two
artifacts: the IaC Agent TDD and the Enterprise Platform Compiler
architecture v0.2).

## Current scope: compiler frontend only

This is **Phase 0** of the architecture's build sequence: fix the IR/DAG
*shape* before wiring up any real provider. Nothing in this repo touches
real infrastructure yet.

Pipeline stages implemented:

1. **Parse** — YAML `PlatformSpec` → AST (`epc.ast`)
2. **Normalize + Resolve References** — AST → `ResourceGraph`, an IR of
   typed nodes and typed edges; undefined references are compile errors
   (`epc.normalizer`, `epc.symboltable`)
3. **Generate DAG** — topological batches, cycle detection
   (`epc.dag`)
4. **Provider dispatch (stub)** — each IR node is handed to whatever
   `Provider` is registered for its `capability`; `providers/fake` is a
   fake provider that just echoes back a `Plan`, so the pipeline can be
   proven end-to-end without a cloud credential in sight

Explicitly **not** in this repo yet (see architecture doc §20 for why):
policy pass, real optimizer passes, incremental compilation *diffing*
(the IR node carries a `hash` field, but nothing compares it against a
stored manifest yet), control plane (API/Scheduler/Queue/Worker),
reconciliation, event bus, real providers.

## Run the tests

```bash
pip install -e ".[dev]"
pytest
```

## Layout

```
src/epc/            compiler frontend — parser, ast, symboltable, normalizer, dag, provider, pipeline
providers/fake/      a fake Provider implementation, used only by tests
tests/               one test module per pipeline stage + one end-to-end pipeline test
```
