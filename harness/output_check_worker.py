"""Private worker for native output.check gateway operations."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from .cross_harness_process import ProcessLaunch
from .evidence_json import canonical_bytes, strict_load_json
from .gateway_operation import AuthorizedOperation, canonicalize_operation, thaw_operation
from .gateway_operation_route import operation_ref_for
from .gateway_worker_env import minimal_worker_env
from .output_check_service import OutputCheckError, run_output_check_operation

_SCHEMA = "flywheel.output-check-worker/v1"


class GatewayOutputCheckProcessFactory:
    def __init__(self, *, repo_root: Path, run_root: Path,
                 state_root: Path | None = None, launcher=None) -> None:
        from .gateway_operation_process import _launch
        self.repo_root, self.run_root = Path(repo_root), Path(run_root)
        self.state_root = Path(state_root) if state_root is not None else None
        self.launcher = launcher or _launch

    def create(self, authorized: AuthorizedOperation,
               progress: Callable[[dict], None]):
        if authorized.action != "output.check":
            raise ValueError("gateway worker action is invalid")
        payload = {"schema": _SCHEMA, "operation": thaw_operation(
            authorized.operation), "repo_root": str(self.repo_root),
            "run_root": str(self.run_root),
            "state_root": str(self.state_root or self.run_root),
            "owner_ref": authorized.owner_ref, "operation_ref": operation_ref_for(
                authorized.owner_ref, authorized.journey_ref,
                authorized.client_request_id)}
        spec = ProcessLaunch(
            (sys.executable, "-m", "harness.output_check_worker"),
            self.repo_root, canonical_bytes(payload), minimal_worker_env(
                self.repo_root, run_root=self.run_root,
                state_root=self.state_root or self.run_root))
        from .gateway_operation_process import GatewayWorker
        return GatewayWorker(self.launcher(spec), progress, ())


class GatewayOperationProcessFactory:
    def __init__(self, *, repo_root: Path, run_root: Path,
                 state_root: Path | None = None, launcher=None) -> None:
        from .gateway_operation_process import GatewayAgentProcessFactory
        self.repo_root, self.run_root = Path(repo_root), Path(run_root)
        self.state_root = Path(state_root) if state_root is not None else None
        self.agent = GatewayAgentProcessFactory(
            repo_root=repo_root, run_root=run_root, state_root=state_root,
            launcher=launcher) if launcher else GatewayAgentProcessFactory(
                repo_root=repo_root, run_root=run_root, state_root=state_root)
        self.output = GatewayOutputCheckProcessFactory(
            repo_root=repo_root, run_root=run_root, state_root=state_root,
            launcher=launcher)

    def create(self, authorized: AuthorizedOperation,
               progress: Callable[[dict], None]):
        if authorized.action == "output.check":
            return self.output.create(authorized, progress)
        return self.agent.create(authorized, progress)


def _emit(value: dict) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")
    sys.stdout.buffer.flush()


def _request() -> tuple[dict, Path, Path, Path, str, str]:
    value = strict_load_json(sys.stdin.buffer.read(), max_bytes=1_048_576)
    if (type(value) is not dict
            or set(value) != {"schema", "operation", "repo_root",
                              "run_root", "state_root", "owner_ref",
                              "operation_ref"}
            or value.get("schema") != _SCHEMA):
        raise ValueError
    operation = canonicalize_operation("output.check", value["operation"])
    return (thaw_operation(operation.operation), Path(value["repo_root"]),
            Path(value["run_root"]), Path(value["state_root"]),
            value["owner_ref"], value["operation_ref"])


def _main() -> int:
    try:
        operation, repo_root, run_root, state_root, owner_ref, op_ref = _request()
        result = run_output_check_operation(operation, repo_root=repo_root,
            run_root=run_root, state_root=state_root, owner_ref=owner_ref,
            operation_ref=op_ref,
            progress=lambda event: _emit({"type": "progress", "event": event}))
        _emit({"type": "terminal", "state": "completed", "result": result})
        return 0
    except OutputCheckError as exc:
        code = exc.code.split(":", 1)[0]
        reason = "SOURCE_CONTEXT_FAILED" if code == "SOURCE_DRIFT" else "EXTERNAL_ACTION_FAILED"
        _emit({"type": "terminal", "state": "failed",
               "result": {"reason": reason, "code": code}})
        return 1
    except Exception:
        _emit({"type": "terminal", "state": "failed",
               "result": {"reason": "EXTERNAL_ACTION_FAILED"}})
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
