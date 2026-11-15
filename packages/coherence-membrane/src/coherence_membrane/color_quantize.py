"""OKLab palette quantization (deterministic median-cut) + measured ΔE error."""
from __future__ import annotations

from .color import Triple, delta_e_ok, oklab_to_srgb
from .color_field import ColorField


def _median_cut(colors: list[Triple], k: int) -> list[list[Triple]]:
    """Split `colors` into up to k boxes; split the widest-extent box at the
    median of its longest axis (deterministic)."""
    boxes: list[list[Triple]] = [list(colors)]
    while len(boxes) < k:
        # pick the splittable box with the largest single-axis extent
        best_i, best_axis, best_extent = -1, 0, -1.0
        for i, box in enumerate(boxes):
            if len(box) < 2:
                continue
            for ax in range(3):
                vals = [c[ax] for c in box]
                extent = max(vals) - min(vals)
                if extent > best_extent:
                    best_extent, best_i, best_axis = extent, i, ax
        if best_i < 0:
            break                                  # nothing left to split
        box = boxes[best_i]
        box.sort(key=lambda c: c[best_axis])       # split along the axis that won selection
        mid = len(box) // 2
        boxes[best_i : best_i + 1] = [box[:mid], box[mid:]]
    return boxes


def _mean(box: list[Triple]) -> Triple:
    n = len(box)
    return (sum(c[0] for c in box) / n, sum(c[1] for c in box) / n, sum(c[2] for c in box) / n)


def _nearest(lab: Triple, palette: tuple[Triple, ...]) -> int:
    best_i, best_d = 0, delta_e_ok(lab, palette[0])
    for i in range(1, len(palette)):
        d = delta_e_ok(lab, palette[i])
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def quantize(field: ColorField, k: int) -> tuple[tuple[int, ...], tuple[Triple, ...]]:
    """Median-cut quantize a ColorField to <= k OKLab colors. Returns
    (indices, palette); UNVERIFIABLE cells get index -1."""
    if k < 1:
        raise ValueError("k must be >= 1")
    known = [field.lab[i] for i in range(len(field.lab)) if not field.unknown[i]]
    if not known:
        return ((-1,) * len(field.lab), ())
    palette = tuple(_mean(box) for box in _median_cut(known, k) if box)
    indices = tuple(
        -1 if field.unknown[i] else _nearest(field.lab[i], palette)
        for i in range(len(field.lab))
    )
    return indices, palette


def quantization_error(field: ColorField, indices: tuple[int, ...], palette: tuple[Triple, ...]) -> dict:
    """Mean and max ΔE-OK between each known cell and its assigned palette color."""
    errs = [
        delta_e_ok(field.lab[i], palette[indices[i]])
        for i in range(len(indices))
        if indices[i] >= 0
    ]
    if not errs:
        return {"mean": 0.0, "max": 0.0}
    return {"mean": sum(errs) / len(errs), "max": max(errs)}


def palette_to_hex(palette: tuple[Triple, ...]) -> tuple[str, ...]:
    """Each OKLab palette color -> #rrggbb (via canonical OKLab->sRGB)."""
    out: list[str] = []
    for lab in palette:
        r, g, b = (round(c * 255) for c in oklab_to_srgb(lab))
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return tuple(out)
