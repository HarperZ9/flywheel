#!/usr/bin/env python3
"""receipt.py — the dataset receipt: corpus -> shards -> checkpoint, one
re-derivable provenance chain written beside the trained adapter.

Today the chain is severed at every joint: manifest.jsonl knows the sources,
the packed shards are opaque, and the checkpoint knows nothing about either.
A trained adapter cannot answer "what exactly did you train on?" with anything
re-checkable. This closes it: one JSON receipt whose every layer is a content
hash a third party can re-derive from the same inputs and compare.

Layers (each independently re-derivable):
  allowlist   sha256 of the allowlist file           (what was ALLOWED in)
  manifest    sha256 of manifest.jsonl               (what was SELECTED)
  corpus      fold over (hashed path, file sha256)   (what the bytes WERE)
  pack        sha256 of each shard + PACK_COMPLETE   (what was TRAINED-shaped)
  checkpoint  sha256 of adapter config + weights     (what came OUT)

PRIVACY (inherited invariant): no source path is ever written into the
receipt. File identities are carried as sha256(path) so drift is localizable
without disclosing the corpus composition. Aggregates only.

Verdicts reuse the harness vocabulary: MATCH (layer re-derives byte-identical),
DRIFT (re-derivation disagrees — the corpus/pack/checkpoint changed), and
UNVERIFIABLE (the layer's inputs are gone; fail closed, never assumed MATCH).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"

RECEIPT_NAME = "dataset_receipt.json"
_CKPT_FILES = ("adapter_config.json", "adapter_model.safetensors",
               "trainer_state.json")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_layer(manifest_path: Path, base: Path) -> dict:
    """Fold the actual corpus bytes: for every manifest record, (sha256 of the
    path, sha256 of the file bytes), combined in stable order. Paths are hashed,
    never stored — drift is localizable without disclosing composition."""
    pairs, missing, total_bytes = [], 0, 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        fp = base / rec["path"]
        pid = _sha(rec["path"].encode("utf-8"))
        try:
            fh = _sha_file(fp)
            total_bytes += fp.stat().st_size
        except OSError:
            missing += 1
            fh = "MISSING"
        pairs.append(f"{pid}:{fh}")
    pairs.sort()
    return {"content_hash": _sha("\n".join(pairs).encode()),
            "files": len(pairs), "files_missing": missing,
            "bytes": total_bytes}


def pack_layer(packed_dir: Path) -> dict:
    marker = packed_dir / "PACK_COMPLETE.json"
    shards = sorted(packed_dir.glob("shard_*.npy"))
    return {"marker_hash": _sha_file(marker) if marker.exists() else "MISSING",
            "shards": len(shards),
            "shards_hash": _sha("\n".join(
                f"{p.name}:{_sha_file(p)}" for p in shards).encode())}


def checkpoint_layer(checkpoint_dir: Path) -> dict:
    out = {}
    for name in _CKPT_FILES:
        p = checkpoint_dir / name
        out[name] = _sha_file(p) if p.exists() else "MISSING"
    return out


def build_receipt(*, allowlist: str | Path, manifest: str | Path,
                  base: str | Path, packed_dir: str | Path | None = None,
                  checkpoint_dir: str | Path | None = None,
                  tokenizer_ref: str = "") -> dict:
    """Derive the full chain from the actual inputs. Deterministic: the same
    bytes produce the identical receipt (no timestamps — git records when)."""
    allowlist, manifest, base = Path(allowlist), Path(manifest), Path(base)
    r = {"receipt": "dataset/v1",
         "tokenizer_ref": tokenizer_ref,
         "allowlist": {"hash": _sha_file(allowlist)},
         "manifest": {"hash": _sha_file(manifest)},
         "corpus": corpus_layer(manifest, base)}
    if packed_dir is not None:
        r["pack"] = pack_layer(Path(packed_dir))
    if checkpoint_dir is not None:
        r["checkpoint"] = checkpoint_layer(Path(checkpoint_dir))
    return r


def write_receipt(receipt: dict, checkpoint_dir: str | Path) -> Path:
    p = Path(checkpoint_dir) / RECEIPT_NAME
    p.write_text(json.dumps(receipt, indent=2, sort_keys=True),
                 encoding="utf-8")
    return p


def verify_receipt(receipt: dict, *, allowlist: str | Path,
                   manifest: str | Path, base: str | Path,
                   packed_dir: str | Path | None = None,
                   checkpoint_dir: str | Path | None = None) -> dict:
    """Re-derive every layer the receipt carries and compare. A layer whose
    inputs are gone is UNVERIFIABLE (fail closed). Overall verdict folds like
    the frontier: any DRIFT -> DRIFT, else any UNVERIFIABLE -> UNVERIFIABLE,
    else MATCH. Layers the receipt never carried are not judged."""
    layers: dict[str, str] = {}
    reasons: dict[str, str] = {}

    def judge(name: str, stored, derive):
        try:
            fresh = derive()
        except OSError as e:
            layers[name] = UNVERIFIABLE
            reasons[name] = f"inputs gone: {e!r}"
            return
        layers[name] = MATCH if fresh == stored else DRIFT
        if fresh != stored:
            reasons[name] = "re-derivation disagrees with the stored layer"

    judge("allowlist", receipt["allowlist"],
          lambda: {"hash": _sha_file(Path(allowlist))})
    judge("manifest", receipt["manifest"],
          lambda: {"hash": _sha_file(Path(manifest))})
    judge("corpus", receipt["corpus"],
          lambda: corpus_layer(Path(manifest), Path(base)))
    if "pack" in receipt:
        if packed_dir is None:
            layers["pack"] = UNVERIFIABLE
            reasons["pack"] = "receipt carries a pack layer but no packed_dir supplied"
        else:
            judge("pack", receipt["pack"], lambda: pack_layer(Path(packed_dir)))
    if "checkpoint" in receipt:
        if checkpoint_dir is None:
            layers["checkpoint"] = UNVERIFIABLE
            reasons["checkpoint"] = ("receipt carries a checkpoint layer but no "
                                     "checkpoint_dir supplied")
        else:
            judge("checkpoint", receipt["checkpoint"],
                  lambda: checkpoint_layer(Path(checkpoint_dir)))
    vs = layers.values()
    overall = (DRIFT if DRIFT in vs
               else UNVERIFIABLE if UNVERIFIABLE in vs else MATCH)
    drifted = sorted(k for k, v in layers.items() if v == DRIFT)
    return {"verdict": overall, "layers": layers, "reasons": reasons,
            "drifted_layers": drifted}
