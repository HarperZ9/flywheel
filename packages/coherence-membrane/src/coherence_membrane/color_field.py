"""ColorField -- the L0 color primitive (per-cell OKLab, UNVERIFIABLE-aware)."""
from __future__ import annotations

from dataclasses import dataclass

from .color import Triple, srgb_to_oklab
from .pngview import decode_png


@dataclass(frozen=True)
class ColorField:
    """A 2-D field of OKLab color triples with a first-class UNVERIFIABLE mask.

    lab     -- row-major, length width*height; each entry an (L, a, b) triple.
    unknown -- row-major bool mask, True where the cell is UNVERIFIABLE.
    """

    width: int
    height: int
    lab: tuple[Triple, ...]
    unknown: tuple[bool, ...]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("color field dimensions must be positive")
        n = self.width * self.height
        if len(self.lab) != n:
            raise ValueError(f"lab length {len(self.lab)} != {n}")
        if len(self.unknown) != n:
            raise ValueError(f"unknown length {len(self.unknown)} != {n}")

    def index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"({x},{y}) out of {self.width}x{self.height}")
        return y * self.width + x

    def at(self, x: int, y: int) -> Triple:
        return self.lab[self.index(x, y)]

    def is_unknown(self, x: int, y: int) -> bool:
        return self.unknown[self.index(x, y)]


def downscale_color_field(
    field: ColorField,
    new_width: int,
    new_height: int | None = None,
) -> ColorField:
    """Box-average (average-pool) a ColorField to a smaller size.

    If new_height is None, it is computed from new_width to preserve the
    original aspect ratio (integer, rounded down, minimum 1).

    Each output cell is the per-channel arithmetic mean of all source cells in
    its footprint.  A target cell is UNVERIFIABLE if ANY source cell in its
    footprint is UNVERIFIABLE (conservative, matching field_ops.downscale).

    This is the color analogue of field_ops.downscale (which is luminance-only).
    Pure function; deterministic.
    """
    if new_height is None:
        new_height = max(1, round(new_width * field.height / field.width))
    if new_width <= 0 or new_height <= 0:
        raise ValueError("target dimensions must be positive")
    if new_width > field.width or new_height > field.height:
        raise ValueError("downscale_color_field cannot upscale")

    w, h = field.width, field.height
    lab_out: list[Triple] = []
    unknown_out: list[bool] = []

    for ty in range(new_height):
        y0 = ty * h // new_height
        y1 = (ty + 1) * h // new_height
        if y1 <= y0:
            y1 = y0 + 1
        for tx in range(new_width):
            x0 = tx * w // new_width
            x1 = (tx + 1) * w // new_width
            if x1 <= x0:
                x1 = x0 + 1

            sum_L = sum_a = sum_b = 0.0
            count = 0
            unk = False
            for sy in range(y0, y1):
                for sx in range(x0, x1):
                    j = sy * w + sx
                    unk = unk or field.unknown[j]
                    L, a, b = field.lab[j]
                    sum_L += L
                    sum_a += a
                    sum_b += b
                    count += 1

            if count:
                lab_out.append((sum_L / count, sum_a / count, sum_b / count))
            else:
                lab_out.append((0.0, 0.0, 0.0))
            unknown_out.append(unk)

    return ColorField(new_width, new_height, tuple(lab_out), tuple(unknown_out))


def color_field_from_png(payload: bytes) -> ColorField:
    """Lower an 8-bit PNG into an OKLab ColorField. Raises PngDecodeError on
    anything undecodable (the caller fail-closes)."""
    img = decode_png(payload)
    n = img.width * img.height
    ch = img.channels
    px = img.pixels
    lab: list[Triple] = [(0.0, 0.0, 0.0) for _ in range(n)]
    for i in range(n):
        if ch == 1:
            v = px[i] / 255.0
            rgb = (v, v, v)
        elif ch == 2:
            v = px[i * 2] / 255.0
            rgb = (v, v, v)
        else:                       # 3=RGB or 4=RGBA (alpha ignored)
            base = i * ch
            rgb = (px[base] / 255.0, px[base + 1] / 255.0, px[base + 2] / 255.0)
        lab[i] = srgb_to_oklab(rgb)
    return ColorField(img.width, img.height, tuple(lab), (False,) * n)
