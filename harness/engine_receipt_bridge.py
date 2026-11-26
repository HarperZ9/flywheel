"""Canonical engine-receipt/1 helper shared across Flywheel harness and packages.

Produces and verifies fail-closed in-toto Statement/v1 envelopes compatible with
the workstation interop verifier (`engine_to_flywheel_receipt.py verify`):
  - Missing oracle execution stays UNVERIFIABLE.
  - Non-zero exit code or any fail marker stays DRIFT.
  - Only exit_code == 0 and fail_lines == 0 promotes verdict to MATCH.

Pure stdlib Python. Every function <= 50 lines, <= 200 lines total.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "engine-receipt/1"
IN_TOTO_STATEMENT = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://flywheel.dev/EngineReceipt/v1"
PASS_LINE_RE = re.compile(r"^\s*(\[PASS\]|PASS\b|ok\b|.*\bsame$)")
FAIL_LINE_RE = re.compile(r"^\s*(\[FAIL\]|FAIL:|FAILED\b|ERROR:|.*\bDIFF$)")


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return "sha256:" + h.hexdigest(), size


def collect_artifacts(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    resolved_root = root.resolve()
    for p in sorted({Path(x).resolve() for x in paths}):
        if not p.is_file():
            raise FileNotFoundError(f"artifact not found: {p}")
        digest, size = sha256_file(p)
        try:
            rel = str(p.relative_to(resolved_root)).replace("\\", "/")
        except ValueError:
            rel = p.name
        items.append({"rel_path": rel, "abs_path": str(p), "sha256": digest, "bytes": size})
    return items


def run_oracle(command: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    combined = stdout + ("\n" + stderr if stderr else "")
    return {
        "command": list(command),
        "cwd": str(cwd.resolve()),
        "exit_code": proc.returncode,
        "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
        "pass_lines": sum(1 for ln in combined.splitlines() if PASS_LINE_RE.search(ln)),
        "fail_lines": sum(1 for ln in combined.splitlines() if FAIL_LINE_RE.search(ln)),
        "stdout_excerpt": stdout[:1200],
    }


def make_oracle_record(
    command: list[str], cwd: Path, exit_code: int, stdout: str = "", stderr: str = "",
    *, pass_lines: int | None = None, fail_lines: int | None = None,
) -> dict[str, Any]:
    combined = stdout + ("\n" + stderr if stderr else "")
    return {
        "command": list(command),
        "cwd": str(cwd.resolve()),
        "exit_code": int(exit_code),
        "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
        "pass_lines": sum(1 for ln in combined.splitlines() if PASS_LINE_RE.search(ln)) if pass_lines is None else int(pass_lines),
        "fail_lines": sum(1 for ln in combined.splitlines() if FAIL_LINE_RE.search(ln)) if fail_lines is None else int(fail_lines),
        "stdout_excerpt": stdout[:1200],
    }


def derive_scope(engine: str, oracle: dict[str, Any] | None, artifacts: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"engine={engine}; fail-closed receipt bridge between engine verification and Flywheel",
        f"hashed {len(artifacts)} artifact file(s) with SHA-256 at emission time",
    ]
    if not oracle:
        lines.append("no oracle command executed: standing remains UNVERIFIABLE until an oracle runs")
    elif oracle["exit_code"] == 0:
        lines.append(
            f"oracle exited 0 with {oracle['pass_lines']} pass marker(s) and {oracle['fail_lines']} fail marker(s); "
            "proves the named command passed on this commit and artifacts, not unexecuted surfaces"
        )
    else:
        lines.append(f"oracle exited {oracle['exit_code']}: standing is DRIFT")
    return lines


def compute_digests(subject: dict[str, Any], claim: dict[str, Any], hmac_key: str | None = None) -> dict[str, Any]:
    subj_sha = sha256_bytes(canonical_bytes(subject))
    claim_sha = sha256_bytes(canonical_bytes(claim))
    seal_payload = {"schema": SCHEMA, "subject_sha256": subj_sha, "claim_sha256": claim_sha}
    env_sha = sha256_bytes(canonical_bytes(seal_payload))
    sig = None
    if hmac_key:
        sig = "hmac-sha256:" + hmac.new(hmac_key.encode("utf-8"), canonical_bytes(seal_payload), hashlib.sha256).hexdigest()
    return {"subject_sha256": subj_sha, "claim_sha256": claim_sha, "envelope_sha256": env_sha, "signature": sig}


def build_receipt(
    engine: str, flagship: str, task_id: str, root: Path, artifact_paths: list[Path],
    *, oracle_cmd: list[str] | None = None, oracle: dict[str, Any] | None = None,
    git_info: dict[str, str] | None = None, hmac_key: str | None = None,
) -> dict[str, Any]:
    artifacts = collect_artifacts(root, artifact_paths)
    obs = oracle if oracle is not None else (run_oracle(oracle_cmd, root) if oracle_cmd else None)
    verdict = "UNVERIFIABLE" if obs is None else ("MATCH" if obs["exit_code"] == 0 and obs["fail_lines"] == 0 else "DRIFT")
    subject = {
        "engine": engine, "flagship": flagship, "task_id": task_id,
        "git": git_info or {"commit": "", "short_commit": "", "branch": "", "subject": ""},
        "artifacts": [{"rel_path": a["rel_path"], "sha256": a["sha256"], "bytes": a["bytes"]} for a in artifacts],
        "oracle_command": obs["command"] if obs else [],
    }
    oracle_claim = (
        {k: obs[k] for k in ("exit_code", "stdout_sha256", "stderr_sha256", "pass_lines", "fail_lines")}
        if obs else None
    )
    scope = derive_scope(engine, obs, artifacts)
    claim = {"subject": subject, "verdict": verdict, "oracle": oracle_claim, "scope": scope}
    return {
        "schema": SCHEMA, "in_toto_statement_type": IN_TOTO_STATEMENT, "predicate_type": PREDICATE_TYPE,
        "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": subject, "verdict": verdict, "oracle": obs,
        "artifact_paths": {a["rel_path"]: a["abs_path"] for a in artifacts},
        "scope": scope, "digests": compute_digests(subject, claim, hmac_key=hmac_key),
    }


def verify_receipt(receipt: dict[str, Any], *, check_files: bool = False, hmac_key: str | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if receipt.get("schema") != SCHEMA:
        errors.append(f"unexpected schema: {receipt.get('schema')}")
    subject = receipt.get("subject") or {}
    oracle = receipt.get("oracle")
    oracle_claim = (
        {k: oracle[k] for k in ("exit_code", "stdout_sha256", "stderr_sha256", "pass_lines", "fail_lines")}
        if isinstance(oracle, dict) else None
    )
    verdict = receipt.get("verdict")
    if verdict == "MATCH" and (not oracle_claim or oracle_claim.get("exit_code") != 0 or oracle_claim.get("fail_lines", 0) != 0):
        errors.append("fail-closed violation: MATCH verdict without passing exit-0 oracle")
    expected_scope = derive_scope(subject.get("engine", ""), oracle if isinstance(oracle, dict) else None, subject.get("artifacts", []))
    if receipt.get("scope") != expected_scope:
        errors.append("scope mismatch: derived scope does not match stored scope")
    claim = {"subject": subject, "verdict": verdict, "oracle": oracle_claim, "scope": expected_scope}
    expected = compute_digests(subject, claim, hmac_key=hmac_key)
    stored = receipt.get("digests") or {}
    for field in ("subject_sha256", "claim_sha256", "envelope_sha256"):
        if stored.get(field) != expected[field]:
            errors.append(f"digest mismatch on {field}: stored={stored.get(field)} expected={expected[field]}")
    if hmac_key and stored.get("signature") != expected["signature"]:
        errors.append("HMAC-SHA256 signature mismatch")
    if check_files:
        path_map = receipt.get("artifact_paths") or {}
        for art in subject.get("artifacts", []):
            fp = Path(path_map.get(art["rel_path"], ""))
            if not fp.is_file():
                errors.append(f"missing artifact file: {fp}")
            else:
                live_sha, _ = sha256_file(fp)
                if live_sha != art["sha256"]:
                    errors.append(f"artifact SHA-256 drift on {art['rel_path']}: live={live_sha} receipt={art['sha256']}")
    return len(errors) == 0, errors
