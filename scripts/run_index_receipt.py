"""Run Index through its CLI surface and emit a receipt.

This is the harness fallback for cases where the Index MCP transport is
unavailable. It keeps the failure visible while preserving the required
workspace-map/context evidence path for benchmark and tool-integration runs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402

JSON_LANES = {"map", "context", "context-envelope", "graph", "check"}
DEGRADED_SUCCESS_VERDICTS = {"MATCH", "DEGRADED_MATCH"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def decode_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def build_index_command(
    *,
    python_exe: str,
    lane: str,
    root: str,
    budget: int,
    focus: str,
    hops: int | None,
    max_docs: int,
    freshness: bool,
) -> list[str]:
    cmd = [python_exe, "-m", "index_graph.cli", lane, "--root", root]
    if lane == "context-envelope":
        cmd.extend(["--budget", str(budget), "--json"])
        if focus:
            cmd.extend(["--focus", focus])
        if hops is not None:
            cmd.extend(["--hops", str(hops)])
    elif lane == "context":
        cmd.append("--json")
        if focus:
            cmd.extend(["--focus", focus])
        if hops is not None:
            cmd.extend(["--hops", str(hops)])
    elif lane in {"map", "graph"}:
        cmd.append("--json")
    elif lane == "check":
        if freshness:
            cmd.append("--freshness")
        cmd.append("--json")
    elif lane == "router":
        cmd.extend(["--max-docs", str(max_docs)])
    else:
        raise ValueError(f"unsupported lane: {lane}")
    return cmd


def build_index_env(index_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = str((index_root / "src").resolve())
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    return env


def parse_json_stdout(stdout: str) -> tuple[bool, str]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return False, ""
    if isinstance(payload, dict):
        return True, str(payload.get("schema", ""))
    return True, ""


def output_valid_for_lane(*, lane: str, stdout: str) -> tuple[bool, str]:
    expects_json = lane in JSON_LANES
    if not stdout.strip():
        return False, ""
    if expects_json:
        return parse_json_stdout(stdout)
    return True, ""


def classify_live_result(
    *,
    lane: str,
    returncode: int | None,
    stdout: str,
    timed_out: bool,
    dry_run: bool,
) -> tuple[str, str]:
    if dry_run:
        return "DRY_RUN", ""
    if timed_out:
        return "UNVERIFIABLE", "timeout"
    if returncode != 0:
        return "UNVERIFIABLE", "nonzero_exit"
    if not stdout.strip():
        return "UNVERIFIABLE", "empty_stdout"
    valid, _schema = output_valid_for_lane(lane=lane, stdout=stdout)
    if not valid:
        return "UNVERIFIABLE", "invalid_json"
    return "MATCH", ""


def read_stale_artifact(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def summarize_result(
    *,
    lane: str,
    root: str,
    index_root: str,
    command: list[str],
    returncode: int | None,
    elapsed_ms: int,
    stdout: str,
    stderr: str,
    artifact_path: str,
    timed_out: bool = False,
    dry_run: bool = False,
    stale_stdout: str = "",
    stale_artifact_path: str = "",
) -> dict:
    expects_json = lane in JSON_LANES
    live_verdict, live_failure_code = classify_live_result(
        lane=lane,
        returncode=returncode,
        stdout=stdout,
        timed_out=timed_out,
        dry_run=dry_run,
    )
    stale_valid, stale_schema = output_valid_for_lane(lane=lane, stdout=stale_stdout)
    stale_artifact_used = bool(live_verdict == "UNVERIFIABLE" and stale_valid)
    effective_stdout = stale_stdout if stale_artifact_used else stdout
    json_valid = False
    output_schema = ""
    if expects_json and effective_stdout.strip():
        json_valid, output_schema = parse_json_stdout(effective_stdout)
    elif stale_artifact_used:
        output_schema = stale_schema

    verdict = "DEGRADED_MATCH" if stale_artifact_used else live_verdict
    failure_code = "" if stale_artifact_used else live_failure_code

    return {
        "schema": "harness.index-cli-receipt/v1",
        "created_utc": utc_now(),
        "lane": lane,
        "root": root,
        "index_root": index_root,
        "command": command,
        "returncode": returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_sha256": text_sha256(stdout),
        "stderr_sha256": text_sha256(stderr),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
        "effective_output_source": "stale_artifact" if stale_artifact_used else "live_stdout",
        "effective_stdout_sha256": text_sha256(effective_stdout),
        "effective_stdout_bytes": len(effective_stdout.encode("utf-8")),
        "live_verdict": live_verdict,
        "live_failure_code": live_failure_code,
        "stale_artifact_path": stale_artifact_path,
        "stale_artifact_sha256": text_sha256(stale_stdout) if stale_stdout else "",
        "stale_artifact_valid": stale_valid,
        "stale_artifact_used": stale_artifact_used,
        "artifact_path": artifact_path,
        "output_format": "json" if expects_json else "markdown",
        "output_json_valid": json_valid if expects_json else None,
        "output_schema": output_schema,
        "verdict": verdict,
        "failure_code": failure_code,
        "artifact_write_policy": "preserve_stale_on_degraded" if stale_artifact_used else "write_live_stdout",
        "dependency_posture": "zero-mandatory",
        "mcp_fallback_reason": "index MCP transport unavailable or degraded",
    }


def write_text(path: str, text: str) -> str:
    if not path:
        return ""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=sorted(JSON_LANES | {"router"}), default="context-envelope")
    parser.add_argument("--root", default="C:/dev")
    parser.add_argument("--index-root", default="C:/dev/public/index")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--budget", type=int, default=12000)
    parser.add_argument("--focus", default="")
    parser.add_argument("--hops", type=int, default=None)
    parser.add_argument("--max-docs", type=int, default=500)
    parser.add_argument("--freshness", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--artifact-out", default="")
    parser.add_argument("--stale-artifact", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    index_root = Path(args.index_root).resolve()
    command = build_index_command(
        python_exe=args.python,
        lane=args.lane,
        root=args.root,
        budget=args.budget,
        focus=args.focus,
        hops=args.hops,
        max_docs=args.max_docs,
        freshness=args.freshness,
    )

    stdout = ""
    stderr = ""
    returncode: int | None = None
    timed_out = False
    elapsed_ms = 0
    stale_artifact_path = args.stale_artifact or args.artifact_out
    stale_stdout = read_stale_artifact(stale_artifact_path)

    if not args.dry_run:
        started = perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(index_root),
                env=build_index_env(index_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
            stdout = decode_output(completed.stdout)
            stderr = decode_output(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = decode_output(exc.stdout or b"")
            stderr = decode_output(exc.stderr or b"")
        elapsed_ms = int((perf_counter() - started) * 1000)

    receipt = summarize_result(
        lane=args.lane,
        root=args.root,
        index_root=str(index_root),
        command=command,
        returncode=returncode,
        elapsed_ms=elapsed_ms,
        stdout=stdout,
        stderr=stderr,
        artifact_path=args.artifact_out,
        timed_out=timed_out,
        dry_run=args.dry_run,
        stale_stdout=stale_stdout,
        stale_artifact_path=stale_artifact_path,
    )
    if args.artifact_out and not receipt["stale_artifact_used"]:
        write_text(args.artifact_out, stdout)
    artifact_path = args.artifact_out

    store_outputs = []
    if args.store_root and not args.dry_run:
        store = FileBackedHarnessStore(Path(args.store_root))
        store_outputs.append(store.put_receipt(
            kind="index_cli_receipt",
            body=receipt,
            run_id=args.run_id,
            verdict=receipt["verdict"],
        ))
        if artifact_path:
            store_outputs.append(store.copy_artifact(
                Path(artifact_path),
                run_id=args.run_id,
                label=f"index-{args.lane}-stdout",
            ))

    result = {
        "schema": "harness.index-cli-command/v1",
        "receipt": receipt,
        "store_outputs": store_outputs,
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        write_text(args.out, text)
    return 0 if args.dry_run or receipt["verdict"] in DEGRADED_SUCCESS_VERDICTS else 1


if __name__ == "__main__":
    raise SystemExit(main())
