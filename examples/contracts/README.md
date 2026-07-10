# Contract examples

Five scenarios, each a real `before.yaml` / `after.yaml` pair, demonstrating
one semantic rule from
[`docs/COMPILER_SEMANTICS.md`](../../docs/COMPILER_SEMANTICS.md). Run either
by hand:

```
epc compile examples/contracts/property_change/before.yaml --manifest /tmp/m.json
epc compile examples/contracts/property_change/after.yaml --manifest /tmp/m.json --explain compute.appServer
```

`expected_output.txt` in each directory is the second command's stdout,
checked in verbatim and enforced by `tests/test_contract_examples.py` — if
compiler behavior changes, that test fails instead of the example going
stale. Regenerate after an intentional change with:

```
python examples/generate_contract_examples.py
```

| Scenario | Demonstrates |
|---|---|
| `property_change/` | A node's own properties changed -> it recompiles, and everything depending on it does too. |
| `dependency_removal/` | A dependency edge removed (not renamed) -> caught via `removed_dependencies`, not a hash comparison. |
| `dependency_swap/` | Rewired to a different, identically-shaped, coexisting sibling -> Graph Identity Invariant: different id is a real change even with identical content. |
| `rename/` | Old id removed + new id added on the same edge -> reported once, not twice (no rename tracking — see `COMPILER_SEMANTICS.md` §1). |
| `no_op/` | Byte-identical recompile -> everything reused, nothing reported as changed. |

Not included: the "manifest references evidence missing from the graph"
scenario (Evidence Closure Invariant). It's structurally unreachable through
`epc compile` — `normalize()` rejects a dangling `dependsOn` before an
`IRGraph` with that shape can exist (`COMPILER_SEMANTICS.md` §5) — so it
can't be expressed as a YAML pair here. It's exercised directly against
`epc.explain.explain_recompile` in `tests/test_missing_evidence.py` instead.
