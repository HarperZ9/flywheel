"""typeface_route.py -- the /api/typeface* POST bodies, out of gateway.py.

Behavior-identical extraction: the gateway keeps a few-line dispatch stub and
this module owns the mint / publish / family / variable route bodies. The
forge, TTF writer, and gallery stay where they were; only the HTTP glue moved.
"""
from __future__ import annotations

import base64


def _seed(req: dict, default: int) -> int:
    try:
        return int(req.get("seed", default))
    except (TypeError, ValueError):
        return default


def _params(req: dict) -> "dict | None":
    p = req.get("params")
    return p if isinstance(p, dict) else None


def typeface_post(p: str, req: dict) -> "tuple[dict, int]":
    """(body, http_code) for one /api/typeface* POST route."""
    if p == "/api/typeface":                       # mint a parametric face under witness
        from harness.typeface_forge import mint
        face = mint(_params(req) or {}, seed=_seed(req, 0))
        if req.get("ttf") and not face.get("refused"):
            # the minted outlines as an installable TrueType file
            from harness.typeface_ttf import to_ttf
            family = str(req.get("family") or "Zentropy Mint")[:48]
            face["ttf_b64"] = base64.b64encode(
                to_ttf(face, family=family)).decode("ascii")
            face["ttf_family"] = family
        if req.get("publish") and not face.get("refused"):
            # file the face in the witnessed gallery so others can browse
            # and reuse it; a refused face is never a product
            from harness.typeface_gallery import publish_face
            face["gallery"] = publish_face(
                face, family=str(req.get("family") or "Zentropy Mint"))
        return face, 200
    if p == "/api/typeface/publish":               # file an already-minted face in the gallery
        from harness.typeface_forge import mint
        from harness.typeface_ttf import to_ttf
        from harness.typeface_gallery import publish_face
        face = mint(_params(req) or {}, seed=_seed(req, 0))
        if not face.get("refused"):
            family = str(req.get("family") or "Zentropy Mint")[:48]
            face["ttf_b64"] = base64.b64encode(
                to_ttf(face, family=family)).decode("ascii")
        out = publish_face(face, family=str(req.get("family") or "Zentropy Mint"))
        return out, 400 if "error" in out else 200
    if p == "/api/typeface/family":                # one seed, a product line of weights
        from harness.typeface_family import mint_family
        out = mint_family(_params(req), seed=_seed(req, 58),
                          family=str(req.get("family") or "Zentropy Mint")[:48])
        return out, 400 if out.get("refused") else 200
    if p == "/api/typeface/variable":              # the family as ONE variable font (wght axis)
        from harness.typeface_family import mint_variable_family
        out = mint_variable_family(_params(req), seed=_seed(req, 58),
                                   family=str(req.get("family") or "Zentropy Mint")[:48])
        return out, 400 if out.get("refused") else 200
    return {"error": "not found"}, 404
