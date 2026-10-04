"""Level 2 for the raw lane: replay a recorded render and compare the bytes.

A ``raw-cert/2`` certificate records the canonical params and the SHA-256 of
every file the verdict was judged from. Replay runs the hash-pinned binary with
those params (``raw_lane.run``) and compares the new digests with the record:

  MATCH         every recorded file is byte-identical
  DRIFT         any file differs. On the same platform the DRIFT is attributed to
                the candidate: the record does not reproduce. Across platforms
                it carries ``CROSS_DEVICE_NOTE`` and is reported as a scope limit,
                as ``certificates/replay.py`` does.
  UNVERIFIABLE  the certificate records no params, or the binary is missing,
                refused, or failed to render

The receipt's tolerance verdict holds the replayed reconcile to the recorded one
with the bounds raw-native fixed before its first WebAssembly-against-native
comparison (its README, 0.4.0): identical pixel count and verdict, RMSE within
1e-4 and maximum error within 1/64. A replay can therefore read DRIFT and PASS
at once, when bytes differ by less than the bound.
"""
from __future__ import annotations

from . import raw_lane, raw_lane_install as inst
from ._vendor import superstack as ss
from .certificates import raw_ao, raw_ao_receipt as rr
from .certificates.replay import CROSS_DEVICE_NOTE, DRIFT, MATCH, REPLAY_DOES_NOT_PROVE, UNVERIFIABLE
from .verdict import Attribution, Execution

BOUNDS = {"pixels_abs_diff_max": 0, "rmse_abs_diff_max": 1e-4,
          "max_error_abs_diff_max": 1 / 64, "verdict_equal": True}


def _tolerance(claimed: dict, replayed: dict | None) -> dict:
    a = claimed.get("exact") if isinstance(claimed.get("exact"), dict) else None
    b = (replayed or {}).get("exact") if isinstance((replayed or {}).get("exact"), dict) else None
    if a is None or b is None:
        return {"verdict": "unverifiable", "metrics": {}, "bounds": dict(BOUNDS),
                "reason": "a reconcile value is missing from the claimed or replayed record"}
    try:
        metrics = {"pixels_abs_diff": abs(int(a["pixels"]) - int(b["pixels"])),
                   "rmse_abs_diff": abs(float(a["rmse"]) - float(b["rmse"])),
                   "max_error_abs_diff": abs(float(a["maxError"]) - float(b["maxError"])),
                   "verdict_equal": claimed.get("verdict") == replayed.get("verdict")}
    except (KeyError, TypeError, ValueError) as e:
        return {"verdict": "unverifiable", "metrics": {}, "bounds": dict(BOUNDS),
                "reason": f"a reconcile value is malformed: {e}"}
    ok = (metrics["pixels_abs_diff"] <= BOUNDS["pixels_abs_diff_max"]
          and metrics["rmse_abs_diff"] <= BOUNDS["rmse_abs_diff_max"]
          and metrics["max_error_abs_diff"] <= BOUNDS["max_error_abs_diff_max"]
          and metrics["verdict_equal"])
    return {"verdict": "verified" if ok else "refuted", "metrics": metrics,
            "bounds": dict(BOUNDS)}


def _verdict(claimed_outputs: dict, replayed: dict, claimed_platform, platform):
    drifted = sorted(n for n in set(claimed_outputs) | set(replayed)
                     if claimed_outputs.get(n) != replayed.get(n))
    if not drifted:
        return MATCH, None, [], "every recorded file is byte-identical"
    cross = claimed_platform != platform
    notes = [CROSS_DEVICE_NOTE] if cross else []
    if claimed_platform is None:
        notes.append("The claimed run did not record its platform, so a cross-platform "
                     "cause cannot be ruled out.")
    who = Attribution.ENVIRONMENT if cross else Attribution.CANDIDATE
    return DRIFT, who, notes, f"files differ: {', '.join(drifted)}"


def _unverifiable(cert, why: str, platform: str, execution=None) -> dict:
    return {"level": 2, "verdict": UNVERIFIABLE, "reason": why, "receipt": None,
            "platform": platform, "execution": execution,
            "certificate_sha256": raw_ao.certificate_sha256(cert)
            if isinstance(cert, dict) else None}


def replay(cert, *, claimed_platform: str | None = None, environ=None,
           pins: inst.Pins = inst.PINS, plat: str | None = None,
           timeout: float | None = None) -> dict:
    """Replay ``cert``'s render and judge it. Executes the pinned binary once."""
    plat = plat or inst.platform_key() or ""
    if not isinstance(cert, dict) or cert.get("schema") != raw_ao.CERT_SCHEMA:
        return _unverifiable(cert, "certificate is not raw-cert/2", plat)
    if not isinstance(cert.get("params"), dict) or not isinstance(cert.get("outputs"), dict):
        return _unverifiable(cert, "certificate records no params or no output digests", plat)
    run = raw_lane.run(cert["params"], environ=environ, timeout=timeout, pins=pins, plat=plat)
    if run.execution is not Execution.COMPLETED or run.certificate is None:
        return _unverifiable(cert, run.result.stdout_excerpt, plat, run.execution.value)
    replayed = {n: ss.sha256_hex(d) for n, d in run.files.items() if n in cert["outputs"]
                or n in (run.certificate.get("outputs") or {})}
    verdict, who, notes, detail = _verdict(cert["outputs"], replayed, claimed_platform, plat)
    if cert.get("renderer") != run.certificate.get("renderer"):
        notes.append(f"The replay used {run.certificate.get('renderer')}; the record names "
                     f"{cert.get('renderer')}.")
    receipt = rr.make(
        level=2, params=cert["params"], producer="raw-native",
        version=rr.renderer_version(run.certificate),
        backend=f"raw-native-{rr.renderer_version(run.certificate)}-cpu-{plat}",
        content=rr.outputs_document(replayed), media=rr.outputs_media(), outputs=replayed,
        reference={"backend": f"recorded run ({claimed_platform or 'platform unrecorded'})",
                   "content_sha256": ss.sha256_hex(rr.outputs_document(cert["outputs"]))},
        tolerance=_tolerance(cert, run.certificate),
        extra_not_proven=(REPLAY_DOES_NOT_PROVE, *notes),
        flywheel={"verdict": verdict, "attribution": who and who.value, "detail": detail,
                  "certificate_sha256": raw_ao.certificate_sha256(cert),
                  "claimed_platform": claimed_platform, "replayed_platform": plat})
    return {"level": 2, "verdict": verdict, "reason": detail, "receipt": receipt,
            "attribution": who and who.value, "platform": plat,
            "execution": run.execution.value,
            "certificate_sha256": raw_ao.certificate_sha256(cert)}
