"""Tests for coherence_membrane.retro -- vintage CGI render pipeline."""
from __future__ import annotations

from coherence_membrane.color import srgb_to_oklab, oklab_to_srgb
from coherence_membrane.color_field import ColorField
from coherence_membrane.dither import ordered_dither
from coherence_membrane.pngencode import encode_png
from coherence_membrane.pngview import decode_png
from coherence_membrane.observation import sha256_hex
from coherence_membrane.retro import (
    RenderResult,
    UPSCALE_FACTOR,
    _palette_from_rgb,
    _palette_indices_to_lab,
    render_vintage,
)


# ---------------------------------------------------------------------------
# Synthetic PNG fixture (programmatic, no binary files)
# ---------------------------------------------------------------------------

def _make_test_png(width: int = 8, height: int = 8) -> bytes:
    """Generate a small synthetic RGB PNG with a gradient pattern."""
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            r = int(255 * x / max(width - 1, 1))
            g = int(255 * y / max(height - 1, 1))
            b = 128
            pixels.extend([r, g, b])
    return encode_png(width, height, bytes(pixels), channels=3)


def _make_solid_png(r: int, g: int, b: int, width: int = 4, height: int = 4) -> bytes:
    """Generate a solid color PNG."""
    pixels = bytes([r, g, b] * (width * height))
    return encode_png(width, height, pixels, channels=3)


# ---------------------------------------------------------------------------
# RenderResult dataclass structure
# ---------------------------------------------------------------------------

def test_render_result_has_required_fields():
    """RenderResult must have output_png, source_sha256, params, output_sha256, palette_hex."""
    png = _make_test_png()
    result = render_vintage(png, target_width=4)
    assert isinstance(result.output_png, bytes)
    assert isinstance(result.source_sha256, str)
    assert isinstance(result.params, dict)
    assert isinstance(result.output_sha256, str)
    assert isinstance(result.palette_hex, list)


# ---------------------------------------------------------------------------
# Determinism -- the cardinal property
# ---------------------------------------------------------------------------

def test_determinism_same_params_same_output():
    """Rendering the same PNG with the same params MUST produce bit-identical output."""
    png = _make_test_png(8, 8)
    result1 = render_vintage(png, target_width=4, palette_k=4, dither=True, scanlines=True)
    result2 = render_vintage(png, target_width=4, palette_k=4, dither=True, scanlines=True)
    assert result1.output_png == result2.output_png, "Output PNG bytes must be identical"
    assert result1.output_sha256 == result2.output_sha256, "Output sha256 must be identical"


def test_determinism_different_param_different_output():
    """Changing one param MUST yield a different output hash."""
    png = _make_test_png(8, 8)
    result_k4 = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False)
    result_k8 = render_vintage(png, target_width=4, palette_k=8, dither=False, scanlines=False)
    assert result_k4.output_sha256 != result_k8.output_sha256, (
        "Different palette_k should produce different output"
    )


def test_determinism_dither_flag_changes_output():
    png = _make_test_png(8, 8)
    r_dither = render_vintage(png, target_width=4, palette_k=4, dither=True, scanlines=False)
    r_no_dither = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False)
    # dither on/off should produce different results (gradient input ensures this)
    assert r_dither.output_sha256 != r_no_dither.output_sha256


def test_determinism_scanlines_flag_changes_output():
    png = _make_test_png(8, 8)
    r_scan = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=True)
    r_no_scan = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False)
    assert r_scan.output_sha256 != r_no_scan.output_sha256


# ---------------------------------------------------------------------------
# Provenance -- sha256 fields
# ---------------------------------------------------------------------------

def test_source_sha256_matches_input():
    png = _make_test_png()
    result = render_vintage(png, target_width=4)
    assert result.source_sha256 == sha256_hex(png)


def test_output_sha256_matches_output_png():
    png = _make_test_png()
    result = render_vintage(png, target_width=4)
    assert result.output_sha256 == sha256_hex(result.output_png)


# ---------------------------------------------------------------------------
# Palette subset property
# ---------------------------------------------------------------------------

def test_palette_subset_all_output_colors_in_palette():
    """Every distinct RGB in the output PNG must be derivable from the palette_hex."""
    png = _make_test_png(8, 8)
    result = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False)

    # Decode the output PNG
    decoded = decode_png(result.output_png)
    assert decoded.channels == 3, "Output should be RGB"

    # Build the set of colors present in the output
    pixels = decoded.pixels
    n = decoded.width * decoded.height
    output_colors = set()
    for i in range(n):
        r, g, b = pixels[i * 3], pixels[i * 3 + 1], pixels[i * 3 + 2]
        output_colors.add((r, g, b))

    # Parse palette_hex -> RGB tuples
    palette_rgb = set()
    for hex_color in result.palette_hex:
        h = hex_color.lstrip('#')
        palette_rgb.add((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))

    # With scanlines off, every output color must be exactly in the palette
    for color in output_colors:
        assert color in palette_rgb, (
            f"Output color {color} not in palette {palette_rgb}. "
            "All output colors must be members of the declared palette."
        )


