"""raw_native_receipt.py -- read raw-native's own superstack receipt and hold it to its files.

From 0.5.0 raw-native writes ``receipt.json`` beside ``certificate.json``: a
``superstack.receipt/1`` whose content is the screen-space AO and whose
reference is the ray-traced AO, both as canonical ``f32`` (float32,
little-endian, rows top-down). Its identity reads DRIFT by design, since the two
are different estimators, and its tolerance verdict is the claim.

The lane reads that receipt directly and checks it rather than trusting it:

* its seal and fields pass the vendored contract's ``verify_receipt``;
* its content and reference hashes are the AO buffers on disk;
* every output digest it lists matches the file, and ``frame.rgb8`` matches the
  pixel body of ``frame.ppm``;
* its producer version, pixel count and tolerance verdict agree with the
  certificate.

A render without a receipt (raw-native 0.4.0 and earlier) is not penalized:
the check reports it absent. Pure data: this module runs nothing.
"""
from __future__ import annotations

import json

from .._vendor import superstack as ss
from .raw_ao_buffers import BufferError, canonical_ao

NAME = "receipt.json"


def _ppm_body(data: bytes) -> bytes:
    parts, pos = [], 0
    while len(parts) < 4:
        end = data.index(b"\n", pos)
        parts += data[pos:end].split()
        pos = end + 1
    return data[pos:]


def _file_digest(name: str, files) -> str | None:
    if name == "frame.rgb8" and "frame.ppm" in files:
        return ss.sha256_hex(_ppm_body(files["frame.ppm"]))
    return ss.sha256_hex(files[name]) if name in files else None


def _agreement(rec: dict, cert: dict, files) -> list[str]:
    """What in the receipt disagrees with the files or the certificate."""
    errors = []
    try:
        if rec["content_sha256"] != ss.sha256_hex(canonical_ao(files["ao_ss.pfm"])[2]):
            errors.append("content is not ao_ss")
        ref = rec["reconcile"]["reference"]["content_sha256"]
        if ref != ss.sha256_hex(canonical_ao(files["ao_rt.pfm"])[2]):
            errors.append("reference is not ao_rt")
    except (BufferError, KeyError, TypeError, ValueError) as e:
        errors.append(f"buffers unreadable: {e}")
    outputs = rec.get("outputs") if isinstance(rec.get("outputs"), dict) else {}
    errors += [f"output {n}" for n, d in sorted(outputs.items())
               if n != NAME and _file_digest(n, files) != d]
    renderer = cert.get("renderer") if isinstance(cert, dict) else None
    producer = rec.get("producer") or {}
    if renderer != f"{producer.get('name')} {producer.get('version')}":
        errors.append("producer is not the certificate's renderer")
    tol = (rec.get("reconcile") or {}).get("tolerance") or {}
    if tol.get("verdict") != (cert or {}).get("verdict"):
        errors.append("tolerance verdict is not the certificate's")
    if (tol.get("metrics") or {}).get("pixels") != ((cert or {}).get("exact") or {}).get("pixels"):
        errors.append("pixel count is not the certificate's")
    return errors


def check(cert, files) -> dict:
    """``{"present", "errors", "receipt_sha256", "identity", "tolerance"}``.
    An empty ``errors`` list means the receipt seals and agrees with its files."""
    data = files.get(NAME)
    if data is None:
        return {"present": False, "errors": [], "receipt_sha256": None}
    try:
        rec = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        return {"present": True, "errors": [f"unreadable: {e}"], "receipt_sha256": None}
    if not isinstance(rec, dict):
        return {"present": True, "errors": ["not a json object"], "receipt_sha256": None}
    errors = [f"superstack:{code}" for code in ss.verify_receipt(rec)]
    errors += _agreement(rec, cert, files)
    rc = rec.get("reconcile") if isinstance(rec.get("reconcile"), dict) else {}
    return {"present": True, "errors": errors, "receipt_sha256": rec.get("receipt_sha256"),
            "identity": rc.get("identity"),
            "tolerance": (rc.get("tolerance") or {}).get("verdict")}
