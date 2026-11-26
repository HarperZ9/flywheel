"""Canonical engine-receipt/1 emitter and verifier for Forum ledger runs."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "engine-receipt/1"
IN_TOTO_STATEMENT = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://flywheel.dev/EngineReceipt/v1"


def _canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return "sha256:" + h.hexdigest(), size


def _derive_scope(engine: str, oracle: dict[str, Any] | None, artifacts: list[dict[str, Any]]) -> list[str]:
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


def _compute_digests(subject: dict[str, Any], claim: dict[str, Any], hmac_key: str | None) -> dict[str, Any]:
    subj_sha = _sha256_bytes(_canonical_bytes(subject))
    claim_sha = _sha256_bytes(_canonical_bytes(claim))
    seal = {"schema": SCHEMA, "subject_sha256": subj_sha, "claim_sha256": claim_sha}
    env_sha = _sha256_bytes(_canonical_bytes(seal))
    sig = None
    if hmac_key:
        sig = "hmac-sha256:" + hmac.new(hmac_key.encode("utf-8"), _canonical_bytes(seal), hashlib.sha256).hexdigest()
    return {"subject_sha256": subj_sha, "claim_sha256": claim_sha, "envelope_sha256": env_sha, "signature": sig}


def emit_forum_engine_receipt(
    task_id: str,
    root: Path,
    artifact_paths: list[Path],
    *,
    verified: bool | None,
    pass_count: int = 0,
    fail_count: int = 0,
    command: list[str] | None = None,
    summary: str = "",
    hmac_key: str | None = None,
) -> dict[str, Any]:
    """Emit a fail-closed canonical engine-receipt/1 envelope for Forum."""
    resolved_root = root.resolve()
    artifacts: list[dict[str, Any]] = []
    for p in sorted({Path(x).resolve() for x in artifact_paths}):
        if not p.is_file():
            raise FileNotFoundError(f"artifact not found: {p}")
        digest, size = _sha256_file(p)
        try:
            rel = str(p.relative_to(resolved_root)).replace("\\", "/")
        except ValueError:
            rel = p.name
        artifacts.append({"rel_path": rel, "abs_path": str(p), "sha256": digest, "bytes": size})
    oracle: dict[str, Any] | None = None
    if verified is not None:
        oracle = {
            "command": list(command or ["forum", "verify"]),
            "cwd": str(resolved_root),
            "exit_code": 0 if verified else 1,
            "stdout_sha256": _sha256_bytes(summary.encode("utf-8")),
            "stderr_sha256": _sha256_bytes(b""),
            "pass_lines": int(pass_count),
            "fail_lines": int(fail_count),
            "stdout_excerpt": summary[:1200],
        }
    verdict = "UNVERIFIABLE" if oracle is None else ("MATCH" if oracle["exit_code"] == 0 and oracle["fail_lines"] == 0 else "DRIFT")
    subject = {
        "engine": "forum", "flagship": "flywheel", "task_id": task_id,
        "git": {"commit": "", "short_commit": "", "branch": "", "subject": ""},
        "artifacts": [{"rel_path": a["rel_path"], "sha256": a["sha256"], "bytes": a["bytes"]} for a in artifacts],
        "oracle_command": oracle["command"] if oracle else [],
    }
    oracle_claim = (
        {k: oracle[k] for k in ("exit_code", "stdout_sha256", "stderr_sha256", "pass_lines", "fail_lines")}
        if oracle else None
    )
    scope = _derive_scope("forum", oracle, artifacts)
    claim = {"subject": subject, "verdict": verdict, "oracle": oracle_claim, "scope": scope}
    return {
        "schema": SCHEMA, "in_toto_statement_type": IN_TOTO_STATEMENT, "predicate_type": PREDICATE_TYPE,
        "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": subject, "verdict": verdict, "oracle": oracle,
        "artifact_paths": {a["rel_path"]: a["abs_path"] for a in artifacts},
        "scope": scope, "digests": _compute_digests(subject, claim, hmac_key),
    }


def verify_forum_engine_receipt(
    receipt: dict[str, Any], *, check_files: bool = False, hmac_key: str | None = None,
) -> tuple[bool, list[str]]:
    """Verify a Forum engine-receipt/1 envelope fail-closed."""
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
    expected_scope = _derive_scope(str(subject.get("engine", "")), oracle if isinstance(oracle, dict) else None, list(subject.get("artifacts", [])))
    if receipt.get("scope") != expected_scope:
        errors.append("scope mismatch: derived scope does not match stored scope")
    claim = {"subject": subject, "verdict": verdict, "oracle": oracle_claim, "scope": expected_scope}
    expected = _compute_digests(subject, claim, hmac_key)
    stored = receipt.get("digests") or {}
    for field in ("subject_sha256", "claim_sha256", "envelope_sha256"):
        if stored.get(field) != expected[field]:
            errors.append(f"digest mismatch on {field}")
    if hmac_key and stored.get("signature") != expected["signature"]:
        errors.append("HMAC-SHA256 signature mismatch")
    if check_files:
        path_map = receipt.get("artifact_paths") or {}
        for art in subject.get("artifacts", []):
            fp = Path(path_map.get(art["rel_path"], ""))
            if not fp.is_file():
                errors.append(f"missing artifact file: {fp}")
            else:
                live_sha, _ = _sha256_file(fp)
                if live_sha != art["sha256"]:
                    errors.append(f"artifact SHA-256 drift on {art['rel_path']}")
    return len(errors) == 0, errors
