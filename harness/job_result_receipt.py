"""job_result_receipt.py -- a result receipt for an approved PySyft job.

PySyft keeps the private model and data hidden while an approved job runs, and
records the hash of the exact job the data owner approved (PR #9536). This module
writes what an outside party can check afterwards, with no access to the model or
the data:

- the approved job's hash, in PySyft's own format (`pysyft_job_hash`), so anyone
  holding the published job code can recompute it;
- the data owner's approval record as PySyft wrote it, bound by its SHA-256;
- the result: an exact integer score, a Merkle root over the per-item rows the job
  released, and the scoring rule;
- commitments to the hidden model and data, which an outsider cannot open;
- a superstack receipt (`superstack.receipt/1`) with its two verdicts: identity
  over the released result bytes, and tolerance for whether the claimed score
  recomputes from those rows;
- a fixed `does_not_prove` list, which a verifier checks word for word;
- an Ed25519 signature over `claim_sha256`, the superstack canonical SHA-256 of
  the whole body. The verifier recomputes that digest and never trusts the
  recorded one.

Building a receipt is standard library only. Signing needs a key and the
`signing` extra (`harness.receipt_signer`); verifying needs neither
(`harness.job_result_verify`).
"""
from __future__ import annotations

import hashlib
import json

from ._vendor import superstack as ss
from . import merkle
from .pysyft_job_hash import HASH_RULE, PYSYFT_SOURCE

SCHEMA = "flywheel.pysyft-job-result/v1"
ENVELOPE_SCHEMA = "flywheel.signed-job-result/v1"
SIGNED_OVER = "claim_sha256"
PRODUCER = "flywheel.job_result_receipt"
PRODUCER_VERSION = "1"
SCORING_RULE = "exact-match-strip/1"
ATTESTATION_GAP = (
    "No enclave attestation is bound to this receipt. The hidden model and data are "
    "named only by commitments the data owner supplied, and nothing here links those "
    "commitments to what actually ran. Closing this needs the enclave attestation "
    "report bound into the receipt.")
DOES_NOT_PROVE = (
    "It does not prove the hidden model or the hidden data were what the parties "
    "said; that needs the enclave attestation link, which this receipt does not carry.",
    "It does not prove the job ran only once, or that a run with a worse score was "
    "not discarded before this receipt was issued.",
    "It does not prove the reviewer read the code or judged it well; it binds the "
    "approval record PySyft wrote, and PySyft does not sign that record.",
    "It does not prove the scoring rule or the benchmark measures what it claims to.",
    "It does not prove the per-item rows are correct until the hidden answers are "
    "revealed and rescored; before that, the score is only consistent with the rows.",
    "It does not prove anything about enclave side channels, the hardware vendor, "
    "or any attestation verifier.",
    "A valid signature shows only that the key holder issued this body. It says "
    "nothing about whether the key holder is honest.",
)


class JobReceiptError(ValueError):
    """Inputs that cannot be built into an honest receipt."""


def score(prediction: str, answer: str) -> bool:
    """SCORING_RULE: exact string match after stripping surrounding whitespace."""
    return str(prediction).strip() == str(answer).strip()


