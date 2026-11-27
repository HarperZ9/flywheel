"""remedy.py -- Check-Contest-Obtain-Remedy receipt protocol (stdlib only).

Composes directly with `harness.contest` (signed, contester-owned disputes),
`harness.merkle` (RFC 6962 chain commitment), and `harness.receipt_fields`
(canonical JSON). Every contested model or tool output is bound by SHA-256 to:
  1. a contester-signed `Contest` verified against the contester's own key;
  2. the contested output bytes and audit trace bytes (exact SHA-256 match);
  3. a deterministic re-derivation oracle verdict (`UPHELD | OVERTURNED | REMEDY_ISSUED`);
  4. a tamper-evident prev-hash chain verified offline with zero external deps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contest import Contest
from .merkle import merkle_root
from .receipt_fields import canonical

REMEDY_SCHEMA = "flywheel.remedy-receipt/v1"
REMEDY_CHAIN_SCHEMA = "flywheel.remedy-chain/v1"
VALID_ACTION_KINDS = frozenset({"none", "correction", "rollback", "restitution", "re_execution"})


class RemedyError(ValueError):
    """Raised fail-closed when a contest, trace binding, or remedy receipt is invalid."""


class RemedyVerdict(str, Enum):
    UPHELD = "UPHELD"
    OVERTURNED = "OVERTURNED"
    REMEDY_ISSUED = "REMEDY_ISSUED"


def hash_bytes(data: bytes) -> str:
    """Return prefixed SHA-256 hex digest of raw bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_canonical(obj: Any) -> str:
    """Return prefixed SHA-256 hex digest of canonical JSON."""
    return hash_bytes(canonical(obj).encode("utf-8"))


