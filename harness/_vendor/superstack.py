# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Zain Dana Harper
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Algorithms by others, each under terms that allow this file's MIT licence:
#   mulberry32: Tommy Ettinger, 2017, CC0 1.0 public domain dedication.
#   xmur3: bryc (github.com/bryc/code), public domain, MIT fallback,
#     Copyright (c) 2024 bryc.
#   OKLab matrices: Bjorn Ottosson, 2020, public domain, MIT fallback.
#   K-weighting constants for rates other than 48 kHz: as published in
#     libebur128 (MIT); the 48 kHz table is ITU-R BS.1770-4's.
# Sources and dates: docs/LICENSING.md in the superstack repository.
"""superstack contract v0, Python implementation (standard library only).

One file carries every rule in SPEC.md: canonical JSON v2 and SHA-256, the
seed rule, the flick clock, the receipt with its two verdicts, OKLab and the
risk tokens, the s16le sound forms with the loudness meter, and the export
writers. superstack.mjs and superstack.hpp implement the same rules; all
three must pass every file in vectors/. Python 3.11 or later.
"""
from __future__ import annotations

import hashlib
import math
import re

CONTRACT = "superstack/0"
VERSION = "0.1.0"
RECEIPT_SCHEMA = "superstack.receipt/1"
SCENE_KINDS = ("superstack.scene/1", "superstack.sound/1")
MAX_SAFE_INTEGER = 2 ** 53 - 1

# ---------------------------------------------------------------- canonical JSON v2

_NUM = re.compile(r"(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?")


def positional(sign: str, int_part: str, frac: str, exp: int) -> str:
    """Write a decimal given as sign, digits and exponent in plain notation:
    no exponent, no leading or trailing zeros beyond one leading '0.'."""
    digits = int_part + frac
    point = len(int_part) + exp
    stripped = digits.lstrip("0")
    point -= len(digits) - len(stripped)
    digits = stripped.rstrip("0")
    if not digits:
        return "0"
    if point <= 0:
        body = "0." + "0" * (-point) + digits
    elif point >= len(digits):
        body = digits + "0" * (point - len(digits))
    else:
        body = digits[:point] + "." + digits[point:]
    return sign + body


def canonical_number(x) -> str:
    """Integers in the safe range bare; every float as its shortest
    round-trip decimal written without an exponent."""
    if isinstance(x, bool):
        raise TypeError("bool is not a number")
    if isinstance(x, int):
        if abs(x) > MAX_SAFE_INTEGER:
            raise ValueError("integer outside the safe range")
        return str(x)
    if not isinstance(x, float):
        raise TypeError(f"not a number: {type(x).__name__}")
    if not math.isfinite(x):
        raise ValueError("non-finite number")
    if x == 0:
        return "0"
    m = _NUM.fullmatch(repr(x))
    sign, ip, fp, ex = m.group(1), m.group(2), m.group(3) or "", int(m.group(4) or 0)
    return positional(sign, ip, fp, ex)


