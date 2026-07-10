"""examples/contracts/*/expected_output.txt are the language semantics of
EPC, made runnable: each directory is two real `epc compile` invocations --
the exact commands a contributor can type by hand -- with the second run's
full stdout checked in as a golden file. This test re-runs the same two
invocations and asserts today's output still matches, so a semantic drift
is caught here instead of discovered by a human reading a stale example.

If a change legitimately alters what one of these prints, regenerate with:
    python examples/generate_contract_examples.py
and review the diff -- that diff IS the changelog entry for the invariant
the scenario demonstrates.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from epc.cli import main

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "examples" / "contracts"
SCENARIOS = sorted(p for p in CONTRACTS_DIR.iterdir() if p.is_dir())


def _run(argv: list[str]) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(argv)
    return buffer.getvalue()


@pytest.mark.parametrize("scenario_dir", SCENARIOS, ids=[p.name for p in SCENARIOS])
def test_contract_example_output_matches_checked_in_golden(scenario_dir, tmp_path):
    focus_node = (scenario_dir / "focus_node.txt").read_text().strip()
    expected = (scenario_dir / "expected_output.txt").read_text()

    manifest = str(tmp_path / "manifest.json")
    _run(["compile", str(scenario_dir / "before.yaml"), "--manifest", manifest])
    actual = _run(["compile", str(scenario_dir / "after.yaml"), "--manifest", manifest, "--explain", focus_node])

    assert actual == expected
