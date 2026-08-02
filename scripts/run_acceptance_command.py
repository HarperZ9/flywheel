"""Run one shell-free command and atomically publish a secret-safe receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acceptance_command_capture import (  # noqa: E402
    argv_secret_values,
    capture_command,
    redact_argv,
    redact_bytes,
    sensitive_name,
    staged_receipt_directory,
)


SCHEMA = "flywheel.acceptance-command/v1"
DEFAULT_EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "closeout" / "FW-2026-08-02-CLOSEOUT"
DEFAULT_OUTPUT_LIMIT = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 900.0
DOES_NOT_PROVE = [
    "A recorded zero exit code does not prove command correctness.",
    "This receipt does not prove exhaustive coverage, cross-system reproducibility, or absence of unobserved side effects.",
]
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], check=False, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", shell=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"cwd is not in a readable Git repository: {cwd}")
    return result.stdout.strip()


def _repository_identity(cwd: Path) -> tuple[str, str, str]:
    repository_root = Path(_git(cwd, "rev-parse", "--show-toplevel")).resolve()
    try:
        relative_cwd = cwd.relative_to(repository_root).as_posix() or "."
    except ValueError as exc:
        raise ValueError("cwd is outside the source repository") from exc
    return repository_root.name, _git(cwd, "rev-parse", "HEAD"), relative_cwd


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _parse_argv(argv_json: str | None, repeated: list[str] | None) -> list[str]:
    if argv_json is not None:
        try:
            parsed = json.loads(argv_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--argv-json is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) for item in parsed):
            raise ValueError("--argv-json must be a non-empty JSON array of strings")
        return parsed
    if not repeated:
        raise ValueError("provide --argv-json or at least one --arg")
    return list(repeated)


def _secret_inputs(explicit_names: list[str], argv: list[str]) -> tuple[list[str], list[bytes]]:
    missing = sorted(name for name in explicit_names if name not in os.environ)
    if missing:
        raise ValueError("secret environment variable is not set: " + ", ".join(missing))
    automatic = sorted(name for name in os.environ if sensitive_name(name))
    names = sorted(set(explicit_names) | set(automatic))
    values = {os.environ[name].encode("utf-8") for name in names if os.environ.get(name)}
    values.update(argv_secret_values(argv))
    return automatic, sorted(values, key=len, reverse=True)


def _validate_inputs(argv: list[str], timeout_seconds: float, output_limit_bytes: int) -> None:
    if any("\x00" in item for item in argv):
        raise ValueError("command argv must not contain NUL")
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if output_limit_bytes < 1:
        raise ValueError("output limit must be positive")


def _bounded_redacted(
    raw: bytes, observed: int, limit: int, secrets: list[bytes]
) -> tuple[bytes, bool, int]:
    redacted, replacements = redact_bytes(raw, secrets)
    return redacted[:limit], observed > len(raw) or len(redacted) > limit, replacements


def _stream_record(
    filename: str, data: bytes, observed: int, truncated: bool, replacements: int
) -> dict[str, object]:
    return {
        "path": filename, "sha256": _sha256(data), "bytes": len(data),
        "observed_bytes": observed, "truncated": truncated, "replacement_count": replacements,
    }


def _validate_staged(stage: Path, receipt: dict) -> None:
    if receipt.get("schema") != SCHEMA or receipt.get("command", {}).get("shell") is not False:
        raise RuntimeError("receipt provenance validation failed")
    if Path(str(receipt.get("cwd", ""))).is_absolute():
        raise RuntimeError("receipt cwd must be repository-relative")
    for stream in ("stdout", "stderr"):
        record = receipt[stream]
        data = (stage / record["path"]).read_bytes()
        if len(data) != record["bytes"] or _sha256(data) != record["sha256"]:
            raise RuntimeError(f"{stream} receipt validation failed")
    if receipt["redaction"]["values_serialized"] is not False:
        raise RuntimeError("receipt redaction posture is invalid")


def record_command(
    *,
    evidence_root: Path,
    artifact_root: Path,
    receipt_name: str,
    cwd: Path,
    argv: list[str],
    secret_environment_names: list[str],
    output_limit_bytes: int,
    timeout_seconds: float,
) -> int:
    evidence_root, artifact_root, cwd = evidence_root.resolve(), artifact_root.resolve(), cwd.resolve()
    if not _inside(artifact_root, evidence_root):
        raise ValueError("artifact root must be inside the configured evidence root")
    if not _SAFE_NAME.fullmatch(receipt_name):
        raise ValueError("receipt name must use only letters, digits, dot, underscore, or hyphen")
    _validate_inputs(argv, timeout_seconds, output_limit_bytes)
    repository, head, relative_cwd = _repository_identity(cwd)
    automatic_names, secret_values = _secret_inputs(secret_environment_names, argv)
    receipt_dir = (artifact_root / receipt_name).resolve()
    if not _inside(receipt_dir, artifact_root):
        raise ValueError("receipt directory must stay inside the artifact root")

    overlap = max((len(value) for value in secret_values), default=0) + 8_192
    started_utc, started_ns = _utc_now(), perf_counter_ns()
    with staged_receipt_directory(receipt_dir) as stage:
        result = capture_command(argv, cwd, timeout_seconds, output_limit_bytes + overlap)
        ended_utc = _utc_now()
        stdout_sink, stderr_sink = result["stdout"], result["stderr"]
        stdout, stdout_truncated, stdout_replacements = _bounded_redacted(
            stdout_sink["captured"], int(stdout_sink["observed"]), output_limit_bytes, secret_values
        )
        stderr, stderr_truncated, stderr_replacements = _bounded_redacted(
            stderr_sink["captured"], int(stderr_sink["observed"]), output_limit_bytes, secret_values
        )
        command_argv, argv_replacements = redact_argv(argv, secret_values)
        (stage / "stdout.txt").write_bytes(stdout)
        (stage / "stderr.txt").write_bytes(stderr)
        receipt = {
            "schema": SCHEMA, "receipt_name": receipt_name,
            "command": {"argv": command_argv, "shell": False}, "cwd": relative_cwd,
            "source_repository": repository, "source_head": head, "started_utc": started_utc,
            "ended_utc": ended_utc, "duration_ms": max(0, (perf_counter_ns() - started_ns) // 1_000_000),
            "exit_code": result["exit_code"], "child_exit_code": result["child_exit_code"],
            "outcome": result["outcome"], "launch_error": result["launch_error"],
            "timed_out": result["timed_out"], "timeout_seconds": timeout_seconds,
            "capture_complete": result["capture_complete"],
            "environment_variable_names": sorted(os.environ), "output_limit_bytes": output_limit_bytes,
            "stdout": _stream_record("stdout.txt", stdout, int(stdout_sink["observed"]), stdout_truncated, stdout_replacements),
            "stderr": _stream_record("stderr.txt", stderr, int(stderr_sink["observed"]), stderr_truncated, stderr_replacements),
            "redaction": {
                "secret_environment_names": sorted(set(secret_environment_names)),
                "automatically_sensitive_environment_names": automatic_names,
                "replacement_count": argv_replacements + stdout_replacements + stderr_replacements,
                "values_serialized": False,
            },
            "does_not_prove": DOES_NOT_PROVE,
        }
        serialized = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        (stage / "receipt.json").write_text(serialized, encoding="utf-8", newline="\n")
        _validate_staged(stage, receipt)
    print(str(receipt_dir / "receipt.json"))
    return int(result["exit_code"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--receipt-name", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--secret-env", action="append", default=[])
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_LIMIT)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--argv-json")
    commands.add_argument("--arg", action="append")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        command = _parse_argv(args.argv_json, args.arg)
        return record_command(
            evidence_root=args.evidence_root, artifact_root=args.artifact_root,
            receipt_name=args.receipt_name, cwd=args.cwd, argv=command,
            secret_environment_names=args.secret_env, output_limit_bytes=args.max_output_bytes,
            timeout_seconds=args.timeout_seconds,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(f"acceptance recorder: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
