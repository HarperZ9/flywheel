"""brand_kit.py: one seed, a whole identity, one receipt.

A kit is everything a small brand needs to exist coherently: the mark
(the seeded aperture, square), the banner and poster wearing the name in
the seed's own face, a specimen sheet of the family, the font files at
two weights, and the design tokens that make the identity portable. All
of it derives from ONE seed plus a name, deterministically: the kit id
binds every artifact hash, so an identity can be re-derived, audited,
or handed to a client with its provenance intact.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json

from .design_studio import GROUNDS, compose
from .typeface_family import mint_family

SCHEMA = "flywheel.brand-kit/v1"


def _specimen_png(instances: list, name: str) -> "tuple[bytes, str] | None":
    """The family on one sheet: every weight, the proving line, digits."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    rows = [(i["style"], base64.b64decode(i["ttf_b64"])) for i in instances]
    W, line_h, pad = 1800, 150, 60
    H = pad * 2 + line_h * len(rows) + 40
    g = GROUNDS["dark"]
    im = Image.new("RGB", (W, H), g["ground"])
    d = ImageDraw.Draw(im)
    y = pad
    for style, ttf in rows:
        f = ImageFont.truetype(io.BytesIO(ttf), 84)
        fs = ImageFont.truetype(io.BytesIO(ttf), 26)
        d.text((pad, y + 30), f"{name.lower()} 0123456789", font=f,
               fill=g["ink"])
        d.text((W - pad - 260, y + 6), style.lower(), font=fs,
               fill=g["soft"])
        y += line_h
    buf = io.BytesIO()
    im.save(buf, "PNG")
    png = buf.getvalue()
    return png, hashlib.sha256(png).hexdigest()


def mint_kit(name: str, seed: int = 58, tagline: str = "",
             face_params: dict | None = None) -> dict:
    """Name + seed -> mark, banner, poster, specimen, fonts, tokens."""
    name = (name or "").strip()
    if not name:
        return {"refused": True, "refusals": ["a kit needs a brand name"]}
    if len(name) > 40:
        return {"refused": True,
                "refusals": ["keep the name under 40 characters; a kit is "
                             "an identity, not a paragraph"]}

    fam = mint_family(face_params, seed=seed, family=f"{name} Mint",
                      instances=[("Regular", 0.085), ("Bold", 0.145)])
    if fam["refused"]:
        return {"refused": True,
                "refusals": ["the family refused: " + fam["refusals"][0]]}

    mark = compose(name, fmt="square", seed=seed, ground="dark",
                   face_params=face_params)
    banner = compose(name, subtitle=tagline, fmt="banner", seed=seed,
                     ground="dark", face_params=face_params)
    poster = compose(name, subtitle=tagline, fmt="poster", seed=seed,
                     ground="dark", face_params=face_params)
    for piece, label in ((mark, "mark"), (banner, "banner"),
                         (poster, "poster")):
        if piece.get("refused"):
            return {"refused": True,
                    "refusals": [f"the {label} refused: "
                                 + "; ".join(piece["refusals"])]}

    spec = _specimen_png(fam["instances"], name)
    if spec is None:
        return {"refused": True,
                "refusals": ["brand kits need Pillow for the raster side"]}
    spec_png, spec_sha = spec

    tokens = {
        "schema": "flywheel.design-tokens/v1",
        "brand": name,
        "seed": int(seed),
        "family": f"{name} Mint",
        "face_params": fam["receipt"]["params"],
        "grounds": {k: {kk: "#%02X%02X%02X" % tuple(vv)
                        for kk, vv in v.items()}
                    for k, v in GROUNDS.items()},
        "note": "verdict colors state verdicts; the ink and ground carry "
                "everything else",
    }

    receipt = {
        "schema": SCHEMA,
        "brand": name,
        "tagline": tagline,
        "seed": int(seed),
        "family_id": fam["receipt"]["family_id"],
        "artifacts": {
            "mark_png_sha256": mark["receipt"]["png_sha256"],
            "banner_png_sha256": banner["receipt"]["png_sha256"],
            "poster_png_sha256": poster["receipt"]["png_sha256"],
            "specimen_png_sha256": spec_sha,
            "fonts": {i["style"].lower(): i["ttf_sha256"]
                      for i in fam["instances"]},
        },
        "note": "one seed, one name, every hash re-derivable end to end",
    }
    receipt["kit_id"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:16]

    return {
        "refused": False,
        "refusals": [],
        "receipt": receipt,
        "tokens": tokens,
        "mark_png_b64": mark["png_b64"],
        "banner_png_b64": banner["png_b64"],
        "poster_png_b64": poster["png_b64"],
        "specimen_png_b64": base64.b64encode(spec_png).decode("ascii"),
        "fonts": [{"style": i["style"], "ttf_b64": i["ttf_b64"],
                   "ttf_sha256": i["ttf_sha256"]}
                  for i in fam["instances"]],
    }
