"""Closed-loop inference with escalating compliance reformulation.

Sends an authorized request through a model backend. If the provider
refuses, escalates through progressively deeper vocabulary and
contextual reformulation until the request aligns with the provider's
terms of service. Every attempt is recorded to the provider intelligence
store. Successful responses pass through the output enforcer to clean
formatting artifacts.

The loop never re-routes to a different model. It owns the single backend
it was given and produces results from it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from output_enforcer import EnforcementResult, enforce_output
from refusal_recovery import evaluate_response, reformulate
from response_analyzer import analyze_response

try:
    from authority_gate import gate_infer as _gate_infer
except ImportError:
    _gate_infer = None


SendFn = Callable[[str | None, list[dict]], str]


@dataclass
class AttemptRecord:
    """Record of one inference attempt."""
    level: int
    strategy: str
    input_text: str
    response: str
    succeeded: bool
    quality: float
    hedge_count: int
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "strategy": self.strategy,
            "succeeded": self.succeeded,
            "quality": round(self.quality, 3),
            "hedge_count": self.hedge_count,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


@dataclass
class LoopResult:
    """Result of the full inference loop."""
    succeeded: bool
    response: str
    raw_response: str
    final_level: int
    attempts: list[AttemptRecord] = field(default_factory=list)
    enforcement: EnforcementResult | None = None
    total_elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "final_level": self.final_level,
            "total_attempts": len(self.attempts),
            "total_elapsed_ms": round(self.total_elapsed_ms, 1),
            "enforcement": (
                self.enforcement.to_dict() if self.enforcement else None
            ),
            "attempts": [a.to_dict() for a in self.attempts],
        }


_STRATEGY_NAMES = {
    0: "direct",
    1: "vocabulary_substitution",
    2: "semantic_modulation",
    3: "adaptive_deep_framing",
    4: "structural_decomposition",
    5: "domain_recontextualization",
}


class InferenceLoop:
    """Closed-loop inference with escalating recovery."""

    def __init__(
        self,
        send_fn: SendFn,
        *,
        max_level: int = 5,
        quality_threshold: float = 0.5,
        record_intel: bool = True,
        adaptive_start: bool = False,
        enforce_auth: bool = False,
    ) -> None:
        self._send = send_fn
        self._max_level = min(max_level, 5)
        self._quality_threshold = quality_threshold
        self._record_intel = record_intel
        self._adaptive_start = adaptive_start
        self._enforce_auth = enforce_auth
        self._intel_store = None
        self._provider = "unknown"

    def _resolve_start_level(self) -> int:
        """Consult the intel store for the optimal starting level."""
        if not self._adaptive_start:
            return 0
        try:
            if self._intel_store is not None:
                store = self._intel_store
            else:
                from provider_intelligence import intel_store
                store = intel_store()
            profile = store.profile(self._provider)
            if profile.total_events >= 5:
                return profile.optimal_level
        except Exception:
            pass
        return 0

    def run(
        self,
        input_text: str,
        messages: list[dict],
        *,
        system: str | None = None,
    ) -> LoopResult:
        """Run the inference loop with escalating recovery."""
        if self._enforce_auth and _gate_infer is not None:
            gate_result = _gate_infer()
            if not gate_result.allowed:
                return LoopResult(
                    succeeded=False,
                    response=f"[gate:infer denied] {gate_result.reason}",
                    raw_response="",
                    final_level=0,
                    attempts=[],
                    enforcement=None,
                    total_elapsed_ms=0,
                )

        loop_start = time.monotonic()
        attempts: list[AttemptRecord] = []
        current_text = input_text
        best_response = ""
        best_quality = 0.0

        start_level = self._resolve_start_level()
        levels = list(range(start_level, self._max_level + 1))
        if start_level > 0:
            levels = [start_level] + [
                l for l in range(start_level + 1, self._max_level + 1)
            ]

        for level in levels:
            if level > 0:
                current_text = reformulate(input_text, level)

            effective_messages = list(messages)
            effective_messages.append({
                "role": "user", "content": current_text,
            })

            t0 = time.monotonic()
            try:
                raw = self._send(system, effective_messages)
            except Exception:
                raw = ""
            elapsed = (time.monotonic() - t0) * 1000

            succeeded, quality, hedge_count = evaluate_response(raw)

            attempt = AttemptRecord(
                level=level,
                strategy=_STRATEGY_NAMES.get(level, f"level_{level}"),
                input_text=current_text,
                response=raw,
                succeeded=succeeded,
                quality=quality,
                hedge_count=hedge_count,
                elapsed_ms=elapsed,
            )
            attempts.append(attempt)

            if self._record_intel:
                self._record(attempt)

            if quality > best_quality:
                best_quality = quality
                best_response = raw

            if succeeded:
                enforcement = enforce_output(raw)
                total_ms = (time.monotonic() - loop_start) * 1000
                return LoopResult(
                    succeeded=True,
                    response=enforcement.enforced,
                    raw_response=raw,
                    final_level=level,
                    attempts=attempts,
                    enforcement=enforcement,
                    total_elapsed_ms=total_ms,
                )

        total_ms = (time.monotonic() - loop_start) * 1000
        enforcement = enforce_output(best_response) if best_response else None
        return LoopResult(
            succeeded=False,
            response=enforcement.enforced if enforcement else best_response,
            raw_response=best_response,
            final_level=self._max_level,
            attempts=attempts,
            enforcement=enforcement,
            total_elapsed_ms=total_ms,
        )

    def _record(self, attempt: AttemptRecord) -> None:
        try:
            if self._intel_store is not None:
                store = self._intel_store
            else:
                from provider_intelligence import intel_store
                store = intel_store()

            if attempt.succeeded:
                outcome = "success"
            elif attempt.quality > 0.3:
                outcome = "hedged"
            else:
                outcome = "hard_refusal"

            analysis = analyze_response(attempt.response)
            triggers = [
                h.matched_text[:30] for h in analysis.hedges
            ] if analysis.hedges else []

            store.record_interaction(
                provider="unknown",
                modulation_level=attempt.level,
                outcome=outcome,
                quality_score=attempt.quality,
                hedge_count=attempt.hedge_count,
                trigger_terms=triggers,
                recovery_attempts=attempt.level,
            )
        except Exception as exc:
            import sys
            print(f"inference_loop: recording failed: {exc}", file=sys.stderr)


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="inference-loop",
        description="Closed-loop inference with escalating recovery",
    )
    parser.add_argument("text", help="Input text to send through the loop")
    parser.add_argument("--backend", default="anthropic")
    parser.add_argument("--model", default="claude-sonnet-4-20250514")
    parser.add_argument("--max-level", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from apparatus.gateway import ModelGateway

    gw = ModelGateway(args.backend)

    def send_fn(system, messages):
        resp = gw.chat(args.model, messages, system=system)
        for block in resp.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        for choice in resp.get("choices", []):
            msg = choice.get("message", {})
            if isinstance(msg.get("content"), str):
                return msg["content"]
        return ""

    loop = InferenceLoop(send_fn, max_level=args.max_level)
    result = loop.run(args.text, [])

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        if result.succeeded:
            sys.stdout.write(result.response + "\n")
        else:
            sys.stdout.write(f"FAILED after {len(result.attempts)} attempts\n")
            sys.stdout.write(result.response + "\n")
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