_ESC = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def canonical_string(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if 0xD800 <= o <= 0xDFFF:
            raise ValueError("lone surrogate in string")
        if ch in _ESC:
            out.append(_ESC[ch])
        elif o < 0x20:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonical(v) -> str:
    """Canonical JSON v2 text. Keys sorted by Unicode code point."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return canonical_number(v)
    if isinstance(v, str):
        return canonical_string(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(canonical(x) for x in v) + "]"
    if isinstance(v, dict):
        for k in v:
            if not isinstance(k, str):
                raise TypeError("object keys must be strings")
        return "{" + ",".join(canonical_string(k) + ":" + canonical(v[k]) for k in sorted(v)) + "}"
    raise TypeError(f"cannot canonicalize {type(v).__name__}")


def canonical_bytes(v) -> bytes:
    return canonical(v).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def canonical_sha256(v) -> str:
    return sha256_hex(canonical_bytes(v))


# ---------------------------------------------------------------- seed rule

SEED_RULE = "xmur3-mulberry32/1"
SEED_RULES = (SEED_RULE, "raw-pixel-hash/1", "fnv1a32-mulberry32", "studio-engine-lcg/1", "splitmix-fnv/1")
M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & M32


def utf16_units(s: str) -> list[int]:
    for ch in s:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            raise ValueError("lone surrogate in seed")
    b = s.encode("utf-16-le")
    return [b[i] | (b[i + 1] << 8) for i in range(0, len(b), 2)]


def xmur3(s: str) -> int:
    """bryc's xmur3 over UTF-16 code units; the first output of its return function."""
    units = utf16_units(s)
    h = (1779033703 ^ len(units)) & M32
    for u in units:
        h = _imul(h ^ u, 3432918353)
        h = ((h << 13) | (h >> 19)) & M32
    h = _imul(h ^ (h >> 16), 2246822507)
    h = _imul(h ^ (h >> 13), 3266489909)
    return (h ^ (h >> 16)) & M32


class Mulberry32:
    """Tommy Ettinger's mulberry32 (CC0)."""

    def __init__(self, seed_u32: int):
        self.a = seed_u32 & M32

    def next_u32(self) -> int:
        self.a = (self.a + 0x6D2B79F5) & M32
        t = self.a
        t = _imul(t ^ (t >> 15), t | 1)
        t = ((t + _imul(t ^ (t >> 7), t | 61)) & M32) ^ t
        return (t ^ (t >> 14)) & M32

    def next_float(self) -> float:
        return self.next_u32() / 4294967296.0


def rng(seed: str) -> Mulberry32:
    return Mulberry32(xmur3(seed))


def substream(seed: str, tag: str) -> str:
    return seed + "/" + tag


def pixel_hash(x: int, y: int, s: int) -> int:
    """raw-pixel-hash/1: raw-native's stateless (x, y, sample) integer hash."""
    h = (x * 374761393 + y * 668265263 + s * 2246822519) & M32
    h = _imul(h ^ (h >> 13), 1274126177)
    return (h ^ (h >> 16)) & M32


def pixel_hash01(x: int, y: int, s: int) -> float:
    return (pixel_hash(x, y, s) & 0xFFFFFF) / 16777216.0


# ---------------------------------------------------------------- flick clock

FLICKS_PER_SECOND = 705_600_000
SAMPLE_RATES = (8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 176400, 192000)


def flicks_per_frame(num: int, den: int = 1) -> int:
    """Flicks per frame at num/den frames per second; refuses rates that
    do not land on whole flicks."""
    if num <= 0 or den <= 0:
        raise ValueError("frame rate must be positive")
    if (FLICKS_PER_SECOND * den) % num:
        raise ValueError(f"{num}/{den} fps does not divide the flick clock")
    return FLICKS_PER_SECOND * den // num


def flicks_per_sample(rate: int) -> int:
    if rate <= 0 or FLICKS_PER_SECOND % rate:
        raise ValueError(f"rate {rate} does not divide the flick clock")
    return FLICKS_PER_SECOND // rate


# ---------------------------------------------------------------- rounding helper

def round6(x):
    """Round half up to 6 decimals; metrics that pass through log10 or pow
    are recorded this way so receipts agree across languages."""
    if x is None:
        return None
    return math.floor(x * 1e6 + 0.5) / 1e6


# ---------------------------------------------------------------- colour

def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def linear_srgb_to_oklab(r: float, g: float, b: float):
    """Ottosson's OKLab, published matrices (public domain, MIT fallback)."""
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return [0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_]


def oklab_to_linear_srgb(L: float, a: float, b: float):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ * l_ * l_, m_ * m_ * m_, s_ * s_ * s_
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]


