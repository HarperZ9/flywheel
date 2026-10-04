"""The vendored superstack copy still behaves as the contract says, on this runtime.

A hash match shows the file is unchanged. These vectors show it still passes the
contract's own test vectors here (VENDORING.md step 4). The three vector files
the raw lane depends on (canonical JSON, the receipt, the reconcile metrics) are
copied from the same v0.1.0 tag, and each is checked against MANIFEST.json first,
so a vector edited by hand fails before it can pass anything.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from harness._vendor import superstack as ss

VEC = Path(__file__).resolve().parent / "fixtures" / "superstack"
FILES = ("canonical.json", "receipt.json", "reconcile.json")


def _vectors(name: str) -> dict:
    raw = (VEC / name).read_bytes()
    manifest = json.loads((VEC / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["contract"] == ss.CONTRACT
    assert hashlib.sha256(raw).hexdigest() == manifest["files"][name], name
    return json.loads(raw.decode("utf-8"))


@pytest.mark.parametrize("name", FILES)
def test_each_vendored_vector_file_matches_the_manifest(name):
    assert _vectors(name)["spec"].startswith("SPEC.md")


def test_canonical_json_vectors():
    v = _vectors("canonical.json")
    for c in v["numbers"]:
        x = float(c["in"]) if c["type"] == "float" else int(c["in"])
        assert ss.canonical_number(x) == c["out"], c["in"]
    for c in v["docs"]:
        out = ss.canonical(json.loads(c["in"]))
        assert out == c["out"], c["in"]
        assert ss.sha256_hex(out.encode("utf-8")) == c["sha256"], c["in"]
    for text in v["reject_docs"]:
        with pytest.raises((ValueError, TypeError, OverflowError)):
            ss.canonical(json.loads(text))


def test_receipt_vectors_make_and_verify():
    v = _vectors("receipt.json")
    assert v["make"] and v["verify"]
    for c in v["make"]:
        args = dict(c["args"])
        content = bytes.fromhex(args.pop("content_hex"))
        got = ss.make_receipt(content=content, **args)
        assert ss.canonical(got) == c["canonical"]
        assert got["receipt_sha256"] == c["receipt_sha256"]
    for c in v["verify"]:
        assert ss.verify_receipt(c["receipt"]) == c["errors"], c["name"]


def test_reconcile_vectors():
    v = _vectors("reconcile.json")
    for c in v["identity"]:
        assert ss.identity(c["ref"], c["cand"]) == c["out"]
    for c in v["f32_rmse"]:
        a = struct.pack(f"<{len(c['ref'])}f", *c["ref"])
        b = struct.pack(f"<{len(c['cand'])}f", *c["cand"])
        mask = None if c["mask"] is None else bytes(c["mask"])
        assert ss.f32_rmse(a, b, mask) == c["rmse"]
    for c in v["round6"]:
        assert ss.round6(c["in"]) == c["out"]
