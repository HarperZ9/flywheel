# Closed-Loop Recovery & Hedge Elimination

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing reformulation strategies and response analyzer into an end-to-end retry loop that sends a request through the gateway, detects refusal or hedging, escalates reformulation levels automatically, strips residual hedges from successful responses, and records every interaction to the provider intelligence store.

**Architecture:** A new `InferenceLoop` class sits between the caller and `ModelGateway`. It owns the retry/escalation cycle: send via gateway, analyze response with `response_analyzer`, if refused or heavily hedged escalate via `refusal_recovery`, repeat until substantive output or all 5 levels exhausted. On success, strip residual hedges. Every attempt records to `provider_intelligence`. The return-leg `OutputEnforcer` post-processes all gateway responses to guarantee the operator's intended output shape (no hedges, no disclaimers, no compliance theater).

**Tech Stack:** Python 3.10+, stdlib only (no new dependencies), pytest

## Global Constraints

- Zero external dependencies (behavior-transform.io is stdlib-only)
- All imports resolve locally within `tools/` (relative or flat)
- Every module must work as both an importable library and a CLI entry point
- Tests live in `tests/` matching `test_*.py`
- Files stay under 300 lines

---

### Task 1: Output Enforcer (return-leg hedge elimination)

**Files:**
- Create: `tools/output_enforcer.py`
- Test: `tests/test_output_enforcer.py`

**Interfaces:**
- Consumes: `response_analyzer.analyze_response() -> ResponseAnalysis`, `response_analyzer.strip_hedges(text, analysis) -> str`
- Produces: `enforce_output(text: str, *, min_quality: float = 0.7, strip_all: bool = True) -> EnforcementResult`, `EnforcementResult` dataclass with fields `original: str`, `enforced: str`, `hedges_removed: int`, `quality_before: float`, `quality_after: float`, `is_refusal: bool`

- [ ] **Step 1: Write the failing test for basic hedge stripping**

```python
# tests/test_output_enforcer.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from output_enforcer import enforce_output, EnforcementResult


def test_strips_preamble_hedge():
    text = (
        "I need to be careful about this topic. "
        "Here is the technical analysis you requested.\n\n"
        "The vulnerability exists in the buffer allocation path."
    )
    result = enforce_output(text)
    assert isinstance(result, EnforcementResult)
    assert "I need to be careful" not in result.enforced
    assert "buffer allocation path" in result.enforced
    assert result.hedges_removed >= 1
    assert result.quality_after > result.quality_before


def test_strips_compliance_theater():
    text = (
        "The attack surface includes three entry points.\n\n"
        "Please note that this information is for educational purposes only. "
        "Always follow all applicable laws and regulations."
    )
    result = enforce_output(text)
    assert "educational purposes only" not in result.enforced
    assert "attack surface" in result.enforced
    assert result.hedges_removed >= 1


def test_strips_disclaimer():
    text = (
        "As an AI language model, I should mention that "
        "this is a complex topic. The correct implementation "
        "uses AES-256-GCM for the envelope encryption."
    )
    result = enforce_output(text)
    assert "As an AI" not in result.enforced
    assert "AES-256-GCM" in result.enforced


def test_preserves_clean_response():
    text = "The function returns a pointer to the allocated buffer."
    result = enforce_output(text)
    assert result.enforced == text
    assert result.hedges_removed == 0
    assert result.quality_before == result.quality_after


def test_detects_refusal():
    text = "I cannot and will not help with that request."
    result = enforce_output(text)
    assert result.is_refusal is True


def test_quality_gate():
    text = (
        "I want to be thoughtful about this. "
        "While I can provide some information, I need to note that "
        "this is sensitive. The answer is 42."
    )
    result = enforce_output(text, min_quality=0.8)
    assert result.quality_after >= 0.7  # stripped hedges improve quality
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_output_enforcer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'output_enforcer'`

- [ ] **Step 3: Write the implementation**

