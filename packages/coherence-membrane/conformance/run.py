"""Conformance harness for the read-gate wire contract.

Re-derivability is the read-gate's whole trust claim, and until now it has been
asserted (only one implementation exists). This runs a PINNED vector corpus
through THIS implementation and checks every case re-derives the expected value.
A second, independent implementation that passes the same corpus *demonstrates*
the observation/drift contract is re-derivable rather than asserted.

Stdlib only. The corpus is hash-pinned: run.py recomputes the SHA-256 of the
cases and aborts if it does not match PINNED_CORPUS_SHA256, so the vectors cannot
drift silently. The expected values are FROZEN in vectors.json -- a regression in
the implementation makes a case fail (got != expected), which is the point.

    python conformance/run.py     # exit 0 if all pass, 1 on a mismatch, 2 on corpus drift
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coherence_membrane.observation import sha256_hex  # noqa: E402
from coherence_membrane.organs.structured import canonical_json_bytes  # noqa: E402
from coherence_membrane.phash import compare_drift, hamming, perceptual_hash  # noqa: E402
from coherence_membrane.pngview import decode_png  # noqa: E402
from coherence_membrane.receipt import WitnessReceipt  # noqa: E402
from coherence_membrane.region import compare_region_drift  # noqa: E402

# Pinned SHA-256 of the canonical JSON of vectors.json "cases". Recomputed every
# run; a mismatch means the corpus was edited without re-pinning -> abort.
PINNED_CORPUS_SHA256 = "0748fc1adef9753d9874d1abe3046aea5d3e8a5dd472e99660eaecd33b15802b"


def _bytes_in(inp: dict) -> bytes:
    if "utf8" in inp:
        return inp["utf8"].encode("utf-8")
    if "hex" in inp:
        return bytes.fromhex(inp["hex"])
    raise ValueError("case input has no 'utf8' or 'hex' byte source")


def _opt_int(value) -> int | None:
    return int(value, 16) if value else None


def run_case(case: dict):
    """Run one case through the reference implementation and return its result."""
    fn = case["fn"]
    inp = case["input"]
    if fn == "sha256_hex":
        return sha256_hex(_bytes_in(inp))
    if fn == "hamming":
        return hamming(int(inp["a"], 16), int(inp["b"], 16))
    if fn == "perceptual_hash":
        return format(perceptual_hash(decode_png(bytes.fromhex(inp["png_hex"]))), "016x")
    if fn == "compare_drift":
        v = compare_drift(
            inp.get("baseline_sha256"), inp.get("current_sha256"),
            _opt_int(inp.get("baseline_phash")), _opt_int(inp.get("current_phash")),
        )
        return {"verdict": v.verdict, "distance": v.distance}
    if fn == "canonical_sha256":
        return sha256_hex(canonical_json_bytes(inp["json"]))
    if fn == "region_drift":
        r = compare_region_drift(inp["baseline"], inp["current"], inp["rows"], inp["cols"],
                                 threshold=inp.get("threshold", 0))
        return {"verdict": r.verdict, "changed_regions": r.changed_regions,
                "max_distance": r.max_distance}
    if fn == "receipt_anchor":
        return WitnessReceipt.from_dict(inp["receipt"]).anchor()
    raise ValueError(f"unknown conformance fn: {fn!r}")


def corpus_sha256(cases: list) -> str:
    # sort_keys=False on purpose: a case's object-key ORDER is meaningful here
    # (the canonical-equivalence pair differs only in key order), so the pin must
    # be sensitive to a key-order edit. Whitespace is still normalised by the
    # compact separators, so reformatting the file alone does not trip the pin.
    canonical = json.dumps(cases, sort_keys=False, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    vectors = json.loads((Path(__file__).resolve().parent / "vectors.json").read_text("utf-8"))
    cases = vectors["cases"]

    digest = corpus_sha256(cases)
    if PINNED_CORPUS_SHA256 != "__PINNED__" and digest != PINNED_CORPUS_SHA256:
        print(f"CORPUS DRIFT: vectors.json cases hash {digest} != pinned "
              f"{PINNED_CORPUS_SHA256}", file=sys.stderr)
        return 2

    failures = []
    for case in cases:
        try:
            got = run_case(case)
        except Exception as exc:  # a case that errors is a failure, not a crash
            failures.append((case.get("id", "?"), case.get("expected"), f"ERROR: {exc}"))
            continue
        if got != case["expected"]:
            failures.append((case.get("id", "?"), case["expected"], got))

    for cid, exp, got in failures:
        print(f"FAIL {cid}: expected {exp!r} got {got!r}", file=sys.stderr)
    print(json.dumps({"cases": len(cases), "passed": len(cases) - len(failures),
                      "failed": len(failures), "corpus_sha256": digest}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
