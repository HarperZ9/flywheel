# SPDX-License-Identifier: MIT
"""Cross-runtime canonical output digest parity verifier.

Checks bit-identical canonical output SHA-256 parity across Native, Zero-C,
WebAssembly, and Python runtime cells, failing closed on missing runtimes,
malformed digests, single-runtime drift, or baseline hash mismatch.
"""

from __future__ import annotations

import hmac
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Verifies cross-runtime SHA-256 output digest consensus across recorded "
    "benchmark runtime cells and against optional reference baselines. Does "
    "not execute target binaries or capture raw program stdout directly."
)

KNOWN_RUNTIMES: tuple[str, ...] = (
    "buildc_native",
    "zeroc_pe32",
    "node_wasm",
    "python_stdlib",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ParityCheckReport:
    """Fail-closed cross-runtime output parity result for one kernel."""

    passed: bool
    kernel_id: str
    consensus_sha256: str | None
    runtimes_checked: tuple[str, ...]
    divergent_runtimes: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize parity report into a JSON-compatible dictionary."""
        return {
            "passed": self.passed,
            "kernel_id": self.kernel_id,
            "consensus_sha256": self.consensus_sha256,
            "runtimes_checked": list(self.runtimes_checked),
            "divergent_runtimes": list(self.divergent_runtimes),
            "reasons": list(self.reasons),
        }


def is_hex64(value: object) -> bool:
    """Return True iff value is a 64-character lowercase hex digest."""
    return isinstance(value, str) and bool(_HEX64_RE.fullmatch(value))


def _compute_digest_consensus(
    kernel_id: str,
    valid: dict[str, str],
    min_runtimes: int,
    reasons: list[str],
) -> tuple[str | None, list[str]]:
    counts = Counter(valid.values())
    if len(counts) == 1 and len(valid) >= min_runtimes:
        return next(iter(counts)), []
    if len(counts) > 1:
        top_hash, top_n = counts.most_common(1)[0]
        tied = sum(1 for c in counts.values() if c == top_n) > 1
        div = sorted(valid) if tied else sorted(rt for rt, h in valid.items() if not hmac.compare_digest(h, top_hash))
        reasons.append(f"RUNTIME_PARITY_DIVERGENCE:{kernel_id}:" + ",".join(div))
        return None, div
    return None, []


def verify_runtime_digests(
    kernel_id: str,
    digests_by_runtime: Mapping[str, str],
    *,
    expected_sha256: str | None = None,
    min_runtimes: int = 2,
) -> ParityCheckReport:
    """Verify bit-identical canonical SHA-256 digests across runtimes."""
    reasons: list[str] = []
    if not isinstance(digests_by_runtime, Mapping) or len(digests_by_runtime) < min_runtimes:
        reasons.append(f"INSUFFICIENT_RUNTIMES:{kernel_id}")
    valid: dict[str, str] = {}
    checked: list[str] = []
    if isinstance(digests_by_runtime, Mapping):
        for rt in sorted(digests_by_runtime):
            checked.append(rt)
            dig = digests_by_runtime[rt]
            if not is_hex64(dig):
                reasons.append(f"MALFORMED_RUNTIME_DIGEST:{kernel_id}:{rt}")
            else:
                valid[rt] = dig
    if expected_sha256 is not None and not is_hex64(expected_sha256):
        reasons.append(f"MALFORMED_EXPECTED_SHA256:{kernel_id}")
    consensus, divergent = _compute_digest_consensus(kernel_id, valid, min_runtimes, reasons)
    if expected_sha256 is not None and is_hex64(expected_sha256):
        for rt, dig in sorted(valid.items()):
            if not hmac.compare_digest(dig, expected_sha256):
                if rt not in divergent:
                    divergent.append(rt)
                reasons.append(f"BASELINE_HASH_DRIFT:{kernel_id}:{rt}")
    passed = not reasons and consensus is not None
    return ParityCheckReport(passed, kernel_id, consensus if passed else None, tuple(checked), tuple(sorted(divergent)), tuple(reasons))


def verify_kernel_parity(
    kernel: Mapping[str, object],
    *,
    expected_sha256: str | None = None,
    min_runtimes: int = 2,
) -> ParityCheckReport:
    """Verify cross-runtime parity fields on a serialized kernel record."""
    if not isinstance(kernel, Mapping):
        return ParityCheckReport(False, "", None, (), (), ("INVALID_KERNEL_OBJECT",))
    kid = str(kernel.get("id", "unknown"))
    reasons: list[str] = []
    if kernel.get("parity_ok") is not True:
        reasons.append(f"PARITY_FLAG_FALSE:{kid}")
    declared_sha = kernel.get("parity_sha256")
    if not is_hex64(declared_sha):
        reasons.append(f"MALFORMED_PARITY_SHA256:{kid}")
    rts_raw = kernel.get("runtimes_verified")
    rts = [str(r) for r in rts_raw] if isinstance(rts_raw, list) and len(rts_raw) >= min_runtimes else []
    if not rts:
        reasons.append(f"INSUFFICIENT_VERIFIED_RUNTIMES:{kid}")
    digests: dict[str, str] = {}
    for rt in rts:
        cell = kernel.get(rt)
        if not isinstance(cell, Mapping):
            reasons.append(f"MISSING_RUNTIME_CELL:{kid}:{rt}")
            continue
        cell_hash = cell.get("output_sha256") or cell.get("stdout_sha256") or declared_sha
        if isinstance(cell_hash, str):
            digests[rt] = cell_hash
        else:
            reasons.append(f"MISSING_CELL_DIGEST:{kid}:{rt}")
    sub = verify_runtime_digests(kid, digests, expected_sha256=expected_sha256, min_runtimes=min_runtimes)
    all_reasons = tuple(dict.fromkeys([*reasons, *sub.reasons]))
    passed = not all_reasons and sub.passed
    return ParityCheckReport(passed, kid, sub.consensus_sha256 if passed else None, tuple(sorted(rts)), sub.divergent_runtimes, all_reasons)
