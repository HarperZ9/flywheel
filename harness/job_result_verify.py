"""job_result_verify.py -- a stranger's check of a PySyft job result receipt.

Standard library only and offline. The verifier holds what an outsider can hold:
the signed receipt, the published job folder, the released results file, the
signer's public key from somewhere it trusts, and optionally the nonce it issued,
the receipt ids it has already seen, the reviewers it accepts, and the hidden
answers once they are revealed. It never needs the model or the data.

Verdicts: MATCH when every check that ran passed; DRIFT naming each check that
failed; UNVERIFIABLE when an input a core check needs is missing. The attestation
link is always reported as UNVERIFIABLE beside the verdict, because this receipt
does not carry one (`job_result_receipt.ATTESTATION_GAP`).

    python -m harness.job_result_verify --receipt r.json --job-dir job/ \\
        --results results.jsonl --public-key <hex> [--nonce N] [--reveal answers.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._vendor import superstack as ss
from .ed25519_verify import Ed25519Error, verify as ed_verify
from . import job_result_receipt as jr
from .pysyft_job_hash import JobHashError, submission_hash

MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"


def _signature(env: dict, public_key_hex: str) -> list:
    sig = env.get("signature")
    body = env.get("body")
    if not isinstance(sig, dict) or not isinstance(body, dict):
        return ["malformed"]
    if sig.get("alg") != "ed25519" or sig.get("signed_over") != jr.SIGNED_OVER:
        return ["signed_over"]
    fails = []
    digest = jr.claim_sha256(body)
    if env.get("claim_sha256") != digest:
        fails.append("claim_digest")
    if sig.get("public_key") != public_key_hex.lower():
        fails.append("wrong_signer")
    try:
        ok = ed_verify(bytes.fromhex(public_key_hex), digest.encode("ascii"),
                       bytes.fromhex(str(sig.get("sig"))))
    except (Ed25519Error, ValueError, TypeError):
        ok = False
    if not ok:
        fails.append("signature")
    return fails


def _job(body: dict, job_dir) -> list:
    job = body["job"]
    fails = [] if job.get("approved_hash") == job.get("received_hash") else ["approval_covers_other_job"]
    try:
        if submission_hash(job_dir) != job.get("approved_hash"):
            fails.append("job_hash")
    except JobHashError:
        fails.append("job_hash")
    return fails


def _approval(body: dict, reviewers) -> list:
    a = body.get("approval") or {}
    fails = [] if a.get("approved_by") and a.get("approved_at") else ["approval_missing"]
    if a.get("status") != "done":
        fails.append("approval_status")
    if reviewers is not None and a.get("approved_by") not in set(reviewers):
        fails.append("approver")
    return fails


def _superstack(body: dict) -> list:
    rec = body.get("superstack")
    fails = ["superstack:" + e for e in ss.verify_receipt(rec)]
    if fails:
        return fails
    if rec["scene_sha256"] != ss.canonical_sha256(jr.job_scene(body["job"])):
        fails.append("superstack_scene")
    if rec["reconcile"]["tolerance"]["verdict"] != "verified":
        fails.append("superstack_tolerance")
    if rec["content_sha256"] != body["result"].get("results_sha256"):
        fails.append("superstack_content")
    return fails


def _results(body: dict, results: bytes) -> list:
    """Identity over the released bytes, then the score from the rows (tolerance)."""
    res = body["result"]
    if ss.identity(res.get("results_sha256"), ss.sha256_hex(results)) != "MATCH":
        return ["results_bytes"]
    rows = jr.parse_rows(results)
    fails = [] if jr.items_root(rows) == res.get("items_root") else ["items_root"]
    if sum(1 for r in rows if r["correct"]) != res.get("correct") or len(rows) != res.get("total"):
        fails.append("score")
    return fails


def _reveal(results: bytes, answers: dict) -> list:
    rows = jr.parse_rows(results)
    if set(answers) != {r["item_id"] for r in rows}:
        return ["reveal_items"]
    wrong = [r for r in rows if jr.score(r["prediction"], answers[r["item_id"]]) != r["correct"]]
    return ["reveal"] if wrong else []


def _replay(body: dict, nonce, seen) -> list:
    fails = []
    if nonce is not None and body.get("nonce") != nonce:
        fails.append("replay_nonce")
    if seen is not None and body.get("receipt_id") in set(seen):
        fails.append("replay_seen")
    return fails


def verify(envelope, *, public_key_hex, job_dir=None, results=None, nonce=None,
           seen_receipt_ids=None, reviewers=None, revealed_answers=None) -> dict:
    """Check a signed receipt. Never raises on a hostile receipt; returns a report."""
    missing = [n for n, v in (("public_key", public_key_hex), ("job_dir", job_dir),
                              ("results", results)) if v is None]
    checks = {}
    try:
        checks["signature"] = _signature(envelope, public_key_hex) if public_key_hex else None
        body = envelope["body"]
        if body.get("schema") != jr.SCHEMA or tuple(body.get("does_not_prove", ())) != jr.DOES_NOT_PROVE:
            checks["schema"] = ["schema_or_limits"]
        checks["job"] = _job(body, job_dir) if job_dir is not None else None
        checks["approval"] = _approval(body, reviewers)
        checks["superstack"] = _superstack(body)
        checks["results"] = _results(body, results) if results is not None else None
        checks["replay"] = _replay(body, nonce, seen_receipt_ids)
        if revealed_answers is not None and results is not None:
            checks["reveal"] = _reveal(results, revealed_answers)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        checks["malformed"] = [f"malformed:{type(exc).__name__}"]
    failed = sorted({f for v in checks.values() if v for f in v})
    verdict = DRIFT if failed else (UNVERIFIABLE if missing else MATCH)
    return {"verdict": verdict, "failed": failed, "missing_inputs": missing,
            "checks_run": sorted(k for k, v in checks.items() if v is not None),
            "attestation": UNVERIFIABLE, "attestation_reason": jr.ATTESTATION_GAP,
            "does_not_prove": list(jr.DOES_NOT_PROVE)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m harness.job_result_verify")
    p.add_argument("--receipt", required=True)
    p.add_argument("--job-dir", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--public-key", required=True, help="the signer's raw key, 64 hex")
    p.add_argument("--nonce")
    p.add_argument("--reviewer", action="append")
    p.add_argument("--reveal", help="JSON object item_id -> answer, once revealed")
    a = p.parse_args(argv)
    env = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    answers = json.loads(Path(a.reveal).read_text(encoding="utf-8")) if a.reveal else None
    report = verify(env, public_key_hex=a.public_key, job_dir=Path(a.job_dir),
                    results=Path(a.results).read_bytes(), nonce=a.nonce,
                    reviewers=a.reviewer, revealed_answers=answers)
    print(json.dumps(report, indent=2))
    return {MATCH: 0, DRIFT: 1}.get(report["verdict"], 2)


if __name__ == "__main__":
    sys.exit(main())
