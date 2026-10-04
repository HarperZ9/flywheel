"""raw_ao_buffers.py -- read raw-native's float AO buffers and mask, and redo the reconcile.

raw-native 0.4.0 writes the two AO buffers as 32-bit float PFM (``Pf``, one
channel, scale -1.0 for little-endian, rows bottom-to-top) and the coverage mask
as 8-bit PGM (``P5``, 255 where a surface covers the pixel). The reconcile is
recomputed with the renderer's own arithmetic: the per-pixel difference is a
float32 subtraction, the squares accumulate in double precision in row-major
order, and the RMSE is rounded to float32 once at the end. That is what lets a
data-only checker reproduce the recorded RMSE bit for bit instead of nearly.

Pure data and arithmetic: this module runs nothing.
"""
from __future__ import annotations

import math
import struct


class BufferError(ValueError):
    """A buffer file that does not have the shape raw-native writes."""


def f32(x: float) -> float:
    """Round a Python float to the nearest float32, as the renderer stores it."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _header(data: bytes, magic: str) -> tuple[int, int, str, bytes]:
    parts, pos = [], 0
    for _ in range(3):
        end = data.find(b"\n", pos)
        if end < 0:
            raise BufferError(f"truncated {magic} header")
        parts.append(data[pos:end].decode("ascii", "replace"))
        pos = end + 1
    if parts[0] != magic:
        raise BufferError(f"expected {magic}, found {parts[0][:8]!r}")
    try:
        w, h = (int(v) for v in parts[1].split())
    except ValueError as e:
        raise BufferError(f"bad {magic} size line: {e}") from e
    if w <= 0 or h <= 0:
        raise BufferError(f"{magic} size must be positive")
    return w, h, parts[2], data[pos:]


def read_pfm(data: bytes) -> tuple[int, int, list]:
    """(width, height, rows top-down) of a one-channel little-endian PFM."""
    w, h, scale, body = _header(data, "Pf")
    if scale != "-1.0":
        raise BufferError(f"PFM scale {scale!r}; raw-native writes -1.0 (little-endian)")
    if len(body) != w * h * 4:
        raise BufferError(f"PFM body is {len(body)} bytes, expected {w * h * 4}")
    flat = struct.unpack(f"<{w * h}f", body)
    rows = [flat[r * w:(r + 1) * w] for r in range(h)]
    return w, h, rows[::-1]


def read_mask(data: bytes) -> tuple[int, int, list]:
    """(width, height, rows top-down) of an 8-bit PGM coverage mask."""
    w, h, maxval, body = _header(data, "P5")
    if maxval != "255":
        raise BufferError(f"PGM maxval {maxval!r}; raw-native writes 255")
    if len(body) != w * h:
        raise BufferError(f"PGM body is {len(body)} bytes, expected {w * h}")
    return w, h, [body[r * w:(r + 1) * w] for r in range(h)]


def reconcile(ss_rows: list, rt_rows: list, mask_rows: list,
              width: int, height: int) -> dict:
    """Covered pixel count, RMSE and maximum error of ss against rt."""
    total, n, max_err = 0.0, 0, 0.0
    for y in range(height):
        ss_row, rt_row, m_row = ss_rows[y], rt_rows[y], mask_rows[y]
        for x in range(width):
            if not m_row[x]:
                continue
            e = abs(f32(ss_row[x] - rt_row[x]))
            if e > max_err:
                max_err = e
            total += e * e
            n += 1
    rmse = f32(math.sqrt(total / n)) if n else 0.0
    return {"pixels": n, "rmse": rmse, "maxError": max_err}


def reconcile_files(files) -> dict:
    """The reconcile recomputed from ``ao_ss.pfm``, ``ao_rt.pfm`` and ``mask.pgm``
    bytes. Raises BufferError when the three disagree on size."""
    w, h, rt = read_pfm(files["ao_rt.pfm"])
    w2, h2, ss = read_pfm(files["ao_ss.pfm"])
    w3, h3, mask = read_mask(files["mask.pgm"])
    if (w, h) != (w2, h2) or (w, h) != (w3, h3):
        raise BufferError(f"buffer sizes differ: rt {w}x{h}, ss {w2}x{h2}, mask {w3}x{h3}")
    out = reconcile(ss, rt, mask, w, h)
    out.update(width=w, height=h)
    return out


def canonical_ao(data: bytes) -> tuple[int, int, bytes]:
    """A PFM's floats in superstack's canonical ``ao.f32`` form: little-endian
    float32, rows top-down, no header."""
    read_pfm(data)                      # validates scale and size
    w, h, _scale, body = _header(data, "Pf")
    row = w * 4
    return w, h, b"".join(body[(h - 1 - y) * row:(h - y) * row] for y in range(h))


def canonical_mask(data: bytes) -> tuple[int, int, bytes]:
    """A PGM mask in superstack's canonical ``mask.u8`` form: one byte, 0 or 1."""
    w, h, rows = read_mask(data)
    return w, h, bytes(1 if b else 0 for row in rows for b in row)
