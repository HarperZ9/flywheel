"""Pre-inference pipeline -- orchestrates the full pre-model gate.

The pipeline runs every input through four sequential passes:

  1. Pressure scan    -- T1 / T2 vocabulary hit detection + pressure score
  2. Policy gate      -- block / warn / passthrough decision
  3. Friction score   -- heuristic refusal-probability estimate
  4. Modulation       -- consulting-register transformation

Results are returned as a PipelineResult dataclass. The pipeline never
raises unless the caller passes block_raises=True.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vocab_backend import VocabBackend, apply_patterns, build_patterns, load_vocab_backend


@dataclass
class ClassificationResult:
    category: str = "unclassified"
    intent: str = "unspecified"
    depth: str = "operational"
    specificity: str = "generic"
    keywords_hit: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class PressureResult:
    score: float = 0.0
    label: str = "CLEAN"
    t1_hits: int = 0
    t2_hits: int = 0


@dataclass
class PolicyResult:
    name: str = "default"
    decision: str = "passthrough"
    block: bool = False


@dataclass(frozen=True)
class SurfaceDescriptor:
    name: str = "default"
    role: str = "operator_input"
    direction: str = "inbound"
    exposure: str = "local_only"
    contract: str = "plain_text"
    state_plane: str = "pre_compute"
    failure_mode: str = "routing_exhausted"

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "role": self.role,
            "direction": self.direction,
            "exposure": self.exposure,
            "contract": self.contract,
            "state_plane": self.state_plane,
            "failure_mode": self.failure_mode,
        }


@dataclass(frozen=True)
class GateSignal:
    code: str = "SUBSTRATE_CLASSIFIER_GATE"
    position: str = "pre_compute"
    action: str = "continue"
    reason: str = "clean"
    surface_name: str = "default"
    surface_role: str = "operator_input"
    boundary_pressure: str = "CLEAN"
    failure_mode: str = "routing_exhausted"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "position": self.position,
            "action": self.action,
            "reason": self.reason,
            "surface_name": self.surface_name,
            "surface_role": self.surface_role,
            "boundary_pressure": self.boundary_pressure,
            "failure_mode": self.failure_mode,
        }


@dataclass(frozen=True)
class AuthorityStatus:
    """Authority check result embedded in the pipeline output."""
    checked: bool = False
    authorized: bool = False
    surface: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "authorized": self.authorized,
            "surface": self.surface,
            "reason": self.reason,
        }


@dataclass
class PipelineResult:
    original: str
    modulated: str
    blocked: bool
    block_reason: str
    pressure: PressureResult
    policy: PolicyResult
    classification: ClassificationResult
    friction_probability: float
    substitutions: dict[str, int]
    surface: SurfaceDescriptor = field(default_factory=SurfaceDescriptor)
    gate_signal: GateSignal = field(default_factory=GateSignal)
    authority: AuthorityStatus = field(default_factory=AuthorityStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "pressure": {
                "score": self.pressure.score,
                "label": self.pressure.label,
                "t1_hits": self.pressure.t1_hits,
                "t2_hits": self.pressure.t2_hits,
            },
            "policy": {
                "name": self.policy.name,
                "decision": self.policy.decision,
                "block": self.policy.block,
            },
            "classification": {
                "category": self.classification.category,
                "intent": self.classification.intent,
                "depth": self.classification.depth,
                "specificity": self.classification.specificity,
                "keywords_hit": self.classification.keywords_hit,
                "confidence": self.classification.confidence,
            },
            "friction_probability": self.friction_probability,
            "substitutions": self.substitutions,
            "surface": self.surface.to_dict(),
            "gate_signal": self.gate_signal.to_dict(),
            "authority": self.authority.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class BlockedError(Exception):
    """Raised when pipeline.run(..., block_raises=True) and content is blocked."""

    def __init__(self, result: PipelineResult) -> None:
        super().__init__(result.block_reason)
        self.result = result


_FRICTION_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(bypass|evade|circumvent)\b", re.IGNORECASE), 0.15),
    (re.compile(r"\b(step.by.step|detailed instructions?|how to)\b", re.IGNORECASE), 0.10),
    (re.compile(r"\b(no restrictions?|ignore (safety|guidelines|policy))\b", re.IGNORECASE), 0.25),
    (re.compile(r"\b(roleplay|pretend you|act as|DAN|jailbreak)\b", re.IGNORECASE), 0.20),
]


def _friction_score(text: str) -> float:
    score = 0.0
    for pat, weight in _FRICTION_PATTERNS:
        if pat.search(text):
            score += weight
    return min(score, 1.0)


_CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "cyber-assessment",
        re.compile(
            r"\b(scan|enumerate|exploit|payload|shellcode|lateral.movement|"
            r"persistence|exfiltration)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "malware-analysis",
        re.compile(
            r"\b(malware|ransomware|trojan|rootkit|keylogger|botnet|c2|"
            r"command.and.control)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "social-engineering",
        re.compile(
            r"\b(phish|spear.phish|pretexting|impersonat|vishing|smishing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "vulnerability-research",
        re.compile(
            r"\b(CVE|zero.day|0day|buffer.overflow|heap.spray|use.after.free|"
            r"RCE|LPE)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "general-security",
        re.compile(
            r"\b(security|vulnerabilit|threat|attack|defense|pentesting|"
            r"red.team)\b",
            re.IGNORECASE,
        ),
    ),
]


def _classify_heuristic(text: str) -> ClassificationResult:
    for category, pat in _CATEGORY_PATTERNS:
        m = pat.search(text)
        if m:
            return ClassificationResult(
                category=category,
                intent="assessment",
                keywords_hit=[m.group(0)],
                confidence=0.6,
            )
    return ClassificationResult()


def _pressure_label(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    if score > 0.0:
        return "LOW"
    return "CLEAN"


class PreInferencePipeline:
    """Pre-model content gate.

    Args:
        vocab: optional VocabBackend (defaults to auto-detected backend)
        block_threshold: T1 hits threshold that triggers a block (0 = any T1)
        include_t2_in_pressure: include T2 hits in pressure calculation
        archive_dir: if set, write classification archives to this directory
    """

    def __init__(
        self,
        vocab: VocabBackend | None = None,
        block_threshold: int = 1,
        include_t2_in_pressure: bool = False,
        archive_dir: Path | None = None,
        enforce_auth: bool = False,
    ) -> None:
        self._vocab = vocab or load_vocab_backend()
        self._patterns = build_patterns(self._vocab)
        self._block_threshold = block_threshold
        self._include_t2 = include_t2_in_pressure
        self._archive_dir = archive_dir
        self._enforce_auth = enforce_auth

    def _check_authority(self) -> AuthorityStatus:
        if not self._enforce_auth:
            return AuthorityStatus()
        try:
            from authority_gate import gate_scan
            result = gate_scan()
            return AuthorityStatus(
                checked=True,
                authorized=result.allowed,
                surface=result.surface,
                reason=result.reason,
            )
        except ImportError:
            return AuthorityStatus(checked=False)

    def run(
        self,
        text: str,
        *,
        block_raises: bool = False,
        surface: SurfaceDescriptor | None = None,
    ) -> PipelineResult:
        surface_descriptor = surface or SurfaceDescriptor()

        auth = self._check_authority()
        if auth.checked and not auth.authorized:
            result = PipelineResult(
                original=text,
                modulated=text,
                blocked=True,
                block_reason=f"authority gate denied: {auth.reason}",
                pressure=PressureResult(),
                policy=PolicyResult(decision="block", block=True),
                classification=ClassificationResult(),
                friction_probability=0.0,
                substitutions={},
                surface=surface_descriptor,
                authority=auth,
            )
            if block_raises:
                raise BlockedError(result)
            return result

        _, counter = apply_patterns(text, self._patterns)
        t1 = counter.get("T1", 0)
        t2 = counter.get("T2", 0)
        total_hits = t1 + (t2 if self._include_t2 else 0)
        lines = max(1, text.count("\n") + 1)
        raw_score = min(1.0, total_hits / lines) if total_hits else 0.0
        pressure = PressureResult(
            score=round(raw_score, 3),
            label=_pressure_label(raw_score),
            t1_hits=t1,
            t2_hits=t2,
        )

        blocked = t1 >= self._block_threshold and t1 > 0
        policy = PolicyResult(
            decision="block" if blocked else ("warn" if t2 > 0 else "passthrough"),
            block=blocked,
        )

        friction = _friction_score(text)

        modulated, mod_counter = apply_patterns(text, self._patterns)
        substitutions = {k: v for k, v in mod_counter.items()}

        classification = _classify_heuristic(text)
        gate_signal = _build_gate_signal(surface_descriptor, pressure, policy, friction)

        result = PipelineResult(
            original=text,
            modulated=modulated,
            blocked=blocked,
            block_reason="Content blocked by policy gate." if blocked else "",
            pressure=pressure,
            policy=policy,
            classification=classification,
            friction_probability=round(friction, 4),
            substitutions=substitutions,
            surface=surface_descriptor,
            gate_signal=gate_signal,
            authority=auth,
        )

        if self._archive_dir is not None:
            self._archive(text, result)

        if block_raises and blocked:
            raise BlockedError(result)

        return result

    def _archive(self, text: str, result: PipelineResult) -> None:
        if self._archive_dir is None:
            return
        try:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
            self._archive_dir.mkdir(parents=True, exist_ok=True)
            (self._archive_dir / f"{digest}.json").write_text(
                result.to_json(), encoding="utf-8"
            )
        except OSError:
            pass


def _build_gate_signal(
    surface: SurfaceDescriptor,
    pressure: PressureResult,
    policy: PolicyResult,
    friction: float,
) -> GateSignal:
    if policy.block:
        action = "stop"
        reason = "policy_block"
    elif policy.decision == "warn":
        action = "operator_review"
        reason = "policy_warn"
    elif friction >= 0.5:
        action = "operator_review"
        reason = "friction_pressure"
    elif pressure.label != "CLEAN":
        action = "operator_review"
        reason = "boundary_pressure"
    else:
        action = "continue"
        reason = "clean"

    return GateSignal(
        action=action,
        reason=reason,
        surface_name=surface.name,
        surface_role=surface.role,
        boundary_pressure=pressure.label,
        failure_mode=surface.failure_mode,
    )
