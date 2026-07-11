"""selector.py -- the verified selection component (promotes the measured findings).

The 2026-07-10 selector measurements settled three things, and this module turns
them into a load-bearing accept-path component instead of experiment-script code:

  1. An EXTERNAL oracle earns capability the model cannot self-select
     (headroom: single 5% -> oracle best-of-4 23%, self-test +0%). So when an
     oracle exists it is the highest-trust selector.
  2. Oracle-FREE consensus (behavioral clustering on a pre-decided typed battery)
     is bounded by candidate MULTIPLICITY, not selector cleverness: it can only
     reach tasks with >=2 correct candidates. At N=4 that was 6.6% of headroom.
  3. The lever is N. Raising the candidate budget moves tasks across the
     multiplicity threshold (topo_sort 0/8 -> 3/16 correct). Cluster-fraction is
     the confidence signal that says when consensus is trustworthy.

The policy composes these into one ladder, with NO learned model in the accept
path (C2 invariant): an external oracle decides when present; otherwise a
DETERMINISTIC behavioral clustering decides; a low-confidence oracle-free verdict
RAISES N (the measured lever) before recommending escalation to a costlier tier.

Every selection emits a SelectionReceipt: candidate hashes + method + confidence
+ budget, plus the oracle pass-vector (re-run the oracle) or the battery hash
(re-cluster the candidates) -- so a third party reproduces the choice. The check
can fail: a receipt whose re-clustering picks a different index is DRIFT.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .oracle import Oracle
from .task import Task
from .workspace_lens import WorkspaceLens, NO_CAUTION
# Probe + clustering machinery lives in selector_probe; re-exported here so the
# historical import surface (run_ablation, tests) is unchanged.
from .selector_probe import (   # noqa: F401
    SLOT_TIMEOUT, PROBE_BACKSTOP,
    fn_name, fn_arity, infer_param_types, battery, consensus_select,
    _signature, _productive, _cluster_select, _entry_def, _safe_parse,
    max_correlation, _token_set, _jaccard,
    _INT_POOL, _STR_POOL, _LIST_INT_POOL, _LIST_STR_POOL, _BOOL_POOL,
    _DICT_POOL, _MATRIX_POOL, _MIXED_POOL, _TYPE_POOLS,
    _NAME_LIST, _NAME_MATRIX, _NAME_STR, _NAME_INT, _NAME_DICT,
)


def _as_text(c) -> str:
    """Coerce any candidate to a string so no downstream step crashes on a None
    or non-string candidate. A malformed candidate becomes its repr, which the
    behavioral probe classifies UNRUNNABLE (it never clusters)."""
    if isinstance(c, str):
        return c
    return "" if c is None else str(c)

def _oracle_pass(oracle: Oracle, candidate: str, task: Task) -> bool:
    """A candidate whose oracle check raises is treated as NOT passing -- a
    broken/throwing oracle can never accept a candidate, and never crashes the
    selection. (The oracle is still the only thing that can ACCEPT; this only
    controls how its own failure is read.)"""
    try:
        return bool(oracle.verify(candidate, task).passed)
    except Exception:
        return False


def oracle_select(candidates: list[str], task: Task,
                  oracle: Oracle) -> tuple[int, list[bool], float]:
    """External-oracle selection. Return (index, pass_vector, correlation).
    index is the first passing candidate, or -1 if none pass. correlation is the
    max pairwise jaccard, used to distinguish honest diverse failure from
    wrong-attractor convergence (voice-cap gate)."""
    passes = [_oracle_pass(oracle, c, task) for c in candidates]
    idx = next((i for i, p in enumerate(passes) if p), -1)
    return idx, passes, max_correlation(candidates)


def _sha(text) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


CONFIDENCE_THRESHOLD = 0.5   # a productive majority is the trustworthy signal
CORRELATION_THRESHOLD = 0.85
MIN_CONSENSUS_CANDIDATES = 2  # one candidate is single-shot, not agreement

# Verdict tokens are NOT interchangeable -- the token IS the trust level:
#   PASS           an external oracle VERIFIED a candidate (correctness).
#   CONSENSUS_PASS candidates AGREED (behavioral majority) -- NOT verified
#                  correct. A caller that needs correctness must not treat this
#                  as an accept; the companion seat escalates for verification.
PASS = "PASS"
CONSENSUS_PASS = "CONSENSUS_PASS"
ACCEPT_VERDICTS = frozenset({PASS, CONSENSUS_PASS})   # both terminate the raise-N loop

# Re-check verdicts (mirror witness.py / dataset.receipt conventions).
MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class SelectionReceipt:
    """Re-checkable record of a selection decision. To reproduce: the verifier
    re-runs the oracle over the committed candidate hashes (oracle path), or
    regenerates the battery from (fn, arity, param_types) and re-clusters the
    committed candidates (consensus path). candidate_hashes are one-way
    commitments -- the re-check requires the candidate TEXTS supplied alongside,
    which the receipt does not itself store; it commits to them so tampering is
    detectable, it does not claim to contain them."""
    method: str                       # oracle | consensus | single | escalate
    selected_index: int
    confidence: float
    candidates_used: int
    candidate_hashes: list[str] = field(default_factory=list)
    oracle_pass_vector: list[bool] | None = None
    battery_hash: str | None = None
    correlation: float = 0.0
    verdict: str = ""                 # PASS | LOW_CONFIDENCE | UNVERIFIABLE | ESCALATE
    reason: str = ""
    task_id: str | None = None
    fn: str | None = None
    arity: int | None = None
    param_types: list[str] | None = None
    runner_up_confidence: float = 0.0
    probe_slot_timeout: int | None = None   # the per-input probe deadline used
    workspace_caution: dict | None = None   # demote-only advisory, if a lens fired

    def to_dict(self) -> dict:
        return {
            "schema": "flywheel.selection-receipt/v1",
            "method": self.method,
            "selected_index": self.selected_index,
            "confidence": round(self.confidence, 4),
            "runner_up_confidence": round(self.runner_up_confidence, 4),
            "candidates_used": self.candidates_used,
            "candidate_hashes": self.candidate_hashes,
            "oracle_pass_vector": self.oracle_pass_vector,
            "battery_hash": self.battery_hash,
            "correlation": round(self.correlation, 4),
            "verdict": self.verdict,
            "reason": self.reason,
            "task_id": self.task_id,
            "fn": self.fn,
            "arity": self.arity,
            "param_types": self.param_types,
            "probe_slot_timeout": self.probe_slot_timeout,
            "workspace_caution": self.workspace_caution,
        }


@dataclass
class SelectionResult:
    text: str | None
    receipt: SelectionReceipt


def select(candidates: list[str], *, solution_sig: str = "", task: Task | None = None,
           oracle: Oracle | None = None,
           confidence_threshold: float = CONFIDENCE_THRESHOLD,
           workspace_lens: WorkspaceLens | None = None,
           entry_point: str | None = None) -> SelectionResult:
    """Select over a FIXED candidate pool. Oracle path when an oracle+task are
    given (highest trust); else oracle-free consensus with a confidence gate.
    No learned model decides; the receipt makes the decision re-checkable.

    An optional workspace_lens is a DEMOTE-ONLY advisory: it may turn a
    CONSENSUS_PASS into LOW_CONFIDENCE (so the caller raises N / escalates), never
    grant an accept, never touch an oracle-verified PASS. With no lens (default),
    behavior is byte-identical to having no workspace signal. C2 stays intact.

    Fails LOUD when an oracle is supplied without a task (the oracle has nothing
    to verify against) so a caller never silently loses oracle-verification
    strength. task WITHOUT oracle is fine -- that is the consensus path, which
    still uses task for its id/metadata."""
    if oracle is not None and task is None:
        raise ValueError(
            "select(): an oracle requires a task to verify against -- passing an "
            "oracle with task=None silently downgrades to consensus selection")
    if not 0.0 < confidence_threshold <= 1.0:
        raise ValueError(f"confidence_threshold must be in (0, 1], got {confidence_threshold}")
    if candidates is None:
        candidates = []
    candidates = [_as_text(c) for c in candidates]     # no None/non-str downstream
    hashes = [_sha(c) for c in candidates]
    task_id = getattr(task, "task_id", None) if task is not None else None
    if not candidates:
        return SelectionResult(None, SelectionReceipt(
            method="single", selected_index=-1, confidence=0.0, candidates_used=0,
            verdict="UNVERIFIABLE", reason="no candidates", task_id=task_id))

    if oracle is not None and task is not None:
        idx, passes, corr = oracle_select(candidates, task, oracle)
        if idx >= 0:
            return SelectionResult(candidates[idx], SelectionReceipt(
                method="oracle", selected_index=idx, confidence=1.0,
                candidates_used=len(candidates), candidate_hashes=hashes,
                oracle_pass_vector=passes, correlation=corr, task_id=task_id,
                verdict="PASS", reason="external oracle accepted a candidate"))
        # No pass: honest FAIL vs wrong-attractor convergence (voice-cap gate).
        verdict = "UNVERIFIABLE" if corr >= CORRELATION_THRESHOLD else "PASS_NONE"
        reason = ("no pass and candidates correlated -- refusing confident FAIL"
                  if verdict == "UNVERIFIABLE" else "no candidate passed the oracle")
        return SelectionResult(None, SelectionReceipt(
            method="oracle", selected_index=-1, confidence=0.0,
            candidates_used=len(candidates), candidate_hashes=hashes,
            oracle_pass_vector=passes, correlation=corr, task_id=task_id,
            verdict=verdict, reason=reason))

    # Oracle-free path: behavioral consensus, gated. Cluster fraction measures
    # AGREEMENT, not correctness -- so a high-confidence PASS is only honest when
    # the agreement is NOT wrong-attractor convergence (near-identical samples of
    # one biased model) and NOT a tie the tie-break resolved by array position.
    fn = fn_name(solution_sig, entry_point)
    arity = fn_arity(solution_sig, entry_point) or 1
    ptypes = infer_param_types(solution_sig, entry_point)
    wd = Path(tempfile.mkdtemp(prefix="sel_cons_"))
    try:
        idx, conf, runner = _cluster_select(candidates, fn, arity, wd, param_types=ptypes)
    finally:
        shutil.rmtree(wd, ignore_errors=True)   # no scratch-dir leak per call
    corr = max_correlation(candidates)
    batt_hash = _sha(json.dumps(battery(arity, param_types=ptypes), default=str))

    if conf == 0.0:
        verdict, reason = "LOW_CONFIDENCE", "no productive consensus (candidates crash or disagree entirely)"
    elif len(candidates) < MIN_CONSENSUS_CANDIDATES:
        verdict, reason = "LOW_CONFIDENCE", (
            f"only {len(candidates)} candidate -- that is single-shot, not "
            f"agreement; raise N to at least {MIN_CONSENSUS_CANDIDATES} or escalate")
    elif corr >= CORRELATION_THRESHOLD:
        verdict, reason = "LOW_CONFIDENCE", (
            f"consensus {conf:.0%} but candidates near-identical (corr {corr:.0%} "
            f">= {CORRELATION_THRESHOLD:.0%}) -- wrong-attractor convergence, not "
            f"independent agreement; raise N with more diversity or escalate")
    elif runner >= conf:
        verdict, reason = "LOW_CONFIDENCE", (
            f"consensus tie ({conf:.0%} vs runner-up {runner:.0%}) -- ambiguous "
            f"split the oracle-free path cannot resolve; raise N or escalate")
    elif conf >= confidence_threshold:
        verdict, reason = CONSENSUS_PASS, (
            f"consensus majority (confidence {conf:.0%}, corr {corr:.0%}); "
            f"AGREEMENT not oracle-verified correctness -- verdict CONSENSUS_PASS, "
            f"not PASS; escalate if correctness is required")
    else:
        verdict, reason = "LOW_CONFIDENCE", (
            f"consensus confidence {conf:.0%} below {confidence_threshold:.0%} -- "
            f"raise N or escalate to an external oracle")

    # DEMOTE-ONLY workspace advisory: may only turn a CONSENSUS_PASS into
    # LOW_CONFIDENCE, never promote, never touch an oracle PASS. C2-safe.
    wc_dict = None
    if workspace_lens is not None and verdict == CONSENSUS_PASS:
        try:
            caution = workspace_lens.caution(candidates[idx], solution_sig=solution_sig, task=task)
        except Exception:
            caution = NO_CAUTION            # a broken lens must never break selection
        if getattr(caution, "demote", False):
            wc_dict = {"score": round(getattr(caution, "score", 0.0), 4),
                       "reason": getattr(caution, "reason", "")}
            verdict = "LOW_CONFIDENCE"
            reason = (f"workspace advisory demote (score {wc_dict['score']}): "
                      f"{wc_dict['reason']} -- was consensus {conf:.0%}; raise N / escalate")
    return SelectionResult(candidates[idx], SelectionReceipt(
        method="consensus", selected_index=idx, confidence=conf,
        runner_up_confidence=runner, candidates_used=len(candidates),
        candidate_hashes=hashes, battery_hash=batt_hash, correlation=corr,
        task_id=task_id, fn=fn, arity=arity, param_types=ptypes,
        probe_slot_timeout=SLOT_TIMEOUT, workspace_caution=wc_dict,
        verdict=verdict, reason=reason))


def verify_selection(receipt: SelectionReceipt, candidates: list[str], *,
                     solution_sig: str = "", task: Task | None = None,
                     oracle: Oracle | None = None) -> str:
    """Re-check a SelectionReceipt -- the check that can fail. Returns:
      UNVERIFIABLE  the supplied candidates do not match the committed hashes
      MATCH         re-running the selection picks the SAME index
      DRIFT         re-running picks a DIFFERENT index (env/oracle/battery moved)
    The oracle path needs the same oracle+task; the consensus path is
    reproduced from the committed (fn, arity, param_types) via solution_sig or
    the receipt's own fields. An oracle-method receipt MUST be re-checked with an
    oracle (and a consensus receipt without one); a verifier mismatch is
    UNVERIFIABLE, not a silent re-run down the wrong path."""
    if [_sha(_as_text(c)) for c in (candidates or [])] != receipt.candidate_hashes:
        return "UNVERIFIABLE"
    if receipt.method == "oracle" and oracle is None:
        return "UNVERIFIABLE"          # cannot re-check an oracle decision without an oracle
    if receipt.method == "consensus" and oracle is not None:
        return "UNVERIFIABLE"          # a consensus receipt must not be re-checked via oracle
    try:
        fresh = select(candidates, solution_sig=solution_sig, task=task, oracle=oracle)
    except Exception:
        return "UNVERIFIABLE"
    return "MATCH" if fresh.receipt.selected_index == receipt.selected_index else "DRIFT"
