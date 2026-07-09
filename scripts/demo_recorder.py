"""Zero-dependency demo shot recorder.

Runs a demo script (JSON list of titled shell steps), captures honest
stdout/stderr/exit-code/wall-time evidence per step, and emits:

* demos/<name>/transcript.json  (schema harness.demo-transcript/v1)
* demos/<name>/player.html      (self-contained offline terminal player)

Python 3.12 stdlib only. No external dependencies, no network of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    from scripts.demo_player_html import render_player_html
except ImportError:  # direct invocation: python scripts/demo_recorder.py
    from demo_player_html import render_player_html

TRANSCRIPT_SCHEMA = "harness.demo-transcript/v1"
DEFAULT_STEP_TIMEOUT_SECONDS = 120.0
MAX_CAPTURED_CHARS = 100_000
DRY_RUN_PLACEHOLDER = (
    "[dry-run] command not executed\n"
    "$ {command}\n"
    "(placeholder output so the demo pipeline can be tested with no side effects)"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _truncate(text: str) -> str:
    if len(text) <= MAX_CAPTURED_CHARS:
        return text
    dropped = len(text) - MAX_CAPTURED_CHARS
    return text[:MAX_CAPTURED_CHARS] + f"\n[recorder] output truncated: {dropped} characters dropped"


def load_demo_script(path: Path) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = raw.get("steps") if isinstance(raw, dict) else raw
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"demo script must be a non-empty list of steps: {path}")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"step {index} is not an object")
        for key in ("title", "command", "narration"):
            if not isinstance(step.get(key), str) or not step[key].strip():
                raise ValueError(f"step {index} is missing a non-empty '{key}'")
    return steps


def execute_step(
    step: dict,
    *,
    index: int,
    dry_run: bool,
    timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
    cwd: Path | None = None,
) -> dict:
    command = step["command"]
    if dry_run:
        stdout = DRY_RUN_PLACEHOLDER.format(command=command)
        stderr = ""
        exit_code = 0
        duration_ms = 0
        mode = "dry-run"
    else:
        mode = "live"
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout_seconds,
                cwd=str(cwd or _repo_root()),
            )
            stdout = completed.stdout.decode("utf-8", errors="replace")
            stderr = completed.stderr.decode("utf-8", errors="replace")
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            stderr += f"\n[recorder] step timed out after {timeout_seconds:g} seconds"
            exit_code = -1
        duration_ms = int(round((time.perf_counter() - started) * 1000))

    stdout = _truncate(stdout).replace("\r\n", "\n")
    stderr = _truncate(stderr).replace("\r\n", "\n")
    output = stdout if not stderr.strip() else (stdout + ("\n" if stdout else "") + stderr)
    return {
        "index": index,
        "title": step["title"],
        "narration": step["narration"],
        "command": command,
        "mode": mode,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
        "output": output,
        "output_sha256": _sha256_text(output),
    }


def transcript_receipt(steps: list[dict]) -> str:
    canonical = json.dumps(steps, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _sha256_text(canonical)


def build_transcript(name: str, steps: list[dict], *, dry_run: bool) -> dict:
    return {
        "schema": TRANSCRIPT_SCHEMA,
        "name": name,
        "timestamp_utc": _now_utc(),
        "dry_run": dry_run,
        "step_count": len(steps),
        "total_duration_ms": sum(int(step.get("duration_ms", 0)) for step in steps),
        "steps": steps,
        "receipt_sha256": transcript_receipt(steps),
    }


def record_demo(
    script_path: Path,
    name: str,
    *,
    out_root: Path | None = None,
    dry_run: bool = False,
    timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
    cwd: Path | None = None,
) -> dict:
    script_steps = load_demo_script(script_path)
    results = [
        execute_step(step, index=index, dry_run=dry_run, timeout_seconds=timeout_seconds, cwd=cwd)
        for index, step in enumerate(script_steps)
    ]
    transcript = build_transcript(name, results, dry_run=dry_run)

    demo_dir = Path(out_root or (_repo_root() / "demos")) / name
    demo_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = demo_dir / "transcript.json"
    player_path = demo_dir / "player.html"
    transcript_path.write_text(
        json.dumps(transcript, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    player_path.write_text(render_player_html(transcript), encoding="utf-8")
    return {
        "transcript": transcript,
        "transcript_path": str(transcript_path),
        "player_path": str(player_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", required=True, help="path to the demo script JSON")
    parser.add_argument("--name", required=True, help="demo name; outputs land in demos/<name>/")
    parser.add_argument("--dry-run", action="store_true", help="execute nothing; emit placeholder output")
    parser.add_argument("--out-root", default="", help="override the demos/ output root")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_STEP_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    result = record_demo(
        Path(args.script),
        args.name,
        out_root=Path(args.out_root) if args.out_root else None,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
    )
    transcript = result["transcript"]
    print(f"recorded {transcript['step_count']} steps in {transcript['total_duration_ms']} ms")
    for step in transcript["steps"]:
        print(
            f"  [{step['index']}] {step['title']}: exit={step['exit_code']} "
            f"{step['duration_ms']} ms ({step['mode']})"
        )
    print(f"transcript: {result['transcript_path']}")
    print(f"player:     {result['player_path']}")
    print(f"receipt:    sha256:{transcript['receipt_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
