# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""D6 Conditional Entropy and Lossless Bijection Verification Across Schema Mappings.

Measures Shannon entropy H(X), H(Y), and conditional entropy H(X | Y) over
discrete schema/format projections, verifying that lossless bijections achieve
H(X | Y) == 0.0 bits, zero injective collisions, and exact decode(encode(x)) == x
round-trip fidelity. Catches lossy projections and broken inverses fail-closed.
Pure Python standard library only.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


def _canonical_key(val: Any) -> str:
    return json.dumps(val, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class IsomorphismVerdict:
    """Fail-closed verdict for a candidate lossless mapping (encode, decode)."""

    ok: bool
    verdict: str
    sample_count: int
    unique_inputs: int
    unique_outputs: int
    input_entropy_bits: float
    output_entropy_bits: float
    conditional_entropy_bits: float
    collisions: int
    roundtrip_mismatches: int
    errors: tuple[str, ...]


def shannon_entropy_bits(values: Sequence[Any]) -> float:
    """Compute empirical Shannon entropy H(V) in base-2 bits."""
    if not values:
        return 0.0
    counts = Counter(_canonical_key(v) for v in values)
    total = float(len(values))
    ent = 0.0
    for cnt in counts.values():
        p = float(cnt) / total
        if p > 0.0:
            ent -= p * math.log2(p)
    return round(ent, 9)


def conditional_entropy_bits(xs: Sequence[Any], ys: Sequence[Any]) -> float:
    """Compute empirical conditional entropy H(X | Y) in base-2 bits.

    H(X | Y) == 0.0 iff Y uniquely determines X on every observed pair (lossless).
    H(X | Y) > 0.0 quantifies exact information loss in bits caused by projection.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have equal length")
    if not xs:
        return 0.0
    by_y: dict[str, list[str]] = defaultdict(list)
    for x_val, y_val in zip(xs, ys):
        by_y[_canonical_key(y_val)].append(_canonical_key(x_val))
    total = float(len(xs))
    cond_h = 0.0
    for x_bucket in by_y.values():
        p_y = float(len(x_bucket)) / total
        sub_counts = Counter(x_bucket)
        bucket_n = float(len(x_bucket))
        h_given_y = 0.0
        for cnt in sub_counts.values():
            p_xy = float(cnt) / bucket_n
            if p_xy > 0.0:
                h_given_y -= p_xy * math.log2(p_xy)
        cond_h += p_y * h_given_y
    return round(max(0.0, cond_h), 9)


def verify_lossless_bijection(
    samples: Sequence[Any],
    encode_fn: Callable[[Any], Any],
    decode_fn: Callable[[Any], Any],
    max_cond_entropy_bits: float = 1.0e-9,
) -> IsomorphismVerdict:
    """Verify injective zero-loss mapping H(X | Y) == 0 and exact decode(encode(x)) == x."""
    if not samples:
        return IsomorphismVerdict(
            ok=False,
            verdict="REJECT",
            sample_count=0,
            unique_inputs=0,
            unique_outputs=0,
            input_entropy_bits=0.0,
            output_entropy_bits=0.0,
            conditional_entropy_bits=0.0,
            collisions=0,
            roundtrip_mismatches=0,
            errors=("empty_sample_set",),
        )

    encoded: list[Any] = []
    errors: list[str] = []
    mismatches = 0
    for idx, item in enumerate(samples):
        try:
            y = encode_fn(item)
        except Exception as exc:
            errors.append(f"encode_error[{idx}]:{type(exc).__name__}")
            y = f"__ENCODE_ERR_{idx}__"
        encoded.append(y)
        try:
            restored = decode_fn(y)
            if _canonical_key(restored) != _canonical_key(item):
                mismatches += 1
        except Exception as exc:
            mismatches += 1
            errors.append(f"decode_error[{idx}]:{type(exc).__name__}")

    x_keys = [_canonical_key(x) for x in samples]
    y_keys = [_canonical_key(y) for y in encoded]
    unique_x = len(set(x_keys))
    unique_y = len(set(y_keys))

    y_to_x: dict[str, set[str]] = defaultdict(set)
    for xk, yk in zip(x_keys, y_keys):
        y_to_x[yk].add(xk)
    collisions = sum(len(xs_set) - 1 for xs_set in y_to_x.values() if len(xs_set) > 1)

    h_x = shannon_entropy_bits(samples)
    h_y = shannon_entropy_bits(encoded)
    h_x_given_y = conditional_entropy_bits(samples, encoded)

    if collisions > 0:
        errors.append(f"lossy_projection_collisions:{collisions}")
    if h_x_given_y > max_cond_entropy_bits:
        errors.append(f"nonzero_conditional_entropy:{h_x_given_y}")
    if mismatches > 0:
        errors.append(f"roundtrip_mismatches:{mismatches}")

    ok = len(errors) == 0
    return IsomorphismVerdict(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        sample_count=len(samples),
        unique_inputs=unique_x,
        unique_outputs=unique_y,
        input_entropy_bits=h_x,
        output_entropy_bits=h_y,
        conditional_entropy_bits=h_x_given_y,
        collisions=collisions,
        roundtrip_mismatches=mismatches,
        errors=tuple(errors),
    )
