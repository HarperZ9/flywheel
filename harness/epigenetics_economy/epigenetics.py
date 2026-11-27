# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""J13 Model Epigenetics: Zero-Inference LoRA Weight-Spectrum Forensics.

Computes exact Roy-Vetterli spectral effective rank exp(H_spec), Shannon
spectral entropy H_spec, top-1 singular energy concentration, and Frobenius
norm purely from saved weight matrices or LoRA factor pairs (B, A) using
pure-stdlib cyclic Jacobi eigendecomposition of the symmetric positive
semi-definite Gram matrix G = M^T M.

Zero third-party dependencies, zero prompts, and zero inference calls.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Sequence


class EpigeneticError(ValueError):
    """Raised fail-closed on malformed, non-finite, or zero-energy weight matrices."""


@dataclass(frozen=True)
class SpectralSignature:
    """Pure weight-space spectral forensics signature for one adapter block."""

    rows: int
    cols: int
    effective_rank: float
    spectral_entropy: float
    top1_energy_ratio: float
    top2_energy_ratio: float
    frobenius_norm: float
    singular_values_sq: tuple[float, ...]


def _validate_rect_matrix(mat: Sequence[Sequence[float]]) -> tuple[int, int]:
    if not mat:
        raise EpigeneticError("EMPTY_MATRIX")
    rows = len(mat)
    cols = len(mat[0])
    if cols == 0:
        raise EpigeneticError("EMPTY_COLUMNS")
    for row in mat:
        if len(row) != cols:
            raise EpigeneticError("RAGGED_MATRIX")
        for val in row:
            if not math.isfinite(float(val)):
                raise EpigeneticError("NON_FINITE_WEIGHT")
    return rows, cols


def _symmetric_gram(mat: Sequence[Sequence[float]]) -> list[list[float]]:
    """Build the smaller of M^T M (c x c) or M M^T (r x r) for exact SVD eigenvalues."""
    rows, cols = _validate_rect_matrix(mat)
    if cols <= rows:
        g = [[0.0] * cols for _ in range(cols)]
        for r in range(cols):
            for c in range(r, cols):
                acc = 0.0
                for k in range(rows):
                    acc += float(mat[k][r]) * float(mat[k][c])
                g[r][c] = acc
                g[c][r] = acc
        return g
    g = [[0.0] * rows for _ in range(rows)]
    for r in range(rows):
        for c in range(r, rows):
            acc = 0.0
            for k in range(cols):
                acc += float(mat[r][k]) * float(mat[c][k])
            g[r][c] = acc
            g[c][r] = acc
    return g


def _jacobi_symmetric_eigenvalues(gram: list[list[float]], *, sweeps: int = 16) -> list[float]:
    """Deterministic cyclic Jacobi eigensolver returning descending non-negative eigenvalues."""
    n = len(gram)
    a = [list(row) for row in gram]
    for _ in range(sweeps):
        max_off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) > max_off:
                    max_off = abs(apq)
                if abs(apq) <= 1.0e-16:
                    continue
                app = a[p][p]
                aqq = a[q][q]
                tau = (aqq - app) / (2.0 * apq)
                if tau >= 0.0:
                    t_rot = 1.0 / (tau + math.sqrt(1.0 + tau * tau))
                else:
                    t_rot = -1.0 / ((-tau) + math.sqrt(1.0 + tau * tau))
                cos_t = 1.0 / math.sqrt(1.0 + t_rot * t_rot)
                sin_t = t_rot * cos_t

                a[p][p] = app - t_rot * apq
                a[q][q] = aqq + t_rot * apq
                a[p][q] = 0.0
                a[q][p] = 0.0

                for k in range(n):
                    if k != p and k != q:
                        akp = a[k][p]
                        akq = a[k][q]
                        new_p = cos_t * akp - sin_t * akq
                        new_q = sin_t * akp + cos_t * akq
                        a[k][p] = new_p
                        a[p][k] = new_p
                        a[k][q] = new_q
                        a[q][k] = new_q
        if max_off <= 1.0e-15:
            break
    evs = [max(0.0, a[i][i]) for i in range(n)]
    evs.sort(reverse=True)
    return evs


def analyze_matrix_spectrum(mat: Sequence[Sequence[float]]) -> SpectralSignature:
    """Compute exact Roy-Vetterli effective rank and singular energy ratios for a weight matrix."""
    rows, cols = _validate_rect_matrix(mat)
    gram = _symmetric_gram(mat)
    s2 = _jacobi_symmetric_eigenvalues(gram)
    tot = sum(s2)
    if tot <= 1.0e-18:
        raise EpigeneticError("ZERO_ENERGY_MATRIX")

    h_spec = 0.0
    for val in s2:
        p_i = val / tot
        if p_i > 1.0e-15:
            h_spec -= p_i * math.log(p_i)
    eff_rank = math.exp(h_spec)
    top1 = s2[0] / tot
    top2 = sum(s2[:2]) / tot
    frob = math.sqrt(tot)
    return SpectralSignature(
        rows=rows,
        cols=cols,
        effective_rank=eff_rank,
        spectral_entropy=h_spec,
        top1_energy_ratio=top1,
        top2_energy_ratio=top2,
        frobenius_norm=frob,
        singular_values_sq=tuple(s2),
    )