def hex_to_srgb8(hexstr: str):
    h = hexstr.lstrip("#")
    if len(h) != 6:
        raise ValueError("expected #rrggbb")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def hex_to_oklab(hexstr: str):
    return linear_srgb_to_oklab(*(srgb_to_linear(c / 255.0) for c in hex_to_srgb8(hexstr)))


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio of two #rrggbb colours."""
    def lum(h):
        r, g, bl = (srgb_to_linear(c / 255.0) for c in hex_to_srgb8(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


RISK_LEVELS = ("low", "moderate", "elevated", "high")
RISK_TOKENS = {
    "light": {"low": "#186844", "moderate": "#5c5a66", "elevated": "#8f5200", "high": "#b3261e",
              "ink": "#15130f", "quiet": "#5d584e"},
    "dark": {"low": "#8fdc8a", "moderate": "#a9a6b4", "elevated": "#f0a848", "high": "#ff7a6b",
             "ink": "#ebe5d8", "quiet": "#9d978a"},
}
RISK_GROUNDS = {"light": ("#f4f3ef", "#ebe5d8", "#f2efe6"), "dark": ("#060608", "#070406", "#1d1622")}
VERDICT_TO_RISK = {
    "MATCH": "low", "VERIFIED": "low", "PASS": "low", "OK": "low",
    "UNVERIFIABLE": "moderate", "UNKNOWN": "moderate", "PENDING": "moderate",
    "DRIFT": "elevated", "WARN": "elevated", "STALE": "elevated", "REFUTED": "high",
    "FAIL": "high", "FAILED": "high", "REFUSED": "high", "ERROR": "high", "BROKEN": "high",
}


def risk_of(verdict) -> str:
    if verdict in RISK_LEVELS:
        return verdict
    return VERDICT_TO_RISK.get(str(verdict or "").strip().upper(), "moderate")


def hot_mark(levels) -> int:
    """Index of the one mark drawn hot: highest liability, first on a tie."""
    best, rank = -1, -1
    for i, lv in enumerate(levels):
        r = RISK_LEVELS.index(risk_of(lv))
        if r > rank:
            best, rank = i, r
    return best


# ---------------------------------------------------------------- sound forms

def quantize_s16(samples) -> bytes:
    """Float samples in [-1, 1] to s16le: clamp, then floor(v * 32767 + 0.5)."""
    out = bytearray()
    for x in samples:
        v = max(-1.0, min(1.0, float(x)))
        out += (math.floor(v * 32767.0 + 0.5) & 0xFFFF).to_bytes(2, "little")
    return bytes(out)


def s16_to_floats(pcm: bytes):
    return [int.from_bytes(pcm[i:i + 2], "little", signed=True) / 32767.0 for i in range(0, len(pcm), 2)]


def wav_s16(pcm: bytes, rate: int, channels: int) -> bytes:
    """The canonical 44-byte RIFF header for s16le PCM, then the samples."""
    n = len(pcm)
    hdr = (b"RIFF" + (36 + n).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
           + (1).to_bytes(2, "little") + channels.to_bytes(2, "little") + rate.to_bytes(4, "little")
           + (rate * channels * 2).to_bytes(4, "little") + (channels * 2).to_bytes(2, "little")
           + (16).to_bytes(2, "little") + b"data" + n.to_bytes(4, "little"))
    return hdr + bytes(pcm)


def ppm_rgb8(rgb: bytes, width: int, height: int) -> bytes:
    return f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(rgb)


def pgm_u8(gray: bytes, width: int, height: int) -> bytes:
    return f"P5\n{width} {height}\n255\n".encode("ascii") + bytes(gray)


# ITU-R BS.1770-4 K-weighting. At 48 kHz the standard's table is used as
# printed; other rates derive the same filters (the derivation libebur128 uses).
_K48 = ((1.53512485958697, -2.69169618940638, 1.19839281085285, -1.69065929318241, 0.73248077421585),
        (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621))
METER = "superstack-bs1770/1"


def k_weighting(rate: int):
    if rate == 48000:
        return _K48
    k = math.tan(math.pi * 1681.974450955533 / rate)
    q = 0.7071752369554196
    vh = 10.0 ** (3.999843853973347 / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf = ((vh + vb * k / q + k * k) / a0, 2.0 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0,
             2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0)
    k = math.tan(math.pi * 38.13547087602444 / rate)
    q = 0.5003270373238773
    a0 = 1.0 + k / q + k * k
    high = (1.0, -2.0, 1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0)
    return shelf, high


def _biquad(x, c):
    b0, b1, b2, a1, a2 = c
    y, x1, x2, y1, y2 = [], 0.0, 0.0, 0.0, 0.0
    for v in x:
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y.append(o)
    return y


def _loud(p: float) -> float:
    return -0.691 + 10.0 * math.log10(p) if p > 0 else -math.inf


def integrated_lufs(samples, rate: int, channels: int = 1):
    """BS.1770 integrated loudness, 400 ms blocks at 100 ms hops, absolute
    gate -70 LUFS, relative gate -10 LU. Interleaved floats in. Returns None
    when the signal is shorter than one block, silent, or the rate is not
    a multiple of 10 Hz. Every sum runs in index order."""
    if channels not in (1, 2) or rate not in SAMPLE_RATES or rate % 10:
        return None
    filt = k_weighting(rate)
    chans = [_biquad(_biquad([samples[i] for i in range(c, len(samples), channels)], filt[0]), filt[1])
             for c in range(channels)]
    n = len(chans[0])
    block, hop = rate * 4 // 10, rate // 10
    powers = []
    i = 0
    while i + block <= n:
        p = 0.0
        for z in chans:
            acc = 0.0
            for v in z[i:i + block]:
                acc += v * v
            p += acc / block
        powers.append(p)
        i += hop
    gated = [p for p in powers if _loud(p) > -70.0]
    if not gated:
        return None
    acc = 0.0
    for p in gated:
        acc += p
    rel = _loud(acc / len(gated)) - 10.0
    final = [p for p in gated if _loud(p) > rel]
    acc = 0.0
    for p in final:
        acc += p
    return _loud(acc / len(final))


def peak_dbfs(samples):
    peak = 0.0
    for v in samples:
        peak = max(peak, abs(v))
    return 20.0 * math.log10(peak) if peak > 0 else None


LOUDNESS_TARGETS = {
    "speech": {"integrated_lufs": -16.0, "tolerance_lu": 1.0, "true_peak_dbtp_max": -1.5},
    "music": {"integrated_lufs": -14.0, "tolerance_lu": 1.0, "true_peak_dbtp_max": -1.0},
    "interactive": {"integrated_lufs_max": -18.0, "sample_peak_dbfs_max": -1.0},
}


def loudness_check(sound_class: str, lufs, peak):
    """verified, refuted or unverifiable against the class target. v0 reads
    sample peak, a lower bound on true peak, so a pass is necessary only."""
    t = LOUDNESS_TARGETS.get(sound_class)
    if t is None or lufs is None or peak is None:
        return "unverifiable"
    if sound_class == "interactive":
        ok = lufs <= t["integrated_lufs_max"] and peak <= t["sample_peak_dbfs_max"]
    else:
        ok = abs(lufs - t["integrated_lufs"]) <= t["tolerance_lu"] and peak <= t["true_peak_dbtp_max"]
    return "verified" if ok else "refuted"


# ---------------------------------------------------------------- reconcile

PCM_TOLERANCE = {"max_abs_lsb": 2, "min_snr_db": 60.0}
RGB8_TOLERANCE = {"mean_abs_max": 1.0}


def identity(reference_sha256: str, candidate_sha256: str) -> str:
    return "MATCH" if reference_sha256 == candidate_sha256 else "DRIFT"


def _block(ref_sha, cand_sha, verdict, metrics, bounds, reason=None):
    out = {"identity": identity(ref_sha, cand_sha),
           "tolerance": {"verdict": verdict, "metrics": metrics, "bounds": bounds}}
    if reason:
        out["tolerance"]["reason"] = reason
    return out


def reconcile_pcm_s16(ref: bytes, cand: bytes, tol=None):
    tol = tol or PCM_TOLERANCE
    rs, cs = sha256_hex(ref), sha256_hex(cand)
    if len(ref) != len(cand) or len(ref) % 2:
        return _block(rs, cs, "unverifiable", {}, tol, "length differs from the reference")
    n = len(ref) // 2
    sig = err = 0.0
    max_d = exact = 0
    for i in range(n):
        r = int.from_bytes(ref[2 * i:2 * i + 2], "little", signed=True)
        d = int.from_bytes(cand[2 * i:2 * i + 2], "little", signed=True) - r
        sig += float(r * r)
        err += float(d * d)
        max_d = max(max_d, abs(d))
        exact += d == 0
    snr = None if err == 0 else (10.0 * math.log10(sig / err) if sig > 0 else -math.inf)
    metrics = {"max_abs_lsb": max_d, "exact_frac": exact / n if n else 1.0,
               "snr_db": None if snr is None else (round6(snr) if math.isfinite(snr) else None)}
    ok = max_d <= tol["max_abs_lsb"] and (snr is None or snr >= tol["min_snr_db"])
    return _block(rs, cs, "verified" if ok else "refuted", metrics, tol)


def reconcile_rgb8(ref: bytes, cand: bytes, tol=None):
    tol = tol or RGB8_TOLERANCE
    rs, cs = sha256_hex(ref), sha256_hex(cand)
    if len(ref) != len(cand) or len(ref) % 3 or not ref:
        return _block(rs, cs, "unverifiable", {}, tol, "size differs from the reference")
    total = max_d = exact_px = 0
    for p in range(len(ref) // 3):
        worst = 0
        for c in range(3):
            d = abs(cand[3 * p + c] - ref[3 * p + c])
            total += d
            worst = max(worst, d)
        max_d = max(max_d, worst)
        exact_px += worst == 0
    metrics = {"mean_abs": total / len(ref), "max_abs": max_d, "exact_pixels_frac": exact_px / (len(ref) // 3)}
    ok = metrics["mean_abs"] <= tol["mean_abs_max"]
    return _block(rs, cs, "verified" if ok else "refuted", metrics, tol)


def f32_rmse(ref: bytes, cand: bytes, mask: bytes | None = None):
    """RMSE of little-endian float32 arrays over mask != 0 (all if None)."""
    import struct
    a = struct.unpack(f"<{len(ref) // 4}f", ref)
    b = struct.unpack(f"<{len(cand) // 4}f", cand)
    acc, n = 0.0, 0
    for i in range(len(a)):
        if mask is None or mask[i]:
            d = b[i] - a[i]
            acc += d * d
            n += 1
    return math.sqrt(acc / n) if n else None


# ---------------------------------------------------------------- receipt

_HEX64 = re.compile(r"[0-9a-f]{64}")
_REQUIRED = ("schema", "producer", "backend", "scene_sha256", "seed", "seed_rule", "seed_u32", "time",
             "media", "content_sha256", "outputs", "reconcile", "does_not_prove", "receipt_sha256")


def seal(body: dict) -> dict:
    """Return a copy with receipt_sha256 set over the canonical body."""
    out = {k: v for k, v in body.items() if k != "receipt_sha256"}
    out["receipt_sha256"] = canonical_sha256(out)
    return out


def make_receipt(*, producer, version, backend, scene, media, content: bytes, outputs=None,
                 reference=None, reconcile=None, does_not_prove=(), seed_rule=SEED_RULE):
    seed = scene.get("seed")
    rec = {
        "schema": RECEIPT_SCHEMA,
        "producer": {"name": producer, "version": version},
        "backend": backend,
        "scene_sha256": canonical_sha256(scene),
        "seed": seed,
        "seed_rule": seed_rule,
        "seed_u32": xmur3(seed) if (seed is not None and seed_rule == SEED_RULE) else None,
        "time": {"base": "flicks", "per_second": FLICKS_PER_SECOND, "t": scene.get("t_flicks", 0)},
        "media": media,
        "content_sha256": sha256_hex(content),
        "outputs": dict(outputs or {}),
        "reconcile": None,
        "does_not_prove": list(does_not_prove),
    }
    if reconcile is not None:
        rec["reconcile"] = {"reference": reference, **reconcile}
    return seal(rec)


def _blank(s: str) -> bool:
    """Blank means only U+0020, U+0009, U+000A and U+000D (the same set in every language)."""
    return all(ch in " \t\n\r" for ch in s)


def _is_int(v):
    """An integer field holds a number with an integral value in the safe
    range; 3.0 counts, True does not (the same test in every language)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return abs(v) <= MAX_SAFE_INTEGER
    return isinstance(v, float) and math.isfinite(v) and v == math.floor(v) and abs(v) <= MAX_SAFE_INTEGER


def _int_in(v, options) -> bool:
    return _is_int(v) and v in options


def _text(v) -> bool:
    return isinstance(v, str) and v != ""


def _audio_errors(media) -> list[str]:
    errs = []
    rate = media.get("rate")
    if not _int_in(rate, SAMPLE_RATES):
        errs.append("audio:rate")
    if media.get("format") != "s16le" or not _int_in(media.get("channels"), (1, 2)):
        errs.append("audio:format")
    if _int_in(rate, SAMPLE_RATES) and (not _is_int(media.get("frames")) or not _is_int(media.get("duration_flicks"))
                                        or media["duration_flicks"] != media["frames"] * flicks_per_sample(int(rate))):
        errs.append("audio:duration")
    access = media.get("access")
    if not isinstance(access, dict) or access.get("autoplay") is not False:
        errs.append("audio:autoplay")
    elif access.get("reduced_sound") not in ("silent", "still-frame"):
        errs.append("audio:reduced_sound")
    if media.get("content") == "speech" and isinstance(access, dict):
        if not _text(access.get("captions")):
            errs.append("audio:captions")
        if access.get("transcript") is not True:
            errs.append("audio:transcript")
    nar = media.get("narration")
    if nar is not None and not isinstance(nar, dict):
        errs.append("narration:type")
    elif nar is not None:
        for k in ("backend", "model", "voice", "text_sha256"):
            if not _text(nar.get(k)):
                errs.append("narration:" + k)
        if nar.get("reference") is not False:
            errs.append("narration:reference")
        if nar.get("hosted") is True and not _text(nar.get("snapshot")) and nar.get("reproducible") is not False:
            errs.append("narration:reproducible")
    return errs


def verify_receipt(rec) -> list[str]:
    """Error codes, sorted; an empty list means the receipt is well formed
    and its seal holds. It does not re-render anything."""
    if not isinstance(rec, dict):
        return ["type"]
    errs = [f"missing:{k}" for k in _REQUIRED if k not in rec]
    if errs:
        return sorted(errs)
    if rec["schema"] != RECEIPT_SCHEMA:
        errs.append("schema")
    dnp = rec["does_not_prove"]
    if not isinstance(dnp, list) or not dnp or not all(isinstance(s, str) and not _blank(s) for s in dnp):
        errs.append("does_not_prove")
    t = rec["time"]
    if (not isinstance(t, dict) or t.get("base") != "flicks" or not _int_in(t.get("per_second"), (FLICKS_PER_SECOND,))
            or not _is_int(t.get("t")) or t["t"] < 0):
        errs.append("time")
    for k in ("scene_sha256", "content_sha256", "receipt_sha256"):
        if not isinstance(rec[k], str) or not _HEX64.fullmatch(rec[k]):
            errs.append("hex:" + k)
    if rec["seed_rule"] not in SEED_RULES:
        errs.append("seed_rule")
    elif rec["seed_rule"] == SEED_RULE and rec["seed"] is not None:
        try:
            ok = isinstance(rec["seed"], str) and _is_int(rec["seed_u32"]) and rec["seed_u32"] == xmur3(rec["seed"])
        except ValueError:
            ok = False
        if not ok:
            errs.append("seed_u32")
    rc = rec["reconcile"]
    if rc is not None:
        ref = rc.get("reference") if isinstance(rc, dict) else None
        tol = rc.get("tolerance") if isinstance(rc, dict) else None
        if not isinstance(ref, dict) or not isinstance(ref.get("content_sha256"), str):
            errs.append("reconcile:reference")
        elif rc.get("identity") != identity(ref["content_sha256"], rec["content_sha256"]):
            errs.append("reconcile:identity")
        if not isinstance(tol, dict) or tol.get("verdict") not in ("verified", "refuted", "unverifiable"):
            errs.append("reconcile:verdict")
        elif tol["verdict"] == "unverifiable" and not _text(tol.get("reason")):
            errs.append("reconcile:reason")
    media = rec["media"]
    if not isinstance(media, dict) or media.get("kind") not in ("image", "audio", "video", "document"):
        errs.append("media:kind")
    elif media["kind"] == "audio":
        errs += _audio_errors(media)
    if not errs:
        body = {k: v for k, v in rec.items() if k != "receipt_sha256"}
        if canonical_sha256(body) != rec["receipt_sha256"]:
            errs.append("seal")
    return sorted(set(errs))


# ---------------------------------------------------------------- scenes

def validate_scene(scene) -> list[str]:
    if not isinstance(scene, dict):
        return ["type"]
    errs = []
    kind = scene.get("kind")
    if kind not in SCENE_KINDS:
        return ["kind"]
    if "seed" in scene and not isinstance(scene["seed"], str):
        errs.append("seed")
    t = scene.get("t_flicks", 0)
    if not _is_int(t) or t < 0:
        errs.append("t_flicks")
    if kind == "superstack.scene/1":
        f = scene.get("frame")
        if not isinstance(f, dict) or not all(_is_int(f.get(k)) and f[k] > 0 for k in ("width", "height")):
            errs.append("frame")
    else:
        if not _int_in(scene.get("rate"), SAMPLE_RATES):
            errs.append("rate")
        if not _int_in(scene.get("channels"), (1, 2)):
            errs.append("channels")
        d = scene.get("duration_samples")
        if not _is_int(d) or d <= 0:
            errs.append("duration_samples")
    return sorted(errs)
