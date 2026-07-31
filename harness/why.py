"""why.py -- "why was this accepted?" answered from the record, offline.

The practitioner contract puts this plainly: doubt is answered with records, never
with friction or blame. Asking has to be the cheapest action in the system, so this
takes a hash prefix, needs no flags, touches no network and no model, and never
asks the operator to justify asking.

Four things it will not do:

  - It will not RECOMPUTE the verdict. It reports what the record says and whether
    the record is internally consistent. Re-running the oracle is `flywheel
    verify`; conflating the two would make asking expensive.
  - It will not lead with reassurance. `what_would_change_it` comes before the
    proof, because an explanation that only recites its evidence is the
    fake-passport failure: true, and useful for implying more than it establishes.
  - It will not hide the limits. `does_not_prove` is part of the answer, not an
    appendix.
  - It will not score the person. Only facts about this record, never a rate, a
    streak, or a history of the operator.
"""
from __future__ import annotations

import json
from pathlib import Path

from .receipt import Receipt
from .receipt_sign import verify_signed, LOCAL_ONLY_ALGS


class WhyError(ValueError):
    """The record cannot answer, and the reason is named rather than guessed."""


def _load(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WhyError(f"no record at {path}")
    except Exception as e:
        raise WhyError(f"record at {path} is unreadable: {e}")


def _envelopes(target: Path) -> list[tuple[Path, dict]]:
    target = Path(target)
    if target.is_dir():
        out = []
        for p in sorted(target.glob("*.json")):
            try:
                d = _load(p)
            except WhyError:
                continue
            if isinstance(d, dict) and isinstance(d.get("receipt"), dict):
                out.append((p, d))
        if not out:
            raise WhyError(f"no receipt envelopes found under {target}")
        return out
    return [(target, _load(target))]


def _signature_state(env: dict) -> dict:
    sig = env.get("signature")
    if sig is None:
        return {"state": "unsigned", "third_party_checkable": False,
                "verified": False, "reason": "unsigned", "key_id": ""}
    alg = sig.get("sig_alg", "")
    if alg in LOCAL_ONLY_ALGS:
        # Honest about the ceiling: a local tag detects local tampering and tells
        # a stranger nothing, because checking it needs the secret.
        return {"state": f"local-only ({alg})", "third_party_checkable": False,
                "verified": False, "reason": "local_only_algorithm",
                "key_id": sig.get("key_id", "")}
    pub = sig.get("public_key", "")
    ok, reason = (False, "no_public_key")
    if pub:
        try:
            ok, reason = verify_signed(env, bytes.fromhex(pub))
        except ValueError:
            ok, reason = False, "malformed_public_key"
    return {"state": f"signed ({alg})", "third_party_checkable": True,
            "verified": bool(ok), "reason": reason,
            "key_id": sig.get("key_id", "")}


def _what_would_change_it(body: dict, receipt: Receipt) -> list[str]:
    """The levers, named before the proof. This is the part a reader can act on."""
    out = [
        f"a different criterion: this used {body['criterion_id']} v"
        f"{body['criterion_version']} ({body['criterion_sha256'][:22]}...), and "
        "amending it would produce a new version with a recorded reason",
        f"a different checker: {body['checker_module']} at source "
        f"{body['checker_source_sha256'][:22]}..., so editing the checker "
        "invalidates this record rather than silently changing it",
    ]
    if body.get("held_out_agreement") != "AGREE":
        out.append("a held-out check that actually ran: this one reports "
                   f"{body.get('held_out_agreement')}, so gaming the visible "
                   "checker was not ruled out")
    if not body.get("oracle_qa_card_hash"):
        out.append("a QA card for the checker: without one its false-accept rate "
                   "was never measured, so this verdict rests on an unmeasured "
                   "verifier")
    cov = body.get("coverage") or {}
    if not cov.get("predicate_exact", False):
        out.append(f"an exact predicate: this one stopped at "
                   f"{cov.get('stop_reason', 'an unstated bound')}"
                   + (f" and weakens above {cov['guarantee_weakens_above']}"
                      if cov.get("guarantee_weakens_above") else ""))
    if receipt.denominator.filter_is_learned:
        out.append("an unlearned task filter: a learned proposer chose the "
                   f"population here ({receipt.denominator.filter_id}), so the "
                   "task set is not independent of the model")
    return out


def explain(target, *, prefix: str = "") -> dict:
    """Answer from the record. `target` is an envelope file or a directory."""
    candidates = _envelopes(Path(target))
    if prefix:
        matched = [(p, e) for p, e in candidates
                   if e["receipt"].get("claim_sha256", "").split(":", 1)[-1]
                   .startswith(prefix)]
        if not matched:
            raise WhyError(
                f"no receipt whose claim digest starts with {prefix!r}. "
                f"searched {len(candidates)} record(s) under {target}")
        digests = {e["receipt"]["claim_sha256"] for _, e in matched}
        if len(digests) > 1:
            raise WhyError(
                f"prefix {prefix!r} is ambiguous across {len(digests)} distinct "
                "claims; give more characters rather than have one picked for you")
        candidates = matched[:1]
    elif len(candidates) > 1:
        raise WhyError(
            f"{len(candidates)} records under {target}; pass a claim-digest "
            "prefix to choose one")

    path, env = candidates[0]
    body = env["receipt"]
    try:
        receipt = Receipt.from_dict(body)
    except Exception as e:
        raise WhyError(f"record at {path} is not a receipt: {e}")

    recomputed = receipt.claim_sha256()
    integrity = "MATCH" if recomputed == body.get("claim_sha256") else "DRIFT"

    return {
        "record": str(path),
        "record_integrity": integrity,
        "claim_sha256": recomputed,
        "recorded_claim_sha256": body.get("claim_sha256", ""),
        "subject_sha256": receipt.subject_sha256(),
        "verdict": body["verdict"],
        "attribution": body["attribution"],
        "criterion_id": body["criterion_id"],
        "criterion_version": body["criterion_version"],
        "what_would_change_it": _what_would_change_it(body, receipt),
        "what_decided_it": {
            "checker_module": body["checker_module"],
            "checker_source_sha256": body["checker_source_sha256"],
            "executes_candidate_code": body["executes_candidate_code"],
            "evidence_kind": body["evidence_kind"],
            "tier": body["tier"],
            "held_out_agreement": body["held_out_agreement"],
            "qa_card": body["oracle_qa_card_hash"] or "(none)",
            "coverage": body.get("coverage", {}),
            "objective": body["objective"],
            "incumbent_objective": body["incumbent_objective"],
            "incumbent_source": body["incumbent_source"],
        },
        "at_what_cost": receipt.denominator.to_dict(),
        "signature": _signature_state(env),
        "does_not_prove": receipt.does_not_prove(),
    }


def render(e: dict) -> str:
    """Plain text. The verdict first, the levers second, the limits last and
    never omitted."""
    d = e["what_decided_it"]
    cost = e["at_what_cost"]
    lines = [
        f"{e['verdict']} on {e['criterion_id']} v{e['criterion_version']} "
        f"(attributed to {e['attribution']})",
        f"record {e['record']}  integrity {e['record_integrity']}",
        f"claim {e['claim_sha256']}",
        "",
        "what would change it:",
    ]
    lines += [f"  - {s}" for s in e["what_would_change_it"]]
    lines += [
        "",
        "what decided it:",
        f"  checker    {d['checker_module']}",
        f"  source     {d['checker_source_sha256']}",
        f"  executes candidate code: {d['executes_candidate_code']}",
        f"  evidence   {d['evidence_kind']} / {d['tier']}",
        f"  held-out   {d['held_out_agreement']}",
        f"  qa card    {d['qa_card']}",
        f"  objective  {d['objective']} against incumbent "
        f"{d['incumbent_objective']} ({d['incumbent_source']})",
        "",
        "at what cost:",
        f"  {cost['hits']} hit(s) from {cost['attempts']} attempt(s), "
        f"{cost['oracle_calls_consumed']} oracle call(s), "
        f"{cost['tokens_out']} token(s) out",
        f"  task filter {cost['filter_id']} (learned: {cost['filter_is_learned']})",
        "",
        f"signature: {e['signature']['state']}, third-party checkable: "
        f"{e['signature']['third_party_checkable']}, verified: "
        f"{e['signature']['verified']} ({e['signature']['reason']})",
        "",
        "what this does not prove:",
    ]
    lines += [f"  - {s}" for s in e["does_not_prove"]]
    return "\n".join(lines)
