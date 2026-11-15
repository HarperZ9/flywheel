"""Vintage CGI render pipeline -- pure functions, stdlib only, deterministic.

render_vintage composes a 7-step pipeline:
  1. REUSE  color_field_from_png -> ColorField (OKLab)
  2. NEW    downscale_color_field -> smaller ColorField (box-average)
  3. REUSE  quantize / palettes.get_palette -> palette (OKLab triples)
  4. NEW    ordered_dither (Bayer) -> palette indices per pixel
  5. REUSE  field_ops.distance (SDF modulation, optional)
  6. NEW    nearest-neighbor upscale + scanlines (CRT effect)
  7. REUSE  encode_png -> output PNG bytes

Palette and colour accuracy
----------------------------
``palette_hex`` is the QUANTIZATION palette -- the set of colours the image was
reduced to during step 3/4.  The final PNG equals that palette exactly ONLY
when ``palette_exact`` (a field of RenderResult) is True, i.e. both
``scanlines=False`` and ``sdf_shade=False``.  When either effect is active,
scanlines or SDF intentionally modulate tone for the vintage look, so the
output PNG contains tones *derived from* the palette colours but not limited
to them.  This is by design and is disclosed by ``palette_exact = False``.

Determinism
-----------
Identical (source_png, params) → identical output_png bytes and output_sha256,
GUARANTEED on a fixed platform / Python build / zlib build (same machine).

Cross-platform caveat: ``color.py`` uses fractional ``**`` (libm pow) and
``pngencode`` uses zlib; both are build-dependent, so bit-identical output
across *different* machines or Python builds is NOT guaranteed.
"""
from __future__ import annotations

from dataclasses import dataclass

from .color import oklab_to_srgb, Triple, srgb_to_oklab
from .color_field import ColorField, color_field_from_png, downscale_color_field
from .color_quantize import quantize, palette_to_hex
from .dither import ordered_dither
from .field import Field, FieldKind
from .field_ops import distance, threshold
from .observation import sha256_hex
from .palettes import get_palette
from .pngencode import encode_png

# Upscale factor for the nearest-neighbor upsample in step 6.
# Output width = target_width * UPSCALE_FACTOR.
UPSCALE_FACTOR: int = 4


@dataclass(frozen=True)
class RenderResult:
    """Result of render_vintage: output PNG bytes and full provenance.

    palette_hex   -- the QUANTIZATION palette used during colour reduction.
    palette_exact -- True IFF the final PNG pixel colours are an exact subset of
                    palette_hex.  This holds only when both scanlines and
                    sdf_shade are disabled; either effect intentionally modulates
                    tone beyond the palette, making palette_exact False.
    """

    output_png: bytes
    source_sha256: str
    params: dict
    output_sha256: str
    palette_hex: list[str]
    palette_exact: bool


# ---------------------------------------------------------------------------
# Internal helpers -- pure, deterministic
# ---------------------------------------------------------------------------

def _palette_from_rgb(
    rgb_palette: list[tuple[int, int, int]],
) -> tuple[Triple, ...]:
    """Convert a list of (R, G, B) int tuples to OKLab triples."""
    return tuple(srgb_to_oklab((r / 255.0, g / 255.0, b / 255.0)) for r, g, b in rgb_palette)


def _palette_indices_to_lab(
    indices: tuple[int, ...],
    palette: tuple[Triple, ...],
    width: int,
    height: int,
) -> list[Triple]:
    """Map palette indices back to OKLab triples, row-major."""
    result: list[Triple] = []
    for i in range(height):
        for j in range(width):
            idx = indices[i * width + j]
            if idx < 0:
                result.append((0.0, 0.0, 0.0))
            else:
                result.append(palette[idx])
    return result


