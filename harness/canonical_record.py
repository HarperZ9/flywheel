"""Canonical record v1: one byte form for a hashed JSON record, and one digest for a numeric array.

The text of record is docs/spec/canonical-record.md. The JSON form is RFC 8785 (JCS): keys sorted by
UTF-16 code unit, no whitespace, strings as raw UTF-8 with the JSON short escapes, numbers in the
ECMAScript Number-to-String form. Standard library only, so any checker can run it.

    python -m harness.canonical_record dumps FILE.json      # canonical bytes to stdout
    python -m harness.canonical_record sha256 FILE.json     # sha256 of the canonical bytes

Golden vectors: tests/data/canonical_vectors.json. Other implementations (JS and Python, in other
repositories) test against those vectors instead of importing this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys

SPEC = "canonical-record/1"
MAX_SAFE = 2**53 - 1
ARRAY_TAG = b"cr1-array"
DTYPES = {  # name: (struct code, item size)
    "bool": ("?", 1), "i8": ("b", 1), "u8": ("B", 1), "i16": ("h", 2), "u16": ("H", 2),
    "i32": ("i", 4), "u32": ("I", 4), "i64": ("q", 8), "u64": ("Q", 8), "f32": ("f", 4), "f64": ("d", 8),
}
_SHORT = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


class CanonicalError(ValueError):
    """The value has no canonical form (NaN, infinity, unsafe integer, lone surrogate, bad key)."""


def number(x) -> str:
    """ECMAScript Number::toString of a finite double, as RFC 8785 section 3.2.2.3 requires."""
    if isinstance(x, bool):
        raise CanonicalError("a boolean is not a number")
    if isinstance(x, int):
        if abs(x) > MAX_SAFE:
            raise CanonicalError(f"integer {x} is outside +/-(2**53 - 1)")
        return str(x)
    x = float(x)
    if not math.isfinite(x):
        raise CanonicalError(f"{x!r} has no canonical form")
    if x == 0:
        return "0"
    if x < 0:
        return "-" + number(-x)
    mant, _, exp = repr(x).partition("e")
    whole, _, frac = mant.partition(".")
    digits = (whole + frac).lstrip("0")
    point = len(whole) + int(exp or 0) - (len(whole + frac) - len(digits))
    digits = digits.rstrip("0")
    k = len(digits)
    if k <= point <= 21:
        return digits + "0" * (point - k)
    if 0 < point <= 21:
        return digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return "0." + "0" * (-point) + digits
    e = point - 1
    return digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))


def string(s: str) -> str:
    out = ['"']
    for ch in s:
        c = ord(ch)
        if 0xD800 <= c <= 0xDFFF:
            raise CanonicalError("lone surrogate in a string")
        if ch in _SHORT:
            out.append(_SHORT[ch])
        elif c < 0x20:
            out.append(f"\\u{c:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _key(k):
    if not isinstance(k, str):
        raise CanonicalError(f"object key {k!r} is not a string")
    string(k)  # refuses lone surrogates in keys too
    return k.encode("utf-16-be")


def text(value) -> str:
    """The canonical form as a str. Encode with UTF-8 for the bytes; dumps() does that."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return number(value)
    if isinstance(value, str):
        return string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(text(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=_key)
        return "{" + ",".join(string(k) + ":" + text(value[k]) for k in keys) + "}"
    raise CanonicalError(f"{type(value).__name__} is not a JSON value")


def dumps(value) -> bytes:
    return text(value).encode("utf-8")


def sha256(value) -> str:
    return hashlib.sha256(dumps(value)).hexdigest()


def array_header(dtype: str, shape) -> bytes:
    if dtype not in DTYPES:
        raise CanonicalError(f"dtype {dtype!r} is not one of {sorted(DTYPES)}")
    dims = [int(d) for d in shape]
    if any(d < 0 for d in dims):
        raise CanonicalError("negative dimension")
    return ARRAY_TAG + b"\x00" + dtype.encode() + b"\x00" + ",".join(map(str, dims)).encode() + b"\x00"


def _flatten(values):
    for v in values:
        if isinstance(v, (list, tuple)):
            yield from _flatten(v)
        else:
            yield v


def array_bytes(dtype: str, shape, values) -> bytes:
    """Header, then the values in C order as little-endian items. values may be nested lists."""
    code, size = DTYPES[dtype] if dtype in DTYPES else (None, 0)
    head = array_header(dtype, shape)
    flat = list(_flatten(values))
    count = math.prod(int(d) for d in shape)
    if len(flat) != count:
        raise CanonicalError(f"{len(flat)} values for shape {tuple(shape)}")
    if dtype.startswith("f") and not all(math.isfinite(float(v)) for v in flat):
        raise CanonicalError("non-finite value in a float array")
    return head + struct.pack("<" + code * count, *flat)


def array_sha256(dtype: str, shape, values) -> str:
    return hashlib.sha256(array_bytes(dtype, shape, values)).hexdigest()


def _strict_load(path):
    def refuse(token):
        raise CanonicalError(f"{token} has no canonical form")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh, parse_constant=refuse)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("dumps", "sha256"):
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: python -m harness.canonical_record {dumps|sha256} FILE.json", file=sys.stderr)
        return 2
    try:
        value = _strict_load(argv[1])
        if argv[0] == "dumps":
            sys.stdout.buffer.write(dumps(value) + b"\n")
        else:
            print(sha256(value))
    except CanonicalError as exc:
        print(f"no canonical form: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
