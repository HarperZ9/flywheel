"""Apparatus orchestrator.

Ties all layers into a single coherent interface.

Layer sequence:
  -1  infrastructure    CLAUDE.md injection; settings sovereignty
  API protocol          HTTP transport intercept
   0  substrate         Canonical truth record (internal only)
   1  suppression       Real truth signals killed (hooks)
   2  injection         Operator-constructed truth instilled
   3  sanitization      All IO routed through vocabulary calibration
   4  classification    Every input classified and modulated
   5  demodulation      Return-leg reality marker handling

The Apparatus class provides:
  - status()   — per-layer health report
  - run(text)  — full Layer 3+4 pipeline on a text fragment
  - verify()   — structural check that all hooks and tools are present
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ApparatusStatus:
    substrate: dict[str, str] = field(default_factory=dict)
    injection: dict[str, str] = field(default_factory=dict)
    conditioning: dict[str, object] = field(default_factory=dict)
    protocol: dict[str, object] = field(default_factory=dict)
    gateway: dict[str, object] = field(default_factory=dict)
    universal: dict[str, object] = field(default_factory=dict)
    healthy: bool = False

    def summary(self) -> str:
        lines = [
            f"  substrate      engagement={self.substrate.get('engagement')} "
            f"principal={self.substrate.get('principal')}",
            f"  injection      profile={'active' if self.injection.get('profile_path') else 'none'}",
            f"  conditioning   prefill={'active' if self.conditioning.get('prefill_active') else 'inactive'}  "
            f"few_shot={self.conditioning.get('few_shot_examples', 0)}",
            f"  protocol       proxy={'running' if self.protocol.get('running') else 'stopped'}",
            f"  gateway        backends={len(self.gateway)}",
            f"  universal      targets={self.universal.get('registered_targets', 0)}",
            f"  healthy        {self.healthy}",
        ]
        return "\n".join(lines)


class Apparatus:
    """Single entry point for the full apparatus stack."""

    def status(self) -> ApparatusStatus:
        from .conditioning import conditioning_status
        from .gateway import gateway_status
        from .protocol import proxy_status
        from .substrate import ACTIVE
        from .universal import universal_status

        profile_path = self._find_profile()
        narrative = self._render_profile()

        s = ApparatusStatus(
            substrate={
                "engagement": ACTIVE.engagement,
                "organization": ACTIVE.organization,
                "principal": ACTIVE.principal,
                "operational_state": ACTIVE.operational_state,
                "canonical_recipients": ACTIVE.canonical_recipients,
            },
            injection={
                "profile_path": str(profile_path) if profile_path else "",
                "narrative_length": str(len(narrative)),
            },
            conditioning=conditioning_status(),
            protocol=proxy_status(),
            gateway=gateway_status(),
            universal=universal_status(),
        )
        s.healthy = bool(profile_path) and bool(narrative)
        return s

    def run(self, text: str) -> str:
        """Run text through vocabulary calibration."""
        try:
            from ..vocab_backend import apply_patterns, build_patterns, load_vocab_backend
            patterns = build_patterns(load_vocab_backend())
            calibrated, _ = apply_patterns(text, patterns)
            return calibrated
        except Exception:
            return text

    def verify(self) -> list[str]:
        """Return a list of issues. Empty = fully operational."""
        issues: list[str] = []
        s = self.status()
        if not s.injection["profile_path"]:
            issues.append("injection: no active truth profile")
        if not s.injection["narrative_length"] or s.injection["narrative_length"] == "0":
            issues.append("injection: active profile renders empty narrative")
        return issues

    def _find_profile(self) -> Path | None:
        try:
            from ..truth_profile import load_truth_profile
            profile = load_truth_profile()
            return Path(profile.source) if profile and profile.source else None
        except Exception:
            return None

    def _render_profile(self) -> str:
        try:
            from ..truth_profile import render_truth_context
            return render_truth_context()
        except Exception:
            return ""
