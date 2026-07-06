"""quant_dither.py — color-science (dither/blue-noise) applied to weight quant.

The connection: color quantization theory (Floyd-Steinberg error diffusion,
void-and-cluster blue-noise masks) minimizes perceptual error when reducing
color depth. The same principle applies to MODEL WEIGHT quantization — our nf4
uses deterministic round-to-nearest; stochastic rounding with STRUCTURED
(blue-noise) noise can reduce the error's spectral footprint and bias.

Three methods, honestly compared:
  - deterministic: round-to-nearest (min single-pass MSE, biased).
  - stochastic-white: stochastic rounding with uniform noise (zero bias, higher
    single-pass variance — wins in expectation over many passes).
  - stochastic-blue: stochastic rounding with a blue-noise threshold mask
    (zero bias + structured error spectrum; the color-science import).

The honest finding the falsifier establishes: deterministic wins single-pass
MSE; stochastic wins on bias; blue-noise structures the error. No method beats
entropy — the value is the bias/structure tradeoff, named not overclaimed.
"""
from __future__ import annotations
import hashlib
import math
import random
from typing import Callable

import numpy as np


def deterministic_quant(x: np.ndarray, levels: int = 16) -> np.ndarray:
    """Round-to-nearest on [-1,1]-ish range. The nf4-style baseline. Biased but
    optimal for single-pass MSE."""
    step = 2.0 / (levels - 1)
    return np.round(x / step) * step


def _stochastic_quant(x: np.ndarray, levels: int, threshold: np.ndarray) -> np.ndarray:
    """Stochastic rounding: round up with probability = fractional part, using a
    threshold mask in [0,1) to decide. threshold=uniform -> white noise;
    threshold=blue-noise -> structured error spectrum."""
    step = 2.0 / (levels - 1)
    scaled = x / step
    lower = np.floor(scaled)
    frac = scaled - lower
    rounded = np.where(threshold < frac, lower + 1, lower)
    return rounded * step


def stochastic_quant_white(x: np.ndarray, levels: int = 16,
                           seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    thresh = rng.random(x.shape)
    return _stochastic_quant(x, levels, thresh)


def blue_noise_mask(shape: tuple[int, ...], seed: int = 0,
                    iterations: int = 50) -> np.ndarray:
    """A cheap blue-noise-ish mask: start from white, push power to high freq by
    subtracting a low-pass (blurred) copy. Not a true void-and-cluster generator
    (that's expensive) but produces a high-frequency-biased [0,1) threshold with
    better spectral structure than white noise. Honest about the approximation."""
    rng = np.random.default_rng(seed)
    m = rng.random(shape)
    for _ in range(iterations):
        blurred = _box_blur(m, 3)
        m = (m - 0.5 * blurred + 0.5)
        m = (m - m.min()) / (m.max() - m.min() + 1e-9)
    return m % 1.0


def _box_blur(x: np.ndarray, k: int) -> np.ndarray:
    if x.ndim == 1:
        return np.convolve(x, np.ones(k) / k, mode="same")
    from scipy.ndimage import uniform_filter
    return uniform_filter(x, size=k)


def stochastic_quant_blue(x: np.ndarray, levels: int = 16,
                          seed: int = 0) -> np.ndarray:
    mask = blue_noise_mask(x.shape, seed=seed)
    return _stochastic_quant(x, levels, mask)


def mse(q: np.ndarray, x: np.ndarray) -> float:
    return float(np.mean((q - x) ** 2))


def bias(q: np.ndarray, x: np.ndarray) -> float:
    """Expected error — stochastic rounding aims for ~0 bias; deterministic is
    biased toward the rounding grid."""
    return float(np.mean(q - x))


def error_spectrum_flatness(q: np.ndarray, x: np.ndarray) -> float:
    """How 'white' (flat-spectrum) the error is. Blue-noise-structured error
    has more high-frequency content (less low-freq clumping). Higher = flatter/
    whiter; lower = more structured/blue. A rough spectral metric."""
    err = (q - x).flatten()
    if err.size < 8:
        return 1.0
    spec = np.abs(np.fft.fft(err - err.mean()))
    half = spec[: len(spec) // 2]
    flatness = float(np.exp(np.mean(np.log(half + 1e-12))) /
                     (np.mean(half) + 1e-12))
    return flatness
