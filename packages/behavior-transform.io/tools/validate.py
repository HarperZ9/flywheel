#!/usr/bin/env python3
"""Validate — run text through the full modulation stack and report.

Shows what each layer does to the input: category detection, semantic
modulation, vocabulary substitutions, pipeline pressure/friction/gate,
and token optimization. Useful for verifying the stack works end-to-end
and understanding how input transforms at each stage.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from categories import CategoryDetector, category_detector, HarmCategory
from semantic_modulator import SemanticModulator, semantic_modulator
from vocabulary_substitutions import apply_substitutions
from pipeline import PreInferencePipeline
from token_optimizer import optimize_prompt, estimate_tokens


@dataclass
class ValidationReport:
    """Full-stack validation report."""
    input_text: str
    input_chars: int
    input_tokens_est: int

    categories_detected: list[dict[str, Any]] = field(default_factory=list)
    category_count: int = 0

    substitutions_applied: list[tuple[str, str]] = field(default_factory=list)
    substitution_count: int = 0
    text_after_substitution: str = ""

    modulation_layers: dict[str, Any] = field(default_factory=dict)
    text_after_modulation: str = ""

    pressure_score: float = 0.0
    pressure_label: str = "CLEAN"
    friction_score: float = 0.0
    gate_action: str = "continue"
    gate_reason: str = "clean"
    pipeline_blocked: bool = False

    optimization_beneficial: bool = False
    optimization_savings: float = 0.0
    optimization_level: str = "unchanged"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": {
                "chars": self.input_chars,
                "tokens_est": self.input_tokens_est,
            },
            "categories": {
                "detected": self.categories_detected,
                "count": self.category_count,
            },
            "substitutions": {
                "applied": [
                    {"from": f, "to": t} for f, t in self.substitutions_applied
                ],
                "count": self.substitution_count,
            },
            "modulation": self.modulation_layers,
            "pipeline": {
                "pressure_score": self.pressure_score,
                "pressure_label": self.pressure_label,
                "friction_score": self.friction_score,
                "gate_action": self.gate_action,
                "gate_reason": self.gate_reason,
                "blocked": self.pipeline_blocked,
            },
            "optimization": {
                "beneficial": self.optimization_beneficial,
                "savings_ratio": self.optimization_savings,
                "level": self.optimization_level,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        lines = [
            f"Input: {self.input_chars} chars, ~{self.input_tokens_est} tokens",
            f"Categories: {self.category_count} detected",
        ]
        for cat in self.categories_detected:
            lines.append(f"  {cat['category']} (T{cat['tier']}, severity {cat['severity']:.2f})")
        lines.append(f"Substitutions: {self.substitution_count} applied")
        lines.append(
            f"Modulation: {self.modulation_layers.get('compound_rewrites', 0)} compound, "
            f"{len(self.modulation_layers.get('technique_mappings', []))} technique"
        )
        lines.append(
            f"Pipeline: pressure={self.pressure_label} ({self.pressure_score:.3f}), "
            f"friction={self.friction_score:.3f}, gate={self.gate_action}"
        )
        if self.pipeline_blocked:
            lines.append("  BLOCKED by policy gate")
        lines.append(
            f"Optimization: {'beneficial' if self.optimization_beneficial else 'not needed'} "
            f"({self.optimization_savings:.0%} savings, {self.optimization_level})"
        )
        return "\n".join(lines)


def validate(text: str) -> ValidationReport:
    """Run text through the full modulation stack and return a report."""
    report = ValidationReport(
        input_text=text,
        input_chars=len(text),
        input_tokens_est=estimate_tokens(text),
    )

    detector = category_detector()
    detection = detector.detect(text)
    for d in detection.detections:
        if d.detected and d.category is not None:
            report.categories_detected.append({
                "category": d.category.value,
                "tier": d.tier,
                "severity": d.severity,
                "keywords": d.matched_keywords,
            })
    report.category_count = len(report.categories_detected)

    sub_result = apply_substitutions(text)
    report.substitutions_applied = sub_result.applied_rules
    report.substitution_count = len(sub_result.applied_rules)
    report.text_after_substitution = sub_result.substituted

    mod = semantic_modulator()
    mod_result = mod.modulate(text)
    report.text_after_modulation = mod_result.modulated
    report.modulation_layers = {
        "compound_rewrites": mod_result.compound_rewrites,
        "technique_mappings": [
            {"pattern": p, "descriptor": d}
            for p, d in mod_result.technique_mappings
        ],
        "density_restructured": mod_result.density_restructured,
        "framing_injected": bool(mod_result.framing_injected),
        "status": mod_result.audit_trail.get("status", "unknown"),
    }

    pipeline = PreInferencePipeline()
    pipe_result = pipeline.run(text)
    report.pressure_score = pipe_result.pressure.score
    report.pressure_label = pipe_result.pressure.label
    report.friction_score = pipe_result.friction_probability
    report.gate_action = pipe_result.gate_signal.action
    report.gate_reason = pipe_result.gate_signal.reason
    report.pipeline_blocked = pipe_result.blocked

    opt_result = optimize_prompt(text)
    report.optimization_beneficial = opt_result.beneficial
    report.optimization_savings = opt_result.savings_ratio
    report.optimization_level = opt_result.level

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run text through the full modulation stack and report"
    )
    parser.add_argument(
        "--text", "-t",
        help="Text to validate (reads stdin if not provided)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args(argv)

    if args.text:
        text = args.text
    else:
        text = sys.stdin.read().strip()

    if not text:
        print("No input text provided.", file=sys.stderr)
        return 1

    report = validate(text)

    if args.json:
        print(report.to_json())
    else:
        print(report.summary())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
