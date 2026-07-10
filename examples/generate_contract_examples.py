"""Generates examples/contracts/*/expected_output.txt -- each scenario is
two real `epc compile` invocations (the exact commands a contributor would
type by hand), with the second run's full stdout (batches, skip/reuse
decision, causal trace) captured verbatim as the golden file.

Not hand-written traces: if compiler behavior changes, this script -- not a
human -- is what updates the expectation, and tests/test_contract_examples.py
is what notices when it silently drifts instead.

    python examples/generate_contract_examples.py
"""

from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "providers"))

from epc.cli import main  # noqa: E402

CONTRACTS_DIR = _ROOT / "examples" / "contracts"


def _run(argv: list[str]) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(argv)
    return buffer.getvalue()


def generate_one(scenario_dir: Path) -> None:
    focus_node = (scenario_dir / "focus_node.txt").read_text().strip()
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = str(Path(tmp) / "manifest.json")
        _run(["compile", str(scenario_dir / "before.yaml"), "--manifest", manifest_path])
        output = _run(
            ["compile", str(scenario_dir / "after.yaml"), "--manifest", manifest_path, "--explain", focus_node]
        )
    (scenario_dir / "expected_output.txt").write_text(output)
    print(f"wrote {scenario_dir.name}/expected_output.txt")


def main_() -> None:
    for scenario_dir in sorted(p for p in CONTRACTS_DIR.iterdir() if p.is_dir()):
        generate_one(scenario_dir)


if __name__ == "__main__":
    main_()
