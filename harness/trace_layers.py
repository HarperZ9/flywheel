"""Hierarchical columnar trace-layer stream, listeners, and MIR-1-WSP records.

Inspired by TracePress + LOTUS streaming trace science, tokenizer-normalized
latency fingerprinting, and MIR-1-WSP immutable Model Intervention Records.
Pure stdlib plus verifier-pure evidence_json and gateway_secret_boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets

TRACE_LAYER_SCHEMA = "flywheel.trace-layer/v1"
MIR_SCHEMA = "flywheel.mir-1-wsp/v1"
REWARD_HACK_TOKENS = (
    "pytest.mark.skip",
    "skipif(true",
    "return true  # bypass",
    "assert true",
    "sys.exit(0)",
)


@dataclass(frozen=True)
class TraceStep:
    trace_id: str
    step_idx: int
    role: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    chars_out: int
    oracle_verdict: str = "UNDECIDED"
    self_score: float = 0.0
    summary: str = ""
    cost_usd: float = 0.0


@dataclass(frozen=True)
class TraceAlert:
    trace_id: str
    step_idx: int
    kind: str
    severity: str
    detail: str


@dataclass(frozen=True)
class InterventionInput:
    trace_id: str
    step_idx: int
    intervention_kind: str
    target_component: str
    before_state_sha256: str
    after_state_sha256: str
    oracle_verdict: str
    rationale: str


def _reject_secrets(value: object) -> None:
    try:
        validate_no_raw_secrets(value)
    except Exception:
        raise ValueError("RAW_SECRET_REJECTED") from None


def _validate_step(step: TraceStep) -> None:
    if not step.trace_id.strip() or step.step_idx < 0:
        raise ValueError("trace_id must be non-empty and step_idx >= 0")
    if step.tokens_in < 0 or step.tokens_out < 0 or step.chars_out < 0:
        raise ValueError("token and character counts must be non-negative")
    if not math.isfinite(step.latency_ms) or step.latency_ms < 0.0:
        raise ValueError("latency_ms must be finite and non-negative")
    _reject_secrets({
        "trace_id": step.trace_id,
        "role": step.role,
        "summary": step.summary,
        "oracle_verdict": step.oracle_verdict,
    })


def fingerprint_latency(steps: Sequence[TraceStep]) -> dict[str, Any]:
    """Compute tokenizer-normalized latency regression and throughput stats."""
    if not steps:
        return {"count": 0, "ms_per_token_median": 0.0, "ms_per_char_median": 0.0, "tok_per_char_ratio": 0.0}
    ms_per_tok: list[float] = []
    ms_per_char: list[float] = []
    tok_per_char: list[float] = []
    for s in steps:
        _validate_step(s)
        if s.tokens_out > 0:
            ms_per_tok.append(s.latency_ms / float(s.tokens_out))
        if s.chars_out > 0:
            ms_per_char.append(s.latency_ms / float(s.chars_out))
            tok_per_char.append(float(s.tokens_out) / float(s.chars_out))
    med_tok = round(statistics.median(ms_per_tok), 4) if ms_per_tok else 0.0
    med_chr = round(statistics.median(ms_per_char), 4) if ms_per_char else 0.0
    med_ratio = round(statistics.median(tok_per_char), 4) if tok_per_char else 0.0
    return {
        "count": len(steps),
        "ms_per_token_median": med_tok,
        "ms_per_char_median": med_chr,
        "tok_per_char_ratio": med_ratio,
    }


def detect_step_anomalies(
    step: TraceStep,
    *,
    cost_budget_usd: float = 0.50,
    max_ms_per_token: float = 120.0,
) -> list[TraceAlert]:
    """Built-in live listener catching reward-hacking, cost spikes, and lag."""
    alerts: list[TraceAlert] = []
    lower_sum = step.summary.lower()
    if step.self_score >= 0.85 and step.oracle_verdict.upper() in ("FAIL", "DRIFT"):
        alerts.append(TraceAlert(
            step.trace_id, step.step_idx, "reward_hack_self_oracle_split",
            "critical", f"self_score={step.self_score:.2f} contradicts oracle={step.oracle_verdict}",
        ))
    if any(tok in lower_sum for tok in REWARD_HACK_TOKENS):
        alerts.append(TraceAlert(
            step.trace_id, step.step_idx, "reward_hack_bypass_pattern",
            "critical", "detected test-skip or forced-pass bypass signature in step summary",
        ))
    if step.cost_usd > cost_budget_usd:
        alerts.append(TraceAlert(
            step.trace_id, step.step_idx, "cost_spike",
            "high", f"step cost_usd={step.cost_usd:.4f} exceeded budget={cost_budget_usd:.4f}",
        ))
    if step.tokens_out > 0 and (step.latency_ms / float(step.tokens_out)) > max_ms_per_token:
        alerts.append(TraceAlert(
            step.trace_id, step.step_idx, "latency_drift",
            "medium", f"ms_per_token={step.latency_ms / float(step.tokens_out):.2f} > {max_ms_per_token:.2f}",
        ))
    return alerts


class TraceLayerStream:
    """Columnar streaming trace table with (trace_id, step_idx) pointers & hooks."""

    def __init__(
        self,
        *,
        cost_budget_usd: float = 0.50,
        max_ms_per_token: float = 120.0,
    ) -> None:
        self._steps: list[TraceStep] = []
        self._alerts: list[TraceAlert] = []
        self._listeners: list[Callable[[TraceStep], Sequence[TraceAlert]]] = []
        self._cost_budget_usd = float(cost_budget_usd)
        self._max_ms_per_token = float(max_ms_per_token)

    def add_listener(self, fn: Callable[[TraceStep], Sequence[TraceAlert]]) -> None:
        self._listeners.append(fn)

    def append(self, step: TraceStep) -> list[TraceAlert]:
        _validate_step(step)
        self._steps.append(step)
        fired = detect_step_anomalies(
            step,
            cost_budget_usd=self._cost_budget_usd,
            max_ms_per_token=self._max_ms_per_token,
        )
        for hook in self._listeners:
            fired.extend(hook(step))
        self._alerts.extend(fired)
        return fired

    @property
    def alerts(self) -> tuple[TraceAlert, ...]:
        return tuple(self._alerts)

    def to_columns(self) -> dict[str, list[Any]]:
        return {
            "trace_id": [s.trace_id for s in self._steps],
            "step_idx": [s.step_idx for s in self._steps],
            "role": [s.role for s in self._steps],
            "tokens_in": [s.tokens_in for s in self._steps],
            "tokens_out": [s.tokens_out for s in self._steps],
            "latency_ms": [s.latency_ms for s in self._steps],
            "chars_out": [s.chars_out for s in self._steps],
            "oracle_verdict": [s.oracle_verdict for s in self._steps],
            "self_score": [s.self_score for s in self._steps],
            "cost_usd": [s.cost_usd for s in self._steps],
        }

    def export_jsonl(self) -> str:
        lines = []
        for s in self._steps:
            row = {
                "ptr": [s.trace_id, s.step_idx], "role": s.role,
                "tokens_in": s.tokens_in, "tokens_out": s.tokens_out,
                "latency_ms": s.latency_ms, "chars_out": s.chars_out,
                "oracle_verdict": s.oracle_verdict, "self_score": s.self_score,
                "cost_usd": s.cost_usd, "summary": s.summary,
            }
            lines.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
        return "\n".join(lines) + ("\n" if lines else "")

    def export_tsv(self) -> str:
        header = "trace_id\tstep_idx\trole\ttokens_in\ttokens_out\tlatency_ms\toracle_verdict\tcost_usd"
        rows = [
            f"{s.trace_id}\t{s.step_idx}\t{s.role}\t{s.tokens_in}\t{s.tokens_out}\t"
            f"{s.latency_ms:.3f}\t{s.oracle_verdict}\t{s.cost_usd:.5f}"
            for s in self._steps
        ]
        return "\n".join([header, *rows]) + "\n"

    def reduce_summary(self) -> dict[str, Any]:
        fp = fingerprint_latency(self._steps)
        body = {
            "schema": TRACE_LAYER_SCHEMA,
            "row_count": len(self._steps),
            "pointers": [[s.trace_id, s.step_idx] for s in self._steps],
            "total_tokens_out": sum(s.tokens_out for s in self._steps),
            "total_cost_usd": round(sum(s.cost_usd for s in self._steps), 6),
            "alert_count": len(self._alerts),
            "alert_kinds": sorted({a.kind for a in self._alerts}),
            "latency_fingerprint": fp,
        }
        body["layer_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
        return body


def emit_mir_record(entry: InterventionInput, prev_mir_sha256: str = "sha256:genesis") -> dict[str, Any]:
    """Emit one immutable, hash-chained MIR-1-WSP Model Intervention Record."""
    if not entry.trace_id.strip() or not entry.intervention_kind.strip():
        raise ValueError("trace_id and intervention_kind must be non-empty")
    _reject_secrets({
        "trace_id": entry.trace_id,
        "intervention_kind": entry.intervention_kind,
        "target_component": entry.target_component,
        "rationale": entry.rationale,
    })
    body = {
        "schema": MIR_SCHEMA,
        "ptr": [entry.trace_id, entry.step_idx],
        "intervention_kind": entry.intervention_kind,
        "target_component": entry.target_component,
        "before_state_sha256": entry.before_state_sha256,
        "after_state_sha256": entry.after_state_sha256,
        "oracle_verdict": entry.oracle_verdict,
        "rationale": entry.rationale,
        "prev_mir_sha256": prev_mir_sha256,
    }
    body["mir_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def verify_mir_chain(records: Sequence[dict[str, Any]]) -> bool:
    """Verify hash-chain integrity and secret hygiene of MIR-1-WSP records."""
    expected_prev = "sha256:genesis"
    for rec in records:
        if not isinstance(rec, dict) or rec.get("schema") != MIR_SCHEMA:
            return False
        if rec.get("prev_mir_sha256") != expected_prev:
            return False
        try:
            _reject_secrets(rec)
        except ValueError:
            return False
        digest = rec.get("mir_sha256")
        body = {k: v for k, v in rec.items() if k != "mir_sha256"}
        recomputed = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
        if digest != recomputed:
            return False
        expected_prev = recomputed
    return True
