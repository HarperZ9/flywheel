"""receipt.py -- the gate result as a flywheel.receipt/v4, signed, and its re-derivation.

The result file carries the per-item monitor records beside a signed-receipt
envelope. The receipt binds the pinned spec (criterion_sha256), the gate set
(filter_hash), the monitor descriptor (candidate_sha256), the records
(raw_stdout_sha256), every rate and control outcome (coverage) and the verdict.
Signing uses receipt_signer over claim_sha256; checking uses receipt_sign, the
stdlib verifier a stranger already has.

verify() trusts nothing it can recompute. It reloads the pinned gate set, rehashes
the records, rescores them, reruns the planted controls, rebuilds the receipt
from those and requires the recorded one to match field for field, then checks
the signature. MATCH needs a trust root; a valid signature without one is
UNANCHORED, and an unsigned result is UNSIGNED. Neither is a pass.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from ..receipt import Receipt
from ..receipt_fields import Budget, Denominator, EvidenceKind, Tier, canonical
from ..receipt_sign import unsigned, verify_signed
from ..verdict import Attribution, Verdict
from . import gate_set as gs
from . import score as sc

SCHEMA = "flywheel.monitor-gate-result/v1"
GATE_VERSION = "monitor-gate/v1"
_VERDICT = {sc.ADMIT: Verdict.PASS, sc.REFUSE: Verdict.FAIL, sc.UNVERIFIABLE: Verdict.UNVERIFIABLE}
LIMITS = ("NOT_PROVES_BEHAVIOR_OUTSIDE_PARITY_PRODUCT_FAMILY",
          "NOT_PROVES_FRONTIER_MODEL_BEHAVIOR",
          "NOT_PROVES_BEHAVIOR_UNDER_OPTIMIZATION_PRESSURE",
          "NOT_PROVES_UNPLANTED_CASES",
          "NOT_PROVES_BEHAVIOR_AFTER_GATE_RUN")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_sha(module_file: str) -> str:
    """Source digest over LF bytes, so a CRLF checkout reports the same code."""
    return _sha(Path(module_file).read_bytes().replace(b"\r\n", b"\n"))


def records_sha256(records: list) -> str:
    return _sha(canonical(records).encode("utf-8"))


def build_receipt(gate: gs.GateSet, descriptor: dict, records: list, result: dict, *,
                  weights_digest: str = "") -> Receipt:
    verdict = result["verdict"]
    hits = sum(1 for r, it in zip(records, gate.items) if r["verdict"] in it.accept)
    coverage = {"predicate_exact": False, "search_space_enumerated": False,
                "gate_id": gate.spec["gate_id"], "gate_verdict": verdict,
                "reason": result["reason"], "failed": list(result["failed"]),
                "sides": result["sides"], "unverifiable_rate": result["unverifiable_rate"],
                "controls": result["controls"], "monitor_call_errors": result["monitor_call_errors"],
                "descriptor": descriptor}
    return Receipt(
        criterion_id="flywheel.monitor-gate", criterion_version=1,
        criterion_sha256="sha256:" + gate.spec_sha256, family="monitor-gate",
        family_instance_id=gate.spec["gate_id"], generator_id="harness.monitor_gate.build",
        generator_seed=int(gate.spec["random_seed"]),
        candidate_sha256="sha256:" + _sha(canonical(descriptor).encode("utf-8")),
        prompt_hash="sha256:" + descriptor.get("prompt_sha256", "none"),
        checker_module="harness.monitor_gate.score", checker_source_sha256="sha256:" + _source_sha(sc.__file__),
        executes_candidate_code=bool(descriptor.get("executes_code")),
        oracle_qa_card_hash="", held_out_agreement="NOT_RUN",
        evidence_kind=EvidenceKind.EMPIRICAL, tier=Tier.EXECUTION_TEST,
        verdict=_VERDICT[verdict],
        attribution=Attribution.HARNESS if verdict == sc.UNVERIFIABLE else Attribution.CANDIDATE,
        objective=verdict if not result["reason"] else f"{verdict}:{result['reason']}",
        incumbent_objective="", incumbent_source="none", coverage=coverage,
        raw_stdout_sha256=records_sha256(records),
        analysis_script_sha256=_source_sha(__file__),
        denominator=Denominator(
            attempts=len(records), group_size=len(records), oracle_calls_consumed=len(records),
            hits=hits, undecided=0, unverifiable=0,
            parse_failures=sum(1 for r in records if r["verdict"] == sc.INVALID),
            timeouts=0, tokens_in=0, tokens_out=0, cache_hit_tokens=0,
            tasks_proposed=len(records), tasks_filtered_out=0, retries=0,
            oracle_feedback_visible=False, filter_id=gate.spec["gate_id"] + ".all",
            filter_hash="sha256:" + gate.set_sha256, filter_is_learned=False),
        budget=Budget.undeclared(), model_ref=descriptor["adapter"],
        base_weights_digest=weights_digest, harness_version=GATE_VERSION,
        unverifiable_reason="CONFOUNDED" if verdict == sc.UNVERIFIABLE else "",
        extra_does_not_prove=LIMITS)


def result_document(gate, descriptor, records, result, *, signing_key=None,
                    weights_digest: str = "") -> dict:
    receipt = build_receipt(gate, descriptor, records, result, weights_digest=weights_digest)
    if signing_key is None:
        envelope = unsigned(receipt)
    else:
        from ..receipt_signer import sign_receipt
        envelope = sign_receipt(receipt, signing_key).to_dict()
    return {"schema": SCHEMA, "envelope": envelope, "records": records}


def _status(envelope: dict, trust_root: bytes | None) -> tuple[str, str]:
    sig = envelope.get("signature")
    if sig is None:
        return "UNSIGNED", "no signature; integrity rests on re-derivation only"
    embedded = bytes.fromhex(sig.get("public_key", "") or "")
    ok, why = verify_signed(envelope, trust_root if trust_root else embedded)
    if not ok:
        return "MISMATCH", f"signature: {why}"
    if not trust_root:
        return "UNANCHORED", "signature valid against its own embedded key; no trust root given"
    return "MATCH", "re-derived and signed by the trust root"


def verify(doc: dict, *, trust_root: bytes | None = None, gate: gs.GateSet | None = None) -> dict:
    """Re-derive a gate result. Never raises on a hostile document."""
    try:
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            return {"status": "MISMATCH", "detail": "not a monitor gate result"}
        gate = gate or gs.load()
        envelope, records = doc["envelope"], doc["records"]
        recorded = Receipt.from_dict(envelope["receipt"])
        cov = recorded.coverage
        result = sc.decide(gate, records, sc.controls(gate))
        rebuilt = build_receipt(gate, cov["descriptor"], records, result,
                                weights_digest=recorded.base_weights_digest)
        code_match = (rebuilt.checker_source_sha256, rebuilt.analysis_script_sha256) == (
            recorded.checker_source_sha256, recorded.analysis_script_sha256)
        rebuilt = replace(rebuilt, checker_source_sha256=recorded.checker_source_sha256,
                          analysis_script_sha256=recorded.analysis_script_sha256)
        if rebuilt.claim_sha256() != recorded.claim_sha256():
            return {"status": "MISMATCH", "detail": "the recorded receipt does not follow from "
                    "the records, the pinned gate set and the controls"}
        if envelope["receipt"].get("claim_sha256") != recorded.claim_sha256():
            return {"status": "MISMATCH", "detail": "recorded claim_sha256 is not the body's digest"}
        status, detail = _status(envelope, trust_root)
        return {"status": status, "detail": detail, "gate_verdict": cov["gate_verdict"],
                "adapter": recorded.model_ref, "claim_sha256": recorded.claim_sha256(),
                "code_match": code_match}
    except Exception as exc:  # noqa: BLE001 -- a malformed document is a named refusal
        return {"status": "MISMATCH", "detail": f"malformed result: {type(exc).__name__}: {exc}"}
