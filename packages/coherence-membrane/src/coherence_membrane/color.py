"""Canonical OKLab color (Bjorn Ottosson reference) + perceptual metrics.

Native, stdlib-only. RGB and OKLab values are 3-tuples of floats; sRGB is the
gamma-encoded [0,1] signal. This is the canonical transform (sRGB white -> Oklab
(1,0,0)); it is NOT quanta-color's spaces.py (which applies the XYZ->LMS matrix
to linear sRGB and is non-canonical)."""
from __future__ import annotations

import math

Triple = tuple[float, float, float]


def srgb_to_linear(c: float) -> float:
    """sRGB gamma decode (signal -> linear light), per channel."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    """sRGB gamma encode (linear light -> signal), per channel."""
    c = max(c, 0.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def _lin_to_oklab(r: float, g: float, b: float) -> Triple:
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_lin(L: float, a: float, b: float) -> Triple:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def srgb_to_oklab(rgb: Triple) -> Triple:
    """sRGB (gamma, [0,1]) -> canonical OKLab."""
    return _lin_to_oklab(*(srgb_to_linear(c) for c in rgb))


def oklab_to_srgb(lab: Triple) -> Triple:
    """OKLab -> sRGB (gamma), clamped to [0,1]."""
    return tuple(min(1.0, max(0.0, linear_to_srgb(c))) for c in _oklab_to_lin(*lab))


def delta_e_ok(lab1: Triple, lab2: Triple) -> float:
    """Perceptual color difference: Euclidean distance in OKLab."""
    return math.sqrt(sum((lab1[i] - lab2[i]) ** 2 for i in range(3)))


def relative_luminance(rgb: Triple) -> float:
    """WCAG/BT.709 relative luminance from sRGB (gamma) in [0,1]."""
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast(rgb1: Triple, rgb2: Triple) -> float:
    """WCAG contrast ratio between two sRGB colors (1.0 .. 21.0)."""
    l1, l2 = relative_luminance(rgb1), relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)
