"""runtime_identity.py -- name the runtime that produced a result.

Same weights and the same prompt do not pin down the computation. The serving
framework, the GPU, the dtype, compile mode, batch shape and any activation
capture hook all change the floating-point path, and a run can differ from its
rerun for any of those reasons. A receipt that leaves them out cannot say why
two runs differ.

Each field is a string. A field the caller did not declare reads "unknown":
Flywheel does not guess a runtime. Booleans read "true" or "false". Capture
hooks read "none" when declared empty, else a sorted comma-joined list.

The rerun witness compares two runs. Equal outputs are MATCH. Different
outputs are DRIFT only when both runs declared deterministic and
batch-invariant execution and every runtime field is known and equal. Any
other mismatch is UNVERIFIABLE and names the fields that differ or are unknown,
because the runtime alone can explain it.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "flywheel.runtime-identity/v2"
SCHEMA_V1 = "flywheel.runtime-identity/v1"
UNKNOWN = "unknown"
MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"

FIELDS = ("serving_framework", "serving_version", "gpu_model", "dtype", "compile_mode",
          "batch_shape", "batch_invariant", "deterministic", "capture_hooks",
          "kernel_stack")
_BOOLS = ("batch_invariant", "deterministic")
SCOPE = ("The witness compares two outputs and the runtime fields each caller declared. "
         "Flywheel takes those fields as reported, without probing the GPU or the serving "
         "stack; equal fields are a declaration, and the kernels themselves go unseen.")


def _value(name: str, raw) -> str:
    if raw is None:
        return UNKNOWN
    if name in _BOOLS:
        if raw is True or str(raw).lower() == "true":
            return "true"
        if raw is False or str(raw).lower() == "false":
            return "false"
        return UNKNOWN
    if name == "capture_hooks":
        if isinstance(raw, (list, tuple, set)):
            hooks = sorted({str(h) for h in raw if str(h)})
            return ",".join(hooks) if hooks else "none"
        return str(raw) or UNKNOWN
    return str(raw) if str(raw) else UNKNOWN


def runtime_identity(declared: dict | None) -> dict:
    """The ten fields, in fixed order, all strings. Unknown keys are refused so a
    misspelled field never hides as unknown."""
    declared = dict(declared or {})
    extra = sorted(set(declared) - set(FIELDS))
    if extra:
        raise ValueError(f"unknown runtime fields {extra}; expected {list(FIELDS)}")
    return {name: _value(name, declared.get(name)) for name in FIELDS}


def well_formed(block) -> bool:
    return (isinstance(block, dict) and list(block) == list(FIELDS)
            and all(isinstance(v, str) and v for v in block.values()))


def known_count(block: dict) -> int:
    return sum(v != UNKNOWN for v in block.values())


def rerun_witness(a: dict, b: dict) -> dict:
    """a, b: {"runtime": runtime_identity(...), "output_sha256": str}."""
    ra, rb = runtime_identity(a.get("runtime")), runtime_identity(b.get("runtime"))
    out = {"schema": SCHEMA, "scope": SCOPE}
    if a.get("output_sha256") == b.get("output_sha256"):
        return dict(out, verdict=MATCH, code="output_equal", fields=[],
                    reason="the two runs produced the same output")
    differ = [f for f in FIELDS if ra[f] != rb[f]]
    if differ:
        return dict(out, verdict=UNVERIFIABLE, code="runtime_differs", fields=differ,
                    reason="the runtimes differ, so the runtime can explain the mismatch")
    unknown = [f for f in FIELDS if ra[f] == UNKNOWN]
    if unknown:
        return dict(out, verdict=UNVERIFIABLE, code="runtime_unknown", fields=unknown,
                    reason="a runtime field is unknown, so the runs cannot be shown equal")
    loose = [f for f in _BOOLS if ra[f] != "true"]
    if loose:
        return dict(out, verdict=UNVERIFIABLE, code="not_deterministic", fields=loose,
                    reason="the runtime does not promise bitwise-repeatable output")
    return dict(out, verdict=DRIFT, code="output_differs", fields=[],
                reason="same declared deterministic runtime, different output")


def _results_sha(receipt: dict) -> str:
    rows = receipt.get("results") or []
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def rerun_witness_receipts(a: dict, b: dict) -> dict:
    """Witness over two eval receipts; the output is the sealed result rows."""
    return rerun_witness({"runtime": a.get("runtime"), "output_sha256": _results_sha(a)},
                         {"runtime": b.get("runtime"), "output_sha256": _results_sha(b)})
