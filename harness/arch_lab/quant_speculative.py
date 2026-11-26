"""BitNet b1.58 ternary + Groupwise INT4 quantization & EAGLE-3 speculative verifier.

Implements consumer-hardware inference levers for JFC-3P:
1. BitNet b1.58 absmean ternary quantization ({-1, 0, +1}) with multiply-free matvec.
2. Symmetric groupwise INT4 quantization ([-7, +7]) with compression & fidelity telemetry.
3. EAGLE-3-style lossless speculative decoding verifier (draft proposal + exact target
   rejection sampling / residual correction + planted corrupted-draft kill control).

Pure stdlib Python (CPU-safe, deterministic, <= 270 lines, every function <= 50 lines).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

from .memory import Mat, Vec, cosine_similarity, matvec


@dataclass(frozen=True)
class QuantizationMetrics:
    scheme: str
    rows: int
    cols: int
    bits_per_weight: float
    compression_vs_fp32: float
    compression_vs_fp16: float
    mse: float
    cosine_fidelity: float
    zero_fraction: float


@dataclass(frozen=True)
class BitNetQuantizedMatrix:
    codes: list[list[int]]  # values strictly in {-1, 0, +1}
    scale: float
    metrics: QuantizationMetrics


@dataclass(frozen=True)
class Int4QuantizedMatrix:
    codes: list[list[int]]  # values strictly in [-7, +7]
    scales: list[list[float]]
    group_size: int
    metrics: QuantizationMetrics


def _flatten(mat: Mat) -> Vec:
    return [v for row in mat for v in row]


def _matrix_mse(a: Mat, b: Mat) -> float:
    fa, fb = _flatten(a), _flatten(b)
    return sum((x - y) ** 2 for x, y in zip(fa, fb)) / max(1, len(fa))


def quantize_bitnet_158(weights: Mat, *, eps: float = 1e-8) -> BitNetQuantizedMatrix:
    """Absmean ternary quantization to {-1, 0, +1} (BitNet b1.58, arXiv:2504.12285)."""
    rows, cols = len(weights), len(weights[0]) if weights else 0
    total = rows * cols
    if total == 0:
        raise ValueError("weights matrix must be non-empty")
    absmean = sum(abs(v) for row in weights for v in row) / total
    scale = max(absmean, eps)
    codes: list[list[int]] = []
    zeros = 0
    for row in weights:
        qrow: list[int] = []
        for v in row:
            q = max(-1, min(1, int(round(v / scale))))
            if q == 0:
                zeros += 1
            qrow.append(q)
        codes.append(qrow)
    recon = dequantize_bitnet_158(codes, scale)
    bits_eff = math.log2(3.0) + (32.0 / total)
    metrics = QuantizationMetrics(
        scheme="bitnet_b1.58",
        rows=rows,
        cols=cols,
        bits_per_weight=bits_eff,
        compression_vs_fp32=32.0 / bits_eff,
        compression_vs_fp16=16.0 / bits_eff,
        mse=_matrix_mse(weights, recon),
        cosine_fidelity=cosine_similarity(_flatten(weights), _flatten(recon)),
        zero_fraction=zeros / total,
    )
    return BitNetQuantizedMatrix(codes=codes, scale=scale, metrics=metrics)


def dequantize_bitnet_158(codes: Sequence[Sequence[int]], scale: float) -> Mat:
    return [[float(q) * scale for q in row] for row in codes]


def bitnet_matvec(qmat: BitNetQuantizedMatrix, x: Sequence[float]) -> Vec:
    """Multiply-free ternary matvec: only add/sub in inner loop, one final scale."""
    out: Vec = []
    scale = qmat.scale
    for qrow in qmat.codes:
        acc = 0.0
        for q, xv in zip(qrow, x):
            if q == 1:
                acc += xv
            elif q == -1:
                acc -= xv
        out.append(acc * scale)
    return out


def quantize_int4_groupwise(
    weights: Mat, *, group_size: int = 16, eps: float = 1e-8
) -> Int4QuantizedMatrix:
    """Symmetric groupwise INT4 quantization to [-7, +7] with per-group FP16 scales."""
    rows, cols = len(weights), len(weights[0]) if weights else 0
    total = rows * cols
    if total == 0 or group_size <= 0:
        raise ValueError("weights must be non-empty and group_size > 0")
    codes: list[list[int]] = []
    scales: list[list[float]] = []
    zeros = 0
    for row in weights:
        qrow: list[int] = []
        srow: list[float] = []
        for start in range(0, cols, group_size):
            chunk = row[start : start + group_size]
            gscale = max(max(abs(v) for v in chunk) / 7.0, eps)
            srow.append(gscale)
            for v in chunk:
                q = max(-7, min(7, int(round(v / gscale))))
                if q == 0:
                    zeros += 1
                qrow.append(q)
        codes.append(qrow)
        scales.append(srow)
    recon = dequantize_int4_groupwise(codes, scales, group_size)
    n_groups = sum(len(sr) for sr in scales)
    bits_eff = 4.0 + (16.0 * n_groups / total)
    metrics = QuantizationMetrics(
        scheme=f"int4_g{group_size}",
        rows=rows,
        cols=cols,
        bits_per_weight=bits_eff,
        compression_vs_fp32=32.0 / bits_eff,
        compression_vs_fp16=16.0 / bits_eff,
        mse=_matrix_mse(weights, recon),
        cosine_fidelity=cosine_similarity(_flatten(weights), _flatten(recon)),
        zero_fraction=zeros / total,
    )
    return Int4QuantizedMatrix(codes=codes, scales=scales, group_size=group_size, metrics=metrics)


def dequantize_int4_groupwise(
    codes: Sequence[Sequence[int]], scales: Sequence[Sequence[float]], group_size: int
) -> Mat:
    out: Mat = []
    for qrow, srow in zip(codes, scales):
        row: Vec = []
        for idx, q in enumerate(qrow):
            row.append(float(q) * srow[idx // group_size])
        out.append(row)
    return out


def int4_matvec(qmat: Int4QuantizedMatrix, x: Sequence[float]) -> Vec:
    return matvec(dequantize_int4_groupwise(qmat.codes, qmat.scales, qmat.group_size), x)


@dataclass(frozen=True)
class SpeculativeDecodeReport:
    tokens_generated: int
    target_calls: int
    accepted_draft_tokens: int
    rejected_draft_tokens: int
    effective_speedup: float
    divergence_count: int
    divergence_rate: float
    tampered_tokens_accepted: int
    tokens: tuple[int, ...]


def _argmax(probs: Sequence[float]) -> int:
    return max(range(len(probs)), key=lambda i: probs[i])


def _sample_categorical(probs: Sequence[float], rng: random.Random) -> int:
    r = rng.random()
    acc = 0.0
    for idx, p in enumerate(probs):
        acc += p
        if r <= acc:
            return idx
    return len(probs) - 1


def _residual_distribution(target_p: Sequence[float], draft_q: Sequence[float]) -> Vec:
    diff = [max(0.0, p - q) for p, q in zip(target_p, draft_q)]
    s = sum(diff)
    if s <= 1e-12:
        return list(target_p)
    return [v / s for v in diff]


class Eagle3SpeculativeVerifier:
    """Lossless speculative verifier (EAGLE-3 style draft + exact target verification)."""

    def __init__(self, *, draft_len: int = 4, greedy: bool = True) -> None:
        if draft_len < 1:
            raise ValueError("draft_len must be >= 1")
        self.draft_len = draft_len
        self.greedy = greedy

    def decode_autoregressive(
        self,
        prefix: Sequence[int],
        max_new_tokens: int,
        target_fn: Callable[[Sequence[int]], Vec],
    ) -> list[int]:
        seq = list(prefix)
        out: list[int] = []
        for _ in range(max_new_tokens):
            tok = _argmax(target_fn(seq))
            seq.append(tok)
            out.append(tok)
        return out

    def _draft_block(
        self,
        seq: list[int],
        k: int,
        draft_fn: Callable[[Sequence[int]], Vec],
        rng: random.Random,
    ) -> tuple[list[int], list[Vec]]:
        draft_toks, draft_qs, tmp = [], [], seq[:]
        for _ in range(k):
            q = draft_fn(tmp)
            tok = _argmax(q) if self.greedy else _sample_categorical(q, rng)
            draft_toks.append(tok)
            draft_qs.append(q)
            tmp.append(tok)
        return draft_toks, draft_qs

    def _verify_block(
        self,
        seq: list[int],
        draft_toks: Sequence[int],
        draft_qs: Sequence[Vec],
        target_fn: Callable[[Sequence[int]], Vec],
        rng: random.Random,
        banned: set[int],
    ) -> tuple[list[int], int, int, int, bool]:
        emitted: list[int] = []
        acc = rej = bad = 0
        for dt, dq in zip(draft_toks, draft_qs):
            p = target_fn(seq)
            ok = (dt == _argmax(p)) if self.greedy else (rng.random() < min(1.0, p[dt] / max(dq[dt], 1e-12)))
            if ok:
                seq.append(dt)
                emitted.append(dt)
                acc += 1
                bad += 1 if dt in banned else 0
            else:
                rej += 1
                res = _argmax(p) if self.greedy else _sample_categorical(_residual_distribution(p, dq), rng)
                seq.append(res)
                emitted.append(res)
                return emitted, acc, rej, bad, False
        return emitted, acc, rej, bad, True

    def decode_speculative(
        self,
        prefix: Sequence[int],
        max_new_tokens: int,
        target_fn: Callable[[Sequence[int]], Vec],
        draft_fn: Callable[[Sequence[int]], Vec],
        *,
        seed: int = 7,
        forbidden_tokens: set[int] | None = None,
    ) -> SpeculativeDecodeReport:
        rng, seq, out, banned = random.Random(seed), list(prefix), [], forbidden_tokens or set()
        target_calls = accepted = rejected = tampered = 0
        while len(out) < max_new_tokens:
            k = min(self.draft_len, max_new_tokens - len(out))
            d_toks, d_qs = self._draft_block(seq, k, draft_fn, rng)
            target_calls += 1
            emitted, a, r, b, all_ok = self._verify_block(seq, d_toks, d_qs, target_fn, rng, banned)
            out.extend(emitted)
            accepted, rejected, tampered = accepted + a, rejected + r, tampered + b
            if all_ok and len(out) < max_new_tokens:
                p_bonus = target_fn(seq)
                bonus = _argmax(p_bonus) if self.greedy else _sample_categorical(p_bonus, rng)
                seq.append(bonus)
                out.append(bonus)
        baseline = self.decode_autoregressive(prefix, max_new_tokens, target_fn) if self.greedy else out
        div = sum(1 for a, b in zip(out, baseline) if a != b)
        return SpeculativeDecodeReport(
            len(out), target_calls, accepted, rejected,
            len(out) / max(1, target_calls), div, div / max(1, len(out)), tampered, tuple(out),
        )
