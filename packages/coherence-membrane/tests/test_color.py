from __future__ import annotations

from coherence_membrane.color import (
    delta_e_ok,
    linear_to_srgb,
    oklab_to_srgb,
    relative_luminance,
    srgb_to_linear,
    srgb_to_oklab,
    wcag_contrast,
)


def test_gamma_roundtrip_and_anchors():
    assert abs(srgb_to_linear(0.0)) < 1e-12
    assert abs(srgb_to_linear(1.0) - 1.0) < 1e-12
    for c in (0.0, 0.04, 0.2, 0.5, 1.0):
        assert abs(linear_to_srgb(srgb_to_linear(c)) - c) < 1e-9


def test_oklab_canonical_anchors():
    # canonical Ottosson: sRGB white -> (1,0,0), black -> (0,0,0)
    L, a, b = srgb_to_oklab((1.0, 1.0, 1.0))
    assert abs(L - 1.0) < 1e-6 and abs(a) < 1e-6 and abs(b) < 1e-6
    L0, a0, b0 = srgb_to_oklab((0.0, 0.0, 0.0))
    assert abs(L0) < 1e-6 and abs(a0) < 1e-6 and abs(b0) < 1e-6


def test_oklab_roundtrip():
    for rgb in [(1, 0, 0), (0, 1, 0), (0, 0, 1), (0.2, 0.5, 0.8), (0.5, 0.5, 0.5)]:
        rgb = tuple(float(c) for c in rgb)
        rt = oklab_to_srgb(srgb_to_oklab(rgb))
        assert all(abs(rt[i] - rgb[i]) < 1e-6 for i in range(3))


def test_delta_e_ok_zero_and_positive():
    assert delta_e_ok((0.5, 0.0, 0.0), (0.5, 0.0, 0.0)) == 0.0
    d = delta_e_ok((0.5, 0.0, 0.0), (0.5, 0.1, 0.0))
    assert abs(d - 0.1) < 1e-12


def test_relative_luminance_anchors():
    assert abs(relative_luminance((0.0, 0.0, 0.0))) < 1e-12
    assert abs(relative_luminance((1.0, 1.0, 1.0)) - 1.0) < 1e-9


def test_wcag_contrast_black_white_is_21():
    # max WCAG contrast (black vs white) = (1+0.05)/(0+0.05) = 21
    assert abs(wcag_contrast((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) - 21.0) < 1e-9
    assert abs(wcag_contrast((0.3, 0.3, 0.3), (0.3, 0.3, 0.3)) - 1.0) < 1e-9
