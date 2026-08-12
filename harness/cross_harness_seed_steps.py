"""Canonical three-phase cross-harness seed command construction."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANONICAL_ROLES = ("codex_harness", "flywheel_harness", "local_14b", "local_32b")


@dataclass(frozen=True)
class OrchestrationStep:
    step_id: str
    purpose: str
    command: list[str]
    timeout_seconds: float
    expected_artifacts: list[str]

    def to_json(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "purpose": self.purpose, "command": self.command,
                "timeout_seconds": self.timeout_seconds, "expected_artifacts": self.expected_artifacts}


def _outputs(root: Path, child_run_id: str) -> list[str]:
    run_root = root / child_run_id
    return [str(run_root / name) for name in ("run.json", "comparison-input.json", "artifact-index.json")]


def _command(args: Any, *, artifact_root: Path, phase: str, tasks: str, roles: str,
             repetitions: int, child_run_id: str, admission_receipt: str = "") -> list[str]:
    command = [
        args.python, "-m", "harness.cli_entry", "cross-harness-execute",
        "--manifest", args.cross_harness_manifest,
        "--runtime-matrix", args.cross_harness_runtime_matrix,
        "--artifact-root", str(artifact_root),
        "--phase", phase,
        "--tasks", tasks,
        "--roles", roles,
        "--repetitions", str(repetitions),
        "--run-id", child_run_id,
        "--source-commit", args.cross_harness_source_commit,
        "--source-root", args.cross_harness_source_root,
        "--timeout-seconds", str(args.cross_harness_attempt_timeout_seconds),
        "--cache-state", "cold_declared",
    ]
    if admission_receipt: command.extend(("--admission-receipt", admission_receipt))
    if phase in {"admission-smoke", "local"}:
        command.extend(("--endpoint-gate", args.cross_harness_endpoint_gate,
                        "--gate-run-id", args.cross_harness_gate_run_id,
                        "--max-gate-age-seconds", str(args.cross_harness_max_gate_age_seconds)))
    command.append("--strict-exit")
    return command


def _required(args: Any) -> None:
    names = ("cross_harness_manifest", "cross_harness_runtime_matrix", "cross_harness_endpoint_gate",
             "cross_harness_gate_run_id", "cross_harness_source_commit", "cross_harness_source_root")
    missing = [name.replace("_", "-") for name in names if not str(getattr(args, name, "")).strip()]
    if missing: raise ValueError("cross-harness inputs required: " + ", ".join(missing))


def build_cross_harness_steps(args: Any, *, run_id: str, artifact_dir: Path) -> list[OrchestrationStep]:
    """Build admission, local, then Spark without expanding the 84-run matrix."""
    _required(args)
    task_pair, tasks = "agt-001,agt-003", "agt-001,agt-003,agt-009,agt-010"
    admission_root, local_root, spark_root = (artifact_dir / name for name in
                                             ("admission-smoke", "local-baseline", "spark-pilot"))
    admission_id, local_id, spark_id = f"{run_id}-admission", f"{run_id}-local", f"{run_id}-spark"
    admission_receipt = str(admission_root / admission_id / "run.json")
    roles = lambda allowed: ",".join(allowed)
    specs = (
        ("cross_harness_admission", "Establish per-role transport and model readiness.", admission_root,
         "admission-smoke", task_pair, roles(("codex_harness", "flywheel_harness", "local_14b", "local_32b")), 1, admission_id, ""),
        ("cross_harness_local", "Run the separately reported local baseline after a fresh gate check.", local_root,
         "local", tasks, roles(("local_14b", "local_32b")), 1, local_id, admission_receipt),
        ("cross_harness_spark", "Run the Codex-versus-Flywheel Spark pilot.", spark_root,
         "spark", tasks, roles(("codex_harness", "flywheel_harness")), 3, spark_id, admission_receipt),
    )
    return [OrchestrationStep(step_id, purpose,
             _command(args, artifact_root=root, phase=phase, tasks=selected, roles=roles,
                      repetitions=repetitions, child_run_id=child_id, admission_receipt=receipt),
             args.benchmark_timeout_seconds, _outputs(root, child_id))
            for step_id, purpose, root, phase, selected, roles, repetitions, child_id, receipt in specs]
