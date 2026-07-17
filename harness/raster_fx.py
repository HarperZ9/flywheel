"""raster_fx.py: the telos raster kernels over real images.

The lane's dither and pixel-sort kernels operate on grayscale buffers;
this module feeds them either the seeded aperture plate (deterministic,
no upload needed) or a caller-supplied PNG, then returns the processed
image as PNG alongside the kernel's own measurement and receipt hashes.
Size is fenced, refusals are named, and the bridge runs the lane's own
code end to end.
"""
from __future__ import annotations

import base64
import hashlib
import io
import math
import random

from .telos_kernels import run_kernel

SCHEMA = "flywheel.telos-raster-fx/v1"
MAX_SIDE = 640

RASTER_KERNELS = ("raster.ordered-dither", "raster.pixel-sort-rows")

_GROUNDS = {"dark": (16, 20, 21), "ceramic": (238, 236, 231)}
_INKS = {"dark": 235, "ceramic": 18}


def _plate_gray(seed: int, width: int, height: int, ground: str):
    """The aperture plate rendered straight to grayscale for the kernels."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (width, height), _GROUNDS[ground][0])
    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    cx, cy, r_base = width * 0.5, height * 0.5, min(width, height) * 0.36
    ink = _INKS[ground]
    for _ in range(2600):
        a = rng.uniform(0, 2 * math.pi)
        band = rng.random()
        if band < 0.62:
            r0 = r_base * rng.uniform(0.86, 1.0)
            r1 = r0 + r_base * rng.uniform(0.015, 0.16)
            alpha = rng.uniform(0.28, 0.95)
        elif band < 0.86:
            r0 = r_base * rng.uniform(0.30, 0.86)
            r1 = r0 + r_base * rng.uniform(0.01, 0.05)
            alpha = rng.uniform(0.10, 0.36)
        else:
            r0 = r_base * rng.uniform(1.02, 1.34)
            r1 = r0 + r_base * rng.uniform(0.01, 0.10)
            alpha = rng.uniform(0.06, 0.24)
        shade = int(_GROUNDS[ground][0] + (ink - _GROUNDS[ground][0]) * alpha)
        draw.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a),
                   cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                  fill=shade, width=1)
    return img


def apply_fx(kernel: str, source: "dict | None" = None,
             args: "dict | None" = None) -> dict:
    """Run one raster kernel over a plate or a supplied PNG."""
    try:
        from PIL import Image
    except ImportError:
        return {"refused": True,
                "refusals": ["raster effects need Pillow on the engine side"]}
    if kernel not in RASTER_KERNELS:
        return {"refused": True,
                "refusals": [f"unknown raster kernel {kernel!r}; bridged: "
                             + ", ".join(RASTER_KERNELS)]}
    source = source or {}
    kind = source.get("kind", "plate")
    if kind == "plate":
        ground = source.get("ground", "dark")
        if ground not in _GROUNDS:
            return {"refused": True,
                    "refusals": [f"unknown ground {ground!r}"]}
        w = max(64, min(MAX_SIDE, int(source.get("width", 480))))
        h = max(64, min(MAX_SIDE, int(source.get("height", 300))))
        img = _plate_gray(int(source.get("seed", 58)), w, h, ground)
        source_note = f"plate seed {source.get('seed', 58)} {ground}"
    elif kind == "png_b64":
        try:
            img = Image.open(io.BytesIO(
                base64.b64decode(str(source.get("data", ""))))).convert("L")
        except Exception:
            return {"refused": True,
                    "refusals": ["the supplied image did not decode as PNG"]}
        if img.width > MAX_SIDE or img.height > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        source_note = "caller-supplied image (grayscale, size-fenced)"
    else:
        return {"refused": True,
                "refusals": [f"unknown source kind {kind!r}; use plate "
                             "or png_b64"]}

    pixels = list(img.tobytes())     # mode L: one byte per pixel, stable API
    payload = {"pixels": pixels, "width": img.width, "height": img.height,
               **(args or {})}
    out = run_kernel(kernel, payload, timeout=60.0)
    if "error" in out:
        return {"refused": True, "refusals": [out["error"]]}
    result = out["result"]
    processed = Image.new("L", (img.width, img.height))
    processed.putdata(result["output"])
    buf = io.BytesIO()
    processed.save(buf, "PNG")
    png = buf.getvalue()

    measurement = dict(result.get("measurement", {}))
    measurement.pop("measurement_hash", None)
    return {
        "refused": False,
        "refusals": [],
        "png_b64": base64.b64encode(png).decode("ascii"),
        "receipt": {
            "schema": SCHEMA,
            "kernel": kernel,
            "source": source_note,
            "size": [img.width, img.height],
            "kernel_measurement_hash":
                result.get("measurement", {}).get("measurement_hash", ""),
            "kernel_receipt_hash": result.get("receipt_hash", ""),
            "png_sha256": hashlib.sha256(png).hexdigest(),
            "note": "the hashes above are the lane's own; the png hash "
                    "binds what you see to what the kernel returned",
        },
        "measurement": measurement,
    }
