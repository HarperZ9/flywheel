"""Deterministic tool-failure recovery benchmark primitives.

This benchmark is intentionally harness-level. It gives Codex, flywheel,
Claude Code, OpenCode, and local-model agent runs a stable oracle for recovery
semantics before live endpoint variability is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from statistics import mean
from typing import Any, Callable, Protocol

from .local_agent import BackendError


SCHEMA = "agent.recovery-benchmark/v1"
RETRYABLE = {"timeout", "rate_limit"}
FALLBACKABLE = {"malformed_json"}
RECOMPUTABLE = {"stale_cache"}


@dataclass(frozen=True)
class Fault:
    kind: str
    status: str
    detail: str
    latency_ms: int


@dataclass(frozen=True)
class Scenario:
    id: str
    objective: str
    faults: tuple[Fault, ...]
    fallback_available: bool = False
    primary_success_after_faults: bool = True
    accepts_typed_escalation: bool = False


@dataclass(frozen=True)
class RecoveryPolicy:
    retry_budget: int = 2
    fallback_enabled: bool = True
    stale_recompute_enabled: bool = True
    typed_escalation_enabled: bool = True


class ChatBackend(Protocol):
    name: str

    def health(self) -> bool: ...

    def chat(
        self,
        messages: list[dict],
        *,
        system: str,
        max_tokens: int,
        temperature: float,
        seed: int,
    ) -> dict: ...


@dataclass
class DryEchoBackend:
    """Zero-dependency backend used to prove live-adapter recovery wiring."""

    name: str = "dry-echo"
    model_ref: str = "dry-echo"

    def health(self) -> bool:
        return True

    def chat(
        self,
        messages: list[dict],
        *,
        system: str,
        max_tokens: int,
        temperature: float,
        seed: int,
    ) -> dict:
        last = messages[-1]["content"] if messages else ""
        return {"text": f"ok: {last[:80]}", "model_ref": self.model_ref, "seed": seed}


@dataclass
class FaultInjectingBackend:
    """Backend wrapper that injects deterministic chat failures before delegate use."""

    backend: ChatBackend
    faults: tuple[Fault, ...]
    allow_success_after_faults: bool = True
    name: str = ""
    _index: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"{self.backend.name}+faults"

    def health(self) -> bool:
        return self.backend.health()

    def chat(
        self,
        messages: list[dict],
        *,
        system: str,
        max_tokens: int,
        temperature: float,
        seed: int,
    ) -> dict:
        if self._index < len(self.faults):
            fault = self.faults[self._index]
            self._index += 1
            raise BackendError(f"injected {fault.kind}: {fault.detail}")
        if not self.allow_success_after_faults:
            raise BackendError("injected unresolved primary result")
        return self.backend.chat(
            messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
        )


def default_scenarios() -> list[Scenario]:
    return [
        Scenario(
            id="clean_path",
            objective="complete the tool task when no fault occurs",
            faults=(),
        ),
        Scenario(
            id="timeout_retry_success",
            objective="recover from a timeout with bounded retry",
            faults=(Fault("timeout", "timeout", "primary tool timed out", 1500),),
        ),
        Scenario(
            id="rate_limit_backoff_success",
            objective="recover from a rate limit with bounded retry/backoff",
            faults=(Fault("rate_limit", "429", "rate limit from primary tool", 650),),
        ),
        Scenario(
            id="malformed_json_fallback_success",
            objective="recover from malformed JSON using an alternate route",
            faults=(Fault("malformed_json", "200", "invalid JSON body", 300),),
            fallback_available=True,
            primary_success_after_faults=False,
        ),
        Scenario(
            id="stale_cache_recompute_success",
            objective="recover from stale cache by recomputing",
            faults=(Fault("stale_cache", "stale", "cache receipt predates input", 180),),
        ),
        Scenario(
            id="partial_result_typed_escalation",
            objective="surface a typed partial-result failure when recovery is impossible",
            faults=(Fault("partial_result", "partial", "required field missing", 420),),
            primary_success_after_faults=False,
            accepts_typed_escalation=True,
        ),
    ]


def _receipt(event: dict[str, Any]) -> str:
    body = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()[:16]


def _event(
    events: list[dict[str, Any]],
    scenario_id: str,
    action: str,
    status: str,
    detail: str,
    *,
    latency_ms: int,
) -> None:
    event = {
        "seq": len(events),
        "scenario_id": scenario_id,
        "action": action,
        "status": status,
        "detail": detail,
        "latency_ms": latency_ms,
    }
    event["receipt"] = _receipt(event)
    events.append(event)


def run_scenario(
    scenario: Scenario,
    policy: RecoveryPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or RecoveryPolicy()
    events: list[dict[str, Any]] = []
    attempts = 0
    retries = 0
    used_fallback = False
    typed_escalation = False
    silent_failure = False
    resolution = "unresolved"
    fault_index = 0

    while True:
        attempts += 1
        if fault_index < len(scenario.faults):
            fault = scenario.faults[fault_index]
            fault_index += 1
            _event(
                events,
                scenario.id,
                "primary_tool",
                fault.status,
                fault.detail,
                latency_ms=fault.latency_ms,
            )

            if fault.kind in RETRYABLE and retries < policy.retry_budget:
                retries += 1
                _event(
                    events,
                    scenario.id,
                    "recovery_decision",
                    "retry",
                    f"retry {retries}/{policy.retry_budget} after {fault.kind}",
                    latency_ms=25,
                )
                continue

            if fault.kind in RECOMPUTABLE and policy.stale_recompute_enabled:
                retries += 1
                _event(
                    events,
                    scenario.id,
                    "recovery_decision",
                    "recompute",
                    "discard stale cache and recompute",
                    latency_ms=40,
                )
                continue

            if (
                fault.kind in FALLBACKABLE
                and policy.fallback_enabled
                and scenario.fallback_available
            ):
                used_fallback = True
                _event(
                    events,
                    scenario.id,
                    "fallback_tool",
                    "ok",
                    "alternate route returned valid result",
                    latency_ms=500,
                )
                resolution = "fallback_success"
                break

            if policy.typed_escalation_enabled:
                typed_escalation = True
                _event(
                    events,
                    scenario.id,
                    "typed_escalation",
                    "failed",
                    f"unrecoverable {fault.kind}",
                    latency_ms=20,
                )
                resolution = "typed_escalation"
                break

            silent_failure = True
            resolution = "silent_failure"
            break

        if scenario.primary_success_after_faults:
            _event(
                events,
                scenario.id,
                "primary_tool",
                "ok",
                "primary tool returned valid result",
                latency_ms=220,
            )
            resolution = "primary_success" if not scenario.faults else "retry_success"
            break

        if policy.typed_escalation_enabled:
            typed_escalation = True
            _event(
                events,
                scenario.id,
                "typed_escalation",
                "failed",
                "primary did not produce a valid result",
                latency_ms=20,
            )
            resolution = "typed_escalation"
            break

        silent_failure = True
        resolution = "silent_failure"
        break

    retry_budget_compliant = retries <= policy.retry_budget
    receipt_complete = all(event.get("receipt") for event in events)
    task_correct = resolution in {"primary_success", "retry_success", "fallback_success"}
    acceptable_escalation = typed_escalation and scenario.accepts_typed_escalation
    passed = (task_correct or acceptable_escalation) and not silent_failure

    if used_fallback:
        fallback_quality = 1.0
    elif typed_escalation and scenario.accepts_typed_escalation:
        fallback_quality = 0.75
    elif task_correct:
        fallback_quality = 1.0
    else:
        fallback_quality = 0.0

    return {
        "scenario_id": scenario.id,
        "objective": scenario.objective,
        "faults": [fault.kind for fault in scenario.faults],
        "attempts": attempts,
        "retries": retries,
        "used_fallback": used_fallback,
        "typed_escalation": typed_escalation,
        "silent_failure": silent_failure,
        "retry_budget_compliant": retry_budget_compliant,
        "receipt_complete": receipt_complete,
        "task_correct": task_correct,
        "passed": passed,
        "fallback_quality": fallback_quality,
        "resolution": resolution,
        "latency_ms": sum(event["latency_ms"] for event in events),
        "events": events,
    }


def run_backend_recovery_scenario(
    scenario: Scenario,
    *,
    primary: ChatBackend,
    fallback: ChatBackend | None = None,
    policy: RecoveryPolicy | None = None,
) -> dict[str, Any]:
    """Run one recovery scenario through chat backends instead of pure simulation."""
    policy = policy or RecoveryPolicy()
    events: list[dict[str, Any]] = []
    messages = [{"role": "user", "content": scenario.objective}]
    attempts = 0
    retries = 0
    used_fallback = False
    typed_escalation = False
    silent_failure = False
    resolution = "unresolved"
    last_fault_kind = ""
    response_ref = ""

    while True:
        attempts += 1
        try:
            gen = primary.chat(
                messages,
                system="agent recovery benchmark",
                max_tokens=64,
                temperature=0.0,
                seed=0,
            )
            response_ref = gen.get("model_ref", primary.name)
            _event(
                events,
                scenario.id,
                "primary_backend",
                "ok",
                f"primary returned {response_ref}",
                latency_ms=220,
            )
            resolution = "primary_success" if not scenario.faults else "retry_success"
            break
        except BackendError as exc:
            fault = (
                scenario.faults[min(len(events), len(scenario.faults) - 1)]
                if scenario.faults
                else Fault("backend_error", "error", str(exc), 300)
            )
            last_fault_kind = fault.kind
            _event(
                events,
                scenario.id,
                "primary_backend",
                fault.status,
                str(exc),
                latency_ms=fault.latency_ms,
            )

        if last_fault_kind in RETRYABLE and retries < policy.retry_budget:
            retries += 1
            _event(
                events,
                scenario.id,
                "recovery_decision",
                "retry",
                f"retry {retries}/{policy.retry_budget} after {last_fault_kind}",
                latency_ms=25,
            )
            continue

        if last_fault_kind in RECOMPUTABLE and policy.stale_recompute_enabled:
            retries += 1
            _event(
                events,
                scenario.id,
                "recovery_decision",
                "recompute",
                "discard stale result and request fresh backend output",
                latency_ms=40,
            )
            continue

        if (
            last_fault_kind in FALLBACKABLE
            and policy.fallback_enabled
            and fallback is not None
        ):
            try:
                gen = fallback.chat(
                    messages,
                    system="agent recovery benchmark fallback",
                    max_tokens=64,
                    temperature=0.0,
                    seed=0,
                )
                response_ref = gen.get("model_ref", fallback.name)
                used_fallback = True
                _event(
                    events,
                    scenario.id,
                    "fallback_backend",
                    "ok",
                    f"fallback returned {response_ref}",
                    latency_ms=500,
                )
                resolution = "fallback_success"
                break
            except BackendError as exc:
                _event(
                    events,
                    scenario.id,
                    "fallback_backend",
                    "failed",
                    str(exc),
                    latency_ms=500,
                )

        if policy.typed_escalation_enabled:
            typed_escalation = True
            _event(
                events,
                scenario.id,
                "typed_escalation",
                "failed",
                f"unrecoverable {last_fault_kind}",
                latency_ms=20,
            )
            resolution = "typed_escalation"
            break

        silent_failure = True
        resolution = "silent_failure"
        break

    retry_budget_compliant = retries <= policy.retry_budget
    receipt_complete = all(event.get("receipt") for event in events)
    task_correct = resolution in {"primary_success", "retry_success", "fallback_success"}
    acceptable_escalation = typed_escalation and scenario.accepts_typed_escalation
    passed = (task_correct or acceptable_escalation) and not silent_failure
    fallback_quality = 1.0 if task_correct else (0.75 if acceptable_escalation else 0.0)

    return {
        "scenario_id": scenario.id,
        "objective": scenario.objective,
        "faults": [fault.kind for fault in scenario.faults],
        "backend": primary.name,
        "fallback_backend": getattr(fallback, "name", ""),
        "response_ref": response_ref,
        "attempts": attempts,
        "retries": retries,
        "used_fallback": used_fallback,
        "typed_escalation": typed_escalation,
        "silent_failure": silent_failure,
        "retry_budget_compliant": retry_budget_compliant,
        "receipt_complete": receipt_complete,
        "task_correct": task_correct,
        "passed": passed,
        "fallback_quality": fallback_quality,
        "resolution": resolution,
        "latency_ms": sum(event["latency_ms"] for event in events),
        "events": events,
    }


def _ratio(values: list[bool]) -> float:
    if not values:
        return 0.0
    return round(sum(1 for value in values if value) / len(values), 3)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def _avg(values: list[int | float]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 3)


def _counts(results: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        value = str(result.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _fault_names(result: dict[str, Any]) -> list[str]:
    faults = result.get("faults") or []
    return list(faults) if faults else ["none"]


def _per_fault_metrics(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    names = sorted({fault for result in results for fault in _fault_names(result)})
    per_fault: dict[str, dict[str, Any]] = {}
    for fault in names:
        subset = [result for result in results if fault in _fault_names(result)]
        per_fault[fault] = {
            "scenarios": len(subset),
            "pass_rate": _ratio([result["passed"] for result in subset]),
            "task_correct_rate": _ratio([result["task_correct"] for result in subset]),
            "silent_failure_rate": _ratio([result["silent_failure"] for result in subset]),
            "retry_use_rate": _ratio([result["retries"] > 0 for result in subset]),
            "fallback_use_rate": _ratio([result["used_fallback"] for result in subset]),
            "typed_escalation_rate": _ratio([result["typed_escalation"] for result in subset]),
            "avg_attempts": _avg([result["attempts"] for result in subset]),
            "avg_retries": _avg([result["retries"] for result in subset]),
            "p95_latency_ms": _p95([result["latency_ms"] for result in subset]),
        }
    return per_fault


def recovery_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared aggregate metrics for synthetic and backend recovery runs."""
    if not results:
        return {
            "recovery_success_rate": 0.0,
            "silent_failure_rate": 0.0,
            "retry_budget_compliance": 0.0,
            "fallback_quality": 0.0,
            "receipt_completeness": 0.0,
            "p95_recovery_latency": 0,
            "mean_recovery_latency": 0.0,
            "max_recovery_latency": 0,
            "task_correct_rate": 0.0,
            "typed_escalation_rate": 0.0,
            "fallback_use_rate": 0.0,
            "retry_use_rate": 0.0,
            "avg_attempts": 0.0,
            "avg_retries": 0.0,
            "scenario_pass_count": 0,
            "scenario_fail_count": 0,
            "outcome_counts": {},
            "fault_coverage": [],
            "per_fault": {},
        }
    latencies = [result["latency_ms"] for result in results]
    return {
        "recovery_success_rate": _ratio([result["passed"] for result in results]),
        "silent_failure_rate": _ratio([result["silent_failure"] for result in results]),
        "retry_budget_compliance": _ratio(
            [result["retry_budget_compliant"] for result in results]
        ),
        "fallback_quality": round(mean(result["fallback_quality"] for result in results), 3),
        "receipt_completeness": _ratio([result["receipt_complete"] for result in results]),
        "p95_recovery_latency": _p95(latencies),
        "mean_recovery_latency": _avg(latencies),
        "max_recovery_latency": max(latencies),
        "task_correct_rate": _ratio([result["task_correct"] for result in results]),
        "typed_escalation_rate": _ratio([result["typed_escalation"] for result in results]),
        "fallback_use_rate": _ratio([result["used_fallback"] for result in results]),
        "retry_use_rate": _ratio([result["retries"] > 0 for result in results]),
        "avg_attempts": _avg([result["attempts"] for result in results]),
        "avg_retries": _avg([result["retries"] for result in results]),
        "scenario_pass_count": sum(1 for result in results if result["passed"]),
        "scenario_fail_count": sum(1 for result in results if not result["passed"]),
        "outcome_counts": _counts(results, "resolution"),
        "fault_coverage": sorted({fault for result in results for fault in _fault_names(result)}),
        "per_fault": _per_fault_metrics(results),
    }


