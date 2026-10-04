"""raw_ao.py -- the ``raw_ao_v1`` certificate family: raw-native's AO certificate, read as data.

raw-native renders one built-in scene on the CPU and computes ambient occlusion
twice: a screen-space shortcut (SSAO) and a ray-traced reference. Its
``certificate.json`` (schema ``raw-cert/2``, oracle ``raw-rt-ao-v1``) says
whether the shortcut stays within an RMSE tolerance of the reference on covered
pixels, and records the renderer version, the canonical parameters, the sample
counts, the exact reconcile values and the SHA-256 of every file it was judged
from.

Two things live here, both pure data:

* ``translate``: raw-native's three-word verdict into Flywheel's ``Verdict``.
  ``verified`` is PASS, ``refuted`` is FAIL, ``unverifiable`` is UNVERIFIABLE
  with ORACLE_UNAVAILABLE, and a missing or malformed certificate is
  UNVERIFIABLE with ENVELOPE_MISSING.
* ``level1``: the arithmetic recheck. It re-hashes every file the certificate
  lists and recomputes pixel count, RMSE, maximum error and verdict from the
  float buffers and the mask. It runs nothing, so a stranger can run it on a
  certificate and files someone else produced.

Every result carries ``DOES_NOT_PROVE``, four fixed sentences a test asserts.
This module imports nothing that can execute.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

from ..oracle import OracleResult
from ..verdict import Attribution, Execution, UnverifiableReason, Verdict
from .base import canonical, parse_certificate
from .raw_ao_buffers import BufferError, f32, reconcile_files

FAMILY = "raw_ao_v1"
ORACLE_ID = "raw-rt-ao-v1"
CERT_SCHEMA = "raw-cert/2"
MATCH, DRIFT = "MATCH", "DRIFT"
COVERAGE_NOTE = ("SSAO RMSE within tolerance on covered pixels; max error is reported, "
                 "not bounded")
DOES_NOT_PROVE = (
    "The reference is a 64-sample hemisphere estimate from a deterministic per-pixel "
    "hash, so it is repeatable, not exact.",
    "A pass on RMSE says nothing about the worst pixel. The high view passes at 0.0827 "
    "RMSE with a 0.625 maximum error.",
    "One built-in scene; no claim about other geometry, lights or materials.",
    "Byte-identical output is checked on x86-64 only.",
)
_RAW_VERDICTS = {"verified": Verdict.PASS, "refuted": Verdict.FAIL,
                 "unverifiable": Verdict.UNVERIFIABLE}
_ENVELOPE = UnverifiableReason.ENVELOPE_MISSING.value
_UNAVAILABLE = UnverifiableReason.ORACLE_UNAVAILABLE.value


@dataclass(frozen=True)
class Translation:
    """raw-native's verdict in Flywheel's vocabulary."""
    verdict: Verdict
    reason: str = ""
    note: str = ""
    raw_verdict: str | None = None


def load_certificate(text) -> tuple[dict | None, str]:
    """(certificate, why). None when the text is not exactly one JSON object."""
    ok, cert, why = parse_certificate(text)
    return (cert, "") if ok else (None, why)


def translate(cert) -> Translation:
    """The translation table. Anything that is not an AO certificate with one of
    the three verdict words is a missing envelope, never a FAIL."""
    if not isinstance(cert, dict) or cert.get("oracle") != ORACLE_ID:
        return Translation(Verdict.UNVERIFIABLE, _ENVELOPE,
                           "missing or malformed raw-rt-ao-v1 certificate")
    raw = cert.get("verdict")
    verdict = _RAW_VERDICTS.get(raw) if isinstance(raw, str) else None
    if verdict is None:
        return Translation(Verdict.UNVERIFIABLE, _ENVELOPE,
                           f"unknown raw-native verdict {raw!r}")
    if verdict is Verdict.PASS:
        return Translation(verdict, "", COVERAGE_NOTE, raw)
    if verdict is Verdict.UNVERIFIABLE:
        return Translation(verdict, _UNAVAILABLE, "raw-native could not compare", raw)
    return Translation(verdict, "", "", raw)


def certificate_sha256(cert: dict) -> str:
    """SHA-256 of the certificate in base.canonical form."""
    return hashlib.sha256(canonical(cert).encode("utf-8")).hexdigest()


def _digests(cert: dict, files: Mapping[str, bytes]) -> tuple[dict, list, list]:
    """(digests on disk, missing names, names whose bytes differ from the record)."""
    found, missing, drift = {}, [], []
    for name, recorded in sorted(cert["outputs"].items()):
        data = files.get(name)
        if data is None:
            missing.append(name)
            continue
        found[name] = hashlib.sha256(data).hexdigest()
        if found[name] != recorded:
            drift.append(name)
    return found, missing, drift


def recomputed_verdict(pixels: int, rmse: float, tolerance: float) -> str:
    """raw-native's rule: no covered pixel is unverifiable, else RMSE against the
    float32 tolerance."""
    if pixels == 0:
        return "unverifiable"
    return "verified" if rmse <= f32(tolerance) else "refuted"


def _evidence_mismatches(cert: dict, got: dict) -> list:
    """The rounded evidence strings must agree with the exact values too, so a
    certificate cannot show one number to a reader and another to a checker."""
    ev = dict(item for item in cert.get("evidence", []) if isinstance(item, list)
              and len(item) == 2)
    out = []
    if ev.get("pixels") != str(got["pixels"]):
        out.append("evidence.pixels")
    for key, value in (("rmse", got["rmse"]), ("maxError", got["maxError"])):
        try:
            if abs(float(ev.get(key)) - value) > 5.01e-5:
                out.append(f"evidence.{key}")
        except (TypeError, ValueError):
            out.append(f"evidence.{key}")
    return out


def _arithmetic_mismatches(cert: dict, got: dict) -> list:
    ex = cert.get("exact") if isinstance(cert.get("exact"), dict) else {}
    out = []
    try:
        tol = float(ex["tolerance"])
        checks = (("pixels", got["pixels"] == ex["pixels"]),
                  ("rmse", got["rmse"] == f32(float(ex["rmse"]))),
                  ("maxError", got["maxError"] == f32(float(ex["maxError"]))),
                  ("verdict", recomputed_verdict(got["pixels"], got["rmse"], tol)
                   == cert.get("verdict")))
    except (KeyError, TypeError, ValueError):
        return ["exact"]
    out += [name for name, ok in checks if not ok]
    params = cert.get("params") if isinstance(cert.get("params"), dict) else {}
    if params.get("tolerance") != ex.get("tolerance"):
        out.append("params.tolerance")
    return out + _evidence_mismatches(cert, got)


def _unverifiable(why: str, **extra) -> dict:
    return {"level": 1, "verdict": Verdict.UNVERIFIABLE.value, "reason": _ENVELOPE,
            "detail": why, "identity": None, "mismatches": [], "tolerance": None, **extra}


def _tolerance_block(cert: dict, got: dict | None, reason: str = "") -> dict:
    tol = (cert.get("exact") or {}).get("tolerance")
    if got is None:
        return {"verdict": "unverifiable", "metrics": {}, "bounds": {"rmse_max": tol},
                "reason": reason or "no ray-traced reference in this render"}
    return {"verdict": recomputed_verdict(got["pixels"], got["rmse"], float(tol)),
            "metrics": {"pixels": got["pixels"], "rmse": got["rmse"],
                        "max_error": got["maxError"]},
            "bounds": {"rmse_max": tol}}


def level1(cert, files: Mapping[str, bytes]) -> dict:
    """Recheck a certificate against the files beside it, without running anything.

    PASS: every listed file hashes to its record and the recomputed reconcile
    equals the recorded exact values and verdict. FAIL: any of that disagrees, a
    forged certificate or a tampered buffer. UNVERIFIABLE with ENVELOPE_MISSING:
    the certificate is not ``raw-cert/2`` or a file it lists is absent.
    """
    if not isinstance(cert, dict) or cert.get("schema") != CERT_SCHEMA:
        return _unverifiable("certificate is not raw-cert/2; level 1 needs the float "
                             "buffers, the mask and the recorded digests")
    if not isinstance(cert.get("outputs"), dict) or not cert["outputs"]:
        return _unverifiable("certificate lists no output digests")
    digests, missing, drift = _digests(cert, files)
    if missing:
        return _unverifiable(f"files absent: {', '.join(missing)}", missing=missing)
    identity = DRIFT if drift else MATCH
    mismatches = [f"sha256 {name}" for name in drift]
    if "ao_rt.pfm" not in cert["outputs"]:
        if cert.get("verdict") != "unverifiable":
            mismatches.append("verdict without reference")
        got, tolerance = None, _tolerance_block(cert, None)
    else:
        try:
            got = reconcile_files(files)
            mismatches += _arithmetic_mismatches(cert, got)
            tolerance = _tolerance_block(cert, got)
        except (BufferError, KeyError) as e:
            got, tolerance = None, _tolerance_block(cert, None, f"buffer unreadable: {e}")
            mismatches.append(f"buffer: {e}")
    verdict = Verdict.FAIL if mismatches else Verdict.PASS
    return {"level": 1, "verdict": verdict.value, "reason": "", "identity": identity,
            "mismatches": mismatches, "digests": digests, "tolerance": tolerance,
            "recomputed": got, "detail": "; ".join(mismatches) or "all checks match"}


def oracle_result(cert, verdict: Verdict, excerpt: str, *, reason: str = "",
                  execution: Execution = Execution.COMPLETED,
                  attribution: Attribution | None = None,
                  coverage: dict | None = None, extra_not_proven=()) -> OracleResult:
    """An OracleResult for this family, hashed over the canonical certificate."""
    cert_canon = canonical(cert) if isinstance(cert, dict) else ""
    preimage = canonical({"cert": cert_canon, "verdict": verdict.value, "family": FAMILY})
    return OracleResult(
        cmd=f"certificate:{FAMILY}",
        output_hash=hashlib.sha256(preimage.encode()).hexdigest()[:16],
        stdout_excerpt=excerpt[:1200], rc=0 if verdict is Verdict.PASS else 1,
        verdict_=verdict, execution=execution, attribution=attribution,
        raw_stdout_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        unverifiable_reason=reason if verdict is Verdict.UNVERIFIABLE else "",
        coverage=dict(coverage or {}, note=COVERAGE_NOTE),
        does_not_prove=[*DOES_NOT_PROVE, *extra_not_proven])


def verify_level1(cert_text: str, files: Mapping[str, bytes]) -> OracleResult:
    """Level 1 as an OracleResult: the entry point a stranger calls."""
    cert, why = load_certificate(cert_text)
    result = level1(cert, files) if cert is not None else _unverifiable(
        f"certificate unreadable: {why}")
    verdict = Verdict(result["verdict"])
    attribution = Attribution.ENVIRONMENT if verdict is Verdict.UNVERIFIABLE else None
    return oracle_result(cert, verdict, result["detail"], reason=result["reason"],
                         attribution=attribution,
                         coverage={"level": 1, "identity": result["identity"]})