def parse_rows(results: bytes) -> list:
    """Per-item rows from a results.jsonl file: item_id, prediction, correct."""
    rows = []
    for n, line in enumerate(results.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if (not isinstance(row, dict) or set(row) != {"item_id", "prediction", "correct"}
                or not isinstance(row["correct"], bool)):
            raise JobReceiptError(f"results line {n}: item_id, prediction, correct")
        rows.append(row)
    if not rows:
        raise JobReceiptError("results: no rows")
    return rows


def items_root(rows) -> str:
    """Merkle root (RFC 6962 style) over each row's canonical JSON bytes, in order."""
    return merkle.root_hex([ss.canonical_bytes(r) for r in rows])


def job_scene(job: dict) -> dict:
    """The superstack scene: what the result is bound to, verdict-free."""
    return {"kind": "pysyft-job", "hash_rule": job["hash_rule"],
            "approved_hash": job["approved_hash"], "name": job["name"]}


def _tolerance(rows, correct: int, total: int) -> dict:
    rows_correct = sum(1 for r in rows if r["correct"])
    ok = rows_correct == correct and len(rows) == total
    return {"verdict": "verified" if ok else "refuted",
            "bounds": {"rule": "rows_correct == claimed_correct and rows_total == claimed_total"},
            "metrics": {"claimed_correct": correct, "rows_correct": rows_correct,
                        "claimed_total": total, "rows_total": len(rows)}}


def superstack_receipt(job: dict, results: bytes, rows, correct: int, total: int) -> dict:
    """A superstack.receipt/1 whose two verdicts cover the released result."""
    content_sha = ss.sha256_hex(results)
    reference = {"content_sha256": content_sha, "what": "results.jsonl as released"}
    reconcile = {"identity": ss.identity(content_sha, content_sha),
                 "tolerance": _tolerance(rows, correct, total)}
    return ss.make_receipt(
        producer=PRODUCER, version=PRODUCER_VERSION, backend="pysyft-syft-job",
        scene=job_scene(job), media={"kind": "document", "format": "jsonl"},
        content=results, reference=reference, reconcile=reconcile,
        does_not_prove=DOES_NOT_PROVE)


def _job_block(name, approved_hash, received_hash) -> dict:
    for label, h in (("approved_hash", approved_hash), ("received_hash", received_hash)):
        if not isinstance(h, str) or len(h) != 64:
            raise JobReceiptError(f"{label}: 64 hex characters from PySyft")
    return {"name": name, "hash_rule": HASH_RULE, "pysyft_source": PYSYFT_SOURCE,
            "approved_hash": approved_hash, "received_hash": received_hash}


def build_body(*, job_name, submission_record: bytes, review: dict, results: bytes,
               commitments: dict, nonce: str, issued_at: str) -> dict:
    """The unsigned receipt body. `submission_record` is PySyft's submission.json
    bytes as the data owner wrote them; `review` holds the reviewer's state fields."""
    record = json.loads(submission_record.decode("utf-8"))
    if not record.get("approved_hash"):
        raise JobReceiptError("submission record has no approved_hash: job not approved")
    if not nonce:
        raise JobReceiptError("nonce: the challenge the requesting party issued")
    job = _job_block(job_name, record["approved_hash"], record.get("received_hash"))
    rows = parse_rows(results)
    correct = sum(1 for r in rows if r["correct"])
    approval = {k: record.get(k) for k in ("approved_by", "approved_at", "approval_method")}
    approval.update(record_sha256=hashlib.sha256(submission_record).hexdigest(),
                    review_reason=review.get("review_reason"),
                    status=review.get("status"), completed_at=review.get("completed_at"))
    body = {
        "schema": SCHEMA, "nonce": nonce, "issued_at": issued_at, "job": job,
        "approval": approval,
        "result": {"scoring_rule": SCORING_RULE, "correct": correct, "total": len(rows),
                   "items_root": items_root(rows), "results_sha256": ss.sha256_hex(results)},
        "commitments": dict(commitments),
        "attestation": {"status": "UNVERIFIABLE", "reason": ATTESTATION_GAP},
        "superstack": superstack_receipt(job, results, rows, correct, len(rows)),
        "does_not_prove": list(DOES_NOT_PROVE),
    }
    body["receipt_id"] = ss.canonical_sha256({"nonce": nonce, "job": job,
                                              "result": body["result"]})
    return body


def claim_sha256(body: dict) -> str:
    """The digest a signature covers: superstack canonical SHA-256 of the body."""
    return ss.canonical_sha256(body)


def attach(body: dict, signature: bytes, public_key: bytes, key_id: str) -> dict:
    """Wrap a body and an Ed25519 signature made elsewhere over claim_sha256."""
    if len(signature) != 64 or len(public_key) != 32 or not key_id:
        raise JobReceiptError("ed25519: 64-byte signature, 32-byte key, a key_id")
    return {"schema": ENVELOPE_SCHEMA, "body": body, "claim_sha256": claim_sha256(body),
            "signature": {"alg": "ed25519", "signed_over": SIGNED_OVER, "key_id": key_id,
                          "public_key": bytes(public_key).hex(),
                          "sig": bytes(signature).hex()}}


def sign(body: dict, key) -> dict:
    """Sign with a `harness.receipt_signer.SigningKey` (needs the signing extra)."""
    sig = key.sign(claim_sha256(body).encode("ascii"))
    return attach(body, sig, key.public_key_bytes, key.key_id)
