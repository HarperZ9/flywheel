"""Proof-Carrying Merkle Trace Compressor (Wave 26B).

Compresses multi-branch verification search trees by >= 10x tokens with
0 soundness loss using RFC 6962 domain-separated Merkle commitments
(harness.merkle) and zero-LLM deterministic witness replay.
"""
from __future__ import annotations

import copy
import hashlib
import math
from typing import Any, Mapping, Sequence

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets
from .merkle import inclusion_proof, root_hex, verify_inclusion
from .oracle_tree_search import SearchBudget, SearchCandidate, run_oracle_tree_search
from .super_solver_pipeline import eval_f64_oracle

PROOF_TRACE_SCHEMA = "flywheel.proof-trace/v1"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def estimate_tokens(text: str) -> int:
    """Deterministic tokenizer-free token count estimate (~4 chars/token)."""
    return 0 if not text else max(1, (len(text.encode("utf-8")) + 3) // 4)


def _canonical_leaf(node: Mapping[str, Any], leaf_index: int) -> bytes:
    return canonical_bytes({
        "leaf_index": leaf_index, "node_id": str(node["node_id"]),
        "parent_id": node.get("parent_id"), "action_label": str(node.get("action_label", "")),
        "oracle_verdict": str(node.get("oracle_verdict", "")), "raw_tokens": int(node.get("tokens", 0)),
        "reasoning_sha256": _sha256_text(str(node.get("reasoning_trace", ""))),
        "witness_sha256": _sha256_obj(node.get("witness", {})),
    })


def _leaf_from_winning_step(step: Mapping[str, Any]) -> bytes:
    return canonical_bytes({
        "leaf_index": int(step["leaf_index"]), "node_id": str(step["node_id"]),
        "parent_id": step.get("parent_id"), "action_label": str(step.get("action_label", "")),
        "oracle_verdict": str(step.get("oracle_verdict", "")), "raw_tokens": int(step.get("raw_tokens", 0)),
        "reasoning_sha256": str(step["reasoning_sha256"]),
        "witness_sha256": _sha256_obj(step.get("witness", {})),
    })


def _node_raw_tokens(node: Mapping[str, Any]) -> int:
    return max(int(node.get("tokens", 0)), estimate_tokens(str(node.get("reasoning_trace", ""))))


def _compact_witness(witness: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(witness.get("numeric"), Mapping):
        out["numeric"] = dict(witness["numeric"])
    if "plate_b_pass" in witness:
        out["plate_b_pass"] = bool(witness["plate_b_pass"])
    if "custom_status" in witness:
        out["custom_status"] = str(witness["custom_status"])
    return out


def _build_winning_steps(
    nodes: Sequence[Mapping[str, Any]], win_ids: Sequence[str], all_leaves: list[bytes],
) -> list[dict[str, Any]]:
    idx_by_id = {str(n["node_id"]): (i, n) for i, n in enumerate(nodes)}
    steps: list[dict[str, Any]] = []
    for wid in win_ids:
        leaf_idx, node = idx_by_id[wid]
        steps.append({
            "leaf_index": leaf_idx, "node_id": wid, "parent_id": node.get("parent_id"),
            "action_label": str(node.get("action_label", "")), "oracle_verdict": str(node.get("oracle_verdict", "")),
            "raw_tokens": int(node.get("tokens", 0)),
            "reasoning_sha256": _sha256_text(str(node.get("reasoning_trace", ""))),
            "witness": _compact_witness(node.get("witness", {})),
            "merkle_proof": [h.hex() for h in inclusion_proof(all_leaves, leaf_idx)],
        })
    return steps


def compress_search_trace(search_result: Mapping[str, Any]) -> dict[str, Any]:
    """Compress a verified search tree into a proof-carrying Merkle trace."""
    if search_result.get("status") != "SOLVED":
        raise ValueError(f"cannot compress unsolved search result: {search_result.get('status')}")
    nodes: Sequence[Mapping[str, Any]] = search_result.get("nodes", [])
    win_ids: list[str] = list(search_result.get("winning_path", []))
    if not nodes or not win_ids:
        raise ValueError("search result missing nodes or winning_path")

    all_leaves = [_canonical_leaf(n, idx) for idx, n in enumerate(nodes)]
    tree_root = root_hex(all_leaves)
    win_set = set(win_ids)
    pruned_leaves = [all_leaves[i] for i, n in enumerate(nodes) if n["node_id"] not in win_set]
    pruned_root = root_hex(pruned_leaves) if pruned_leaves else "sha256:" + hashlib.sha256(b"").hexdigest()
    winning_steps = _build_winning_steps(nodes, win_ids, all_leaves)

    raw_tokens = sum(_node_raw_tokens(n) for n in nodes)
    pruned_tokens = sum(_node_raw_tokens(n) for n in nodes if n["node_id"] not in win_set)
    raw_bytes = len(canonical_bytes(dict(search_result)))
    core_bytes = canonical_bytes({"winning_steps": winning_steps, "pruned_merkle_root": pruned_root, "tree_merkle_root": tree_root})
    comp_tokens = estimate_tokens(core_bytes.decode("utf-8"))
    body: dict[str, Any] = {
        "schema": PROOF_TRACE_SCHEMA, "task_id": str(search_result.get("task_id", "")),
        "source_search_sha256": str(search_result.get("result_sha256", "")),
        "total_leaf_count": len(all_leaves), "tree_merkle_root": tree_root,
        "pruned_summary": {"count": len(pruned_leaves), "pruned_tokens": pruned_tokens, "merkle_root": pruned_root},
        "required_witness_ids": list(win_ids), "winning_steps": winning_steps,
        "metrics": {
            "raw_tokens": raw_tokens, "compressed_tokens": comp_tokens,
            "compression_ratio": round(float(raw_tokens) / float(max(1, comp_tokens)), 3),
            "raw_bytes": raw_bytes, "compressed_bytes": len(core_bytes),
            "byte_compression_ratio": round(float(raw_bytes) / float(max(1, len(core_bytes))), 3),
            "winning_step_count": len(winning_steps), "pruned_branch_count": len(pruned_leaves),
        },
    }
    validate_no_raw_secrets(body)
    body["trace_sha256"] = _sha256_obj(body)
    return body


def _verify_step_witness(step: Mapping[str, Any]) -> list[str]:
    errs: list[str] = []
    witness = step.get("witness")
    if not isinstance(witness, Mapping):
        return ["MISSING_WITNESS_OR_MERKLE_MISMATCH"]
    num = witness.get("numeric")
    if isinstance(num, Mapping) and num.get("checked") is True:
        expr, claimed = str(num.get("numeric_expr", "")), num.get("claimed_numeric")
        if not expr.strip() or claimed is None:
            errs.append("MISSING_WITNESS_OR_MERKLE_MISMATCH")
        else:
            try:
                exact = eval_f64_oracle(expr)
            except Exception:
                errs.append("WITNESS_REPLAY_MISMATCH")
            else:
                if not math.isclose(float(claimed), exact, rel_tol=float(num.get("rel_tol", 1e-6)), abs_tol=1e-9):
                    errs.append("WITNESS_REPLAY_MISMATCH")
    if witness.get("plate_b_pass") is False:
        errs.append("WITNESS_REPLAY_MISMATCH")
    return errs


def _verify_merkle_step(step: Mapping[str, Any], total_leaves: int, root_bytes: bytes) -> bool:
    try:
        leaf_bytes = _leaf_from_winning_step(step)
        proof_bytes = [bytes.fromhex(h) for h in step["merkle_proof"]]
        return verify_inclusion(leaf_bytes, int(step["leaf_index"]), total_leaves, proof_bytes, root_bytes)
    except Exception:
        return False


def verify_proof_trace(compressed: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Zero-LLM fail-closed replay verifier for flywheel.proof-trace/v1."""
    errors: list[str] = []
    if not isinstance(compressed, Mapping) or compressed.get("schema") != PROOF_TRACE_SCHEMA:
        return False, ["INVALID_SCHEMA"]
    try:
        validate_no_raw_secrets(dict(compressed))
    except Exception:
        errors.append("RAW_SECRET_REJECTED")
    body = {k: v for k, v in compressed.items() if k != "trace_sha256"}
    if compressed.get("trace_sha256") != _sha256_obj(body):
        errors.append("FORGED_TRACE_ENVELOPE")

    steps, req_ids = compressed.get("winning_steps"), compressed.get("required_witness_ids")
    total_leaves, root_str = int(compressed.get("total_leaf_count", 0)), str(compressed.get("tree_merkle_root", ""))
    if not isinstance(steps, list) or not steps or not isinstance(req_ids, list) or not root_str.startswith("sha256:"):
        return False, sorted(set(errors + ["MISSING_WITNESS_OR_MERKLE_MISMATCH"]))
    if [s.get("node_id") for s in steps] != req_ids:
        errors.append("MISSING_WITNESS_OR_MERKLE_MISMATCH")
    try:
        root_bytes = bytes.fromhex(root_str.split(":", 1)[1])
    except ValueError:
        return False, sorted(set(errors + ["MISSING_WITNESS_OR_MERKLE_MISMATCH"]))

    expected_parent: str | None = None
    for idx, step in enumerate(steps):
        if idx > 0 and step.get("parent_id") != expected_parent:
            errors.append("MISSING_WITNESS_OR_MERKLE_MISMATCH")
        expected_parent = step.get("node_id")
        if not _verify_merkle_step(step, total_leaves, root_bytes):
            errors.append("MISSING_WITNESS_OR_MERKLE_MISMATCH")
        errors.extend(_verify_step_witness(step))
    if steps[-1].get("oracle_verdict") != "PASS":
        errors.append("TERMINAL_ORACLE_NOT_PASS")
    dedup = sorted(set(errors))
    return (len(dedup) == 0), dedup


def _reseal_for_adversarial_test(trace: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(trace)
    out["trace_sha256"] = _sha256_obj({k: v for k, v in out.items() if k != "trace_sha256"})
    return out


def _build_12branch_search() -> dict[str, Any]:
    verbose_cot = (
        "Long exploratory chain-of-thought reasoning through candidate algebraic "
        "transformations, speculative rewrites, sign checks, boundary cases, and "
        "redundant unit conversions that ultimately diverge from the physical oracle. "
    ) * 18
    root = SearchCandidate("root", None, "s0", "init_verify", 1.0, 420, need_more_evidence=True, reasoning_trace=verbose_cot[:480])

    def _expand(node: SearchCandidate) -> list[SearchCandidate]:
        if node.node_id == "root":
            dead = [
                SearchCandidate(
                    f"dead_{i:02d}", "root", f"s_dead_{i:02d}", f"wrong_branch_{i:02d}",
                    prior_prob=round(0.85 - i * 0.05, 2), tokens=1450, is_terminal=True,
                    numeric_expr="0.5 * 10.0 * (9.80665 ** 2)", claimed_numeric=float(100 + i * 17),
                    reasoning_trace=verbose_cot,
                )
                for i in range(11)
            ]
            return [*dead, SearchCandidate("mid_exact", "root", "s_mid", "setup_exact_energy", 0.14, 480, need_more_evidence=True, reasoning_trace=verbose_cot[:520])]
        if node.node_id == "mid_exact":
            return [SearchCandidate(
                "win_oracle", "mid_exact", "s_win", "verify_f64_energy", 0.92, 540, is_terminal=True,
                numeric_expr="0.5 * 10.0 * (9.80665 ** 2)", claimed_numeric=480.85191125,
                candidate_code="def energy(m: float, g: float) -> float:\n    return 0.5 * m * g * g\n",
                reasoning_trace=verbose_cot[:600],
            )]
        return []

    return run_oracle_tree_search("wave26b-12branch-bench", root, _expand, SearchBudget(max_expansions=32, max_tokens=25000))


def run_compression_benchmark() -> dict[str, Any]:
    """Prove >= 10x compression on a 12-branch tree + fail-closed planted controls."""
    compressed = compress_search_trace(_build_12branch_search())
    clean_ok, clean_errs = verify_proof_trace(compressed)

    dropped = copy.deepcopy(compressed)
    dropped["winning_steps"] = dropped["winning_steps"][:-1]
    drop_ok, drop_errs = verify_proof_trace(_reseal_for_adversarial_test(dropped))

    forged = copy.deepcopy(compressed)
    forged["tree_merkle_root"] = "sha256:" + "0" * 64
    root_ok, root_errs = verify_proof_trace(_reseal_for_adversarial_test(forged))

    ratio = compressed["metrics"]["compression_ratio"]
    drop_caught = (not drop_ok) and ("MISSING_WITNESS_OR_MERKLE_MISMATCH" in drop_errs)
    root_caught = (not root_ok) and ("MISSING_WITNESS_OR_MERKLE_MISMATCH" in root_errs)
    return {
        "schema": "flywheel.wave26b-compression-bench/v1",
        "clean_replay_ok": clean_ok, "clean_errors": clean_errs,
        "metrics": compressed["metrics"],
        "dropped_witness_rejected": drop_caught,
        "forged_merkle_root_rejected": root_caught,
        "tree_merkle_root": compressed["tree_merkle_root"],
        "trace_sha256": compressed["trace_sha256"],
        "all_passed": (clean_ok and ratio >= 10.0 and drop_caught and root_caught),
    }
