"""CLI adapter for OpenTofu / Terraform (architecture doc §04, §13 provisioning
capability). One class serves both `provider: opentofu` (default) and
`provider: terraform-cli` -- their CLIs and `-json` output formats are
compatible, so there's nothing capability-specific to duplicate between them.
Even within one capability's provider family, "call the capability, never
the vendor" (architecture doc §01) turns out to hold.

Phase 1 scope: validate() and plan() only. apply()/destroy()/status()/
rollback() raise NotImplementedError on purpose -- no infrastructure risk
until that gate is explicitly lifted in a later phase.

Every IR node lowers to a single `terraform_data` resource -- part of the
`terraform.io/builtin/terraform` provider that ships inside the binary
itself, so `init` never downloads a plugin or touches the network. This is
deliberately not real per-cloud resource codegen (that's a separate, later
module-registry subsystem) -- it's enough to prove subprocess execution,
JSON (de)serialization, error handling, and version detection end-to-end,
against a real CLI, with zero infrastructure risk.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from epc.ir import IRNode
from epc.provider import Plan, Provider, ValidationResult

MIN_VERSION = (1, 4, 0)  # terraform_data requires Terraform >=1.4 / OpenTofu >=1.6
_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH", "HOME")


class CliNotFoundError(RuntimeError):
    pass


class UnsupportedVersionError(RuntimeError):
    pass


class TerraformCliProvider(Provider):
    def __init__(self, binary: str = "tofu", name: str | None = None):
        self.binary = binary
        self.name = name or binary

    def initialize(self, config: dict[str, Any]) -> None:
        self.binary = config.get("binary", self.binary)
        version = self._detect_version()
        if version < MIN_VERSION:
            raise UnsupportedVersionError(
                f"{self.binary} {'.'.join(map(str, version))} < required {'.'.join(map(str, MIN_VERSION))}"
            )

    def validate(self, node: IRNode) -> ValidationResult:
        with tempfile.TemporaryDirectory(prefix=f"epc-{self.binary}-") as raw_workdir:
            workdir = Path(raw_workdir)
            init = self._prepare_workspace(workdir, node)
            if init.returncode != 0:
                return ValidationResult(ok=False, errors=[self._error_text(init)])

            result = self._run("validate", "-json", cwd=workdir)
            payload = json.loads(result.stdout)
            if payload["valid"]:
                return ValidationResult(ok=True)
            return ValidationResult(ok=False, errors=[d.get("summary", str(d)) for d in payload.get("diagnostics", [])])

    def plan(self, node: IRNode) -> Plan:
        with tempfile.TemporaryDirectory(prefix=f"epc-{self.binary}-") as raw_workdir:
            workdir = Path(raw_workdir)
            init = self._prepare_workspace(workdir, node)
            if init.returncode != 0:
                raise RuntimeError(f"{self.binary} init failed for {node.id}: {self._error_text(init)}")

            plan_run = self._run("plan", "-input=false", "-no-color", "-out=tfplan", cwd=workdir)
            if plan_run.returncode != 0:
                raise RuntimeError(f"{self.binary} plan failed for {node.id}: {self._error_text(plan_run)}")

            show = self._run("show", "-json", "tfplan", cwd=workdir)
            plan_json = json.loads(show.stdout)
            changes = plan_json.get("resource_changes", [])
            diff = {
                "actions": [action for change in changes for action in change["change"]["actions"]],
                "resource_changes": changes,
            }
            return Plan(node_id=node.id, provider=self.name, diff=diff)

    def apply(self, plan: Plan) -> dict[str, Any]:
        raise NotImplementedError(
            "apply() is intentionally disabled in Phase 1 -- validate/plan only, no infrastructure risk yet"
        )

    def destroy(self, node_id: str) -> None:
        raise NotImplementedError("destroy() disabled alongside apply() in Phase 1")

    def status(self, node_id: str) -> dict[str, Any]:
        raise NotImplementedError("status() requires applied state, which Phase 1 never creates")

    def health(self) -> bool:
        try:
            self._detect_version()
            return True
        except (CliNotFoundError, UnsupportedVersionError):
            return False

    def rollback(self, checkpoint_id: str) -> None:
        raise NotImplementedError("rollback() requires applied state, which Phase 1 never creates")

    # -- internal -----------------------------------------------------------

    def _lower(self, node: IRNode) -> dict[str, Any]:
        """Provider Generation (architecture doc §03 stage 9), narrowed to one
        placeholder resource type -- see module docstring."""
        resource_name = node.id.replace(".", "_").replace("-", "_")
        return {
            "terraform": {"required_version": f">= {'.'.join(map(str, MIN_VERSION))}"},
            "resource": {"terraform_data": {resource_name: {"input": node.properties}}},
        }

    def _prepare_workspace(self, workdir: Path, node: IRNode) -> subprocess.CompletedProcess:
        (workdir / "main.tf.json").write_text(json.dumps(self._lower(node)))
        return self._run("init", "-input=false", "-no-color", cwd=workdir)

    def _detect_version(self) -> tuple[int, int, int]:
        result = self._run("version", "-json", cwd=Path(tempfile.gettempdir()))
        if result.returncode != 0:
            raise CliNotFoundError(f"'{self.binary} version' failed: {result.stderr.strip()}")
        payload = json.loads(result.stdout)
        # OpenTofu keeps the "terraform_version" key for CLI/output compatibility;
        # fall back to "version" defensively in case a future release renames it.
        raw = payload.get("terraform_version") or payload.get("version")
        major, minor, patch = (int(p) for p in raw.split(".")[:3])
        return (major, minor, patch)

    def _run(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        # ponytail: env allowlist is a minimal sandbox gesture (no arbitrary parent
        # secrets reach the subprocess). Real network/credential isolation per
        # architecture doc §17 is container-level, Phase 1+.
        env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST}
        try:
            return subprocess.run(
                [self.binary, *args], cwd=cwd, capture_output=True, text=True, timeout=120, env=env
            )
        except FileNotFoundError as exc:
            raise CliNotFoundError(f"'{self.binary}' not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"'{self.binary} {' '.join(args)}' timed out after 120s") from exc

    @staticmethod
    def _error_text(result: subprocess.CompletedProcess) -> str:
        return (result.stderr or result.stdout).strip()
