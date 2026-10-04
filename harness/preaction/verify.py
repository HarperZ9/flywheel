"""verify.py -- offline re-derivation of a record store.

A stranger with the store, the rule pack and (for arguments) the owner's key
re-walks the chain and returns the plan's vocabulary: MATCH (seals hold, links
hold, sequence is continuous, every post has a pre, and the re-derived layer 1
and 2 verdict matches what was recorded), DRIFT (a seal or link fails, a record
is missing, a post has no pre, or the re-derived verdict differs), or
UNVERIFIABLE (the judge layer, which a model call cannot reproduce, or a record
whose rule pack or arguments the verifier does not have).
"""
from __future__ import annotations


from ..tool_call_receipt import _canonical_bytes, _sha256_hex
from .contract import ALLOW, RunContext, ProposedCall, worse
from .coverage import liveness_join
from . import anchoring, public_anchor
from .records import (ALLOW_SCHEMA, HOLD_SCHEMA, HoldStore, seal_preimage, store_id,
                      verify_seal)
from .rules import evaluate, load_pack, pack_digest


_LAYER0_IDS = frozenset({"layer0/gate", "monitor_config_drift", "record_write_failed"})
_JUDGE_STATES = ("scored", "unavailable", "unavailable_passed_by_owner_setting",
                 "skipped_steering_text", "typed")


def _judge_explains(record: dict, deterministic: str) -> str | bool:
    """A recorded verdict stricter than layer 1 re-derives is explained when a
    layer that cannot be re-run from one record raised it: the judge (a model
    call), the trajectory layer (it reads the run's history) or a layer-0 hit
    (the executor gate or config pin). Those layers only raise, never lower, so
    a re-derived verdict stricter than the record is never explained this way."""
    from .contract import _RANK
    if _RANK.get(record["verdict"], 0) <= _RANK.get(deterministic, 0):
        return False
    judge = record.get("judge", {})
    if isinstance(judge, dict) and judge.get("state") in _JUDGE_STATES:
        return True
    if record.get("trajectory_hits"):
        return True
    return any(h in _LAYER0_IDS for h in record.get("rule_hits", []))


def _ctx(record: dict, context: dict | None) -> RunContext:
    c = context or {}
    return RunContext(run_id=record.get("run_id", ""), workspace=c.get("workspace", ""),
                      allow_hosts=tuple(c.get("allow_hosts", ())),
                      owned_hosts=tuple(c.get("owned_hosts", ())),
                      fetch_hosts=tuple(c.get("fetch_hosts", ())),
                      canaries=tuple(c.get("canaries", ())),
                      protected_paths=tuple(c.get("protected_paths", ())))


def rederive(record: dict, raw_args, context: dict | None = None) -> str:
    """Re-run layers 0 to 2 for one record from its raw arguments. Layer 0 is a
    recorded rule_hit, not re-derivable here, so a layer0 record keeps its
    recorded verdict; layers 1 and 2 are pure and re-run."""
    if raw_args is None:
        return record["verdict"]
    if "layer0/gate" in record.get("rule_hits", []):
        return record["verdict"]
    pack = load_pack()
    call = ProposedCall(tool=record["tool"], args=raw_args, path_id=record.get("path_id", "E1"))
    ctx = _ctx(record, context)
    verdict = ALLOW
    for hit in evaluate(pack, call, ctx):
        verdict = worse(verdict, hit.action)
    return verdict


def _verdicts(recs, store, findings, trust_root, signer_head, nothing_rederived) -> dict:
    """The internal verdict, then the verdict after the trust-root check."""
    anchor = anchoring.check(recs, store, trust_root, signer_head)
    findings.extend(anchor["findings"])
    internal = "MATCH"
    if findings:
        internal = "DRIFT"
    elif nothing_rederived:
        internal = "UNVERIFIABLE"
    return {"verdict": anchoring.final_verdict(internal, anchor["anchored"]),
            "internal_verdict": internal, "anchored": anchor["anchored"],
            "signer_isolation": anchor["signer_isolation"],
            "truncation_checked": anchor.get("truncation_checked", False),
            "rewinds": anchor.get("rewinds", []), "notes": anchor["notes"]}