def test_palette_subset_named_retro_palette():
    """With a fixed named retro palette, all output colors come from that palette."""
    png = _make_test_png(8, 8)
    result = render_vintage(
        png, target_width=4, palette="cga", dither=False, scanlines=False
    )
    decoded = decode_png(result.output_png)
    pixels = decoded.pixels
    n = decoded.width * decoded.height

    output_colors = set()
    for i in range(n):
        r, g, b = pixels[i * 3], pixels[i * 3 + 1], pixels[i * 3 + 2]
        output_colors.add((r, g, b))

    palette_rgb = set()
    for hex_color in result.palette_hex:
        h = hex_color.lstrip('#')
        palette_rgb.add((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))

    for color in output_colors:
        assert color in palette_rgb, (
            f"Output color {color} not in CGA palette {palette_rgb}"
        )


# ---------------------------------------------------------------------------
# Output is a valid decodable PNG
# ---------------------------------------------------------------------------

def test_output_is_valid_png():
    png = _make_test_png(8, 8)
    result = render_vintage(png, target_width=4)
    decoded = decode_png(result.output_png)
    assert decoded.width > 0
    assert decoded.height > 0
    assert decoded.channels == 3


def test_output_has_expected_dimensions():
    """Output width should be target_width * upscale_factor."""
    png = _make_test_png(16, 16)
    result = render_vintage(png, target_width=8)
    from coherence_membrane.retro import UPSCALE_FACTOR
    decoded = decode_png(result.output_png)
    assert decoded.width == 8 * UPSCALE_FACTOR


# ---------------------------------------------------------------------------
# Params dict
# ---------------------------------------------------------------------------

def test_params_contains_all_pipeline_params():
    png = _make_test_png()
    result = render_vintage(
        png, target_width=4, palette_k=6, dither=True, scanlines=False, sdf_shade=False
    )
    assert "target_width" in result.params
    assert "palette_k" in result.params
    assert "dither" in result.params
    assert "scanlines" in result.params
    assert "sdf_shade" in result.params
    assert result.params["target_width"] == 4
    assert result.params["palette_k"] == 6
    assert result.params["dither"] is True
    assert result.params["scanlines"] is False


def test_params_with_named_palette():
    png = _make_test_png()
    result = render_vintage(png, target_width=4, palette="ega")
    assert result.params.get("palette") == "ega"


# ---------------------------------------------------------------------------
# SDF shade (optional feature)
# ---------------------------------------------------------------------------

def test_sdf_shade_produces_valid_output():
    png = _make_test_png(8, 8)
    result = render_vintage(png, target_width=4, sdf_shade=True, dither=False, scanlines=False)
    decoded = decode_png(result.output_png)
    assert decoded.width > 0
    assert decoded.height > 0


def test_sdf_shade_changes_output():
    """sdf_shade=True vs False must yield different hashes on a non-trivial input."""
    png = _make_test_png(8, 8)
    r_sdf = render_vintage(png, target_width=4, dither=False, scanlines=False, sdf_shade=True)
    r_no = render_vintage(png, target_width=4, dither=False, scanlines=False, sdf_shade=False)
    assert r_sdf.output_sha256 != r_no.output_sha256


# ---------------------------------------------------------------------------
# Named retro palette
# ---------------------------------------------------------------------------

def test_named_palette_cga():
    png = _make_test_png(8, 8)
    result = render_vintage(png, target_width=4, palette="cga")
    assert len(result.palette_hex) == 4  # CGA has 4 colors


def test_named_palette_ega():
    png = _make_test_png(8, 8)
    result = render_vintage(png, target_width=4, palette="ega")
    assert len(result.palette_hex) == 16  # EGA has 16 colors


