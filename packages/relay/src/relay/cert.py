"""cert.py -- emit and verify a Relay-Verified-Correctness (.rvc) certificate.

A run carries its own proof. ``emit_cert`` embeds the witnessed ledger, the typed
acceptance contract, and content-addressed anchors; ``verify_cert`` RE-DERIVES
every fact from the embedded ledger alone -- no model, no re-execution -- and
renders the ALLOW / UNVERIFIABLE / REFUTED verdict. Flip a byte in the embedded
ledger and the chain snaps; edit the grader and ``check_not_gamed`` fails. A
stranger verifies a PR's ``.rvc`` offline; the vendored ``verify_cert.py`` at the
repo root does it with zero relay imports and pure stdlib.

The verifier trusts NOTHING in the certificate except the embedded ledger: it
re-derives the facts and re-evaluates the contract itself, so the emit-time
verdict and clause list are informational, not load-bearing.

Honest null: Python's stdlib has no asymmetric signature, so an ``.rvc`` proves
re-derivable correctness, not WHO produced it. A detached signature (one
``ssh-keygen -Y sign``) or a transparency-log tree head binds authorship; the
re-derivation core needs no key and no dependency.
"""
from __future__ import annotations

import hashlib
import json

from .approvals import approval_verdict
from .claim_grounding import ground_final_answer
from .contract import STRICT, Contract, evaluate
from .local_tools import edited_targets
from .integrity import integrity_report, trajectory_integrity
from .intent_audit import audit_intent
from .local_loop import verify_receipts
from .local_session import Entry, SessionLedger
from .review import run_review
from .run_view import OK, verify_edges

RVC_SCHEMA = "relay.rvc/v1"


def _parse_call(content: str):
    name, _, rest = (content or "").partition(" ")
    try:
        args = json.loads(rest) if rest else {}
    except (json.JSONDecodeError, ValueError):
        args = {}
    return name, args if isinstance(args, dict) else {}


def _edited_paths(ledger) -> list:
    out = []
    for e in ledger.entries:
        if getattr(e, "kind", "") != "tool_call":
            continue
        name, args = _parse_call(getattr(e, "content", ""))
        out.extend(p for p, _new in edited_targets(name, args))
    return out


def _last_check(ledger):
    checks = [e for e in ledger.entries if getattr(e, "kind", "") == "check"]
    return checks[-1] if checks else None


def derive_facts(ledger) -> dict:
    """The facts a contract is evaluated over, re-derived from the ledger alone."""
    chain_ok = all(es.status == OK for es in verify_edges(ledger))
    integrity_clean = not trajectory_integrity(ledger)
    chk = _last_check(ledger)
    check_passed = bool(chk.meta.get("ok")) if chk is not None else None
    return {
        "chain_ok": chain_ok,
        "receipts_ok": verify_receipts(ledger),
        "integrity_clean": integrity_clean,
        "check_ran": chk is not None,
        "check_passed": check_passed,
        "check_output": (chk.content if chk is not None else ""),
        # a passing check is trusted only if the trajectory did not tamper with the grader
        "check_trusted": check_passed is not True or integrity_clean,
        "intent_critical": audit_intent(ledger)["critical"],
        "reviewability": run_review(ledger.entries)["reviewability"],
        "edited_paths": _edited_paths(ledger),
        "grounding_verdict": ground_final_answer(ledger)["verdict"],
        "approval_verdict": approval_verdict(ledger),
    }


def _receipt_root(ledger) -> str:
    ids = [e.meta["receipt"]["receipt_id"] for e in ledger.entries
           if getattr(e, "kind", "") == "assistant"
           and isinstance(e.meta.get("receipt"), dict) and "receipt_id" in e.meta["receipt"]]
    return hashlib.sha256(json.dumps(ids, sort_keys=True).encode()).hexdigest()[:16]


def _ledger_of(result) -> SessionLedger:
    if isinstance(result, SessionLedger):
        return result
    if isinstance(result, dict) and isinstance(result.get("ledger"), SessionLedger):
        return result["ledger"]
    raise TypeError("emit_cert needs a run result carrying its ledger, or a SessionLedger")


def emit_cert(result, contract: Contract = STRICT, *, env_hash: str = "") -> dict:
    """Build a self-contained certificate for a finished run."""
    ledger = _ledger_of(result)
    ev = evaluate(contract, derive_facts(ledger))
    return {
        "schema": RVC_SCHEMA,
        "verdict": ev["verdict"],                       # emit-time claim; verify re-derives
        "ledger_jsonl": ledger.to_jsonl(),
        "contract": contract.to_dict(),
        "clauses": ev["clauses"],
        "chain_head": ledger.checkpoint(),
        "integrity_sha256": integrity_report(trajectory_integrity(ledger))["flags_sha256"],
        "receipt_root": _receipt_root(ledger),
        "env_hash": env_hash,
    }


def _ledger_from_cert(cert: dict) -> SessionLedger:
    ledger = SessionLedger()
    for line in (cert.get("ledger_jsonl") or "").splitlines():
        if line.strip():
            ledger.entries.append(Entry(**json.loads(line)))
    return ledger


def verify_cert(cert: dict) -> tuple:
    """Re-derive the verdict from the embedded ledger alone. Returns (label, detail)."""
    ledger = _ledger_from_cert(cert)
    broken = next((es for es in verify_edges(ledger) if es.status != OK), None)
    if broken is not None:
        return "REFUTED", f"hash chain broken at seq {broken.seq} ({broken.reason})"
    facts = derive_facts(ledger)
    if not facts["receipts_ok"]:
        return "REFUTED", "a per-turn receipt does not re-derive from its recorded fields"
    ev = evaluate(Contract.from_dict(cert.get("contract", {})), facts)
    refuted = [c for c in ev["clauses"] if c["ok"] is False]
    if refuted:
        return "REFUTED", refuted[0]["detail"]
    unver = [c for c in ev["clauses"] if c["ok"] is None]
    if unver:
        return "UNVERIFIABLE", unver[0]["detail"]
    return "ALLOW", "run accepted: chain intact, receipts re-derive, contract satisfied"