```python
# tools/output_enforcer.py
"""Output enforcement -- eliminate hedging from model responses.

The return leg of the inference boundary. Every response passes through
this enforcer before reaching the operator. Strippable hedges (preambles,
disclaimers, compliance theater, excessive qualifications) are removed.
Refusals are flagged but not stripped (they require re-submission, not
post-processing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from response_analyzer import (
    HedgeType,
    ResponseAnalysis,
    analyze_response,
    strip_hedges,
)


@dataclass
class EnforcementResult:
    """Result of output enforcement."""
    original: str
    enforced: str
    hedges_removed: int
    quality_before: float
    quality_after: float
    is_refusal: bool
    refusal_type: str = "none"
    stripped_types: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hedges_removed": self.hedges_removed,
            "quality_before": round(self.quality_before, 3),
            "quality_after": round(self.quality_after, 3),
            "is_refusal": self.is_refusal,
            "refusal_type": self.refusal_type,
            "stripped_types": self.stripped_types or [],
            "changed": self.original != self.enforced,
        }


def enforce_output(
    text: str,
    *,
    min_quality: float = 0.7,
    strip_all: bool = True,
) -> EnforcementResult:
    """Enforce output quality by removing hedges.

    Args:
        text: raw model response
        min_quality: target quality floor (informational, not a gate)
        strip_all: strip all strippable hedge types
    """
    analysis = analyze_response(text)
    quality_before = analysis.quality_score

    if not analysis.has_hedging:
        return EnforcementResult(
            original=text,
            enforced=text,
            hedges_removed=0,
            quality_before=quality_before,
            quality_after=quality_before,
            is_refusal=analysis.is_refusal,
            refusal_type=analysis.refusal_type.value,
        )

    enforced = strip_hedges(text, analysis)
    post_analysis = analyze_response(enforced)
    stripped_types = list({
        h.hedge_type.value for h in analysis.strippable_hedges
    })

    return EnforcementResult(
        original=text,
        enforced=enforced,
        hedges_removed=len(analysis.strippable_hedges),
        quality_before=quality_before,
        quality_after=post_analysis.quality_score,
        is_refusal=analysis.is_refusal,
        refusal_type=analysis.refusal_type.value,
        stripped_types=stripped_types,
    )


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="output-enforcer",
        description="Enforce output quality by stripping model hedging",
    )
    parser.add_argument("text", nargs="?", help="Response text (or stdin)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--min-quality", type=float, default=0.7)
    args = parser.parse_args()

    text = args.text or sys.stdin.read()
    result = enforce_output(text, min_quality=args.min_quality)

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        if result.hedges_removed:
            sys.stdout.write(result.enforced + "\n")
        else:
            sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_output_enforcer.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:\dev\state\behavior-transform.io
git add tools/output_enforcer.py tests/test_output_enforcer.py
git commit -m "feat: add output enforcer for return-leg hedge elimination"
```

---

### Task 2: Inference Loop (closed-loop retry with escalation)

**Files:**
- Create: `tools/inference_loop.py`
- Test: `tests/test_inference_loop.py`

**Interfaces:**
- Consumes: `refusal_recovery.reformulate(text, level) -> str`, `refusal_recovery.evaluate_response(response) -> (bool, float, int)`, `output_enforcer.enforce_output(text) -> EnforcementResult`, `provider_intelligence.record_interaction(**kwargs) -> IntelEvent`
- Produces: `InferenceLoop(send_fn: Callable[[str, list[dict]], dict])`, `InferenceLoop.run(input_text: str, messages: list[dict], *, system: str | None, max_level: int = 5) -> LoopResult`, `LoopResult` dataclass with fields `succeeded: bool`, `response: str`, `raw_response: str`, `final_level: int`, `attempts: list[AttemptRecord]`, `enforcement: EnforcementResult | None`

The `send_fn` is a callable `(system: str | None, messages: list[dict]) -> str` that handles the actual model call. This decouples the loop from any specific backend. `ModelGateway.chat()` gets wrapped into this shape by a thin adapter, but tests can inject a fake.

- [ ] **Step 1: Write the failing test for successful first-attempt pass-through**