def test_palette_hex_format():
    """All palette_hex entries are valid #rrggbb hex strings."""
    png = _make_test_png()
    result = render_vintage(png, target_width=4, palette_k=4)
    for h in result.palette_hex:
        assert h.startswith('#'), f"Palette entry {h!r} should start with #"
        assert len(h) == 7, f"Palette entry {h!r} should be 7 chars (#rrggbb)"
        int(h[1:], 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# End-to-end provenance round-trip
# ---------------------------------------------------------------------------

def test_end_to_end_provenance_round_trip():
    """Build a synthetic PNG, render it, verify the provenance fields are re-derivable."""
    source_png = _make_solid_png(200, 100, 50, 8, 8)
    result = render_vintage(source_png, target_width=4, palette_k=4)

    # Re-derive source_sha256
    assert result.source_sha256 == sha256_hex(source_png)

    # Re-derive output_sha256
    assert result.output_sha256 == sha256_hex(result.output_png)

    # output_png re-decodable
    decoded = decode_png(result.output_png)
    assert decoded.width > 0 and decoded.height > 0


# ---------------------------------------------------------------------------
# C1/C2 -- palette_exact field and scanlines/SDF disclosure (all 4 combinations)
# ---------------------------------------------------------------------------

def test_palette_exact_all_four_combinations():
    """palette_exact must be True IFF scanlines=False AND sdf_shade=False."""
    png = _make_test_png(8, 8)

    # (scanlines=False, sdf_shade=False) -> palette_exact=True
    r = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False, sdf_shade=False)
    assert r.palette_exact is True, "Both off -> palette_exact must be True"

    # (scanlines=True, sdf_shade=False) -> palette_exact=False
    r = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=True, sdf_shade=False)
    assert r.palette_exact is False, "scanlines on -> palette_exact must be False"

    # (scanlines=False, sdf_shade=True) -> palette_exact=False
    r = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=False, sdf_shade=True)
    assert r.palette_exact is False, "sdf_shade on -> palette_exact must be False"

    # (scanlines=True, sdf_shade=True) -> palette_exact=False
    r = render_vintage(png, target_width=4, palette_k=4, dither=False, scanlines=True, sdf_shade=True)
    assert r.palette_exact is False, "Both on -> palette_exact must be False"


def test_palette_exact_true_means_output_colors_in_palette():
    """When palette_exact is True, every distinct output colour IS in palette_hex."""
    png = _make_test_png(8, 8)
    result = render_vintage(
        png, target_width=4, palette_k=4, dither=False, scanlines=False, sdf_shade=False
    )
    assert result.palette_exact is True

    decoded = decode_png(result.output_png)
    px = decoded.pixels
    n = decoded.width * decoded.height
    output_colors = set()
    for i in range(n):
        output_colors.add((px[i * 3], px[i * 3 + 1], px[i * 3 + 2]))

    palette_rgb = set()
    for h in result.palette_hex:
        hx = h.lstrip('#')
        palette_rgb.add((int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)))

    for color in output_colors:
        assert color in palette_rgb, (
            f"palette_exact=True but output colour {color} not in palette {palette_rgb}"
        )


def test_palette_exact_false_with_scanlines_exceeds_palette_size():
    """When scanlines=True, palette_exact is False AND output colour count > palette size."""
    png = _make_test_png(8, 8)
    result = render_vintage(
        png, target_width=4, palette_k=4, dither=False, scanlines=True, sdf_shade=False
    )
    assert result.palette_exact is False

    decoded = decode_png(result.output_png)
    px = decoded.pixels
    n = decoded.width * decoded.height
    output_colors = set()
    for i in range(n):
        output_colors.add((px[i * 3], px[i * 3 + 1], px[i * 3 + 2]))

    assert len(output_colors) > len(result.palette_hex), (
        f"scanlines=True should produce more colours ({len(output_colors)}) "
        f"than the palette ({len(result.palette_hex)})"
    )


# ---------------------------------------------------------------------------
# C3 -- golden-hash test: same-platform determinism
# ---------------------------------------------------------------------------

def test_golden_hash_same_platform_determinism():
    """Same-platform golden: fixed input+params always yield this exact sha256.

    This is a same-platform golden hash -- it pins determinism and will catch
    any regression on this machine/Python/zlib build.  It is NOT a cross-machine
    bit-identity guarantee (libm ** and zlib are build-dependent).

    Input:  8x8 gradient PNG (R=x/7*255, G=y/7*255, B=128)
    Params: target_width=4, palette_k=4, dither=False, scanlines=False, sdf_shade=False
    """
    width, height = 8, 8
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            r = int(255 * x / max(width - 1, 1))
            g = int(255 * y / max(height - 1, 1))
            b = 128
            pixels.extend([r, g, b])
    source_png = encode_png(width, height, bytes(pixels), channels=3)

    result = render_vintage(
        source_png,
        target_width=4,
        palette_k=4,
        palette=None,
        dither=False,
        scanlines=False,
        sdf_shade=False,
    )

    # Same-platform golden hash (computed on this machine; will catch divergence)
    GOLDEN_HASH = "7a725808df70c62aa152ab6b6020e1b023afdf17bb61e8b3f961254294a0b72c"
    assert result.output_sha256 == GOLDEN_HASH, (
        f"Golden hash mismatch: got {result.output_sha256!r}, expected {GOLDEN_HASH!r}. "
        "This indicates a determinism regression on this platform/build."
    )


