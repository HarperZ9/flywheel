"""Epistemic vorticity monitor, definition-integrity auditor, and expander witness mesh.

Three stdlib-only primitives derived from the Navier-Stokes regularity analogy
(Beale-Kato-Majda peak vorticity integral), formal axiom-graph auditing (zero
hidden sorry/custom-axiom/weakened-assertion checks), and deterministic
Ramanujan/Cayley expander routing meshes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _sha256_json(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# 1. Beale-Kato-Majda Epistemic Vorticity Monitor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VorticityTurn:
    turn_index: int
    self_reference_ratio: float
    claim_confidence: float
    novel_evidence_ratio: float
    vorticity: float
    cumulative_integral: float
    regime: str


class EpistemicVorticityMonitor:
    """Track cumulative peak self-amplification across multi-turn agent loops.

    In an unforced fluid, finite-time blow-up requires the time-integral of
    peak vorticity to diverge (Beale-Kato-Majda). In an unforced agent loop,
    self-reference amplified by high confidence with little fresh external
    evidence creates an analogous runaway feedback loop.
    """

    def __init__(
        self,
        *,
        turbulent_threshold: float = 1.5,
        blowup_threshold: float = 3.0,
        dt: float = 1.0,
    ) -> None:
        if turbulent_threshold <= 0 or blowup_threshold <= turbulent_threshold:
            raise ValueError("require 0 < turbulent_threshold < blowup_threshold")
        self.turbulent_threshold = float(turbulent_threshold)
        self.blowup_threshold = float(blowup_threshold)
        self.dt = float(dt)
        self._turns: list[VorticityTurn] = []
        self._integral: float = 0.0

    def record_turn(
        self,
        *,
        self_reference_ratio: float,
        claim_confidence: float,
        novel_evidence_ratio: float,
    ) -> VorticityTurn:
        sr = max(0.0, min(1.0, float(self_reference_ratio)))
        conf = max(0.0, min(1.0, float(claim_confidence)))
        ev = max(0.0, min(1.0, float(novel_evidence_ratio)))
        # Self-amplification grows when an agent cites itself with high
        # confidence and low fresh external evidence; new external evidence
        # acts as viscous dissipation.
        omega = (sr * conf) / (0.25 + ev)
        self._integral += omega * self.dt
        if self._integral >= self.blowup_threshold:
            regime = "BLOWUP_RISK"
        elif self._integral >= self.turbulent_threshold:
            regime = "TURBULENT"
        else:
            regime = "LAMINAR"
        turn = VorticityTurn(
            turn_index=len(self._turns),
            self_reference_ratio=sr,
            claim_confidence=conf,
            novel_evidence_ratio=ev,
            vorticity=round(omega, 6),
            cumulative_integral=round(self._integral, 6),
            regime=regime,
        )
        self._turns.append(turn)
        return turn

    def should_vent_or_rest(self) -> bool:
        return bool(self._turns) and self._turns[-1].regime == "BLOWUP_RISK"

    def summary(self) -> dict[str, Any]:
        peak = max((t.vorticity for t in self._turns), default=0.0)
        regime = self._turns[-1].regime if self._turns else "LAMINAR"
        payload = {
            "turns": len(self._turns),
            "peak_vorticity": round(peak, 6),
            "cumulative_integral": round(self._integral, 6),
            "regime": regime,
            "should_vent_or_rest": self.should_vent_or_rest(),
        }
        payload["digest"] = _sha256_json(payload)
        return payload


# ---------------------------------------------------------------------------
# 2. Definition-Integrity & Escape-Hatch Auditor
# ---------------------------------------------------------------------------

_ESCAPE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("lean_sorry", re.compile(r"\bsorry\b"), "Unproven Lean placeholder (sorry)"),
    ("lean_custom_axiom", re.compile(r"^\s*axiom\s+[A-Za-z0-9_']+", re.M), "Custom Lean axiom declaration"),
    ("python_trivial_assert", re.compile(r"^\s*assert\s+True\b", re.M), "Trivial always-true assertion"),
    ("python_silent_except", re.compile(r"except\b[^:]*:\s*pass\b"), "Silent exception swallow"),
    ("python_unconditional_skip", re.compile(r"@pytest\.mark\.skip\b|pytest\.skip\("), "Skipped test check"),
)


@dataclass(frozen=True)
class AuditFinding:
    module: str
    rule: str
    line: int
    message: str


def audit_definition_integrity(
    modules: Mapping[str, str],
    *,
    required_symbols: Sequence[str] = (),
) -> dict[str, Any]:
    """Audit source modules for hidden escape hatches and missing required symbols."""
    findings: list[dict[str, Any]] = []
    combined_source = "\n".join(modules.values())
    for mod_name in sorted(modules):
        text = modules[mod_name]
        for rule_id, pat, msg in _ESCAPE_PATTERNS:
            for match in pat.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "module": mod_name,
                        "rule": rule_id,
                        "line": line_no,
                        "message": msg,
                    }
                )
    missing_symbols = [sym for sym in required_symbols if sym not in combined_source]
    verdict = "CLEAN" if (not findings and not missing_symbols) else "DRIFT"
    result: dict[str, Any] = {
        "verdict": verdict,
        "modules_audited": len(modules),
        "finding_count": len(findings),
        "findings": findings,
        "missing_symbols": missing_symbols,
    }
    result["digest"] = _sha256_json(result)
    return result


# ---------------------------------------------------------------------------
# 3. Deterministic Cayley / Expander Witness Mesh
# ---------------------------------------------------------------------------


def build_expander_witness_graph(
    node_ids: Sequence[str],
    *,
    degree: int = 4,
) -> dict[str, Any]:
    """Build a deterministic regular expander witness mesh over node_ids.

    Uses deterministic modular jump steps (1, floor(sqrt(N)), and coprime
    offsets) to produce a well-connected regular witness topology with no
    randomness, then computes its algebraic connectivity proxy via power
    iteration on the normalized adjacency matrix.
    """
    n = len(node_ids)
    if n < 3:
        raise ValueError("expander witness mesh requires at least 3 nodes")
    steps = [1]
    stride = max(2, int(math.isqrt(n)))
    while len(steps) * 2 < min(degree, n - 1):
        cand = stride % n
        if cand != 0 and cand not in steps and (n - cand) not in steps:
            steps.append(cand)
        stride += 1
        if stride >= n:
            break

    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    adj_idx: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        seen: set[int] = set()
        for s in steps:
            for j in ((i + s) % n, (i - s) % n):
                if j != i and j not in seen:
                    seen.add(j)
                    adj_idx[i].append(j)
        adj_idx[i].sort()
        adj[node_ids[i]] = [node_ids[j] for j in adj_idx[i]]

    # Estimate second-largest normalized adjacency eigenvalue |lambda_2| via
    # orthogonalized power iteration (smaller |lambda_2| -> larger spectral gap).
    vec = [math.sin((i + 1) * 1.61803398875) for i in range(n)]
    mean = sum(vec) / n
    vec = [v - mean for v in vec]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    vec = [v / norm for v in vec]

    lam2 = 1.0
    for _ in range(40):
        nxt = [0.0] * n
        for i in range(n):
            deg_i = len(adj_idx[i]) or 1
            nxt[i] = sum(vec[j] for j in adj_idx[i]) / deg_i
        mean_n = sum(nxt) / n
        nxt = [v - mean_n for v in nxt]
        norm_n = math.sqrt(sum(v * v for v in nxt))
        if norm_n < 1e-12:
            lam2 = 0.0
            break
        lam2 = norm_n
        vec = [v / norm_n for v in nxt]

    spectral_gap = max(0.0, round(1.0 - min(1.0, lam2), 6))
    result: dict[str, Any] = {
        "node_count": n,
        "steps": steps,
        "min_degree": min(len(v) for v in adj_idx),
        "max_degree": max(len(v) for v in adj_idx),
        "lambda2_estimate": round(min(1.0, lam2), 6),
        "spectral_gap": spectral_gap,
        "adjacency": adj,
    }
    result["digest"] = _sha256_json(result)
    return result