def _nearest_neighbor_upscale(
    pixels_rgb: list[tuple[int, int, int]],
    src_w: int,
    src_h: int,
    scale: int,
) -> list[tuple[int, int, int]]:
    """Nearest-neighbor upscale by integer scale factor. Deterministic."""
    assert len(pixels_rgb) == src_w * src_h, (
        f"pixels_rgb length {len(pixels_rgb)} != {src_w}*{src_h}={src_w * src_h}"
    )
    dst_w = src_w * scale
    dst_h = src_h * scale
    out: list[tuple[int, int, int]] = []
    for dy in range(dst_h):
        sy = dy // scale
        for dx in range(dst_w):
            sx = dx // scale
            out.append(pixels_rgb[sy * src_w + sx])
    return out


def _apply_scanlines(
    pixels_rgb: list[tuple[int, int, int]],
    width: int,
    height: int,
) -> list[tuple[int, int, int]]:
    """CRT scanline effect: darken alternate rows + a slight bloom on bright rows.

    - Even rows (0-indexed): darken to 65% of original (scanline gap).
    - Odd rows: apply subtle bloom (brighten by 10%, clamped to 255).
    Deterministic; no external state.
    """
    out: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            r, g, b = pixels_rgb[y * width + x]
            if y % 2 == 0:
                # Scanline gap: darken
                r = int(r * 65 // 100)
                g = int(g * 65 // 100)
                b = int(b * 65 // 100)
            else:
                # Slight bloom: brighten
                r = min(255, int(r * 110 // 100))
                g = min(255, int(g * 110 // 100))
                b = min(255, int(b * 110 // 100))
            out.append((r, g, b))
    return out


def _lab_to_luminance(lab: Triple) -> float:
    """OKLab L channel as approximate luminance (0=black, 1=white)."""
    return lab[0]  # L channel is perceptual lightness


def _build_luminance_field_from_color_field(field: ColorField) -> Field:
    """Derive a LUMINANCE Field from a ColorField via OKLab L channel."""
    values = tuple(_lab_to_luminance(lab) for lab in field.lab)
    return Field(field.width, field.height, FieldKind.LUMINANCE, values, field.unknown)


def _apply_sdf_shade(
    lab_pixels: list[Triple],
    sdf_field: Field,
    src_w: int,
    src_h: int,
) -> list[Triple]:
    """Modulate brightness by SDF for a vintage early-3D look.

    The SDF field is min-max normalised to [-1, 1] across its known values
    before applying the effect.  This means the actual geometry (inside vs.
    outside the original boundary) is NOT the driver; instead the effect is
    *relative-depth shading*: cells at the low end of the normalised range
    are darkened, cells at the high end are brightened, and the midpoint is
    unchanged.  On an all-inside image this still produces useful depth
    shading because interior SDF magnitudes vary with distance from the
    nearest boundary.

    Factor = 1.0 + 0.3 * sdf_norm, clamped to [0.5, 1.3], applied to the
    OKLab L channel.  Modulation is clamped and deterministic.
    Unknown SDF cells are left unmodified.
    """
    # Compute SDF range for normalization
    known_vals = [sdf_field.values[i] for i in range(len(sdf_field.values))
                  if not sdf_field.unknown[i]]
    if not known_vals:
        return lab_pixels

    sdf_min = min(known_vals)
    sdf_max = max(known_vals)
    sdf_range = sdf_max - sdf_min if sdf_max != sdf_min else 1.0

    result: list[Triple] = []
    for i, lab in enumerate(lab_pixels):
        if sdf_field.unknown[i]:
            result.append(lab)
            continue
        # Normalize SDF to [-1, 1]
        sdf_norm = 2.0 * (sdf_field.values[i] - sdf_min) / sdf_range - 1.0
        # Modulation: inside (negative) darkens, outside (positive) brightens
        # Factor in [0.5, 1.3] range
        factor = 1.0 + 0.3 * sdf_norm
        factor = max(0.5, min(1.3, factor))
        L, a, b = lab
        L_mod = max(0.0, min(1.0, L * factor))
        result.append((L_mod, a, b))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_vintage(
    source_png: bytes,
    *,
    target_width: int,
    palette_k: int = 8,
    palette: str | None = None,
    dither: bool = True,
    scanlines: bool = True,
    sdf_shade: bool = False,
) -> RenderResult:
    """Render a source PNG through a vintage CGI pipeline.

    Pipeline (step labels match the brief):
      1. REUSE  color_field_from_png(source_png) -> ColorField
      2. NEW    downscale_color_field(field, effective_target_width) -> smaller ColorField
                effective_target_width = min(target_width, source_width)
                (target_width larger than source is clamped, never upscales)
      3. REUSE  quantize(field, palette_k) OR palettes.get_palette(palette)
                -> OKLab palette triples
      4. NEW    ordered_dither (Bayer) mapping -> palette index per pixel
               (or nearest-only if dither=False)
      5. REUSE  field_ops.distance (SDF) -> modulate brightness for 3D shading
               (only if sdf_shade=True)
      6. NEW    nearest-neighbor upscale by UPSCALE_FACTOR + scanline/CRT effect
               (scanlines only if scanlines=True)
      7. REUSE  encode_png(...) -> output PNG bytes

    Palette accuracy
    ----------------
    ``palette_hex`` is the QUANTIZATION palette -- the colours the image was
    reduced to.  The output PNG equals that palette exactly only when
    ``result.palette_exact`` is True (i.e. both ``scanlines=False`` and
    ``sdf_shade=False``).  When either effect is active, the output contains
    tones derived from but not limited to the palette, and ``palette_exact``
    is False.  Dithering itself only ever emits palette colours; it does NOT
    break exactness.

    Args:
        source_png:   Raw bytes of an 8-bit RGB/RGBA/grayscale PNG.
        target_width: Desired width of the quantized low-res image (before
                      upscale).  If larger than the source width, it is
                      clamped to the source width (no upscaling).
                      Output width = effective_target_width * UPSCALE_FACTOR.
        palette_k:    Number of colors for median-cut quantization (used when
                      ``palette`` is None).
        palette:      Name of a fixed retro palette (e.g. 'cga', 'ega').
                      Overrides palette_k when provided.
        dither:       If True, apply Bayer ordered dithering during palette
                      mapping.  If False, use nearest-only (no dither).
        scanlines:    If True, apply CRT scanline effect in step 6.
        sdf_shade:    If True, compute an SDF from the luminance field and
                      modulate per-pixel brightness for an early-3D look.

    Returns:
        RenderResult with output_png bytes, source/output sha256 digests,
        the params dict, palette_hex list, and palette_exact flag.

    Determinism: identical (source_png, params) always yields identical
    output_png bytes and output_sha256 on the same platform/Python/zlib
    build.  Cross-machine bit-identity is NOT guaranteed (libm ``**``, zlib).
    """
    # Provenance anchor for the source
    source_sha256 = sha256_hex(source_png)

    # ------------------------------------------------------------------
    # Step 1 (REUSE): Decode source PNG into OKLab ColorField
    # ------------------------------------------------------------------
    color_field = color_field_from_png(source_png)

    # ------------------------------------------------------------------
    # Step 2 (NEW): Box-downscale ColorField to target_width
    # Clamp to source width: downscale_color_field cannot upscale.
    # ------------------------------------------------------------------
    effective_target_width = min(target_width, color_field.width)
    small_field = downscale_color_field(color_field, effective_target_width)
    small_w, small_h = small_field.width, small_field.height

    # ------------------------------------------------------------------
    # Step 3 (REUSE / NEW): Build OKLab palette
    # ------------------------------------------------------------------
    if palette is not None:
        # Named retro palette: convert RGB -> OKLab
        rgb_palette = get_palette(palette)
        oklab_palette: tuple[Triple, ...] = _palette_from_rgb(rgb_palette)
        # raw_indices needed only when dither=False; computed there (I4)
        raw_indices: tuple[int, ...] = ()
    else:
        raw_indices, oklab_palette = quantize(small_field, palette_k)

    # ------------------------------------------------------------------
    # Step 4 (NEW): Ordered Bayer dither (or nearest-only if dither=False)
    # ------------------------------------------------------------------
    if dither:
        palette_indices = ordered_dither(small_field, oklab_palette, bayer_size=4)
    else:
        if palette is not None:
            # Named palette, no dither: compute nearest now (only when used)
            from .color_quantize import _nearest as _cn
            raw_indices = tuple(
                -1 if small_field.unknown[i] else _cn(lab, oklab_palette)
                for i, lab in enumerate(small_field.lab)
            )
        # Preserve -1 sentinel for unknown cells; _palette_indices_to_lab maps -1 -> black
        palette_indices = tuple(raw_indices)

    # ------------------------------------------------------------------
    # Step 5 (REUSE): SDF shading (optional)
    # ------------------------------------------------------------------
    # Map indices to OKLab pixel list
    lab_pixels: list[Triple] = _palette_indices_to_lab(
        palette_indices, oklab_palette, small_w, small_h
    )

    if sdf_shade:
        # Derive luminance Field from the small ColorField
        lum_field = _build_luminance_field_from_color_field(small_field)
        # Threshold to OCCUPANCY (pixels brighter than mid-gray = inside)
        occ_field = threshold(lum_field, 0.5)
        # Compute SDF
        sdf_field = distance(occ_field)
        # Modulate brightness
        lab_pixels = _apply_sdf_shade(lab_pixels, sdf_field, small_w, small_h)

    # ------------------------------------------------------------------
    # Convert OKLab pixels -> 8-bit sRGB
    # ------------------------------------------------------------------
    rgb_pixels: list[tuple[int, int, int]] = []
    for lab in lab_pixels:
        r_f, g_f, b_f = oklab_to_srgb(lab)
        rgb_pixels.append((
            max(0, min(255, round(r_f * 255))),
            max(0, min(255, round(g_f * 255))),
            max(0, min(255, round(b_f * 255))),
        ))

    # ------------------------------------------------------------------
    # Step 6 (NEW): Nearest-neighbor upscale + CRT scanlines
    # ------------------------------------------------------------------
    upscaled = _nearest_neighbor_upscale(rgb_pixels, small_w, small_h, UPSCALE_FACTOR)
    dst_w = small_w * UPSCALE_FACTOR
    dst_h = small_h * UPSCALE_FACTOR

    if scanlines:
        upscaled = _apply_scanlines(upscaled, dst_w, dst_h)

    # Flatten to bytes
    pixel_bytes = bytearray()
    for r, g, b in upscaled:
        pixel_bytes.extend([r, g, b])

    # ------------------------------------------------------------------
    # Step 7 (REUSE): Encode to PNG bytes
    # ------------------------------------------------------------------
    output_png = encode_png(dst_w, dst_h, bytes(pixel_bytes), channels=3)

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------
    output_sha256 = sha256_hex(output_png)

    # Build palette_hex from the OKLab palette (reuse palette_to_hex)
    hex_colors = list(palette_to_hex(oklab_palette))

    # palette_exact: True only when no post-palette tone modulation is active
    palette_exact = not (scanlines or sdf_shade)

    # Build params dict
    params: dict = {
        "target_width": target_width,
        "effective_target_width": effective_target_width,
        "palette_k": palette_k,
        "palette": palette,
        "dither": dither,
        "scanlines": scanlines,
        "sdf_shade": sdf_shade,
    }

    return RenderResult(
        output_png=output_png,
        source_sha256=source_sha256,
        params=params,
        output_sha256=output_sha256,
        palette_hex=hex_colors,
        palette_exact=palette_exact,
    )