# ---------------------------------------------------------------------------
# I1 -- unknown cells render black, not palette[0]
# ---------------------------------------------------------------------------

def test_unknown_cell_renders_black_not_palette_zero():
    """Unknown cells must render black (OKLab 0,0,0), not palette[0].

    Previously, the -1 unknown sentinel was collapsed to index 0 (a real colour)
    via max(0, i), silently mapping UNVERIFIABLE data to a confident palette colour.
    Now -1 propagates to _palette_indices_to_lab which maps it to (0,0,0) = black.

    Uses a palette where palette[0] is clearly non-black (red), so the test
    distinguishes the two behaviours.
    """
    # Palette: index 0 = red, index 1 = green
    palette = (
        srgb_to_oklab((1.0, 0.0, 0.0)),
        srgb_to_oklab((0.0, 1.0, 0.0)),
    )
    # Cell 0: unknown, but OKLab very close to red (nearest would be index 0 = red)
    # Cell 1: known, close to green
    lab = (
        srgb_to_oklab((0.9, 0.1, 0.1)),
        srgb_to_oklab((0.1, 0.9, 0.1)),
    )
    cf = ColorField(2, 1, lab, (True, False))  # cell 0 is UNVERIFIABLE

    indices = ordered_dither(cf, palette, bayer_size=4)
    assert indices[0] == -1, "Unknown cell must produce -1 sentinel, not a palette index"

    # _palette_indices_to_lab must map -1 to black
    lab_pixels = _palette_indices_to_lab(indices, palette, 2, 1)
    assert lab_pixels[0] == (0.0, 0.0, 0.0), (
        f"Unknown cell must render as black OKLab (0,0,0), got {lab_pixels[0]}"
    )

    # Confirm black in sRGB -- not palette[0] (red)
    r_f, g_f, b_f = oklab_to_srgb(lab_pixels[0])
    r = max(0, min(255, round(r_f * 255)))
    g = max(0, min(255, round(g_f * 255)))
    b = max(0, min(255, round(b_f * 255)))
    assert (r, g, b) == (0, 0, 0), f"Unknown cell sRGB must be (0,0,0), got {(r,g,b)}"

    # palette[0] is red -- confirm the two are distinct
    r_f2, g_f2, b_f2 = oklab_to_srgb(palette[0])
    p0 = (
        max(0, min(255, round(r_f2 * 255))),
        max(0, min(255, round(g_f2 * 255))),
        max(0, min(255, round(b_f2 * 255))),
    )
    assert (r, g, b) != p0, (
        f"Test is vacuous: unknown-cell colour {(r,g,b)} == palette[0] {p0}. "
        "palette[0] must not be black for this test to be meaningful."
    )


# ---------------------------------------------------------------------------
# I2 -- target_width larger than source does not crash
# ---------------------------------------------------------------------------

def test_target_width_larger_than_source_does_not_crash():
    """target_width > source width must not crash; effective_target clamped to source."""
    # Source is 4x4; request target_width=999 (much larger than source)
    png = _make_test_png(4, 4)
    result = render_vintage(png, target_width=999, palette_k=4, dither=False, scanlines=False)

    # Must not raise; output must be decodable
    decoded = decode_png(result.output_png)
    assert decoded.width > 0
    assert decoded.height > 0

    # effective_target_width should be clamped to source width (4)
    assert result.params["effective_target_width"] == 4, (
        f"effective_target_width should be 4 (source width), "
        f"got {result.params['effective_target_width']}"
    )

    # Output dimensions follow effective_target_width * UPSCALE_FACTOR
    assert decoded.width == 4 * UPSCALE_FACTOR, (
        f"Output width {decoded.width} != effective 4 * {UPSCALE_FACTOR}"
    )

    # Both requested and effective target_width recorded in params
    assert result.params["target_width"] == 999
    assert result.params["effective_target_width"] == 4


# ---------------------------------------------------------------------------
# RenderResult.palette_exact field exists and has correct type
# ---------------------------------------------------------------------------

def test_render_result_palette_exact_field_exists():
    """RenderResult must have a palette_exact boolean field."""
    png = _make_test_png()
    result = render_vintage(png, target_width=4)
    assert hasattr(result, "palette_exact"), "RenderResult must have palette_exact field"
    assert isinstance(result.palette_exact, bool), "palette_exact must be a bool"
