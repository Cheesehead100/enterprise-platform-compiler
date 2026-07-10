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


def test_explain_across_two_real_invocations_traces_a_cascaded_recompile(tmp_path, capsys):
    """The case --explain exists for: a node nobody edited (appServer)
    recompiles because something it depends on (dbPassword) did -- and the
    CLI can only know that by reading the manifest this same command wrote
    on the previous, separate invocation."""
    manifest = str(tmp_path / "manifest.json")
    main(["compile", "tests/fixtures/incremental_before.yaml", "--manifest", manifest])
    capsys.readouterr()

    main(["compile", "tests/fixtures/incremental_after.yaml", "--manifest", manifest, "--explain", "compute.appServer"])
    out = capsys.readouterr().out

    assert "Target\n  compute.appServer" in out
    assert "Decision\n  RECOMPILED" in out
    assert "dependency hash changed (secret.dbPassword)" in out
    assert "edited: rotation: 90 -> 30" in out


def test_explain_reports_reused_for_an_unrelated_sibling(tmp_path, capsys):
    manifest = str(tmp_path / "manifest.json")
    main(["compile", "tests/fixtures/incremental_before.yaml", "--manifest", manifest])
    capsys.readouterr()

    main(["compile", "tests/fixtures/incremental_after.yaml", "--manifest", manifest, "--explain", "storage.bucket1"])
    out = capsys.readouterr().out

    assert "Decision\n  REUSED" in out
    assert "Provider Lowering          skipped (reused from previous compile)" in out


def test_explain_without_a_manifest_reports_everything_as_new(capsys):
    main(["compile", "tests/fixtures/incremental_after.yaml", "--explain", "network.vpc"])
    out = capsys.readouterr().out

    assert "Decision\n  RECOMPILED" in out
    assert "new node, no previous compile to compare against" in out


def test_explain_reports_a_removed_dependency_not_unchanged(tmp_path, capsys):
    """Regression: the Incremental Analysis line used to only check
    is_new/own_properties_changed/caused_by, so a recompile caused solely by
    a removed or added dependency edge (no endpoint's own hash changes --
    see tests/test_dependency_swap.py) fell through to "unchanged" right
    below a Decision of RECOMPILED. An explanation contradicting the
    decision it explains is exactly what the Compiler Explainability
    Contract forbids."""
    before = """
metadata: {name: x}
spec:
  resources:
    - capability: compute
      name: database
    - capability: compute
      name: service
      dependsOn: ["compute.database"]
"""
    after = """
metadata: {name: x}
spec:
  resources:
    - capability: compute
      name: service
"""
    before_file = tmp_path / "before.yaml"
    after_file = tmp_path / "after.yaml"
    before_file.write_text(before)
    after_file.write_text(after)
    manifest = str(tmp_path / "manifest.json")

    main(["compile", str(before_file), "--manifest", manifest])
    capsys.readouterr()

    main(["compile", str(after_file), "--manifest", manifest, "--explain", "compute.service"])
    out = capsys.readouterr().out

    assert "Decision\n  RECOMPILED" in out
    assert "Incremental Analysis       unchanged" not in out
    assert "removed dependency: compute.database" in out
