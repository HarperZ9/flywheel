"""The raw lane's adapter: run raw-native once and return a verdict with a receipt.

raw-native (HarperZ9/raw-native, FSL-1.1-MIT) renders a built-in scene on the
CPU and certifies its screen-space AO against a ray-traced reference. The lane
has no MCP server. ``run`` resolves the hash-pinned binary
(``raw_lane_install.resolve``), runs it once in a temporary folder with a params
file, reads ``certificate.json``, ``arena_certificate.json``, ``channels.json``
and raw-native's own superstack ``receipt.json``, rechecks the certificate and
that receipt against the files beside them (level 1, ``certificates/raw_ao.py``),
and returns a ``RawRun``.

Execution mapping:

  exit 0                          COMPLETED
  exit 1                          RESOURCE_EXCEEDED (the arena certificate is refuted)
  exit 2                          HARNESS_ERROR (bad params are the caller's fault)
  any other exit                  CRASHED
  binary missing or not pinned    TOOLCHAIN_MISSING (UNVERIFIABLE, TOOLCHAIN_MISSING)
  past the time budget            TIMEOUT

On exit 0 the verdict is the certificate's, translated (verified PASS, refuted
FAIL, unverifiable UNVERIFIABLE). When the renderer's own files fail the level-1
recheck, the run is UNVERIFIABLE with ORACLE_UNAVAILABLE instead: a renderer
whose certificate disagrees with its own files is not a usable oracle.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import raw_lane_install as inst
from .certificates import raw_ao, raw_ao_receipt
from .oracle import OracleResult
from .verdict import Attribution, Execution, UnverifiableReason, Verdict

EXIT_EXECUTION = {0: Execution.COMPLETED, 1: Execution.RESOURCE_EXCEEDED,
                  2: Execution.HARNESS_ERROR}
_UNAVAILABLE = UnverifiableReason.ORACLE_UNAVAILABLE.value
_TOOLCHAIN = UnverifiableReason.TOOLCHAIN_MISSING.value
#: raw-native 0.4.0 renders 512 x 512 with the reference in about 1.0 s on one
#: thread (its README, median of 5). The budget allows 20 times that per 512 x 512
#: of frame, plus 10 s to start, because CI runners are slower and shared.
BASE_SECONDS, SECONDS_PER_512_SQUARE = 10.0, 20.0


@dataclass
class RawRun:
    result: OracleResult
    execution: Execution
    platform: str = ""
    rc: int | None = None
    certificate: dict | None = None
    arena: dict | None = None
    channels: dict | None = None
    receipt: dict | None = None
    files: dict = field(default_factory=dict)
    native_receipt: dict | None = None      # raw-native's own receipt.json (0.5.0+)


def budget_seconds(params: dict) -> float:
    try:
        pixels = int(params.get("width", 256)) * int(params.get("height", 256))
    except (TypeError, ValueError, AttributeError):
        pixels = 256 * 256
    return BASE_SECONDS + SECONDS_PER_512_SQUARE * max(pixels, 1) / (512 * 512)


def _not_run(execution: Execution, verdict: Verdict, reason: str, detail: str,
             attribution: Attribution | None = None, **kw) -> RawRun:
    result = raw_ao.oracle_result(None, verdict, detail, reason=reason,
                                  execution=execution, attribution=attribution)
    return RawRun(result, execution, **kw)


def _read_json(files: dict, name: str) -> dict | None:
    data = files.get(name)
    return raw_ao.load_certificate(data.decode("utf-8", "replace"))[0] if data else None


def _spawn(binary: Path, params: dict, timeout: float) -> tuple[int, dict, str]:
    """Run the binary once; return (exit code, files written, output excerpt)."""
    with tempfile.TemporaryDirectory(prefix="flywheel-raw-") as tmp:
        work = Path(tmp)
        (work / "params.json").write_text(json.dumps(params), encoding="utf-8")
        out = work / "out"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        env = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
        proc = subprocess.run(
            [str(binary), "--params", str(work / "params.json"), "--out", str(out)],
            cwd=str(work), env=env, capture_output=True, timeout=timeout,
            creationflags=flags, check=False)
        files = ({p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
                 if out.is_dir() else {})
    said = (proc.stderr or b"") + (proc.stdout or b"")
    return proc.returncode, files, said.decode("utf-8", "replace")[-600:]


def _completed(run: RawRun) -> RawRun:
    """Exit 0: translate the verdict, then recheck the renderer's own files."""
    cert = run.certificate
    translation = raw_ao.translate(cert)
    check = raw_ao.level1(cert, run.files) if cert is not None else None
    verdict, reason, detail = translation.verdict, translation.reason, translation.note
    if check is not None and check["verdict"] != Verdict.PASS.value:
        verdict, reason = Verdict.UNVERIFIABLE, _UNAVAILABLE
        detail = f"the renderer's own files fail the level-1 recheck: {check['detail']}"
    attribution = Attribution.ENVIRONMENT if verdict is Verdict.UNVERIFIABLE else None
    run.result = raw_ao.oracle_result(
        cert, verdict, detail or f"raw-native verdict {translation.raw_verdict}",
        reason=reason, attribution=attribution,
        coverage={"level": "run", "identity": check and check["identity"]})
    if cert is not None:
        run.receipt = raw_ao_receipt.level1_receipt(
            cert, run.files, level="run", platform=run.platform,
            flywheel={"verdict": verdict.value, "reason": reason,
                      "raw_verdict": translation.raw_verdict,
                      "level1": check and check["verdict"],
                      "execution": Execution.COMPLETED.value,
                      "arena_verdict": (run.arena or {}).get("verdict")})
    return run


