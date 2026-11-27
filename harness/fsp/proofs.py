"""Proof bundles a device checks before it acts (SPEC.md section 8.4, checks 4 to 6).

A bundle carries one log's leaf for a message, the inclusion proof, a
checkpoint, witness cosignatures on it and a consistency proof from the
last checkpoint the device accepted from that log. A device holds a view:
the last accepted checkpoint per log. It never accepts a smaller one.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from .canon import canon
from .log import TransparencyLog, checkpoint_valid, leaf_hash_of, root_bytes
from .merkle import verify_consistency, verify_inclusion
from .witness import count_cosigs


def make_bundle(log: TransparencyLog, index: int, cp: dict, cosigs: list[dict],
                from_size: int) -> dict:
    size = cp["body"]["size"]
    consistency = log.consistency(from_size, size) if 0 < from_size < size else []
    return {"log_id": log.log_id, "index": index, "leaf": log.leaves[index],
            "checkpoint": cp, "cosigs": cosigs,
            "inclusion": log.inclusion(index, size), "consistency": consistency,
            "from_size": from_size}


@dataclass
class BundleResult:
    ok: bool
    check: int
    reason: str
    log_id: str = ""
    index: int = -1
    logged_ms: int = -1


@dataclass
class EntryResult:
    ok: bool
    check: int
    reason: str
    indices: dict = field(default_factory=dict)
    logged_ms: dict = field(default_factory=dict)


def _policy_log(policy: dict, log_id: str) -> dict | None:
    for entry in policy["logs"]:
        if entry["log_id"] == log_id:
            return entry
    return None


def _consistent(view: dict, log_id: str, cp: dict, proof: list[str]) -> bool:
    prev = view.get(log_id)
    if prev is None:
        return True
    old, new = prev["size"], cp["body"]["size"]
    if new < old:
        return False
    if new == old:
        return prev["root"] == cp["body"]["root"]
    old_root = base64.b64decode(prev["root"])
    return verify_consistency(old, new, old_root, root_bytes(cp), [bytes.fromhex(h) for h in proof])


def verify_bundle(msg: dict, bundle: dict, policy: dict, view: dict) -> BundleResult:
    """Checks 4 to 6 for one bundle. Any malformed bundle is a check-4 failure,
    never an exception, so the device can still sign a refusal."""
    try:
        return _verify_bundle(msg, bundle, policy, view)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        log_id = bundle.get("log_id", "") if isinstance(bundle, dict) else ""
        return BundleResult(False, 4, f"malformed bundle for {log_id!r}: {type(exc).__name__}")


def _verify_bundle(msg: dict, bundle: dict, policy: dict, view: dict) -> BundleResult:
    log_id = bundle.get("log_id", "")
    entry = _policy_log(policy, log_id)
    if entry is None:
        return BundleResult(False, 4, f"log {log_id!r} is not in the log policy")
    cp = bundle["checkpoint"]
    if not checkpoint_valid(cp, entry["key"]) or cp["body"]["origin"] != log_id:
        return BundleResult(False, 4, f"checkpoint of {log_id} not signed by its log key")
    leaf = bundle["leaf"]
    if canon(leaf.get("entry")) != canon(msg):
        return BundleResult(False, 4, f"leaf in {log_id} holds a different message")
    proof = [bytes.fromhex(h) for h in bundle["inclusion"]]
    if not verify_inclusion(leaf_hash_of(leaf), bundle["index"], cp["body"]["size"], proof,
                            root_bytes(cp)):
        return BundleResult(False, 4, f"inclusion proof in {log_id} does not verify")
    witnesses = {w["key"] for w in policy["witnesses"]}
    got = count_cosigs(cp["body"], bundle["cosigs"], witnesses)
    if got < policy["k_witness"]:
        return BundleResult(False, 5, f"{log_id} checkpoint has {got} of "
                                      f"{policy['k_witness']} required witness cosignatures")
    if not _consistent(view, log_id, cp, bundle["consistency"]):
        return BundleResult(False, 6, f"{log_id} checkpoint is not consistent with the "
                                      "last one this device accepted")
    return BundleResult(True, 0, "ok", log_id, bundle["index"], leaf["logged_ms"])


def _distinct(policy: dict, log_ids, field_name: str) -> int:
    """Distinct operators or jurisdictions among the logs that passed.

    A policy entry without the field counts as its own value, so an older
    policy that names only log ids behaves as before.
    """
    values = set()
    for log_id in log_ids:
        entry = _policy_log(policy, log_id) or {}
        values.add(entry.get(field_name) or f"log:{log_id}")
    return len(values)


def verify_in_logs(msg: dict, bundles: list[dict], policy: dict, view: dict,
                   commit: bool = True) -> EntryResult:
    """Checks 4 to 6 for one message across logs.

    LOGS_MIN counts distinct log operators in distinct jurisdictions, as
    SPEC.md 0.2 defines it, taken from the log policy (Finding P42 in README.md;
    an earlier version counted distinct log ids only).

    View commit: a checkpoint that passes checks 4 to 6 is committed to the
    device's view even when the message it proves is refused later, for
    example at check 9. The checkpoint is a fact about the log, signed and
    cosigned and consistent with the device's view, whatever happens to the
    order, so advancing the view is safe and keeps the device's split-view
    check current.
    """
    passed: dict[str, BundleResult] = {}
    failures: list[BundleResult] = []
    for bundle in bundles or []:
        res = verify_bundle(msg, bundle, policy, view)
        if res.ok and res.log_id not in passed:
            passed[res.log_id] = res
            if commit:
                view[res.log_id] = {**bundle["checkpoint"]["body"], "cp": bundle["checkpoint"]}
        elif not res.ok:
            failures.append(res)
    need = policy["logs_min"]
    operators = _distinct(policy, passed, "operator")
    places = _distinct(policy, passed, "jurisdiction")
    if len(passed) >= need and min(operators, places) < need:
        return EntryResult(False, 4, f"included in {len(passed)} logs but only {operators} "
                                     f"operators in {places} jurisdictions; LOGS_MIN is {need}")
    if len(passed) >= need:
        return EntryResult(True, 0, "ok", {k: v.index for k, v in passed.items()},
                           {k: v.logged_ms for k, v in passed.items()})
    if failures:
        worst = min(failures, key=lambda r: r.check)
        return EntryResult(False, worst.check, f"included in {len(passed)} of {need} "
                                               f"required logs; {worst.reason}")
    return EntryResult(False, 4, f"included in {len(passed)} of {need} required logs")
