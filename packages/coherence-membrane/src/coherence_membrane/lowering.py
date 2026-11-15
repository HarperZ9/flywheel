"""Lowerings: external media -> Field (the afferent edge of the algebra)."""
from __future__ import annotations

from .field import Field, FieldKind
from .pngview import decode_png


def field_from_png(payload: bytes) -> Field:
    """Lower an 8-bit PNG into a LUMINANCE Field in [0, 1] (Rec.601 luma).

    Raises PngDecodeError (from pngview) on anything undecodable -- the caller
    (an organ) is responsible for fail-closed witnessing. Rec.601 weights match
    the existing phash convention (299/587/114) for cross-module consistency.
    """
    img = decode_png(payload)
    n = img.width * img.height
    ch = img.channels
    px = img.pixels
    values = [0.0] * n
    for i in range(n):
        if ch == 1:                         # grayscale
            luma = px[i]
        elif ch == 2:                       # grayscale + alpha
            luma = px[i * 2]
        else:                               # 3=RGB or 4=RGBA
            base = i * ch
            luma = (px[base] * 299 + px[base + 1] * 587 + px[base + 2] * 114) // 1000
        values[i] = luma / 255.0
    return Field(
        width=img.width,
        height=img.height,
        kind=FieldKind.LUMINANCE,
        values=tuple(values),
        unknown=(False,) * n,
    )