def run(params: dict, *, environ=None, timeout: float | None = None,
        pins: inst.Pins = inst.PINS, plat: str | None = None) -> RawRun:
    """Render once with ``params`` (raw-native's params object) and judge it."""
    plat = plat or inst.platform_key() or ""
    try:
        binary = inst.resolve(environ, pins, plat or None)
    except inst.Refused as e:
        return _not_run(Execution.TOOLCHAIN_MISSING, Verdict.UNVERIFIABLE, _TOOLCHAIN,
                        str(e), platform=plat)
    budget = budget_seconds(params) if timeout is None else timeout
    try:
        rc, files, said = _spawn(binary, params, budget)
    except subprocess.TimeoutExpired:
        return _not_run(Execution.TIMEOUT, Verdict.UNVERIFIABLE, _UNAVAILABLE,
                        f"raw-native ran past its {budget:.1f} s budget",
                        Attribution.HARNESS, platform=plat)
    except OSError as e:
        return _not_run(Execution.TOOLCHAIN_MISSING, Verdict.UNVERIFIABLE, _TOOLCHAIN,
                        f"raw-native could not start: {e}", platform=plat)
    execution = EXIT_EXECUTION.get(rc, Execution.CRASHED)
    run_ = RawRun(None, execution, plat, rc, _read_json(files, "certificate.json"),
                  _read_json(files, "arena_certificate.json"),
                  _read_json(files, "channels.json"), None, files,
                  _read_json(files, "receipt.json"))
    if execution is Execution.COMPLETED:
        return _completed(run_)
    if execution is Execution.RESOURCE_EXCEEDED:
        run_.result = raw_ao.oracle_result(
            run_.arena, Verdict.FAIL, "memory budget breached; the arena certificate "
            f"says {(run_.arena or {}).get('verdict')!r}", execution=execution)
        return run_
    attribution = Attribution.HARNESS if execution is Execution.CRASHED else None
    run_.result = raw_ao.oracle_result(
        None, Verdict.UNVERIFIABLE, f"raw-native exited {rc}: {said.strip()}",
        reason=_UNAVAILABLE, execution=execution, attribution=attribution)
    return run_


def status(environ=None, pins: inst.Pins = inst.PINS) -> tuple[bool, str]:
    """(present, detail) for the lane roster. Re-hashes the binary; runs nothing."""
    try:
        path = inst.resolve(environ, pins)
    except inst.Refused as e:
        return False, f"{inst.TOOLCHAIN_MISSING}: {e}"
    return True, (f"adapter lane; raw-native {pins.version} binary {path.name} matches "
                  "its pinned SHA-256; no MCP server")