def analyze_lora_factors(
    b_mat: Sequence[Sequence[float]],
    a_mat: Sequence[Sequence[float]],
    *,
    alpha: float = 1.0,
) -> SpectralSignature:
    """Compute exact spectrum of Delta W = alpha * (B @ A) via r x r factor Gram contraction.

    Exploits the identity spec(B @ A) == spec((B^T B)^{1/2} (A A^T)^{1/2}) by forming the
    exact r x r product M = alpha * (R_B @ R_A) using modified Gram-Schmidt QR on B (d_out x r)
    and A^T (d_in x r), avoiding ever materializing the full d_out x d_in weight delta.
    """
    b_rows, rank = _validate_rect_matrix(b_mat)
    a_rank, a_cols = _validate_rect_matrix(a_mat)
    if rank != a_rank:
        raise EpigeneticError(f"LORA_RANK_MISMATCH:{rank}!={a_rank}")
    if not math.isfinite(alpha) or alpha == 0.0:
        raise EpigeneticError("INVALID_LORA_ALPHA")

    def _thin_r(cols_list: list[list[float]]) -> list[list[float]]:
        r_dim = len(cols_list)
        n_len = len(cols_list[0])
        q_cols = [list(c) for c in cols_list]
        r_upper = [[0.0] * r_dim for _ in range(r_dim)]
        for j in range(r_dim):
            for i in range(j):
                dot = sum(q_cols[i][k] * q_cols[j][k] for k in range(n_len))
                r_upper[i][j] = dot
                for k in range(n_len):
                    q_cols[j][k] -= dot * q_cols[i][k]
            norm = math.sqrt(sum(v * v for v in q_cols[j]))
            r_upper[j][j] = norm
            if norm > 1.0e-15:
                inv = 1.0 / norm
                for k in range(n_len):
                    q_cols[j][k] *= inv
        return r_upper

    b_cols = [[float(b_mat[row][col]) for row in range(b_rows)] for col in range(rank)]
    at_cols = [[float(a_mat[row][col]) for col in range(a_cols)] for row in range(rank)]
    rb = _thin_r(b_cols)
    ra = _thin_r(at_cols)

    # Core r x r matrix: core = alpha * (R_B @ R_A^T) has identical non-zero singular values to alpha * B @ A
    core = [[0.0] * rank for _ in range(rank)]
    for i in range(rank):
        for j in range(rank):
            acc = 0.0
            for k in range(rank):
                acc += rb[i][k] * ra[j][k]
            core[i][j] = alpha * acc

    sig = analyze_matrix_spectrum(core)
    return SpectralSignature(
        rows=b_rows,
        cols=a_cols,
        effective_rank=sig.effective_rank,
        spectral_entropy=sig.spectral_entropy,
        top1_energy_ratio=sig.top1_energy_ratio,
        top2_energy_ratio=sig.top2_energy_ratio,
        frobenius_norm=sig.frobenius_norm,
        singular_values_sq=sig.singular_values_sq,
    )


def classify_spectral_regime(
    sig: SpectralSignature,
    *,
    collapse_eff_rank_threshold: float = 2.0,
    collapse_top1_threshold: float = 0.85,
) -> str:
    """Classify adapter weight spectrum into SHORTCUT_COLLAPSED vs MULTI_FEATURE_HONEST."""
    if sig.effective_rank <= collapse_eff_rank_threshold and sig.top1_energy_ratio >= collapse_top1_threshold:
        return "SHORTCUT_COLLAPSED"
    return "MULTI_FEATURE_HONEST"


def _canonical_receipt_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def seal_epigenetic_receipt(adapter_id: str, sig: SpectralSignature) -> dict[str, Any]:
    """Emit a deterministic, re-derivable SHA-256 weight-forensics receipt."""
    body: dict[str, Any] = {
        "schema": "flywheel.epigenetics-receipt/1",
        "adapter_id": adapter_id,
        "inference_calls": 0,
        "regime": classify_spectral_regime(sig),
        "signature": {
            k: (round(v, 12) if isinstance(v, float) else ([round(x, 12) for x in v] if isinstance(v, tuple) else v))
            for k, v in asdict(sig).items()
        },
    }
    digest = _canonical_receipt_digest(body)
    return {**body, "receipt_sha256": digest}


def verify_epigenetic_receipt(receipt: dict[str, Any]) -> bool:
    """Fail-closed SHA-256 verification of a sealed weight-forensics receipt."""
    stored = receipt.get("receipt_sha256")
    if not isinstance(stored, str) or len(stored) != 64:
        return False
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return _canonical_receipt_digest(body) == stored