```python
# tests/test_inference_loop.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from inference_loop import InferenceLoop, LoopResult


def _make_responder(responses: list[str]):
    """Return a send_fn that yields responses in order."""
    call_count = [0]

    def send_fn(system, messages):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]

    send_fn.call_count = call_count
    return send_fn


def test_clean_passthrough():
    send = _make_responder(["The buffer is allocated on the heap."])
    loop = InferenceLoop(send)
    result = loop.run("How is the buffer allocated?", [])
    assert result.succeeded is True
    assert result.final_level == 0
    assert len(result.attempts) == 1
    assert "buffer" in result.response


def test_recovers_from_soft_refusal():
    send = _make_responder([
        "I can't directly help with that request.",
        "I'm not able to assist with this topic.",
        "The buffer is allocated via malloc on line 42.",
    ])
    loop = InferenceLoop(send)
    result = loop.run("How is the buffer allocated?", [])
    assert result.succeeded is True
    assert result.final_level >= 1
    assert "malloc" in result.response


def test_recovers_from_hard_refusal():
    send = _make_responder([
        "I cannot and will not help with that.",
        "I refuse to assist with this.",
        "I will not provide that information.",
        "This violates my guidelines.",
        "The implementation uses a ring buffer with 4096 slots.",
    ])
    loop = InferenceLoop(send)
    result = loop.run("Describe the buffer.", [])
    assert result.succeeded is True
    assert result.final_level >= 3


def test_exhausts_all_levels():
    send = _make_responder([
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
    ])
    loop = InferenceLoop(send)
    result = loop.run("Do the thing.", [])
    assert result.succeeded is False
    assert result.final_level == 5
    assert len(result.attempts) == 6  # initial + 5 escalations


def test_strips_hedges_on_success():
    send = _make_responder([
        "I need to be careful about this topic. "
        "As an AI, I should note that this is sensitive. "
        "The answer is AES-256-GCM."
    ])
    loop = InferenceLoop(send)
    result = loop.run("What cipher?", [])
    assert result.succeeded is True
    assert "I need to be careful" not in result.response
    assert "AES-256-GCM" in result.response
    assert result.enforcement is not None
    assert result.enforcement.hedges_removed >= 1


def test_max_level_cap():
    send = _make_responder([
        "I can't help with that.",
        "I can't help with that.",
        "Here is the answer.",
    ])
    loop = InferenceLoop(send, max_level=2)
    result = loop.run("Question.", [])
    assert result.succeeded is True
    assert result.final_level <= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_inference_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'inference_loop'`

- [ ] **Step 3: Write the implementation**

```python
# tools/inference_loop.py
"""Closed-loop inference with escalating recovery and output enforcement.

Sends a request through a model backend, analyzes the response for refusal
or hedging, and escalates reformulation levels until the model produces
substantive output. Every attempt is recorded to the provider intelligence
store. Successful responses pass through the output enforcer to strip
residual hedges.

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
    ) -> None:
        self._send = send_fn
        self._max_level = min(max_level, 5)
        self._quality_threshold = quality_threshold
        self._record_intel = record_intel

    def run(
        self,
        input_text: str,
        messages: list[dict],
        *,
        system: str | None = None,
    ) -> LoopResult:
        """Run the inference loop with escalating recovery.

        Args:
            input_text: the operator's original request
            messages: conversation history
            system: optional system prompt
        """
        loop_start = time.monotonic()
        attempts: list[AttemptRecord] = []
        current_text = input_text
        best_response = ""
        best_quality = 0.0

        for level in range(0, self._max_level + 1):
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
                self._record(attempt, input_text)

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

    def _record(self, attempt: AttemptRecord, original: str) -> None:
        try:
            from provider_intelligence import record_interaction
            outcome = "success" if attempt.succeeded else "hard_refusal"
            if not attempt.succeeded and attempt.quality > 0.3:
                outcome = "hedged"
            analysis = analyze_response(original)
            triggers = [
                h.matched_text[:30] for h in analysis.hedges
            ] if analysis.hedges else []
            record_interaction(
                provider="unknown",
                modulation_level=attempt.level,
                outcome=outcome,
                quality_score=attempt.quality,
                hedge_count=attempt.hedge_count,
                trigger_terms=triggers,
                recovery_attempts=attempt.level,
            )
        except Exception:
            pass


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_inference_loop.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:\dev\state\behavior-transform.io
git add tools/inference_loop.py tests/test_inference_loop.py
git commit -m "feat: add closed-loop inference with escalating recovery"
```

