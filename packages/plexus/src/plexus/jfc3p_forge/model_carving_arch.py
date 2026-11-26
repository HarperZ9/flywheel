"""JFC-3P Architecture Prototype: Model Carving (arXiv:2611.27962), Loom vs mHC (arXiv:2611.30634),
BuildLang kcore/buildc Oracle Head, and Jack Morris capacity bit-transfer diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Sequence

STEFAN_BOLTZMANN = 5.670374419e-8


def _sigmoid(x: float) -> float:
    if x >= 0.0:
        z = math.exp(-min(x, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(x, -60.0))
    return z / (1.0 + z)


@dataclass(frozen=True)
class CarvingHealthReport:
    healthy: bool
    verdict: str
    active_params: int
    total_params: int
    sparsity_ratio: float
    reason: str


@dataclass(frozen=True)
class OracleCheckResult:
    formula_id: str
    passed: bool
    expected: float | None
    predicted: float | None
    rel_error: float | None
    reason: str


class CarvedSublayerGate:
    """Learnable sublayer sparsity gates implementing Model Carving (arXiv:2611.27962)."""

    def __init__(self, sublayer_names: Sequence[str], param_counts: Sequence[int], init_logits: Sequence[float] | None = None) -> None:
        if not sublayer_names or len(sublayer_names) != len(param_counts):
            raise ValueError("sublayer_names and param_counts must be non-empty and equal length")
        if any(p <= 0 for p in param_counts):
            raise ValueError("param_counts must be strictly positive")
        self.sublayer_names = tuple(sublayer_names)
        self.param_counts = tuple(int(p) for p in param_counts)
        self.logits = [float(v) for v in (init_logits if init_logits is not None else [0.5] * len(sublayer_names))]
        if len(self.logits) != len(self.sublayer_names):
            raise ValueError("init_logits length must match sublayer_names")

    def gate_values(self, temperature: float = 1.0) -> tuple[float, ...]:
        if temperature <= 0.0:
            raise ValueError("temperature must be positive")
        return tuple(_sigmoid(v / temperature) for v in self.logits)

    def binary_mask(self, threshold: float = 0.5) -> tuple[int, ...]:
        return tuple(1 if g >= threshold else 0 for g in self.gate_values())

    def stats(self, threshold: float = 0.5) -> dict[str, Any]:
        mask = self.binary_mask(threshold=threshold)
        total = sum(self.param_counts)
        active = sum(p for p, m in zip(self.param_counts, mask) if m == 1)
        sparsity = 1.0 - (active / float(total))
        return {
            "active_sublayers": sum(mask),
            "total_sublayers": len(mask),
            "active_params": active,
            "total_params": total,
            "sparsity_ratio": round(sparsity, 6),
            "parameter_reduction_ratio": round(sparsity, 6),
            "mask": list(mask),
        }

    def carve_step(self, importance_scores: Sequence[float], *, target_sparsity: float = 0.35, lr: float = 0.4) -> dict[str, Any]:
        if len(importance_scores) != len(self.logits):
            raise ValueError("importance_scores length must match sublayers")
        cur_sparsity = self.stats()["sparsity_ratio"]
        pressure = target_sparsity - cur_sparsity
        mean_imp = sum(importance_scores) / float(len(importance_scores))
        for idx, imp in enumerate(importance_scores):
            centered = float(imp) - mean_imp
            self.logits[idx] += lr * (centered - 2.0 * pressure)
        return self.stats()


def validate_carving_health(
    gate: CarvedSublayerGate,
    *,
    threshold: float = 0.5,
    min_sparsity: float = 0.10,
    max_sparsity: float = 0.85,
) -> CarvingHealthReport:
    """Reject collapsed all-zero carving gates, unpruned gates, or non-finite logits."""
    if any(not math.isfinite(v) for v in gate.logits):
        return CarvingHealthReport(False, "NON_FINITE_GATE", 0, sum(gate.param_counts), 1.0, "gate logits contain NaN or Inf")
    st = gate.stats(threshold=threshold)
    active = int(st["active_params"])
    total = int(st["total_params"])
    sparsity = float(st["sparsity_ratio"])
    if active <= 0 or sparsity > max_sparsity:
        return CarvingHealthReport(
            False, "COLLAPSED_CARVING_GATE", active, total, sparsity,
            f"carving collapse detected: sparsity={sparsity:.4f} exceeds max={max_sparsity:.2f} (active={active})",
        )
    if sparsity < min_sparsity:
        return CarvingHealthReport(
            False, "UNPRUNED_CARVING_GATE", active, total, sparsity,
            f"carving gate failed to prune: sparsity={sparsity:.4f} below min={min_sparsity:.2f}",
        )
    return CarvingHealthReport(True, "HEALTHY", active, total, sparsity, "carving gate within healthy sparsity bounds")


def sinkhorn_knopp(logits_matrix: Sequence[Sequence[float]], iters: int = 24) -> list[list[float]]:
    """Project a square logit matrix onto the Birkhoff polytope of doubly-stochastic matrices (mHC)."""
    n = len(logits_matrix)
    if n == 0 or any(len(row) != n for row in logits_matrix):
        raise ValueError("logits_matrix must be a non-empty square matrix")
    max_v = max(v for row in logits_matrix for v in row)
    mat = [[math.exp(max(v - max_v, -40.0)) for v in row] for row in logits_matrix]
    for _ in range(iters):
        for i in range(n):
            rs = sum(mat[i]) or 1e-12
            mat[i] = [v / rs for v in mat[i]]
        for j in range(n):
            cs = sum(mat[i][j] for i in range(n)) or 1e-12
            for i in range(n):
                mat[i][j] /= cs
    return mat


class LoomMHCRouter:
    """Multi-stream residual router comparing unconstrained Loom mixing vs doubly-stochastic mHC."""

    def __init__(self, logits_matrix: Sequence[Sequence[float]]) -> None:
        n = len(logits_matrix)
        if n == 0 or any(len(row) != n for row in logits_matrix):
            raise ValueError("logits_matrix must be square and non-empty")
        self.n_streams = n
        self.raw_matrix = [[float(v) for v in row] for row in logits_matrix]
        self.mhc_matrix = sinkhorn_knopp(self.raw_matrix)

    def _apply(self, mat: Sequence[Sequence[float]], streams: Sequence[Sequence[float]]) -> list[list[float]]:
        if len(streams) != self.n_streams:
            raise ValueError(f"expected {self.n_streams} streams, got {len(streams)}")
        dim = len(streams[0])
        out: list[list[float]] = []
        for i in range(self.n_streams):
            vec = [0.0] * dim
            for j in range(self.n_streams):
                w = mat[i][j]
                src = streams[j]
                for d in range(dim):
                    vec[d] += w * src[d]
            out.append(vec)
        return out

    def route(self, streams: Sequence[Sequence[float]], *, mode: str = "mhc") -> dict[str, Any]:
        if mode not in {"mhc", "loom"}:
            raise ValueError(f"unsupported router mode: {mode}")
        mat = self.mhc_matrix if mode == "mhc" else self.raw_matrix
        routed = self._apply(mat, streams)
        in_norm = math.sqrt(sum(v * v for s in streams for v in s)) or 1e-12
        out_norm = math.sqrt(sum(v * v for s in routed for v in s))
        row_sums = [sum(row) for row in mat]
        col_sums = [sum(mat[i][j] for i in range(self.n_streams)) for j in range(self.n_streams)]
        return {
            "mode": mode,
            "outputs": routed,
            "amplification_ratio": round(out_norm / in_norm, 6),
            "max_row_sum_err": round(max(abs(s - 1.0) for s in row_sums), 9),
            "max_col_sum_err": round(max(abs(s - 1.0) for s in col_sums), 9),
        }


def _oracle_formulas() -> dict[str, Callable[[dict[str, float]], float]]:
    return {
        "PHY_KINETIC_ENERGY": lambda p: 0.5 * p["mass"] * (p["velocity"] ** 2),
        "PHY_STEFAN_BOLTZMANN": lambda p: STEFAN_BOLTZMANN * (p["temperature"] ** 4),
        "PHY_OHM_POWER": lambda p: (p["voltage"] ** 2) / p["resistance"],
        "OPT_SNELL_SIN_T2": lambda p: (p["n1"] / p["n2"]) * math.sin(p["theta1"]),
    }


class BuildLangOracleHead:
    """Independent deterministic kcore/buildc verification head refusing self-scored outputs."""

    def __init__(self, rel_tol: float = 1e-9) -> None:
        self.rel_tol = rel_tol
        self._formulas = _oracle_formulas()

    def verify_numeric(self, formula_id: str, params: dict[str, float], predicted: Any) -> OracleCheckResult:
        fn = self._formulas.get(formula_id)
        if fn is None:
            return OracleCheckResult(formula_id, False, None, None, None, f"unknown formula_id: {formula_id}")
        if not isinstance(predicted, (int, float)) or isinstance(predicted, bool) or not math.isfinite(float(predicted)):
            return OracleCheckResult(formula_id, False, None, None, None, "predicted value is non-numeric or non-finite")
        expected = float(fn(params))
        pred_f = float(predicted)
        denom = max(abs(expected), 1e-12)
        rel_err = abs(pred_f - expected) / denom
        if rel_err <= self.rel_tol:
            return OracleCheckResult(formula_id, True, expected, pred_f, rel_err, "exact IEEE-754 oracle match")
        return OracleCheckResult(formula_id, False, expected, pred_f, rel_err, f"oracle mismatch: rel_err={rel_err:.3e}")

    def verify_buildlang_source(self, source: str) -> OracleCheckResult:
        text = (source or "").strip()
        if not text or "TODO" in text.upper() or "STUB" in text.upper() or "fn " not in text:
            return OracleCheckResult("BUILDC_STRUCT", False, None, None, None, "rejected stub or malformed BuildLang source")
        if text.count("{") == 0 or text.count("{") != text.count("}"):
            return OracleCheckResult("BUILDC_STRUCT", False, None, None, None, "unbalanced braces in BuildLang source")
        return OracleCheckResult("BUILDC_STRUCT", True, None, None, 0.0, "BuildLang structural oracle check passed")


def compute_capacity_bit_transfer(
    pre_loss_nats: float,
    post_loss_nats: float,
    num_examples: int,
    active_params: int,
    total_params: int,
) -> dict[str, float]:
    """Compute Jack Morris capacity/bit-transfer and parameter-reduction diagnostics."""
    if active_params <= 0 or total_params <= 0 or active_params > total_params or num_examples <= 0:
        raise ValueError("active_params, total_params, and num_examples must be valid positive integers")
    delta_nats = max(0.0, float(pre_loss_nats) - float(post_loss_nats))
    bits_transferred = (delta_nats / math.log(2.0)) * float(num_examples)
    return {
        "bits_transferred": round(bits_transferred, 6),
        "bits_per_active_param": round(bits_transferred / float(active_params), 9),
        "bits_per_total_param": round(bits_transferred / float(total_params), 9),
        "parameter_reduction_ratio": round(1.0 - (active_params / float(total_params)), 6),
        "effective_density_gain": round(total_params / float(active_params), 6),
    }


class JFC3PCarvedModel:
    """Unified JFC-3P prototype integrating Model Carving, Loom/mHC routing, and Oracle verification."""

    def __init__(self, gate: CarvedSublayerGate, router: LoomMHCRouter, oracle: BuildLangOracleHead | None = None) -> None:
        self.gate = gate
        self.router = router
        self.oracle = oracle if oracle is not None else BuildLangOracleHead()

    def evaluate_step(
        self,
        streams: Sequence[Sequence[float]],
        *,
        router_mode: str = "mhc",
        pre_loss_nats: float = 2.4,
        post_loss_nats: float = 1.6,
        num_examples: int = 1024,
    ) -> dict[str, Any]:
        health = validate_carving_health(self.gate)
        routed = self.router.route(streams, mode=router_mode)
        cap = (
            compute_capacity_bit_transfer(pre_loss_nats, post_loss_nats, num_examples, health.active_params, health.total_params)
            if health.active_params > 0
            else None
        )
        return {
            "carving_health": health.__dict__,
            "routing": {k: v for k, v in routed.items() if k != "outputs"},
            "capacity_diagnostics": cap,
        }
