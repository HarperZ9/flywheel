"""typeface_gallery.py: a witnessed marketplace of minted faces.

A minted face is already reproducible from its seed and params; publishing
one files it in the verifiable store under a stable kind, so a face someone
minted can be browsed, fetched, and reused by anyone with the engine. The
listing carries only metadata (id, family, the design params, the font's
hash); the bytes come on demand from the single-face fetch. Every entry
re-derives: mint the stored seed+params and you get the same mint_id back.
"""
from __future__ import annotations

import base64

from .store import get_entity, put_entity, query_entities

KIND = "typeface-face"


def publish_face(face: dict, family: str = "Zentropy Mint") -> dict:
    """File a minted face in the gallery. Returns its listing id, or an
    error when the face was refused (a refused face is not a product)."""
    if face.get("refused"):
        return {"error": "a refused face cannot be published"}
    receipt = face.get("receipt", {})
    mint_id = str(receipt.get("mint_id", "")).strip()
    if not mint_id:
        return {"error": "the face carries no mint_id to key on"}
    ttf_b64 = face.get("ttf_b64", "")
    doc = {"mint_id": mint_id, "family": family[:48],
           "params": receipt.get("params", {}),
           "seed": receipt.get("seed", 0),
           "metrics": face.get("metrics", {}),
           "ttf_sha256": receipt.get("ttf_sha256")
           or (base64_sha(ttf_b64) if ttf_b64 else ""),
           "ttf_b64": ttf_b64, "svg": face.get("svg", "")}
    # key on the mint_id so republishing the same face is idempotent, not a
    # second row: the gallery lists faces, not attempts.
    res = put_entity(KIND, doc, eid=f"face-{mint_id}")
    return {"published": True, "eid": res["eid"], "mint_id": mint_id,
            "sha256": res["sha256"]}


def base64_sha(b64: str) -> str:
    import hashlib
    try:
        return hashlib.sha256(base64.b64decode(b64)).hexdigest()
    except Exception:
        return ""


def gallery(limit: int = 60) -> dict:
    """The listing: metadata only, newest first. The bytes are a fetch away
    so a browse never ships megabytes of fonts nobody asked for."""
    rows = query_entities(kind=KIND, limit=max(1, min(limit, 500)))
    faces = []
    for r in rows:
        ent = get_entity(r["eid"])
        if not ent:
            continue
        d = ent["data"]
        faces.append({"eid": r["eid"], "mint_id": d.get("mint_id"),
                      "family": d.get("family"), "seed": d.get("seed"),
                      "params": d.get("params", {}),
                      "ttf_sha256": d.get("ttf_sha256"),
                      "created": r["created"]})
    return {"schema": "flywheel.typeface-gallery/v1", "count": len(faces),
            "faces": faces}


def fetch_face(eid: str) -> dict:
    """One face in full, bytes included, for wearing or downloading."""
    ent = get_entity((eid or "").strip())
    if not ent or ent["kind"] != KIND:
        return {"error": f"no gallery face with id {eid!r}"}
    d = ent["data"]
    return {"eid": ent["eid"], "mint_id": d.get("mint_id"),
            "family": d.get("family"), "seed": d.get("seed"),
            "params": d.get("params", {}), "svg": d.get("svg", ""),
            "ttf_sha256": d.get("ttf_sha256"), "ttf_b64": d.get("ttf_b64", "")}
