"""The CLI itself, end to end -- this is the interface the roadmap flagged as
still exercising only the fake provider. Proves --providers actually changes
what runs, from argv to stdout.
"""

import shutil

import pytest

from epc.cli import main

TERRAFORM_BINARY = "tofu" if shutil.which("tofu") else "terraform"
HAS_CLI = shutil.which(TERRAFORM_BINARY) is not None


def test_compile_with_no_providers_flag_defaults_everything_to_fake(capsys):
    exit_code = main(["compile", "tests/fixtures/data_platform.yaml"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "storage.dataLake -> fake" in out


def test_compile_with_manifest_reports_skipped_nodes_on_second_run(tmp_path, capsys):
    manifest = str(tmp_path / "manifest.json")
    main(["compile", "tests/fixtures/data_platform.yaml", "--manifest", manifest])
    capsys.readouterr()  # discard first run's output

    main(["compile", "tests/fixtures/data_platform.yaml", "--manifest", manifest])
    out = capsys.readouterr().out
    assert "skipped (unchanged):" in out
    assert "storage.dataLake" in out


@pytest.mark.skipif(not HAS_CLI, reason="no terraform/tofu binary on PATH")
def test_compile_with_providers_config_uses_the_real_cli_for_storage(tmp_path, capsys):
    config = tmp_path / "providers.yaml"
    provider_name = "opentofu" if TERRAFORM_BINARY == "tofu" else "terraform-cli"
    config.write_text(f"providers:\n  storage:\n    provider: {provider_name}\n")

    main(["compile", "tests/fixtures/data_platform.yaml", "--providers", str(config)])
    out = capsys.readouterr().out

    storage_line = next(line for line in out.splitlines() if line.strip().startswith("storage.dataLake"))
    assert f"-> {TERRAFORM_BINARY}:" in storage_line
    assert "terraform_data" in storage_line  # real plan diff, not the fake provider's echo