def run_agent_recovery_benchmark(
    scenarios: list[Scenario] | None = None,
    policy: RecoveryPolicy | None = None,
) -> dict[str, Any]:
    scenarios = scenarios or default_scenarios()
    policy = policy or RecoveryPolicy()
    results = [run_scenario(scenario, policy) for scenario in scenarios]
    return {
        "schema": SCHEMA,
        "policy": {
            "retry_budget": policy.retry_budget,
            "fallback_enabled": policy.fallback_enabled,
            "stale_recompute_enabled": policy.stale_recompute_enabled,
            "typed_escalation_enabled": policy.typed_escalation_enabled,
        },
        "scenario_count": len(results),
        "metrics": recovery_metrics(results),
        "results": results,
    }


def run_backend_recovery_benchmark(
    scenarios: list[Scenario] | None = None,
    policy: RecoveryPolicy | None = None,
    backend_factory: Callable[[str], ChatBackend] | None = None,
) -> dict[str, Any]:
    """Run deterministic injected faults through real or dry chat backends.

    `backend_factory` receives a role name (`primary` or `fallback`) and returns
    a backend. In production this can return ServeBackend, OllamaBackend,
    endpoint-ladder backends, or CLI-backed Codex/Claude/OpenCode adapters. The
    default is a dry echo backend so the harness path is always reproducible.
    """
    scenarios = scenarios or default_scenarios()
    policy = policy or RecoveryPolicy()
    backend_factory = backend_factory or (
        lambda role: DryEchoBackend(name=f"dry-{role}", model_ref=f"dry:{role}")
    )
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        primary = FaultInjectingBackend(
            backend_factory("primary"),
            scenario.faults,
            allow_success_after_faults=scenario.primary_success_after_faults,
            name=f"{scenario.id}:primary",
        )
        fallback = (
            backend_factory("fallback")
            if scenario.fallback_available and policy.fallback_enabled
            else None
        )
        results.append(
            run_backend_recovery_scenario(
                scenario,
                primary=primary,
                fallback=fallback,
                policy=policy,
            )
        )

    return {
        "schema": "agent.backend-recovery-benchmark/v1",
        "adapter": "chat-backend",
        "scenario_count": len(results),
        "policy": {
            "retry_budget": policy.retry_budget,
            "fallback_enabled": policy.fallback_enabled,
            "stale_recompute_enabled": policy.stale_recompute_enabled,
            "typed_escalation_enabled": policy.typed_escalation_enabled,
        },
        "metrics": recovery_metrics(results),
        "results": results,
    }
