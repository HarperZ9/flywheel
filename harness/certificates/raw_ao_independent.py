"""raw_ao_independent.py -- level 3: reconcile another renderer's AO against raw-native's.

A GPU or browser renderer cannot vouch for its own ambient occlusion. raw-native
has no GPU, driver or graphics API in its trust path, so its ray-traced AO
buffer is the reference another renderer's AO is held to, for the same camera
and frame. The candidate hands over its AO as canonical ``ao.f32`` and its
coverage as ``mask.u8``; the checker never runs the candidate and the candidate
does not control the checker (the pattern of ``crossing_independent.py``).

Two verdicts, as every raw lane receipt has:

* identity: MATCH only when the candidate's AO bytes equal raw-native's;
* tolerance: coverage mismatch at most 0.5 % of reference-covered pixels and
  AO RMSE at most 0.02 on pixels both cover. These are the bounds the
  superstack contract's 3 October 2026 pixel proof fixed before its first
  comparison (``examples/check.py`` in the superstack repository); this module
  adopts them unchanged rather than choosing new ones after seeing data.

Pure data: this module runs nothing.
"""
from __future__ import annotations

import math

from .._vendor import superstack as ss
from .raw_ao import certificate_sha256
from .raw_ao_buffers import BufferError, canonical_ao, canonical_mask
from .raw_ao_receipt import ao_media, make

BOUNDS = {"coverage_mismatch_frac_max": 0.005, "ao_rmse_max": 0.02}
NOT_PROVEN = ("Agreement with raw-native's ray-traced AO covers this camera and frame "
              "of the built-in scene only; it says nothing about the candidate's other "
              "passes, scenes or frames.",)


def _unverifiable(reason: str) -> dict:
    return {"verdict": "unverifiable", "metrics": {}, "bounds": dict(BOUNDS),
            "reason": reason}


def _reference(files) -> tuple[int, int, bytes, bytes]:
    w, h, ao = canonical_ao(files["ao_rt.pfm"])
    w2, h2, mask = canonical_mask(files["mask.pgm"])
    if (w, h) != (w2, h2):
        raise BufferError("reference AO and mask sizes differ")
    return w, h, ao, mask


def tolerance(reference_files, candidate: dict) -> dict:
    """The superstack tolerance block for one candidate AO against the reference."""
    try:
        w, h, ref_ao, ref_mask = _reference(reference_files)
    except (BufferError, KeyError) as e:
        return _unverifiable(f"reference unreadable: {e}")
    ao, mask = candidate.get("ao_f32"), candidate.get("mask_u8")
    if (candidate.get("width"), candidate.get("height")) != (w, h) or not isinstance(
            ao, bytes) or not isinstance(mask, bytes) or len(ao) != len(ref_ao) or len(
            mask) != len(ref_mask):
        return _unverifiable("size differs from the reference")
    covered = sum(ref_mask)
    if covered == 0:
        return _unverifiable("the reference covers no pixel")
    mismatch = sum(1 for a, b in zip(ref_mask, mask) if bool(a) != bool(b))
    both = bytes(1 if (a and b) else 0 for a, b in zip(ref_mask, mask))
    rmse = ss.f32_rmse(ref_ao, ao, both)
    if rmse is None:
        return _unverifiable("no pixel is covered by both renderers")
    frac = mismatch / covered
    finite = math.isfinite(rmse)
    ok = finite and frac <= BOUNDS["coverage_mismatch_frac_max"] and rmse <= BOUNDS["ao_rmse_max"]
    return {"verdict": "verified" if ok else "refuted",
            "metrics": {"coverage_mismatch_frac": frac,
                        "ao_rmse": ss.round6(rmse) if finite else None},
            "bounds": dict(BOUNDS)}


def receipt(reference_cert: dict, reference_files, candidate: dict) -> dict:
    """A level-3 receipt: the candidate's AO as content, raw-native's as reference."""
    tol = tolerance(reference_files, candidate)
    try:
        w, h, ref_ao, _mask = _reference(reference_files)
        ref_sha = ss.sha256_hex(ref_ao)
    except (BufferError, KeyError):
        w, h, ref_sha = candidate.get("width"), candidate.get("height"), ss.sha256_hex(b"")
    content = candidate.get("ao_f32") if isinstance(candidate.get("ao_f32"), bytes) else b""
    renderer = str(reference_cert.get("renderer", "raw-native unknown"))
    return make(
        level=3, params=reference_cert.get("params") or {},
        producer=str(candidate.get("producer", "unknown")),
        version=str(candidate.get("version", "unknown")),
        backend=str(candidate.get("backend", "unknown")), content=content,
        media=ao_media(w, h),
        outputs={"ao.f32": ss.sha256_hex(content),
                 "mask.u8": ss.sha256_hex(candidate.get("mask_u8") or b"")},
        reference={"backend": renderer.replace(" ", "-") + "-cpu-ray-traced-ao",
                   "content_sha256": ref_sha},
        tolerance=tol, extra_not_proven=NOT_PROVEN,
        flywheel={"reference_certificate_sha256": certificate_sha256(reference_cert),
                  "verdict": "PASS" if tol["verdict"] == "verified" else
                  "FAIL" if tol["verdict"] == "refuted" else "UNVERIFIABLE"})