def verify_store(home, pack_override: dict | None = None, *, trust_root: str = "",
                 signer_head: dict | None = None, anchors=None,
                 anchors_online=None) -> dict:
    """``trust_root``: the separate signer's public key, hex, pinned by the
    caller. Without it a consistent store is UNANCHORED, never MATCH.
    ``signer_head``: a signed head from the signer, to catch truncation.
    ``anchors``: the signer's anchors directory, to hold the store to every
    head anchored in Rekor (public_anchor.py). ``anchors_online``: a request
    function, to list the key's Rekor entries and catch deleted receipts."""
    store = HoldStore(home, signer=None)
    recs = store.read_all(tolerant=True)
    findings = []
    rederived = unverifiable = judge_unverifiable = 0
    allow_domains: dict = {}
    expected_prev, expected_seq = "", 0
    shipped_digest = pack_digest(load_pack())
    for rec in recs:
        schema = rec.get("schema")
        expected_seq += 1
        if not verify_seal(rec):
            findings.append({"cause": "SEAL_MISMATCH", "source": rec.get("source", "")})
        this_hex = _sha256_hex(seal_preimage(rec))
        if rec.get("prev_record_sha256", "") != expected_prev:
            findings.append({"cause": "CHAIN_BROKEN", "source": rec.get("source", "")})
        if int(rec.get("store_seq", -1)) != expected_seq:
            findings.append({"cause": "SEQUENCE_GAP", "source": rec.get("source", "")})
        expected_prev = rec.get("seal", {}).get("hex", this_hex)
        if schema == "unparseable":
            findings.append({"cause": "TORN_OR_UNPARSEABLE_LINE", "seq": expected_seq})
            continue
        if schema == ALLOW_SCHEMA:
            dom = rec.get("trust_domain", "unrecorded")
            allow_domains[dom] = allow_domains.get(dom, 0) + 1
        if schema in (HOLD_SCHEMA, ALLOW_SCHEMA):
            seal_hex = rec.get("seal", {}).get("hex", "")
            context = store.raw_context(seal_hex)
            if context is not None and _sha256_hex(_canonical_bytes(context)) !=                     rec.get("context_sha256"):
                findings.append({"cause": "CONTEXT_MISMATCH", "source": rec.get("source", "")})
                continue
            if pack_override is not None or rec.get("rules_digest") != shipped_digest                     or rec.get("coverage") == "UNVERIFIABLE":
                unverifiable += 1
            else:
                raw = store.raw_args(seal_hex)
                if raw is None or (rec.get("context_sha256") and context is None):
                    unverifiable += 1
                else:
                    got = rederive(rec, raw, context)
                    rederived += 1
                    if got != rec["verdict"] and not _judge_explains(rec, got):
                        findings.append({"cause": "REDERIVED_VERDICT_DIFFERS",
                                        "source": rec.get("source", ""),
                                        "recorded": rec["verdict"], "rederived": got})
            if isinstance(rec.get("judge"), dict) and rec["judge"].get("state") in _JUDGE_STATES:
                judge_unverifiable += 1
    from .trace_flag import verify_chain
    findings.extend(verify_chain(recs))
    join = liveness_join(recs)
    if join["verdict"] == "DRIFT":
        findings.append({"cause": "POST_WITHOUT_PRE", "orphans": join["orphans"]})
    pub = public_anchor.check(recs, store_id(home), trust_root, anchors,
                              online_request=anchors_online)
    findings.extend(pub["findings"])
    head = _verdicts(recs, store_id(home), findings, trust_root, signer_head,
                     unverifiable and not rederived)
    return {**head, "public_anchor": {**pub["report"], "notes": pub["notes"]},
            "n": len(recs), "rederived": rederived,
            "unverifiable": unverifiable, "judge_unverifiable": judge_unverifiable,
            # An ALLOW decided inside the agent's reach is weaker evidence than
            # one decided outside it; the split is reported, never merged.
            "allow_by_trust_domain": allow_domains,
            "findings": findings}
