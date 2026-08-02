"""Run one shell-free command and write a bounded, secret-safe receipt tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns


SCHEMA = "flywheel.acceptance-command/v1"
DEFAULT_EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "closeout" / "FW-2026-08-02-CLOSEOUT"
DEFAULT_OUTPUT_LIMIT = 1_000_000
DOES_NOT_PROVE = [
    "A recorded zero exit code does not prove command correctness.",
    "This receipt does not prove exhaustive coverage, cross-system reproducibility, or absence of unobserved side effects.",
]
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SENSITIVE_NAME = re.compile(
    r"(?:AUTHORIZATION|API[_-]?KEY|ACCESS[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE[_-]?KEY)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_-]?key|access[_-]?key|secret|token|password|passwd|credential)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
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


def _secret_inputs(explicit_names: list[str]) -> tuple[list[str], list[str]]:
    missing = sorted(name for name in explicit_names if name not in os.environ)
    if missing:
        raise ValueError("secret environment variable is not set: " + ", ".join(missing))
    automatic = sorted(name for name in os.environ if _SENSITIVE_NAME.search(name))
    names = sorted(set(explicit_names) | set(automatic))
    values = sorted({os.environ[name] for name in names if os.environ.get(name)}, key=len, reverse=True)
    return automatic, values


def _argv_secret_values(argv: list[str]) -> list[str]:
    values: set[str] = set()
    for index, item in enumerate(argv):
        option, separator, value = item.partition("=")
        if option.startswith("-") and _SENSITIVE_NAME.search(option):
            candidate = value if separator else (argv[index + 1] if index + 1 < len(argv) else "")
            if candidate:
                values.add(candidate)
    return sorted(values, key=len, reverse=True)


def _redact_text(text: str, secret_values: list[str]) -> str:
    redacted = text
    for value in secret_values:
        redacted = redacted.replace(value, "<redacted>")
    redacted = _PRIVATE_KEY.sub("<redacted:private-key>", redacted)
    redacted = _BEARER.sub("Bearer <redacted>", redacted)
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", redacted)


def _redact_argv(argv: list[str], secret_values: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        option, separator, value = item.partition("=")
        if option.startswith("-") and _SENSITIVE_NAME.search(option):
            redacted.append(f"{option}=<redacted>" if separator else option)
            hide_next = not separator
            continue
        redacted.append(_redact_text(item, secret_values))
    return redacted


def _capture_stream(pipe, keep_bytes: int, sink: dict[str, object]) -> None:
    captured = bytearray()
    observed = 0
    while True:
        chunk = pipe.read(65_536)
        if not chunk:
            break
        observed += len(chunk)
        remaining = keep_bytes - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
    pipe.close()
    sink["captured"] = bytes(captured)
    sink["observed"] = observed


def _bounded_redacted(data: bytes, observed: int, limit: int, secrets: list[str]) -> tuple[bytes, bool]:
    text = data.decode("utf-8", errors="replace")
    encoded = _redact_text(text, secrets).encode("utf-8")
    return encoded[:limit], observed > len(data) or len(encoded) > limit


def _stream_record(filename: str, data: bytes, observed: int, truncated: bool) -> dict[str, object]:
    return {
        "path": filename,
        "sha256": _sha256(data),
        "bytes": len(data),
        "observed_bytes": observed,
        "truncated": truncated,
    }


def record_command(
    *,
    evidence_root: Path,
    artifact_root: Path,
    receipt_name: str,
    cwd: Path,
    argv: list[str],
    secret_environment_names: list[str],
    output_limit_bytes: int,
) -> int:
    evidence_root = evidence_root.resolve()
    artifact_root = artifact_root.resolve()
    cwd = cwd.resolve()
    if not _inside(artifact_root, evidence_root):
        raise ValueError("artifact root must be inside the configured evidence root")
    if not _SAFE_NAME.fullmatch(receipt_name):
        raise ValueError("receipt name must use only letters, digits, dot, underscore, or hyphen")
    if output_limit_bytes < 1:
        raise ValueError("output limit must be positive")
    repository, head, relative_cwd = _repository_identity(cwd)
    automatic_names, secret_values = _secret_inputs(secret_environment_names)
    secret_values = sorted(set(secret_values) | set(_argv_secret_values(argv)), key=len, reverse=True)
    receipt_dir = (artifact_root / receipt_name).resolve()
    if not _inside(receipt_dir, artifact_root):
        raise ValueError("receipt directory must stay inside the artifact root")
    receipt_dir.mkdir(parents=True, exist_ok=False)

    overlap = max((len(value.encode("utf-8")) for value in secret_values), default=0) + 8_192
    keep_bytes = output_limit_bytes + overlap
    started_utc = _utc_now()
    started_ns = perf_counter_ns()
    launch_error = ""
    stdout_sink: dict[str, object] = {"captured": b"", "observed": 0}
    stderr_sink: dict[str, object] = {"captured": b"", "observed": 0}
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False
        )
        assert process.stdout is not None and process.stderr is not None
        threads = [threading.Thread(target=_capture_stream, args=(pipe, keep_bytes, sink))
                   for pipe, sink in ((process.stdout, stdout_sink), (process.stderr, stderr_sink))]
        for thread in threads:
            thread.start()
        exit_code = process.wait()
        for thread in threads:
            thread.join()
    except OSError as exc:
        exit_code = 127
        launch_error = _redact_text(f"{type(exc).__name__}: {exc}", secret_values)
        stderr_sink = {"captured": launch_error.encode("utf-8"), "observed": len(launch_error.encode("utf-8"))}

    ended_utc = _utc_now()
    duration_ms = max(0, (perf_counter_ns() - started_ns) // 1_000_000)
    stdout, stdout_truncated = _bounded_redacted(
        stdout_sink["captured"], int(stdout_sink["observed"]), output_limit_bytes, secret_values
    )
    stderr, stderr_truncated = _bounded_redacted(
        stderr_sink["captured"], int(stderr_sink["observed"]), output_limit_bytes, secret_values
    )
    receipt = {
        "schema": SCHEMA,
        "receipt_name": receipt_name,
        "command": {"argv": _redact_argv(argv, secret_values), "shell": False},
        "cwd": relative_cwd,
        "source_repository": repository,
        "source_head": head,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "launch_error": bool(launch_error),
        "environment_variable_names": sorted(os.environ),
        "output_limit_bytes": output_limit_bytes,
        "stdout": _stream_record("stdout.txt", stdout, int(stdout_sink["observed"]), stdout_truncated),
        "stderr": _stream_record("stderr.txt", stderr, int(stderr_sink["observed"]), stderr_truncated),
        "redaction": {
            "secret_environment_names": sorted(set(secret_environment_names)),
            "automatically_sensitive_environment_names": automatic_names,
            "values_serialized": False,
        },
        "does_not_prove": DOES_NOT_PROVE,
    }
    serialized = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if any(value in serialized or value.encode() in stdout or value.encode() in stderr for value in secret_values):
        raise RuntimeError("secret redaction invariant failed")
    (receipt_dir / "stdout.txt").write_bytes(stdout)
    (receipt_dir / "stderr.txt").write_bytes(stderr)
    temporary = receipt_dir / "receipt.json.tmp"
    temporary.write_text(serialized, encoding="utf-8", newline="\n")
    temporary.replace(receipt_dir / "receipt.json")
    print(str(receipt_dir / "receipt.json"))
    return exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--receipt-name", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--secret-env", action="append", default=[])
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_LIMIT)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--argv-json")
    commands.add_argument("--arg", action="append")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        command = _parse_argv(args.argv_json, args.arg)
        return record_command(
            evidence_root=args.evidence_root,
            artifact_root=args.artifact_root,
            receipt_name=args.receipt_name,
            cwd=args.cwd,
            argv=command,
            secret_environment_names=args.secret_env,
            output_limit_bytes=args.max_output_bytes,
        )
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(f"acceptance recorder: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
