# SPDX-License-Identifier: MIT
"""Deterministic sharded proof-certificate replay verifier.

Replays buildlang.gpu-tv-cert/v1 and buildlang.superopt-cert/v1 proof
artifacts across configurable worker shards with guaranteed worker-count
invariance (shards=1 matches shards=4).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

HONEST_SCOPE_LIMIT = (
    "Replays and checks serialized buildlang.gpu-tv-cert/v1 and "
    "buildlang.superopt-cert/v1 certificates across deterministic worker "
    "shards. Does not re-run e-graph saturation, SMT equivalence solvers, or "
    "GPU shader compilers."
)

GPU_CERT_SCHEMA = "buildlang.gpu-tv-cert/v1"
SUPEROPT_CERT_SCHEMA = "buildlang.superopt-cert/v1"
TARGET_SHADER_EXT: dict[str, str] = {
    "wgsl": ".wgsl",
    "hlsl": ".hlsl",
    "msl": ".metal",
    "spirv": ".spv",
    "glsl": ".glsl",
}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_RULE_ID_RE = re.compile(r"^R\d+_[A-Z0-9_]+$")


@dataclass(frozen=True)
class ProofArtifact:
    """One replayable proof certificate with optional paired shader bytes."""

    artifact_id: str
    cert: Mapping[str, object]
    shader_bytes: bytes | None = None
    expected_cert_sha256: str | None = None


@dataclass(frozen=True)
class ReplayItemResult:
    """Fail-closed replay verification result for one ProofArtifact."""

    artifact_id: str
    passed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize replay result into a JSON-compatible dictionary."""
        return {"artifact_id": self.artifact_id, "passed": self.passed, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ShardedReplayReport:
    """Worker-count-invariant replay summary across a proof corpus."""

    passed: bool
    shards: int
    artifacts_checked: int
    artifacts_passed: int
    results: tuple[ReplayItemResult, ...]
    replay_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize sharded replay summary into a JSON-compatible dict."""
        return {
            "passed": self.passed,
            "shards": self.shards,
            "artifacts_checked": self.artifacts_checked,
            "artifacts_passed": self.artifacts_passed,
            "results": [r.to_dict() for r in self.results],
            "replay_attestation_sha256": self.replay_attestation_sha256,
        }


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX64_RE.fullmatch(value))


def _is_nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _verify_steps(steps: list[object], reasons: list[str], max_ulps: int) -> tuple[int, int, bool]:
    sb_sum, sa_sum, steps_ok = 0, 0, True
    for idx, step in enumerate(steps):
        if not isinstance(step, Mapping):
            reasons.append(f"INVALID_STEP:{idx}")
            steps_ok = False
            continue
        rule = step.get("rule")
        if not isinstance(rule, str) or not _RULE_ID_RE.fullmatch(rule):
            reasons.append(f"INVALID_RULE_ID:{idx}:{rule}")
        sb, sa = step.get("cost_before"), step.get("cost_after")
        if not _is_nonneg_int(sb) or not _is_nonneg_int(sa):
            reasons.append(f"NEGATIVE_OR_INVALID_STEP_COST:{idx}")
            steps_ok = False
        else:
            sb_sum += int(sb)
            sa_sum += int(sa)
            if int(sa) > int(sb):
                reasons.append(f"STEP_COST_INVERSION:{idx}:{sb}->{sa}")
        witness = step.get("error_witness")
        if isinstance(witness, Mapping) and "max_ulps" in witness:
            ulps = witness["max_ulps"]
            if not _is_nonneg_int(ulps) or int(ulps) > max_ulps:
                reasons.append(f"ULP_BOUND_EXCEEDED:{idx}:{ulps}")
    return sb_sum, sa_sum, steps_ok


def _verify_superopt_inner(so: Mapping[str, object], reasons: list[str], max_ulps: int) -> None:
    if so.get("schema") != SUPEROPT_CERT_SCHEMA:
        reasons.append("INVALID_SUPEROPT_SCHEMA")
    if so.get("verified") is not True:
        reasons.append("SUPEROPT_NOT_VERIFIED")
    for field in ("mir_before_sha256", "mir_after_sha256", "cert_sha256"):
        if not _is_hex64(so.get(field)):
            reasons.append(f"MALFORMED_{field.upper()}")
    tb, ta, rw = so.get("total_cost_before"), so.get("total_cost_after"), so.get("rewrites_applied")
    valid_totals = _is_nonneg_int(tb) and _is_nonneg_int(ta)
    if not valid_totals:
        reasons.append("NEGATIVE_OR_INVALID_TOTAL_COST")
    elif int(ta) > int(tb):
        reasons.append(f"COST_INVERSION:{tb}->{ta}")
    rw_int = int(rw) if _is_nonneg_int(rw) else -1
    if rw_int < 0:
        reasons.append("INVALID_REWRITES_APPLIED")
    steps = so.get("steps")
    if not isinstance(steps, list):
        reasons.append("INVALID_STEPS_LIST")
        return
    if rw_int >= 0 and len(steps) != rw_int:
        reasons.append(f"STEP_COUNT_MISMATCH:{len(steps)}!={rw_int}")
    sb_sum, sa_sum, steps_ok = _verify_steps(steps, reasons, max_ulps)
    if valid_totals and steps_ok and (sb_sum != int(tb) or sa_sum != int(ta)):
        reasons.append(f"STEP_COST_SUM_MISMATCH:{sb_sum}/{sa_sum}!={tb}/{ta}")


def verify_proof_artifact(artifact: ProofArtifact, *, max_allowed_ulps: int = 1) -> ReplayItemResult:
    """Verify one GPU or superoptimizer proof artifact fail-closed."""
    reasons: list[str] = []
    cert = artifact.cert
    if not isinstance(cert, Mapping):
        return ReplayItemResult(artifact.artifact_id, False, ("INVALID_CERT_OBJECT",))

    schema = cert.get("schema")
    if cert.get("verified") is not True:
        reasons.append("CERT_NOT_VERIFIED")
    cert_sha = cert.get("cert_sha256")
    if not _is_hex64(cert_sha):
        reasons.append("MALFORMED_CERT_SHA256")
    elif artifact.expected_cert_sha256 is not None and not hmac.compare_digest(
        str(cert_sha), artifact.expected_cert_sha256
    ):
        reasons.append("CERT_SHA256_MISMATCH")

    if schema == GPU_CERT_SCHEMA:
        declared_shader = cert.get("shader_sha256")
        if not _is_hex64(declared_shader):
            reasons.append("MALFORMED_SHADER_SHA256")
        elif artifact.shader_bytes is not None:
            actual = hashlib.sha256(artifact.shader_bytes).hexdigest()
            if not hmac.compare_digest(actual, str(declared_shader)):
                reasons.append("SHADER_SHA256_MISMATCH")
        so = cert.get("superopt_cert")
        if not isinstance(so, Mapping):
            reasons.append("MISSING_SUPEROPT_CERT")
        else:
            _verify_superopt_inner(so, reasons, max_allowed_ulps)
    elif schema == SUPEROPT_CERT_SCHEMA:
        _verify_superopt_inner(cert, reasons, max_allowed_ulps)
    else:
        reasons.append(f"UNSUPPORTED_PROOF_SCHEMA:{schema}")

    unique = tuple(dict.fromkeys(reasons))
    return ReplayItemResult(artifact.artifact_id, not unique, unique)


def load_gpu_proof_corpus(emitted_dir: Path) -> list[ProofArtifact]:
    """Load all *.gpu-cert.json certificates and paired shader bytes from disk."""
    if not emitted_dir.is_dir():
        return []
    artifacts: list[ProofArtifact] = []
    for cert_path in sorted(emitted_dir.glob("*.gpu-cert.json")):
        kernel, target = cert_path.name[: -len(".gpu-cert.json")].rsplit(".", 1)
        cert_obj = json.loads(cert_path.read_text(encoding="utf-8"))
        ext = TARGET_SHADER_EXT.get(target, "")
        shader_path = emitted_dir / f"{kernel}{ext}"
        shader_bytes = shader_path.read_bytes() if ext and shader_path.is_file() else None
        expected_sha = str(cert_obj.get("cert_sha256")) if isinstance(cert_obj, Mapping) else None
        artifacts.append(ProofArtifact(cert_path.name, cert_obj, shader_bytes, expected_sha))
    return artifacts


def replay_corpus_sharded(
    artifacts: Sequence[ProofArtifact],
    *,
    shards: int = 1,
    max_allowed_ulps: int = 1,
) -> ShardedReplayReport:
    """Replay artifacts across worker shards with deterministic attestation."""
    if not isinstance(shards, int) or isinstance(shards, bool) or shards < 1:
        raise ValueError("shards must be a positive integer")

    ordered = sorted(artifacts, key=lambda item: item.artifact_id)
    buckets: list[list[ProofArtifact]] = [[] for _ in range(shards)]
    for idx, item in enumerate(ordered):
        buckets[idx % shards].append(item)

    def _run(bucket: list[ProofArtifact]) -> list[ReplayItemResult]:
        return [verify_proof_artifact(a, max_allowed_ulps=max_allowed_ulps) for a in bucket]

    collected: list[ReplayItemResult] = []
    if shards == 1:
        collected = _run(buckets[0])
    else:
        with ThreadPoolExecutor(max_workers=shards) as pool:
            for part in pool.map(_run, buckets):
                collected.extend(part)

    collected.sort(key=lambda r: r.artifact_id)
    passed_count = sum(1 for r in collected if r.passed)
    passed = bool(collected) and passed_count == len(collected)
    payload = {"passed": passed, "results": [r.to_dict() for r in collected]}
    seal = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ShardedReplayReport(passed, shards, len(collected), passed_count, tuple(collected), seal)


def verify_worker_count_invariance(
    artifacts: Sequence[ProofArtifact],
    *,
    shard_counts: Sequence[int] = (1, 4),
    max_allowed_ulps: int = 1,
) -> bool:
    """Return True iff every shard count produces bit-identical replay digests."""
    reports = [replay_corpus_sharded(artifacts, shards=sc, max_allowed_ulps=max_allowed_ulps) for sc in shard_counts]
    if not reports:
        return False
    ref = reports[0]
    return all(r.replay_attestation_sha256 == ref.replay_attestation_sha256 and r.results == ref.results for r in reports[1:])
