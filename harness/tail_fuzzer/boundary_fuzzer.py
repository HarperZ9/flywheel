# SPDX-License-Identifier: MIT
"""Deterministic seed-pinned adversarial boundary and tail-edge fuzzer.

Generates extreme IEEE-754 float edges (subnormals, -0.0, NaN, Inf, 2^53+1),
integer boundaries, adversarial Unicode and null-byte strings, boundary
lengths, and empty/singleton/skewed partitions with exact seed reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Generates deterministic seed-pinned boundary and tail-edge test cases "
    "over IEEE-754 floats, integers, strings, bytes, and partitions using "
    "random.Random(seed). Does not perform coverage-guided binary fuzzing "
    "or symbolic path exploration."
)

EXTREME_FLOATS: tuple[float, ...] = (
    0.0,
    -0.0,
    5e-324,
    -5e-324,
    sys.float_info.min * 1e-6,
    sys.float_info.min,
    -sys.float_info.min,
    1.0,
    -1.0,
    float((1 << 53) + 1),
    float(-((1 << 53) + 1)),
    sys.float_info.max,
    -sys.float_info.max,
    float("nan"),
    float("inf"),
    float("-inf"),
)

BOUNDARY_INTS: tuple[int, ...] = (
    0,
    1,
    -1,
    127,
    128,
    255,
    256,
    (1 << 31) - 1,
    -(1 << 31),
    (1 << 32) - 1,
    (1 << 53) + 1,
    (1 << 63) - 1,
    -(1 << 63),
)

BOUNDARY_LENGTHS: tuple[int, ...] = (0, 1, 2, 15, 16, 31, 32, 63, 64, 127, 128, 255, 256)

ADVERSARIAL_STRINGS: tuple[str, ...] = (
    "",
    "a",
    "\x00",
    "prefix\x00suffix",
    "\u202ereversed",
    "e\u0301\u0302\u0303",
    " " * 16,
    "A" * 256,
    "{\"\x00\": [1, 2, 3]}",
)


@dataclass(frozen=True)
class BoundaryCase:
    """One deterministic adversarial boundary test case."""

    case_id: int
    category: str
    value: object


def generate_float_tail_cases(seed: int, count: int = 128) -> list[BoundaryCase]:
    """Generate deterministic IEEE-754 edge cases plus heavy-tail draws."""
    if count <= 0:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    cases: list[BoundaryCase] = []
    for idx, val in enumerate(EXTREME_FLOATS):
        if len(cases) >= count:
            break
        cases.append(BoundaryCase(idx, "extreme_float", val))
    while len(cases) < count:
        idx = len(cases)
        u = max(rng.random(), 1e-12)
        pareto = (u ** -0.8) - 1.0
        signed = -pareto if rng.random() < 0.5 else pareto
        cases.append(BoundaryCase(idx, "heavy_tail_float", signed))
    return cases


def generate_mixed_boundary_cases(seed: int, count: int = 160) -> list[BoundaryCase]:
    """Generate deterministic mix of floats, ints, strings, bytes, and partitions."""
    if count <= 0:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    seeded_pool: list[tuple[str, object]] = [
        *[("extreme_float", v) for v in EXTREME_FLOATS],
        *[("boundary_int", v) for v in BOUNDARY_INTS],
        *[("adversarial_str", v) for v in ADVERSARIAL_STRINGS],
        ("empty_partition", []),
        ("singleton_partition", [0.0]),
        ("skewed_partition", [1.0] * 19 + [1e9]),
        ("null_bytes", b"\x00\x01\xff\x00"),
        ("empty_bytes", b""),
    ]
    cases: list[BoundaryCase] = []
    for idx, (cat, val) in enumerate(seeded_pool):
        if len(cases) >= count:
            break
        cases.append(BoundaryCase(idx, cat, val))

    while len(cases) < count:
        idx = len(cases)
        pick = idx % 4
        if pick == 0:
            length = rng.choice(BOUNDARY_LENGTHS)
            payload = bytes(rng.randrange(0, 256) for _ in range(length))
            cases.append(BoundaryCase(idx, "boundary_bytes", payload))
        elif pick == 1:
            length = rng.choice((0, 1, 2, 7, 16))
            part = [rng.uniform(-1e6, 1e6) for _ in range(length)]
            cases.append(BoundaryCase(idx, "random_partition", part))
        elif pick == 2:
            val = rng.choice(BOUNDARY_INTS) ^ rng.randrange(0, 256)
            cases.append(BoundaryCase(idx, "perturbed_int", val))
        else:
            exp = rng.randint(-308, 308)
            mant = rng.uniform(-10.0, 10.0)
            cases.append(BoundaryCase(idx, "scaled_float", math.ldexp(mant, min(max(exp, -1000), 1000))))
    return cases


def _canonical_case_repr(case: object) -> object:
    if isinstance(case, BoundaryCase):
        return {"id": case.case_id, "cat": case.category, "val": _canonical_case_repr(case.value)}
    if isinstance(case, float):
        if math.isnan(case):
            return "FLOAT:NaN"
        if math.isinf(case):
            return "FLOAT:+Inf" if case > 0 else "FLOAT:-Inf"
        if case == 0.0 and math.copysign(1.0, case) < 0:
            return "FLOAT:-0.0"
        return repr(case)
    if isinstance(case, (bytes, bytearray)):
        return "BYTES:" + bytes(case).hex()
    if isinstance(case, (list, tuple)):
        return [_canonical_case_repr(x) for x in case]
    if isinstance(case, dict):
        return {str(k): _canonical_case_repr(v) for k, v in sorted(case.items())}
    return case


def fingerprint_cases(cases: Sequence[object]) -> str:
    """Compute a deterministic SHA-256 fingerprint over a generated case stream."""
    payload = [_canonical_case_repr(c) for c in cases]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_seed_reproducible(
    generator_fn: Callable[[int, int], Sequence[object]],
    seed: int,
    count: int = 64,
) -> bool:
    """Verify two invocations with the same seed produce identical case streams."""
    first = generator_fn(seed, count)
    second = generator_fn(seed, count)
    return len(first) == len(second) and fingerprint_cases(first) == fingerprint_cases(second)
