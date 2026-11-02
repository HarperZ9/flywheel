"""64-bit SimHash over word shingles, and line hashes for boilerplate.

Both use blake2b, so results are identical across machines and runs.
Near-duplicates are found by banding: four 16-bit bands, so any two hashes
within Hamming distance 3 share at least one band exactly.
"""

import hashlib
import re

_WORD = re.compile(r"[a-z0-9]+")
BANDS = 4
MAX_HAMMING = 3


def _h64(data: str) -> int:
    return int.from_bytes(hashlib.blake2b(data.encode("utf-8", "replace"),
                                          digest_size=8).digest(), "big")


# Lane packing: 64 counters of 16 bits each live in one Python int, so a
# shingle costs eight table lookups and one big-int add instead of 64 adds.
_LANE = 16
_SPREAD = [sum(((v >> b) & 1) << (_LANE * b) for b in range(8)) for v in range(256)]
MAX_GRAMS = (1 << (_LANE - 1)) - 1


def _spread64(h: int) -> int:
    out = 0
    for i in range(8):
        out |= _SPREAD[(h >> (8 * i)) & 0xFF] << (_LANE * 8 * i)
    return out


def simhash(text: str, shingle: int = 3) -> int:
    words = _WORD.findall(text.lower())
    if not words:
        return 0
    grams = [" ".join(words[i:i + shingle])
             for i in range(max(1, len(words) - shingle + 1))][:MAX_GRAMS]
    acc = 0
    for g in grams:
        acc += _spread64(_h64(g))
    half, out, mask = len(grams) / 2.0, 0, (1 << _LANE) - 1
    for bit in range(64):
        if ((acc >> (_LANE * bit)) & mask) > half:
            out |= 1 << bit
    return out


def bands(h: int) -> list[int]:
    """Band keys, each tagged with its band index so bands never collide."""
    return [(i << 16) | ((h >> (16 * i)) & 0xFFFF) for i in range(BANDS)]


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def line_hash(line: str) -> int:
    """Signed 63-bit hash of a normalised line, for SQLite INTEGER keys."""
    norm = " ".join(_WORD.findall(line.lower()))
    return _h64(norm) >> 1 if norm else 0
