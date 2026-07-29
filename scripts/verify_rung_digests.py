#!/usr/bin/env python3
"""verify_rung_digests.py -- is the local model store the ladder we preregistered?

A preregistration that pins nine rungs by digest is a promise until something
checks it. This is the check. The pins come from `rung_pins.py`, which reads them
out of the frozen document and refuses if its bytes have changed, so no pin is
ever transcribed into code where it could go stale.

What is checkable offline, and what is not, measured rather than assumed:

  * Ollama stores the registry manifest byte-for-byte, so the local manifest
    file's sha256 IS the pinned registry manifest digest. Verified empirically
    against R5 and R8 before this script was written.
  * The model-layer digest inside that manifest names the weight blob, and the
    blob is stored under that digest as its filename.
  * Ollama verified the blob against its digest at pull time. This script does
    NOT rehash multi-gigabyte blobs by default; it checks that the pinned blob
    exists at the pinned size. `--rehash` upgrades that to a content check, at
    the cost of reading every byte.

The distinction the prereg draws between PINNED and SERVABLE is kept here: a
rung that is absent is reported ABSENT, not FAIL, because pinning never required
possession. `--require-all` is how a demonstration run asserts possession.

Exit 0 when nothing contradicts the freeze, 1 on any mismatch (or any absence
under --require-all).

Stdlib only, like every other checker here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rung_pins import (BLOB_PIN, HEX64, FreezeMismatch,  # noqa: E402,F401
                       blob_sha256, frozen_prereg, parse_pins, pins_in_order)

REPO = Path(__file__).resolve().parent.parent

MODEL_MEDIA_SUFFIX = ".image.model"


def default_store() -> tuple[Path, str]:
    """(store path, where that came from).

    Resolved from the environment rather than hard-coded, for two reasons. A
    published repo must name no operator's drive. And a relocated store is
    exactly the case where a hard-coded default would check the WRONG directory:
    the old store often still exists and partially satisfies the pins, so the
    checker would report some rungs absent and look merely incomplete rather than
    misaimed. Naming the source in the output is how a reader can tell which
    happened.
    """
    env = os.environ.get("OLLAMA_MODELS", "").strip()
    if env:
        return Path(env), "OLLAMA_MODELS"
    return Path.home() / ".ollama" / "models", "ollama default location"

PASS, FAIL, ABSENT, UNCHECKED = "PIN_MATCH", "PIN_MISMATCH", "ABSENT", "UNCHECKED"


def manifest_path(store: Path, model: str) -> Path:
    name, _, tag = model.partition(":")
    return (store / "manifests" / "registry.ollama.ai" / "library"
            / name / (tag or "latest"))


def model_layer(doc: dict) -> dict | None:
    for layer in doc.get("layers", []):
        if str(layer.get("mediaType", "")).endswith(MODEL_MEDIA_SUFFIX):
            return layer
    return None


def check_rung(pin: dict, store: Path, rehash: bool) -> dict:
    out = {"rung": pin["rung"], "model": pin["model"], "kind": pin["kind"],
           "notes": []}
    path = manifest_path(store, pin["model"])

    if pin["kind"] == "weight":
        # A weight pin names a GGUF on disk, so it starts out unservable and
        # unchecked here. But registering that GGUF makes the pin checkable for
        # free: Ollama stores the file under its own sha256, so the model-layer
        # digest of a registered local artifact IS the pinned weight digest.
        # This is the provenance closure R4 already has, and refusing to check
        # it once available would leave the strongest rung the weakest verified.
        if not path.is_file():
            out["status"] = UNCHECKED
            out["notes"].append(
                "pinned but not servable: no store entry, so the weight digest "
                "is not checkable here. Verify the GGUF against its release "
                "manifest, or register it to make this a store check.")
            return out
        out["notes"].append(
            "registered local artifact: the store blob digest is compared "
            "against the pinned weight sha256 directly")

    if not path.is_file():
        out["status"] = ABSENT
        out["notes"].append(f"no manifest at {path}")
        return out
    raw = path.read_bytes()
    doc = json.loads(raw)
    layer = model_layer(doc)
    if layer is None:
        out["status"] = FAIL
        out["notes"].append("manifest carries no model layer")
        return out
    digest = str(layer["digest"])
    blob = store / "blobs" / digest.replace(":", "-")
    bad = []

    if pin["kind"] == "manifest":
        got = blob_sha256(raw)
        out["manifest_sha256"] = got
        if got != pin["manifest_sha256"]:
            bad.append(f"manifest sha256 {got} != pinned {pin['manifest_sha256']}")
        out["model_layer"] = digest
        if digest != pin["model_layer"]:
            bad.append(f"model layer {digest} != pinned {pin['model_layer']}")
    elif pin["kind"] == "blob":  # R1-R4: pinned in filename form, sha256-...
        got = digest.replace(":", "-")
        out["blob"] = got
        if got != pin["blob"]:
            bad.append(f"weight blob {got} != pinned {pin['blob']}")
    else:  # weight pin, now registered: bare hex, plus an exact byte count
        got = digest.split(":", 1)[-1]
        out["weight_sha256"] = got
        if got != pin["weight_sha256"]:
            bad.append(f"weight sha256 {got} != pinned {pin['weight_sha256']}")
        declared = layer.get("size")
        if isinstance(declared, int) and declared != pin["bytes"]:
            bad.append(f"weights are {declared} bytes, pinned {pin['bytes']}")

    if not blob.is_file():
        bad.append(f"pinned blob missing from store: {blob.name}")
    else:
        size = blob.stat().st_size
        out["bytes"] = size
        declared = layer.get("size")
        if isinstance(declared, int) and declared != size:
            bad.append(f"blob is {size} bytes, manifest declares {declared}")
        if rehash:
            h = hashlib.sha256()
            with blob.open("rb") as fh:
                for chunk in iter(lambda: fh.read(8 << 20), b""):
                    h.update(chunk)
            out["rehashed"] = h.hexdigest()
            if h.hexdigest() != digest.split(":", 1)[-1]:
                bad.append("blob CONTENT does not hash to its own digest")
            else:
                out["notes"].append("blob content rehashed and matches")
        else:
            out["notes"].append(
                "blob present at declared size; content not rehashed "
                "(ollama verified it at pull time). Use --rehash to check bytes.")

    out["status"] = FAIL if bad else PASS
    out["notes"].extend(bad)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None,
                    help="Ollama model store root (manifests/ and blobs/); "
                         "defaults to $OLLAMA_MODELS, else ollama's own default")
    ap.add_argument("--require-all", action="store_true",
                    help="treat an absent rung as a failure (possession asserted)")
    ap.add_argument("--rehash", action="store_true",
                    help="rehash every pinned blob; reads every byte")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    try:
        text, record = frozen_prereg(REPO)
    except FreezeMismatch as exc:
        print(f"FREEZE MISMATCH: {exc}", file=sys.stderr)
        return 1
    pins = parse_pins(text)
    if args.store:
        store, source = Path(args.store), "--store"
    else:
        store, source = default_store()
    findings = [check_rung(p, store, args.rehash) for p in pins_in_order(pins)]

    mismatch = [f for f in findings if f["status"] == FAIL]
    absent = [f for f in findings if f["status"] == ABSENT]
    unchecked = [f for f in findings if f["status"] == UNCHECKED]
    # --require-all asserts the whole ladder is possessed AND verified, so an
    # unchecked rung fails it too. Counting UNCHECKED as satisfied would let a
    # demonstration claim a nine-rung ladder while one rung was never verified.
    unestablished = absent + unchecked
    ok = not mismatch and not (unestablished and args.require_all)

    if args.as_json:
        print(json.dumps({
            "prereg_id": record["prereg_id"],
            "frozen_sha256": record["frozen_sha256"],
            "store": str(store),
            "store_from": source,
            "rehashed": args.rehash,
            "findings": findings,
            "verdict": "CONSISTENT_WITH_FREEZE" if ok else "CONTRADICTS_FREEZE",
        }, indent=1))
        return 0 if ok else 1

    print(f"prereg {record['prereg_id']}")
    print(f"  frozen sha256 {record['frozen_sha256']} (bytes still match)")
    print(f"  store {store}  (from {source})")
    print(f"  {len(pins)} rungs pinned\n")
    for f in findings:
        print(f"  {f['status']:<14} {f['rung']:<3} {f['model']}")
        for note in f["notes"]:
            print(f"                     - {note}")
    served = sum(1 for f in findings if f["status"] == PASS)
    print(f"\n{served} rung(s) present and matching the pin, "
          f"{len(absent)} absent, {len(unchecked)} unchecked, "
          f"{len(mismatch)} contradicting")
    if mismatch:
        print("A PINNED RUNG DOES NOT MATCH THE FREEZE. The ladder being served "
              "is not the ladder that was preregistered.")
    elif unestablished and args.require_all:
        names = ", ".join(f"{f['rung']} ({f['status']})" for f in unestablished)
        print(f"--require-all was given and these rungs are not established: "
              f"{names}. Possession and verification of the full ladder is not "
              f"yet demonstrated.")
    else:
        print("Nothing in the local store contradicts the frozen preregistration.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
