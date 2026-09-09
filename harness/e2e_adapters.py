"""Runtime adapters for product E2E journeys."""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Any

from harness.cross_harness_process import MAX_CAPTURE_BYTES, ProcessOutcome, _child_env, run_process
from harness.cross_harness_types import sanitize_evidence
from harness.mcp_client import LaunchSpec, MCPAllowlist, MCPClient, MCPError


@dataclass(frozen=True)
class JourneyStepResult:
    step_id: str
    status: str
    stdout: str = ""
    stderr_tail: str = ""
    parsed_json: dict[str, Any] | None = None
    returncode: int | None = None
    elapsed_ms: int = 0
    timed_out: bool = False
    malformed_output: bool = False
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.step_id,
            "status": self.status,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
            "timed_out": self.timed_out,
            "malformed_output": self.malformed_output,
            "stdout": self.stdout[-4000:],
            "stderr_tail": self.stderr_tail[-4000:],
            "parsed_json": self.parsed_json,
            "evidence": self.evidence or {},
        }
        return sanitize_evidence(payload)


def _json_step(step_id: str, outcome: ProcessOutcome) -> JourneyStepResult:
    status = "completed" if outcome.returncode == 0 and not outcome.timed_out else "failed"
    parsed = None
    malformed = outcome.malformed_output
    if outcome.stdout.strip() and outcome.returncode == 0:
        try:
            candidate = json.loads(outcome.stdout)
            if isinstance(candidate, dict):
                parsed = candidate
            else:
                malformed = True
                status = "failed"
        except json.JSONDecodeError:
            malformed = True
            status = "failed"
    return JourneyStepResult(
        step_id=step_id,
        status=status,
        stdout=outcome.stdout,
        stderr_tail=outcome.stderr,
        parsed_json=parsed,
        returncode=outcome.returncode,
        elapsed_ms=outcome.elapsed_ms,
        timed_out=outcome.timed_out,
        malformed_output=malformed,
    )


class CliProcessJourneyAdapter:
    kind = "cli_process"

    def __init__(self, executable: Path, *, timeout_seconds: float = 30.0):
        self.executable = Path(executable)
        self.timeout_seconds = timeout_seconds

    def run_json(self, args: list[str], *, cwd: Path, step_id: str) -> JourneyStepResult:
        try:
            outcome = run_process(
                [str(self.executable), *args],
                cwd=Path(cwd),
                stdin_text="",
                timeout_seconds=self.timeout_seconds,
            )
        except OSError as exc:
            return JourneyStepResult(step_id=step_id, status="failed", stderr_tail=str(exc))
        return _json_step(step_id, outcome)

    def close(self) -> None:
        return None


def validate_gather_context_schema(tools: list[dict[str, Any]]) -> None:
    context = next((tool for tool in tools if tool.get("name") == "gather.context"), None)
    if not context:
        raise ValueError("gather.context tool is not available")
    schema = context.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("gather.context inputSchema must be an object")
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if "corpus" not in required or not isinstance(properties, dict):
        raise ValueError("gather.context inputSchema must require corpus")
    for field in ("corpus", "select", "expected_corpus_digest"):
        if field not in properties:
            raise ValueError(f"gather.context inputSchema missing {field}")
    if properties.get("corpus", {}).get("type") != "string":
        raise ValueError("gather.context corpus must be a string")
    if properties.get("select", {}).get("type") != "array":
        raise ValueError("gather.context select must be an array")


def validate_gather_run_schema(tools: list[dict[str, Any]]) -> None:
    run_tool = next((tool for tool in tools if tool.get("name") == "gather.run"), None)
    if not run_tool:
        raise ValueError("gather.run tool is not available")
    run_schema = run_tool.get("inputSchema")
    run_properties = run_schema.get("properties", {}) if isinstance(run_schema, dict) else {}
    if "config" not in run_properties and "config_path" not in run_properties:
        raise ValueError("gather.run inputSchema missing config")


class MCPStdioJourneyAdapter:
    kind = "mcp_stdio"

    def __init__(self, executable: Path, *, cwd: Path, timeout_seconds: float = 30.0):
        self.executable = Path(executable)
        self.cwd = Path(cwd)
        self.timeout_seconds = timeout_seconds
        self.client: MCPClient | None = None
        self.tools: list[dict[str, Any]] = []

    def start(self) -> list[dict[str, Any]]:
        command = [str(self.executable), "mcp"]
        MCPAllowlist([command]).check(command)
        env = _child_env()
        env.pop("PYTHONPATH", None)
        spec = LaunchSpec(
            argv=tuple(command),
            cwd=str(self.cwd),
            inherit_env=False,
            env_overrides=tuple(env.items()),
        )
        client = MCPClient(spec, timeout=self.timeout_seconds, client_name="flywheel-e2e")
        try:
            self.client = client.start()
            self.tools = self.client.list_tools()
            validate_gather_context_schema(self.tools)
            validate_gather_run_schema(self.tools)
            return self.tools
        except Exception:
            client.close()
            self.client = None
            raise

    def call_json(self, name: str, arguments: dict[str, Any], *, step_id: str) -> JourneyStepResult:
        if self.client is None:
            self.start()
        assert self.client is not None
        started = time.perf_counter()
        try:
            response = self.client.call_text(name, arguments)
        except Exception as exc:
            elapsed = max(0, round((time.perf_counter() - started) * 1000))
            message = str(exc)
            timed_out = isinstance(exc, MCPError) and ("no response within" in message or "timeout" in message.lower())
            return JourneyStepResult(step_id=step_id, status="failed", stderr_tail=message,
                                     elapsed_ms=elapsed, timed_out=timed_out)
        elapsed = max(0, round((time.perf_counter() - started) * 1000))
        text = response.get("text", "")
        if len(text.encode("utf-8")) > MAX_CAPTURE_BYTES:
            return JourneyStepResult(
                step_id=step_id,
                status="failed",
                stdout=text[:4000],
                elapsed_ms=elapsed,
                malformed_output=True,
                evidence={"reason": "mcp_response_too_large", "max_bytes": MAX_CAPTURE_BYTES},
            )
        if not response.get("ok", False):
            return JourneyStepResult(
                step_id=step_id,
                status="failed",
                stdout=text,
                stderr_tail=self.client.stderr_tail(),
                elapsed_ms=elapsed,
                evidence={"mcp_is_error": True, "raw": response.get("raw", {})},
            )
        try:
            parsed = json.loads(text) if text.strip() else {}
            if not isinstance(parsed, dict):
                return JourneyStepResult(step_id=step_id, status="failed", stdout=text,
                                         elapsed_ms=elapsed, malformed_output=True)
        except json.JSONDecodeError:
            return JourneyStepResult(step_id=step_id, status="failed", stdout=text,
                                     elapsed_ms=elapsed, malformed_output=True)
        return JourneyStepResult(step_id=step_id, status="completed", stdout=text,
                                 parsed_json=parsed, elapsed_ms=elapsed)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