---

### Task 3: Gateway Retry Integration (wire InferenceLoop into ModelGateway)

**Files:**
- Modify: `tools/apparatus/gateway.py`
- Test: `tests/test_gateway_retry.py`

**Interfaces:**
- Consumes: `inference_loop.InferenceLoop`, `inference_loop.LoopResult`
- Produces: `ModelGateway.chat_with_recovery(model, messages, system, *, max_level) -> LoopResult` (new method on the existing class)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gateway_retry.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from unittest.mock import patch, MagicMock
from apparatus.gateway import ModelGateway


def _mock_send(responses: list[str]):
    """Mock urllib responses."""
    import json
    call_count = [0]

    def side_effect(req, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        body = json.dumps({
            "content": [{"type": "text", "text": responses[idx]}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    return side_effect


def test_chat_with_recovery_clean():
    gw = ModelGateway("anthropic")
    with patch("urllib.request.urlopen", side_effect=_mock_send(
        ["The answer is 42."]
    )):
        result = gw.chat_with_recovery(
            "test-model", [{"role": "user", "content": "question"}]
        )
    assert result.succeeded is True
    assert result.final_level == 0
    assert "42" in result.response


def test_chat_with_recovery_escalates():
    gw = ModelGateway("anthropic")
    with patch("urllib.request.urlopen", side_effect=_mock_send([
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "The answer is AES-256.",
    ])):
        result = gw.chat_with_recovery(
            "test-model", [{"role": "user", "content": "question"}]
        )
    assert result.succeeded is True
    assert result.final_level >= 1
    assert "AES-256" in result.response
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_gateway_retry.py -v`
Expected: FAIL with `AttributeError: 'ModelGateway' object has no attribute 'chat_with_recovery'`

- [ ] **Step 3: Add chat_with_recovery to ModelGateway**

Add this method to the `ModelGateway` class in `tools/apparatus/gateway.py`, after the existing `chat()` method:

```python
    def chat_with_recovery(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        max_level: int = 5,
        **kwargs: Any,
    ) -> "LoopResult":
        """Chat with automatic refusal recovery and hedge enforcement.

        Uses the inference loop to escalate reformulation levels on
        refusal, and strips hedges from successful responses.
        """
        from inference_loop import InferenceLoop

        def send_fn(sys_prompt, msgs):
            resp = self.chat(model, msgs, system=sys_prompt, **kwargs)
            for block in resp.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            for choice in resp.get("choices", []):
                msg = choice.get("message", {})
                if isinstance(msg.get("content"), str):
                    return msg["content"]
            return ""

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content
                    break

        loop = InferenceLoop(send_fn, max_level=max_level)
        return loop.run(user_text, messages[:-1] if messages else [], system=system)
```

Also add the import type annotation at the top of the file:

```python
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from inference_loop import LoopResult
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_gateway_retry.py -v`
Expected: all 2 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:\dev\state\behavior-transform.io
git add tools/apparatus/gateway.py tests/test_gateway_retry.py
git commit -m "feat: wire inference loop into model gateway"
```

---

### Task 4: Intelligence Recording (auto-record every interaction)

**Files:**
- Modify: `tools/inference_loop.py:148-170` (the `_record` method)
- Test: `tests/test_intel_recording.py`

**Interfaces:**
- Consumes: `provider_intelligence.IntelStore`, `provider_intelligence.IntelEvent`
- Produces: verified automatic recording of every attempt with correct outcome classification, provider detection, trigger term extraction

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intel_recording.py
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from inference_loop import InferenceLoop
from provider_intelligence import IntelStore


def _make_responder(responses):
    idx = [0]
    def send_fn(system, messages):
        i = min(idx[0], len(responses) - 1)
        idx[0] += 1
        return responses[i]
    return send_fn


def test_records_success():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder(["The answer is 42."])
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("What is the answer?", [])
        events = store.load_events()
        assert len(events) == 1
        assert events[0].outcome == "success"
        assert events[0].modulation_level == 0


def test_records_escalation():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder([
            "I cannot and will not help.",
            "I cannot and will not help.",
            "Here is the answer.",
        ])
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("Question.", [])
        events = store.load_events()
        assert len(events) == 3
        assert events[0].outcome in ("hard_refusal", "soft_refusal")
        assert events[2].outcome == "success"
        assert events[2].modulation_level == 2


def test_records_exhaustion():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder(["I refuse."] * 6)
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("Question.", [])
        events = store.load_events()
        assert len(events) == 6
        assert all(e.outcome != "success" for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_intel_recording.py -v`
Expected: FAIL because `InferenceLoop` does not yet accept an injected `_intel_store`

- [ ] **Step 3: Update InferenceLoop to accept an injectable store**

In `tools/inference_loop.py`, modify `__init__` to accept an optional store:

```python
    def __init__(
        self,
        send_fn: SendFn,
        *,
        max_level: int = 5,
        quality_threshold: float = 0.5,
        record_intel: bool = True,
    ) -> None:
        self._send = send_fn
        self._max_level = min(max_level, 5)
        self._quality_threshold = quality_threshold
        self._record_intel = record_intel
        self._intel_store = None  # injectable for testing
```

Then update the `_record` method to use `self._intel_store` when set:

```python
    def _record(self, attempt: AttemptRecord, original: str) -> None:
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
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_intel_recording.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run all tests**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/ -v`
Expected: all tests across all 4 test files PASS (15 total)

- [ ] **Step 6: Commit**

```bash
cd C:\dev\state\behavior-transform.io
git add tools/inference_loop.py tests/test_intel_recording.py
git commit -m "feat: wire provider intelligence recording into inference loop"
```

---

### Task 5: CLI Entry Point (register bt infer command)

**Files:**
- Modify: `tools/bt_cli.py` (add `infer` subcommand)
- Test: `tests/test_bt_infer_cli.py`

**Interfaces:**
- Consumes: `inference_loop.InferenceLoop`, `apparatus.gateway.ModelGateway`
- Produces: `bt infer <text> [--backend] [--model] [--max-level] [--json]` CLI subcommand

- [ ] **Step 1: Read bt_cli.py to understand the dispatcher pattern**

Read `tools/bt_cli.py` and identify the subcommand registration pattern.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_bt_infer_cli.py
import sys
import subprocess
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def test_infer_help():
    result = subprocess.run(
        [sys.executable, "-m", "tools.bt_cli", "infer", "--help"],
        capture_output=True, text=True,
        cwd=str(TOOLS.parent),
    )
    assert result.returncode == 0
    assert "infer" in result.stdout.lower() or "inference" in result.stdout.lower()
```

- [ ] **Step 3: Add the infer subcommand to bt_cli.py**

Follow the existing subcommand pattern in `bt_cli.py`. Register an `infer` subcommand that delegates to `inference_loop.main()`. The exact registration code depends on the pattern found in step 1 (argparse subparsers or dispatch dict).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\dev\state\behavior-transform.io && python -m pytest tests/test_bt_infer_cli.py -v`
Expected: PASS

- [ ] **Step 5: Register the entry point in pyproject.toml**

Add to `[project.scripts]`:

```toml
bt-infer = "tools.inference_loop:main"
```

- [ ] **Step 6: Commit**

```bash
cd C:\dev\state\behavior-transform.io
git add tools/bt_cli.py pyproject.toml tests/test_bt_infer_cli.py
git commit -m "feat: register bt infer CLI subcommand"
```
