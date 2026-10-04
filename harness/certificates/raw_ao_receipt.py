"""raw_ao_receipt.py -- superstack receipts for the raw lane, with both verdicts.

Every receipt the raw lane writes is a ``superstack.receipt/1`` (the contract
vendored at ``harness/_vendor/superstack.py``, v0.1.0), so any of the
contract's three implementations can check its seal. Each one carries two
verdicts side by side, never folded into one:

* identity, ``MATCH`` or ``DRIFT``: are the bytes the same as the reference's?
* tolerance, ``PASS``, ``FAIL`` or ``UNVERIFIABLE``: is the measurement within
  its bound? superstack spells these ``verified``, ``refuted`` and
  ``unverifiable``; the ``flywheel`` block repeats them in Flywheel's words.

What is hashed as the content depends on the level:

* run, level 1 and level 2: the canonical JSON of the output digests, file name
  to SHA-256 (media kind ``document``, format ``raw-outputs/1``). The reference
  is the digest map a certificate records, so identity is MATCH only when every
  file is byte-identical.
* level 3: raw-native's ray-traced AO as canonical ``ao.f32`` (float32,
  little-endian, rows top-down), against another renderer's AO.

Every receipt lists the family's fixed ``DOES_NOT_PROVE`` lines first. Pure
data: this module runs nothing.
"""
from __future__ import annotations

from .._vendor import superstack as ss
from .raw_ao import DOES_NOT_PROVE, FAMILY, certificate_sha256, level1

SEED_RULE = "raw-pixel-hash/1"
OUTPUTS_FORMAT = "raw-outputs/1"
TOLERANCE_WORDS = {"verified": "PASS", "refuted": "FAIL", "unverifiable": "UNVERIFIABLE"}


def scene_for(params: dict) -> dict:
    """The superstack scene for one raw-native render: its frame, its camera and
    the full canonical parameter object, under the built-in scene."""
    p = params if isinstance(params, dict) else {}
    return {"kind": "superstack.scene/1",
            "frame": {"width": p.get("width"), "height": p.get("height"),
                      "pixel_center": 0.5, "origin": "top-left"},
            "camera": {k: p.get(k) for k in ("eye", "target", "up", "fovy")},
            "raw_native": {"scene": "builtin/1", "params": p}}


def outputs_document(digests: dict) -> bytes:
    """The canonical bytes of a file-name-to-SHA-256 map."""
    return ss.canonical_bytes({k: digests[k] for k in sorted(digests)})


def outputs_media() -> dict:
    return {"kind": "document", "format": OUTPUTS_FORMAT}


def ao_media(width: int, height: int) -> dict:
    return {"kind": "image", "width": width, "height": height, "format": "ao.f32",
            "transfer": "linear"}


def _flywheel_block(level, identity: str, tolerance: dict, extra: dict) -> dict:
    return {"family": FAMILY, "level": level, "identity": identity,
            "tolerance": TOLERANCE_WORDS[tolerance["verdict"]], **extra}


def make(*, level, params: dict, producer: str, version: str, backend: str,
         content: bytes, media: dict, outputs: dict, reference: dict,
         tolerance: dict, flywheel: dict | None = None, extra_not_proven=()) -> dict:
    """A sealed receipt. ``reference`` is ``{backend, content_sha256}``;
    ``tolerance`` is a superstack tolerance block (verdict, metrics, bounds and,
    when unverifiable, a reason)."""
    identity = ss.identity(reference["content_sha256"], ss.sha256_hex(content))
    rec = ss.make_receipt(
        producer=producer, version=version, backend=backend, scene=scene_for(params),
        media=media, content=content, outputs=outputs, reference=reference,
        reconcile={"identity": identity, "tolerance": tolerance},
        does_not_prove=[*DOES_NOT_PROVE, *extra_not_proven], seed_rule=SEED_RULE)
    rec["flywheel"] = _flywheel_block(level, identity, tolerance, dict(flywheel or {}))
    return ss.seal(rec)


def check(rec) -> list[str]:
    """superstack's own receipt check plus the raw lane's: both verdicts present
    and in agreement with the reconcile block, and every fixed line carried."""
    errors = list(ss.verify_receipt(rec))
    if not isinstance(rec, dict):
        return errors
    fw, rc = rec.get("flywheel"), rec.get("reconcile")
    if not isinstance(fw, dict) or not isinstance(rc, dict):
        return sorted(set(errors + ["flywheel:verdicts"]))
    if fw.get("identity") not in ("MATCH", "DRIFT") or fw["identity"] != rc.get("identity"):
        errors.append("flywheel:identity")
    tol = rc.get("tolerance") if isinstance(rc.get("tolerance"), dict) else {}
    if fw.get("tolerance") != TOLERANCE_WORDS.get(tol.get("verdict")):
        errors.append("flywheel:tolerance")
    if fw.get("family") != FAMILY:
        errors.append("flywheel:family")
    dnp = rec.get("does_not_prove") or []
    if list(dnp[:len(DOES_NOT_PROVE)]) != list(DOES_NOT_PROVE):
        errors.append("flywheel:does_not_prove")
    return sorted(set(errors))


def renderer_version(cert) -> str:
    """``0.4.0`` from ``raw-native 0.4.0``; ``unknown`` when the record has none."""
    renderer = cert.get("renderer") if isinstance(cert, dict) else None
    parts = renderer.split() if isinstance(renderer, str) else []
    return parts[-1] if len(parts) == 2 and parts[0] == "raw-native" else "unknown"


def level1_receipt(cert, files, *, level=1, platform: str = "", flywheel=None) -> dict:
    """Level 1 as a receipt: the files' digests against the certificate's record
    (identity) and the AO reconcile recomputed from the float buffers (tolerance).
    The flywheel block's ``verdict`` is the recheck's: PASS only when both the
    digests and the arithmetic agree with the certificate."""
    result = level1(cert, files)
    record = cert.get("outputs") if isinstance(cert, dict) else None
    record = record if isinstance(record, dict) else {}
    found = result.get("digests") or {name: ss.sha256_hex(data)
                                      for name, data in files.items() if name in record}
    tol = result.get("tolerance") or {"verdict": "unverifiable", "metrics": {},
                                      "bounds": {}, "reason": result["detail"]}
    version = renderer_version(cert)
    return make(
        level=level, params=(cert.get("params") if isinstance(cert, dict) else None) or {},
        producer="raw-native", version=version,
        backend=f"raw-native-{version}-cpu" + (f"-{platform}" if platform else ""),
        content=outputs_document(found), media=outputs_media(), outputs=found,
        reference={"backend": "raw-cert/2 outputs record",
                   "content_sha256": ss.sha256_hex(outputs_document(record))},
        tolerance=tol,
        flywheel={"verdict": result["verdict"], "reason": result["reason"],
                  "detail": result["detail"], "mismatches": result["mismatches"],
                  "certificate_sha256": (certificate_sha256(cert)
                                         if isinstance(cert, dict) else None),
                  "renderer": cert.get("renderer") if isinstance(cert, dict) else None,
                  "platform": platform or None, **dict(flywheel or {})})
