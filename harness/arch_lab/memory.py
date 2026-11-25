"""Linear algebra, mHC Birkhoff projection, and Fast-Weight Delta Memory.

Implements Schmidhuber Fast Weight Programmers (arXiv:2102.11174) with
Gated DeltaNet-2 decoupled erase/write gates (arXiv:2605.22791) and
DeepSeek mHC doubly-stochastic Sinkhorn-Knopp residual mixing (arXiv:2512.24880).
Pure stdlib Python, CPU-only, <= 200 lines, every function <= 50 lines.
"""
from __future__ import annotations

import math
import random
from typing import Sequence

Vec = list[float]
Mat = list[list[float]]


def zeros(n: int) -> Vec:
    return [0.0] * n


def zeros_mat(rows: int, cols: int) -> Mat:
    return [[0.0] * cols for _ in range(rows)]


def rand_mat(rows: int, cols: int, scale: float, rng: random.Random) -> Mat:
    return [[rng.gauss(0.0, scale) for _ in range(cols)] for _ in range(rows)]


def matvec(m: Mat, x: Sequence[float]) -> Vec:
    return [sum(a * b for a, b in zip(row, x)) for row in m]


def vec_norm(x: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in x))


def l2_normalize(x: Sequence[float], eps: float = 1e-8) -> Vec:
    n = vec_norm(x)
    return [v / (n + eps) for v in x]


def cosine_similarity(a: Sequence[float], b: Sequence[float], eps: float = 1e-8) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (vec_norm(a) * vec_norm(b) + eps)


def sinkhorn_doubly_stochastic(raw: Mat, iters: int = 12, eps: float = 1e-9) -> Mat:
    """Project matrix onto Birkhoff polytope (DeepSeek mHC residual mixing)."""
    mat = [[math.exp(max(-20.0, min(20.0, v))) for v in row] for row in raw]
    n = len(mat)
    for _ in range(iters):
        for i in range(n):
            rs = sum(mat[i]) + eps
            mat[i] = [v / rs for v in mat[i]]
        for j in range(n):
            cs = sum(mat[i][j] for i in range(n)) + eps
            for i in range(n):
                mat[i][j] /= cs
    return mat


class FastWeightDeltaMemory:
    """Schmidhuber FWP + Gated DeltaNet-2 decoupled erase/write associative memory."""

    def __init__(
        self,
        key_dim: int,
        val_dim: int,
        *,
        erase_rate: float = 0.9,
        write_rate: float = 0.9,
        decay: float = 0.01,
    ) -> None:
        self.key_dim = key_dim
        self.val_dim = val_dim
        self.erase_rate = erase_rate
        self.write_rate = write_rate
        self.decay = decay
        self.matrix: Mat = zeros_mat(val_dim, key_dim)
        self.last_surprise: float = 0.0

    def reset(self) -> None:
        self.matrix = zeros_mat(self.val_dim, self.key_dim)
        self.last_surprise = 0.0

    def read(self, key: Sequence[float]) -> Vec:
        return matvec(self.matrix, l2_normalize(key))

    def write(self, key: Sequence[float], value: Sequence[float]) -> float:
        k = l2_normalize(key)
        v_hat = matvec(self.matrix, k)
        surprise = vec_norm([v - vh for v, vh in zip(value, v_hat)])
        self.last_surprise = surprise
        keep = 1.0 - self.decay
        for i in range(self.val_dim):
            row = self.matrix[i]
            delta_i = self.write_rate * value[i] - self.erase_rate * v_hat[i]
            for j in range(self.key_dim):
                row[j] = keep * row[j] + delta_i * k[j]
        return surprise


class StaticMemoryBaseline:
    """Frozen static projection baseline without test-time fast-weight updates."""

    def __init__(self, key_dim: int, val_dim: int, seed: int = 7) -> None:
        rng = random.Random(seed)
        self.matrix = rand_mat(val_dim, key_dim, 1.0 / math.sqrt(key_dim), rng)

    def write(self, key: Sequence[float], value: Sequence[float]) -> float:
        _ = (key, value)
        return 0.0

    def read(self, key: Sequence[float]) -> Vec:
        return matvec(self.matrix, l2_normalize(key))
