"""Ordered (Bayer) dithering -- pure functions, stdlib only, deterministic.

Algorithm reference:
  Bayer, B. E. (1973). "An Optimum Method for Two-Level Rendition of
  Continuous-Tone Pictures." Proceedings of the IEEE International
  Conference on Communications. Vol. 1. 1973.

The Bayer matrix of size n is defined by the recurrence:
  M(1) = [[0]]
  M(2n) = 4*M(n) tiled 2x2, with offsets [[0,2],[3,1]] applied per tile.
  Normalized by dividing by n^2 so values lie in [0, 1).

ordered_dither maps each pixel of a ColorField to the nearest palette entry
using OKLab perceptual distance, with a Bayer threshold perturbation that
shifts the choice toward the 2nd-nearest entry when the threshold exceeds
the distance ratio.  This achieves spatial color diffusion without any
mutable state or error accumulation -- fully deterministic.
"""
from __future__ import annotations

from .color import Triple, delta_e_ok
from .color_field import ColorField


_VALID_N: tuple[int, ...] = (2, 4, 8)


def bayer_matrix(n: int) -> list[list[float]]:
    """Return the n×n Bayer threshold matrix, normalized to values in [0, 1).

    n must be one of {2, 4, 8}.  Values are the canonical Bayer ordered-dither
    thresholds, computed via the standard recursive construction:
        M(1) = [[0]]
        M(2n) = block-compose from M(n) with offsets [[0,2],[3,1]] * n^2
    then divided by n^2 so the result is in [0, 1).
    """
    if n not in _VALID_N:
        raise ValueError(f"bayer_matrix requires n in {sorted(_VALID_N)}, got {n}")

    # Build the integer matrix first via recurrence, normalize at the end.
    # The standard construction for the n×n Bayer matrix (n = power of 2):
    #   Start with the 2×2 base:  [[0, 2], [3, 1]]
    #   Each doubling step:
    #     M(2k) = concat of four k×k blocks arranged as:
    #       | 4*M(k)+0   4*M(k)+2 |
    #       | 4*M(k)+3   4*M(k)+1 |
    # After k doublings from the 2×2 base we have a 2^(k+1) × 2^(k+1) matrix
    # whose integer values are in [0, n^2) and are all distinct.
    # Normalize by dividing by n^2 to get [0, 1).

    # Base: 2×2
    m: list[list[int]] = [[0, 2], [3, 1]]
    size = 2
    while size < n:
        new_size = size * 2
        new_m = [[0] * new_size for _ in range(new_size)]
        for y in range(size):
            for x in range(size):
                v = m[y][x]
                new_m[y][x]                   = 4 * v + 0  # TL
                new_m[y][x + size]             = 4 * v + 2  # TR
                new_m[y + size][x]             = 4 * v + 3  # BL
                new_m[y + size][x + size]      = 4 * v + 1  # BR
        m = new_m
        size = new_size

    # Normalize by n^2 so values are in [0, 1)
    total = n * n
    return [[m[y][x] / total for x in range(n)] for y in range(n)]


def _nearest_two(lab: Triple, palette: tuple[Triple, ...]) -> tuple[int, int, float, float]:
    """Return (best_idx, second_idx, best_dist, second_dist) for a lab color."""
    dists = [(delta_e_ok(lab, palette[i]), i) for i in range(len(palette))]
    dists.sort()
    best_d, best_i = dists[0]
    if len(dists) > 1:
        second_d, second_i = dists[1]
    else:
        second_d, second_i = best_d, best_i
    return best_i, second_i, best_d, second_d


def ordered_dither(
    field: ColorField,
    palette: tuple[Triple, ...],
    *,
    bayer_size: int = 4,
) -> tuple[int, ...]:
    """Map each pixel of `field` to a palette index using Bayer ordered dithering.

    For each pixel at (x, y):
      1. Find the nearest and 2nd-nearest palette entry (by OKLab delta-E).
      2. Compute a normalized distance ratio:
             t = best_dist / (best_dist + second_dist)   in [0, 0.5]
         This measures how close the pixel is to the boundary between the two
         palette colors.  t near 0 = very close to best; t near 0.5 = midway.
      3. Compare against the Bayer threshold bayer[y % n][x % n] scaled to [0, 0.5]:
             scaled_thr = bayer[y%n][x%n] * 0.5
         If t > scaled_thr: keep the nearest palette index (confident assignment).
         If t <= scaled_thr: choose the 2nd-nearest (dither diffusion).
    For UNKNOWN cells (field.unknown[i] is True): use nearest without perturbation.

    Pure function; identical inputs -> identical outputs (deterministic).
    """
    if not palette:
        raise ValueError("palette must be non-empty")

    bm = bayer_matrix(bayer_size)
    n = bayer_size
    w = field.width

    result: list[int] = []
    for i, lab in enumerate(field.lab):
        x = i % w
        y = i // w
        is_unknown = field.unknown[i]

        best_i, second_i, best_d, second_d = _nearest_two(lab, palette)

        if is_unknown:
            # Unknown cell: preserve the -1 sentinel so downstream renders black
            result.append(-1)
            continue

        if len(palette) == 1:
            # Single-colour palette: no dither possible
            result.append(best_i)
            continue

        # Distance ratio: 0.0 = at best color, 0.5 = equidistant from both
        total_d = best_d + second_d
        if total_d < 1e-12:
            result.append(best_i)
            continue
        t = best_d / total_d  # in [0.0, 0.5]

        # Bayer threshold scaled to [0, 0.5]
        scaled_thr = bm[y % n][x % n] * 0.5

        if t <= scaled_thr:
            result.append(second_i)
        else:
            result.append(best_i)

    return tuple(result)
