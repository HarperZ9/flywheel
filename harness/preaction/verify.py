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

from pathlib import Path

from ..tool_call_receipt import _canonical_bytes, _sha256_hex
from .contract import ALLOW, HOLD, BLOCK, RunContext, ProposedCall, worse
from .coverage import liveness_join
from .records import (ALLOW_SCHEMA, DECISION_SCHEMA, HOLD_SCHEMA, HoldStore, verify_seal)
from .rules import evaluate, load_pack, pack_digest


def _judge_explains(record: dict, deterministic: str) -> str | bool:
    """A recorded HOLD that the deterministic layers do not produce is fine when
    the judge layer raised it (a model call is not re-derivable). The judge can
    only raise, never lower, so a deterministic verdict stricter than the record
    is never explained this way."""
    from .contract import _RANK
    judge = record.get("judge", {})
    if _RANK.get(record["verdict"], 0) <= _RANK.get(deterministic, 0):
        return False
    return isinstance(judge, dict) and judge.get("state") in (
        "scored", "unavailable", "unavailable_passed_by_owner_setting")


def rederive(record: dict, raw_args) -> str:
    """Re-run layers 0 to 2 for one record from its raw arguments. Layer 0 is a
    recorded rule_hit, not re-derivable here, so a layer0 record keeps its
    recorded verdict; layers 1 and 2 are pure and re-run."""
    if raw_args is None:
        return record["verdict"]
    if "layer0/gate" in record.get("rule_hits", []):
        return record["verdict"]
    pack = load_pack()
    call = ProposedCall(tool=record["tool"], args=raw_args, path_id=record.get("path_id", "E1"))
    ctx = RunContext(run_id=record.get("run_id", ""))
    verdict = ALLOW
    for hit in evaluate(pack, call, ctx):
        verdict = worse(verdict, hit.action)
    return verdict


def verify_store(home, pack_override: dict | None = None) -> dict:
    store = HoldStore(home)
    recs = store.read_all()
    findings = []
    rederived = unverifiable = judge_unverifiable = 0
    expected_prev, expected_seq = "", 0
    shipped_digest = pack_digest(load_pack())
    for rec in recs:
        schema = rec.get("schema")
        expected_seq += 1
        if not verify_seal(rec):
            findings.append({"cause": "SEAL_MISMATCH", "source": rec.get("source", "")})
        probe = dict(rec)
        probe["seal"] = {"algorithm": "sha256", "hex": ""}
        this_hex = _sha256_hex(_canonical_bytes(probe))
        if rec.get("prev_record_sha256", "") != expected_prev:
            findings.append({"cause": "CHAIN_BROKEN", "source": rec.get("source", "")})
        if int(rec.get("store_seq", -1)) != expected_seq:
            findings.append({"cause": "SEQUENCE_GAP", "source": rec.get("source", "")})
        expected_prev = rec.get("seal", {}).get("hex", this_hex)
        if schema in (HOLD_SCHEMA, ALLOW_SCHEMA):
            if pack_override is not None or rec.get("rules_digest") != shipped_digest:
                unverifiable += 1
            else:
                raw = store.raw_args(rec.get("seal", {}).get("hex", ""))
                if raw is None:
                    unverifiable += 1
                else:
                    got = rederive(rec, raw)
                    rederived += 1
                    if got != rec["verdict"] and not _judge_explains(rec, got):
                        findings.append({"cause": "REDERIVED_VERDICT_DIFFERS",
                                        "source": rec.get("source", ""),
                                        "recorded": rec["verdict"], "rederived": got})
            if isinstance(rec.get("judge"), dict) and rec["judge"].get("state") in (
                    "scored", "unavailable", "unavailable_passed_by_owner_setting"):
                judge_unverifiable += 1
    join = liveness_join(recs)
    if join["verdict"] == "DRIFT":
        findings.append({"cause": "POST_WITHOUT_PRE", "orphans": join["orphans"]})
    verdict = "MATCH"
    if findings:
        verdict = "DRIFT"
    elif unverifiable and not rederived:
        verdict = "UNVERIFIABLE"
    return {"verdict": verdict, "n": len(recs), "rederived": rederived,
            "unverifiable": unverifiable, "judge_unverifiable": judge_unverifiable,
            "findings": findings}
