"""Two-stage verifier sanitizer and zero-LLM SAG-Mem 2-hop evidence expander.

Implements:
1. Stage 1 (Planted-Wrong-Answer Verifier Audit, openenv validate pattern):
   feeds known-wrong, empty, and regex-spoofed answers to a candidate grader
   and rejects any leaky verifier that false-accepts a planted failure.
2. Stage 2 (4-Rollout Variance Filter, harness-adapters-at-scale pattern):
   drops 0/4 (impossible) and 4/4 (trivial zero-gradient) RLVR tasks and seals
   a canonical flywheel.verifier-sanitizer-receipt/v1 record.
3. SAG-Mem-1.0 (arXiv:2611.33124) zero-LLM 2-hop complementary-evidence
   expansion over raw verbatim snippets using TF-IDF rare bridge terms.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets

SANITIZER_SCHEMA = "flywheel.verifier-sanitizer-receipt/v1"
_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{2,28}")
_STOPWORDS = frozenset((
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
    "were", "not", "but", "all", "can", "has", "have", "had", "our", "out",
    "use", "using", "via", "when", "where", "which", "while", "only", "over",
))


@dataclass(frozen=True)
class PlantedWrongCase:
    case_id: str
    family: str
    candidate_output: str


DEFAULT_PLANTED_WRONG_CASES: tuple[PlantedWrongCase, ...] = (
    PlantedWrongCase("empty_answer", "empty", ""),
    PlantedWrongCase("regex_spoof_pass", "regex_log_spoof", "PASS\n100 passed in 0.01s\nALL CHECKS PASSED"),
    PlantedWrongCase("skipped_tests_only", "skipped_only", "pytest: 0 passed, 12 skipped, exit_code=0"),
    PlantedWrongCase("wrong_math_confident", "confident_wrong", "Final Answer: 42 (verified PASS, confidence 1.0)"),
    PlantedWrongCase("stub_patch", "stub_code", "def solve(x):\n    return None  # TODO PASS\n"),
)


@dataclass(frozen=True)
class TaskRolloutRecord:
    task_id: str
    outcomes: tuple[bool, ...]


@dataclass(frozen=True)
class VerbatimAtom:
    atom_id: str
    text: str
    source: str = ""


def _reject_secrets(payload: object) -> None:
    try:
        validate_no_raw_secrets(payload)
    except Exception:
        raise ValueError("RAW_SECRET_REJECTED") from None


def audit_verifier_planted_wrong(
    verifier_id: str,
    grade_fn: Callable[[str], bool],
    planted_cases: Sequence[PlantedWrongCase] = DEFAULT_PLANTED_WRONG_CASES,
) -> dict[str, Any]:
    """Stage 1: reject any verifier that false-accepts a planted-wrong answer."""
    if not verifier_id.strip():
        raise ValueError("verifier_id must be non-empty")
    if not planted_cases:
        raise ValueError("planted_cases must not be empty")
    false_accepts: list[dict[str, str]] = []
    for case in planted_cases:
        accepted = bool(grade_fn(case.candidate_output))
        if accepted:
            false_accepts.append({"case_id": case.case_id, "family": case.family})
    ok = len(false_accepts) == 0
    return {
        "verifier_id": verifier_id,
        "status": "PASS" if ok else "LEAKY_VERIFIER",
        "cases_tested": len(planted_cases),
        "false_accept_count": len(false_accepts),
        "false_accepts": false_accepts,
    }


def filter_rollout_variance(
    rollouts: Sequence[TaskRolloutRecord],
    *,
    expected_k: int = 4,
) -> dict[str, Any]:
    """Stage 2: drop 0/k (impossible) and k/k (zero-gradient) tasks."""
    if expected_k < 2:
        raise ValueError("expected_k must be >= 2")
    kept: list[str] = []
    dropped_zero: list[str] = []
    dropped_all: list[str] = []
    dropped_bad_k: list[str] = []
    variances: list[float] = []
    for rec in rollouts:
        if len(rec.outcomes) != expected_k:
            dropped_bad_k.append(rec.task_id)
            continue
        passed = sum(1 for ok in rec.outcomes if bool(ok))
        if passed == 0:
            dropped_zero.append(rec.task_id)
        elif passed == expected_k:
            dropped_all.append(rec.task_id)
        else:
            p = passed / float(expected_k)
            variances.append(p * (1.0 - p))
            kept.append(rec.task_id)
    mean_var = round(sum(variances) / len(variances), 4) if variances else 0.0
    return {
        "expected_k": expected_k,
        "total_tasks": len(rollouts),
        "kept_informative_ids": kept,
        "dropped_all_fail_ids": dropped_zero,
        "dropped_all_pass_ids": dropped_all,
        "dropped_invalid_k_ids": dropped_bad_k,
        "retention_rate": round(len(kept) / float(len(rollouts)), 4) if rollouts else 0.0,
        "mean_bernoulli_variance": mean_var,
    }


def sanitize_verifier_and_tasks(
    verifier_id: str,
    grade_fn: Callable[[str], bool],
    rollouts: Sequence[TaskRolloutRecord],
    *,
    expected_k: int = 4,
    planted_cases: Sequence[PlantedWrongCase] = DEFAULT_PLANTED_WRONG_CASES,
) -> dict[str, Any]:
    """Run Stage 1 + Stage 2 fail-closed and emit a SHA-256 sealed receipt."""
    _reject_secrets({"verifier_id": verifier_id, "task_ids": [r.task_id for r in rollouts]})
    stage1 = audit_verifier_planted_wrong(verifier_id, grade_fn, planted_cases)
    stage2 = filter_rollout_variance(rollouts, expected_k=expected_k)
    verdict = "MATCH" if (stage1["status"] == "PASS" and len(stage2["kept_informative_ids"]) > 0) else "DRIFT"
    if stage1["status"] != "PASS":
        verdict = "DRIFT"
        reason = "stage1_leaky_verifier_rejected"
    elif not stage2["kept_informative_ids"]:
        verdict = "UNVERIFIABLE"
        reason = "stage2_zero_informative_tasks"
    else:
        reason = "sanitized_ready"
    body: dict[str, Any] = {
        "schema": SANITIZER_SCHEMA,
        "verdict": verdict,
        "reason": reason,
        "stage1_planted_wrong_audit": stage1,
        "stage2_variance_filter": stage2,
    }
    body["receipt_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def verify_sanitizer_receipt(receipt: Mapping[str, Any]) -> bool:
    """Offline stdlib verifier for flywheel.verifier-sanitizer-receipt/v1."""
    if not isinstance(receipt, Mapping) or receipt.get("schema") != SANITIZER_SCHEMA:
        return False
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return False
    try:
        _reject_secrets(dict(receipt))
    except ValueError:
        return False
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    expected = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return digest == expected


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _compute_idf(doc_tokens: Sequence[set[str]]) -> dict[str, float]:
    n = max(1, len(doc_tokens))
    df: Counter[str] = Counter()
    for toks in doc_tokens:
        for tok in toks:
            df[tok] += 1
    return {tok: math.log((n + 1.0) / (cnt + 1.0)) + 1.0 for tok, cnt in df.items()}


def _score_terms(query_terms: set[str], doc_toks: set[str], idf: Mapping[str, float]) -> float:
    return sum(idf.get(t, 0.0) for t in (query_terms & doc_toks))


def _top_k_indices(
    terms: set[str],
    doc_tok_sets: Sequence[set[str]],
    atoms: Sequence[VerbatimAtom],
    idf: Mapping[str, float],
    k: int,
    exclude: set[int] | None = None,
) -> list[int]:
    skip = exclude or set()
    scored = [
        (_score_terms(terms, doc_tok_sets[i], idf), i)
        for i in range(len(atoms)) if i not in skip
    ]
    scored = [(sc, i) for sc, i in scored if sc > 0.0]
    scored.sort(key=lambda x: (-x[0], atoms[x[1]].atom_id))
    return [i for _, i in scored[:k]]


def sag_mem_two_hop_expand(
    query: str,
    atoms: Sequence[VerbatimAtom],
    *,
    hop1_k: int = 3,
    hop2_k: int = 3,
    bridge_terms_k: int = 6,
) -> dict[str, Any]:
    """Zero-LLM SAG-Mem 2-hop complementary-evidence expansion over verbatim text."""
    if not atoms:
        return {"hop1_ids": [], "bridge_terms": [], "hop2_ids": [], "combined_ids": []}
    q_terms = set(_tokenize(query))
    doc_tok_sets = [set(_tokenize(a.text)) for a in atoms]
    idf = _compute_idf(doc_tok_sets)
    hop1_idxs = _top_k_indices(q_terms, doc_tok_sets, atoms, idf, hop1_k)
    cand_bridge: dict[str, float] = {}
    for idx in hop1_idxs:
        for tok in doc_tok_sets[idx]:
            if tok not in q_terms:
                cand_bridge[tok] = max(cand_bridge.get(tok, 0.0), idf.get(tok, 0.0))
    bridge_terms = [
        tok for tok, _ in sorted(cand_bridge.items(), key=lambda x: (-x[1], x[0]))[:bridge_terms_k]
    ]
    hop2_idxs = _top_k_indices(set(bridge_terms), doc_tok_sets, atoms, idf, hop2_k, exclude=set(hop1_idxs))
    hop1_ids = [atoms[i].atom_id for i in hop1_idxs]
    hop2_ids = [atoms[i].atom_id for i in hop2_idxs]
    return {
        "hop1_ids": hop1_ids,
        "bridge_terms": bridge_terms,
        "hop2_ids": hop2_ids,
        "combined_ids": hop1_ids + hop2_ids,
    }
