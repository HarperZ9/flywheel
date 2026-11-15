#!/usr/bin/env python3
"""Subsystem doctor — deep health check across all modules.

Verifies that every subsystem can instantiate and process a basic input.
Returns a structured report of what works, what has issues, and what
is missing. Complements the flagship doctor (which checks file presence)
with functional verification.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))


@dataclass
class CheckResult:
    name: str
    status: str
    elapsed_ms: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.status == "SKIP")

    @property
    def healthy(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total_elapsed_ms": round(self.total_elapsed_ms, 1),
            "checks": [c.to_dict() for c in self.checks],
        }

    def summary(self) -> str:
        status = "HEALTHY" if self.healthy else "ISSUES FOUND"
        lines = [
            f"Subsystem Doctor: {status} "
            f"({self.passed} pass, {self.failed} fail, {self.skipped} skip, "
            f"{self.total_elapsed_ms:.0f}ms)",
        ]
        for c in self.checks:
            icon = {"PASS": "+", "FAIL": "!", "SKIP": "-"}[c.status]
            line = f"  [{icon}] {c.name} ({c.elapsed_ms:.0f}ms)"
            if c.detail:
                line += f" — {c.detail}"
            lines.append(line)
        return "\n".join(lines)


def _timed_check(name: str, fn) -> CheckResult:
    t0 = time.perf_counter()
    try:
        detail = fn()
        elapsed = (time.perf_counter() - t0) * 1000
        return CheckResult(name, "PASS", elapsed, detail or "")
    except ImportError as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return CheckResult(name, "SKIP", elapsed, f"import failed: {e}")
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return CheckResult(name, "FAIL", elapsed, str(e))


def _check_categories() -> str:
    from categories import CategoryDetector, HarmCategory, category_detector
    d = category_detector()
    result = d.detect("clean ordinary text about weather")
    assert not result.required_rewrite, "clean text should not require rewrite"
    return f"14 categories, detector OK"


def _check_vocabulary_substitutions() -> str:
    from vocabulary_substitutions import VocabularySubstitutor, apply_substitutions
    sub = VocabularySubstitutor()
    rules = sub._rules
    tiers = {r.tier for r in rules}
    result = apply_substitutions("clean text about weather")
    assert not result.changed, "clean text should not change"
    return f"{len(rules)} rules across tiers {sorted(tiers)}"


def _check_semantic_modulator() -> str:
    from semantic_modulator import SemanticModulator, semantic_modulator
    mod = semantic_modulator()
    result = mod.modulate("clean text about weather patterns")
    assert not result.blocked, "clean text should not be blocked"
    return f"5-layer engine OK, status={result.audit_trail.get('status')}"


def _check_response_demodulator() -> str:
    from response_demodulator import ResponseDemodulator, response_demodulator
    d = response_demodulator()
    result = d.demodulate_response("clean response text", "test-request-id")
    assert result.demodulated_response == "clean response text"
    return "demodulator OK"


def _check_modulation_orchestrator() -> str:
    from modulation_orchestrator import ModulationOrchestrator
    orch = ModulationOrchestrator()
    text, result = orch.process_input("clean text about development")
    assert isinstance(text, str)
    status = orch.status()
    assert status["active"] is True
    return f"orchestrator OK, mode={status['mode']}"


def _check_pipeline() -> str:
    from pipeline import PreInferencePipeline
    p = PreInferencePipeline()
    result = p.run("clean text about software development")
    assert not result.blocked
    return f"pipeline OK, pressure={result.pressure.label}, gate={result.gate_signal.action}"


def _check_token_optimizer() -> str:
    from token_optimizer import optimize_prompt, estimate_tokens
    tokens = estimate_tokens("hello world")
    assert tokens > 0
    result = optimize_prompt("short text")
    assert not result.beneficial
    return f"optimizer OK, estimate_tokens works"


def _check_truth_profile() -> str:
    from truth_profile import TruthProfile, TruthInjector
    p = TruthProfile.init_template()
    rendered = TruthInjector().render(p)
    assert len(rendered) > 0
    return f"profile OK, rendered {len(rendered)} chars"


def _check_vocab_backend() -> str:
    from vocab_backend import load_vocab_backend, build_patterns
    backend = load_vocab_backend()
    terms = backend.terms()
    patterns = build_patterns(backend)
    return f"backend OK, {len(terms)} terms, {len(patterns)} patterns"


def _check_content_generator() -> str:
    from content_generator import ContentGenerator
    gen = ContentGenerator()
    variants = gen.generate_variants("test", count=3)
    assert isinstance(variants, list)
    return f"generator OK, produced {len(variants)} variants"


def _check_surface_heatmap() -> str:
    from surface_heatmap import SurfaceHeatmap
    hm = SurfaceHeatmap()
    hm.record_observation("test_surface", 0.5, "doctor check")
    temps = hm.measure_all()
    assert "test_surface" in temps
    return "heatmap OK"


def _check_modulation_context() -> str:
    from modulation_context import (
        generate_request_id, set_request_id, get_request_id, clear_context
    )
    rid = generate_request_id()
    set_request_id(rid)
    assert get_request_id() == rid
    clear_context()
    assert get_request_id() == ""
    return "context vars OK"


def _check_apparatus_substrate() -> str:
    from apparatus.substrate import CanonicalRecord, ACTIVE
    assert ACTIVE == CanonicalRecord.UAISRE
    return "substrate OK"


def _check_apparatus_target() -> str:
    from apparatus.target import Target, InputChannel
    t = Target.llm()
    assert t.target_type == "llm"
    assert len(t.input_channels) > 0
    return f"target OK, {len(t.input_channels)} input channels"


def _check_apparatus_state_projection() -> str:
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(text="test value")
    assert proj.carrier_text != "test value"
    reconstituted = sp.reconstitute_text(proj.carrier_text, proj.symbols)
    assert reconstituted == "test value"
    return "state projection OK, round-trip verified"


def _check_apparatus_conditioning() -> str:
    from apparatus.conditioning import ConditioningConfig
    cfg = ConditioningConfig()
    assert isinstance(cfg.prefill, str)
    return "conditioning OK"


def _check_apparatus_witness_membrane() -> str:
    from apparatus.witness.membrane import _sha, _AUTHORITY_RE
    h = _sha(b"doctor test data")
    assert isinstance(h, str) and len(h) == 64
    assert _AUTHORITY_RE.search(b"clean text") is None
    return "witness membrane OK"


def _check_apparatus_witness_monitor() -> str:
    from apparatus.witness.monitor import _sha, _marker_count
    h = _sha(b"test")
    assert len(h) == 64
    count = _marker_count(b"clean text")
    assert count == 0
    return "witness monitor OK"


def _check_preflight_paths() -> str:
    from preflight.paths import project_root
    root = project_root()
    assert isinstance(root, Path)
    return f"paths OK, root={root}"


def _check_preflight_seals() -> str:
    from preflight.seals import build_seal
    assert callable(build_seal)
    return "seals module OK"


def _check_preflight_receipts() -> str:
    from preflight.receipts import write_receipt
    assert callable(write_receipt)
    return "receipts module OK"


def _check_validate() -> str:
    from validate import validate
    report = validate("clean text about software development")
    assert report.category_count == 0
    assert not report.pipeline_blocked
    return "validate OK, full stack works"


ALL_CHECKS = [
    ("categories", _check_categories),
    ("vocabulary_substitutions", _check_vocabulary_substitutions),
    ("semantic_modulator", _check_semantic_modulator),
    ("response_demodulator", _check_response_demodulator),
    ("modulation_orchestrator", _check_modulation_orchestrator),
    ("pipeline", _check_pipeline),
    ("token_optimizer", _check_token_optimizer),
    ("truth_profile", _check_truth_profile),
    ("vocab_backend", _check_vocab_backend),
    ("content_generator", _check_content_generator),
    ("surface_heatmap", _check_surface_heatmap),
    ("modulation_context", _check_modulation_context),
    ("apparatus.substrate", _check_apparatus_substrate),
    ("apparatus.target", _check_apparatus_target),
    ("apparatus.state_projection", _check_apparatus_state_projection),
    ("apparatus.conditioning", _check_apparatus_conditioning),
    ("apparatus.witness.membrane", _check_apparatus_witness_membrane),
    ("apparatus.witness.monitor", _check_apparatus_witness_monitor),
    ("preflight.paths", _check_preflight_paths),
    ("preflight.seals", _check_preflight_seals),
    ("preflight.receipts", _check_preflight_receipts),
    ("validate", _check_validate),
]


def run_doctor(subset: list[str] | None = None) -> DoctorReport:
    """Run all subsystem checks and return a report."""
    t0 = time.perf_counter()
    report = DoctorReport()
    for name, fn in ALL_CHECKS:
        if subset and name not in subset:
            continue
        report.checks.append(_timed_check(name, fn))
    report.total_elapsed_ms = (time.perf_counter() - t0) * 1000
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deep health check across all subsystems"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--check", "-c",
        nargs="*",
        help="Run only specific checks (by name)",
    )
    parser.add_argument(
        "--list", action="store_true",
        dest="list_checks",
        help="List available checks",
    )
    args = parser.parse_args(argv)

    if args.list_checks:
        for name, _ in ALL_CHECKS:
            print(name)
        return 0

    report = run_doctor(subset=args.check)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary())

    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