@dataclass(frozen=True)
class ContestedOutput:
    output_id: str
    output_sha256: str
    audit_trace_sha256: str
    claim_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.output_id or not self.output_id.strip():
            raise RemedyError("output_id must be non-empty")
        if not self.output_sha256.startswith("sha256:") or len(self.output_sha256) != 71:
            raise RemedyError("output_sha256 must be a sha256:<64-hex> digest")
        if not self.audit_trace_sha256.startswith("sha256:") or len(self.audit_trace_sha256) != 71:
            raise RemedyError("audit_trace_sha256 must be a sha256:<64-hex> digest")
        if not self.claim_sha256:
            object.__setattr__(self, "claim_sha256", self.output_sha256)

    def to_dict(self) -> dict[str, str]:
        return {
            "output_id": self.output_id,
            "output_sha256": self.output_sha256,
            "audit_trace_sha256": self.audit_trace_sha256,
            "claim_sha256": self.claim_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContestedOutput:
        return cls(
            output_id=str(data["output_id"]),
            output_sha256=str(data["output_sha256"]),
            audit_trace_sha256=str(data["audit_trace_sha256"]),
            claim_sha256=str(data.get("claim_sha256", "")),
        )


@dataclass(frozen=True)
class RemedyAction:
    action_kind: str = "none"
    summary: str = ""
    artifact_sha256: str = ""

    def __post_init__(self) -> None:
        if self.action_kind not in VALID_ACTION_KINDS:
            raise RemedyError(f"unsupported remedy action_kind: {self.action_kind!r}")
        if self.artifact_sha256 and (
            not self.artifact_sha256.startswith("sha256:") or len(self.artifact_sha256) != 71
        ):
            raise RemedyError("artifact_sha256 must be empty or sha256:<64-hex>")

    def to_dict(self) -> dict[str, str]:
        return {
            "action_kind": self.action_kind,
            "summary": self.summary,
            "artifact_sha256": self.artifact_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemedyAction:
        return cls(
            action_kind=str(data.get("action_kind", "none")),
            summary=str(data.get("summary", "")),
            artifact_sha256=str(data.get("artifact_sha256", "")),
        )


@dataclass(frozen=True)
class RemedyReceipt:
    contest: Contest
    contested_output: ContestedOutput
    oracle_id: str
    oracle_output_sha256: str
    verdict: RemedyVerdict
    rationale: str
    remedy: RemedyAction
    prev_receipt_sha256: str = "genesis"
    receipt_sha256: str = ""

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema": REMEDY_SCHEMA,
            "contest": self.contest.to_dict(),
            "contested_output": self.contested_output.to_dict(),
            "oracle_id": self.oracle_id,
            "oracle_output_sha256": self.oracle_output_sha256,
            "verdict": self.verdict.value,
            "rationale": self.rationale,
            "remedy": self.remedy.to_dict(),
            "prev_receipt_sha256": self.prev_receipt_sha256,
        }

    def compute_digest(self) -> str:
        return hash_canonical(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "receipt_sha256": self.receipt_sha256 or self.compute_digest()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemedyReceipt:
        return cls(
            contest=Contest.from_dict(data["contest"]),
            contested_output=ContestedOutput.from_dict(data["contested_output"]),
            oracle_id=str(data["oracle_id"]),
            oracle_output_sha256=str(data["oracle_output_sha256"]),
            verdict=RemedyVerdict(data["verdict"]),
            rationale=str(data["rationale"]),
            remedy=RemedyAction.from_dict(data["remedy"]),
            prev_receipt_sha256=str(data.get("prev_receipt_sha256", "genesis")),
            receipt_sha256=str(data.get("receipt_sha256", "")),
        )


def adjudicate_contest(
    contest: Contest,
    contested_output: ContestedOutput,
    *,
    output_bytes: bytes,
    audit_trace_bytes: bytes,
    oracle_fn: Callable[[bytes, bytes], tuple[RemedyVerdict, bytes, str]],
    oracle_id: str,
    remedy_builder: Callable[[RemedyVerdict, bytes], RemedyAction] | None = None,
    prev_receipt_sha256: str = "genesis",
) -> RemedyReceipt:
    """Verify contest & trace bindings fail-closed, run oracle, and emit a sealed RemedyReceipt."""
    if not oracle_id or not oracle_id.strip():
        raise RemedyError("oracle_id must be non-empty")

    ok_sig, sig_why = contest.verify()
    if not ok_sig:
        raise RemedyError(f"FORGED_OR_UNSIGNED_CONTEST:{sig_why}")
    if contest.disputed_claim_sha256 != contested_output.claim_sha256:
        raise RemedyError("CLAIM_BINDING_MISMATCH")
    if hash_bytes(output_bytes) != contested_output.output_sha256:
        raise RemedyError("OUTPUT_HASH_MISMATCH")
    if hash_bytes(audit_trace_bytes) != contested_output.audit_trace_sha256:
        raise RemedyError("AUDIT_TRACE_HASH_MISMATCH")

    verdict, oracle_evidence, rationale = oracle_fn(output_bytes, audit_trace_bytes)
    if not isinstance(verdict, RemedyVerdict):
        verdict = RemedyVerdict(verdict)
    if not rationale or not rationale.strip():
        raise RemedyError("oracle rationale must be non-empty")
    oracle_digest = hash_bytes(oracle_evidence)

    if remedy_builder is not None:
        remedy = remedy_builder(verdict, oracle_evidence)
    elif verdict == RemedyVerdict.REMEDY_ISSUED:
        remedy = RemedyAction(
            action_kind="re_execution",
            summary="Deterministic re-derivation issued a corrected artifact.",
            artifact_sha256=oracle_digest,
        )
    else:
        remedy = RemedyAction(action_kind="none", summary="", artifact_sha256="")

    _validate_verdict_remedy_consistency(verdict, remedy)
    draft = RemedyReceipt(
        contest=contest,
        contested_output=contested_output,
        oracle_id=oracle_id,
        oracle_output_sha256=oracle_digest,
        verdict=verdict,
        rationale=rationale,
        remedy=remedy,
        prev_receipt_sha256=prev_receipt_sha256,
        receipt_sha256="",
    )
    return RemedyReceipt(**{**draft.__dict__, "receipt_sha256": draft.compute_digest()})


def _validate_verdict_remedy_consistency(verdict: RemedyVerdict, remedy: RemedyAction) -> None:
    if verdict == RemedyVerdict.REMEDY_ISSUED:
        if remedy.action_kind == "none" or not remedy.summary.strip():
            raise RemedyError("REMEDY_ISSUED requires a concrete non-empty remedy action and summary")
    elif verdict == RemedyVerdict.UPHELD and remedy.action_kind != "none":
        raise RemedyError("UPHELD verdict cannot attach a corrective remedy action")


def verify_remedy_receipt(
    receipt: RemedyReceipt | dict[str, Any],
    *,
    output_bytes: bytes | None = None,
    audit_trace_bytes: bytes | None = None,
) -> tuple[bool, str]:
    """Fail-closed offline verifier for a Check-Contest-Obtain-Remedy receipt."""
    try:
        if isinstance(receipt, dict):
            if receipt.get("schema") != REMEDY_SCHEMA:
                return False, "SCHEMA_MISMATCH"
            rec = RemedyReceipt.from_dict(receipt)
        else:
            rec = receipt
        _validate_verdict_remedy_consistency(rec.verdict, rec.remedy)
    except (KeyError, TypeError, ValueError, RemedyError) as exc:
        return False, f"MALFORMED_RECEIPT:{exc}"

    ok_sig, sig_why = rec.contest.verify()
    if not ok_sig:
        return False, f"FORGED_OR_UNSIGNED_CONTEST:{sig_why}"
    if rec.contest.disputed_claim_sha256 != rec.contested_output.claim_sha256:
        return False, "CLAIM_BINDING_MISMATCH"
    if not rec.rationale.strip() or not rec.oracle_id.strip():
        return False, "MISSING_ORACLE_METADATA"
    expected_digest = rec.compute_digest()
    if rec.receipt_sha256 != expected_digest:
        return False, "RECEIPT_DIGEST_TAMPERED"
    if output_bytes is not None and hash_bytes(output_bytes) != rec.contested_output.output_sha256:
        return False, "OUTPUT_HASH_MISMATCH"
    if audit_trace_bytes is not None and hash_bytes(audit_trace_bytes) != rec.contested_output.audit_trace_sha256:
        return False, "AUDIT_TRACE_HASH_MISMATCH"
    return True, "MATCH"


def verify_remedy_chain(receipts: Sequence[RemedyReceipt | dict[str, Any]]) -> tuple[bool, str, str]:
    """Verify an append-only chain of remedy receipts and return its RFC 6962 Merkle root."""
    if not receipts:
        return False, "EMPTY_CHAIN", ""
    seen_contests: set[str] = set()
    leaf_bytes: list[bytes] = []
    expected_prev = "genesis"

    for idx, raw in enumerate(receipts):
        ok, reason = verify_remedy_receipt(raw)
        if not ok:
            return False, f"RECEIPT_INVALID_AT_{idx}:{reason}", ""
        rec = RemedyReceipt.from_dict(raw) if isinstance(raw, dict) else raw
        if rec.prev_receipt_sha256 != expected_prev:
            return False, f"CHAIN_LINK_BROKEN_AT_{idx}", ""
        cid = rec.contest.contest_id()
        if cid in seen_contests:
            return False, f"DUPLICATE_CONTEST_AT_{idx}", ""
        seen_contests.add(cid)
        expected_prev = rec.receipt_sha256
        leaf_bytes.append(canonical(rec.to_dict()).encode("utf-8"))

    root_hex = "sha256:" + merkle_root(leaf_bytes).hex()
    return True, "MATCH", root_hex
