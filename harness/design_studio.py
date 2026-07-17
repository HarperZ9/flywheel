"""design_studio.py: the poster composer, the design pillar as one call.

A poster here is a witnessed composition: the seeded aperture plate (the
ecosystem's one recurring form, fine radial line-work on a calm ground)
typeset in a face the forge minted from the same seed, with the receipt
line carried ON the artwork as a design element. The same inputs always
compose the same bytes, so a poster's originality is re-derivable: plate
seed, face mint, and copy hash all ride one receipt.

Pillow is the one soft dependency; without it the composer refuses by
name instead of pretending.
"""
from __future__ import annotations

import base64
import hashlib
import io
import math
import random

from .typeface_forge import DEFAULTS, mint
from .typeface_ttf import to_ttf

SCHEMA = "flywheel.studio-poster/v1"

FORMATS = {
    "poster": (1200, 1600),
    "banner": (1600, 900),
    "og": (1280, 640),
    "slide": (2560, 1440),
    "square": (1080, 1080),
}

GROUNDS = {
    "dark": {"ground": (11, 14, 15), "ink": (238, 241, 238),
             "soft": (170, 176, 178), "accent": (95, 174, 147)},
    "ceramic": {"ground": (244, 243, 239), "ink": (11, 12, 14),
                "soft": (90, 94, 100), "accent": (31, 122, 82)},
}


def _aperture(draw, cx, cy, r_base, ink, rng, strokes, ss):
    for _ in range(strokes):
        a = rng.uniform(0, 2 * math.pi)
        band = rng.random()
        if band < 0.62:
            r0 = r_base * rng.uniform(0.86, 1.0)
            r1 = r0 + r_base * rng.uniform(0.015, 0.16)
            alpha = int(rng.uniform(26, 92))
        elif band < 0.86:
            r0 = r_base * rng.uniform(0.30, 0.86)
            r1 = r0 + r_base * rng.uniform(0.01, 0.05)
            alpha = int(rng.uniform(10, 34))
        else:
            r0 = r_base * rng.uniform(1.02, 1.34)
            r1 = r0 + r_base * rng.uniform(0.01, 0.10)
            alpha = int(rng.uniform(6, 22))
        x0, y0 = cx + r0 * math.cos(a), cy + r0 * math.sin(a)
        x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
        draw.line((x0, y0, x1, y1), fill=ink + (alpha,), width=ss)


def _scanlines(Image, ImageDraw, img, ground, step=6, alpha=10):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    dark = tuple(max(0, c - 14) for c in ground)
    for y in range(0, img.size[1], step):
        d.line((0, y, img.size[0], y), fill=dark + (alpha,), width=1)
    return Image.alpha_composite(img, overlay)


# composition presets: where the orb sits and how dense the line-work is
ORBS = {
    "auto": None,                                  # portrait/landscape logic
    "center": ((0.5, 0.45), 0.30, 4200),
    "high": ((0.5, 0.30), 0.27, 4200),
    "right": ((0.72, 0.46), 0.34, 4200),
    "quiet": ((0.82, 0.22), 0.16, 2600),
}


def compose(title: str, subtitle: str = "", fmt: str = "poster",
            seed: int = 58, ground: str = "dark", accent: bool = True,
            face_params: dict | None = None, orb: str = "auto",
            density: float = 1.0, want_svg: bool = False,
            want_pdf: bool = False) -> dict:
    """Title + subtitle on a seeded plate, typeset in the seed's own face."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        return {"refused": True,
                "refusals": ["design-studio needs Pillow for rasterization; "
                             "install pillow or render the SVG side"]}
    # the minted face is lowercase + digits: fold the copy honestly and
    # refuse what still has no glyph, never drop characters in silence
    title = (title or "").strip().lower()
    subtitle = (subtitle or "").lower()
    if not title:
        return {"refused": True, "refusals": ["a poster needs a title"]}
    if fmt not in FORMATS:
        return {"refused": True,
                "refusals": [f"unknown format {fmt!r}; "
                             f"formats: {', '.join(sorted(FORMATS))}"]}
    if ground not in GROUNDS:
        return {"refused": True,
                "refusals": [f"unknown ground {ground!r}; grounds: "
                             f"{', '.join(sorted(GROUNDS))}"]}
    if orb not in ORBS:
        return {"refused": True,
                "refusals": [f"unknown orb preset {orb!r}; presets: "
                             f"{', '.join(sorted(ORBS))}"]}
    density = max(0.4, min(2.0, float(density)))

    face = mint({**DEFAULTS, **(face_params or {})}, seed=seed)
    if face["refused"]:
        return {"refused": True,
                "refusals": ["the face refused: " + "; ".join(face["refusals"])]}
    # the supported set is the mint's own charset, never a guess here
    supported = set(face["receipt"]["charset"]) | {" ", "\n"}
    missing = sorted(set(title + subtitle) - supported)
    if missing:
        return {"refused": True,
                "refusals": ["no glyph yet for: " + " ".join(missing)]}
    ttf = to_ttf(face, family=f"Zentropy Mint {seed}")

    W, H = FORMATS[fmt]
    g = GROUNDS[ground]
    ss = 2
    w, h = W * ss, H * ss
    img = Image.new("RGBA", (w, h), g["ground"] + (255,))
    draw = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(seed)
    portrait = H >= W
    if ORBS[orb] is None:
        orb_at = (0.5, 0.34) if portrait else (0.74, 0.46)
        r_frac = 0.30 if portrait else 0.34
        base_strokes = 4200
    else:
        orb_at, r_frac, base_strokes = ORBS[orb]
    strokes = int(base_strokes * density)
    _aperture(draw, w * orb_at[0], h * orb_at[1], min(w, h) * r_frac,
              g["ink"], rng, strokes=strokes, ss=ss)
    if accent:
        r = min(w, h) * r_frac
        cx, cy = w * orb_at[0], h * orb_at[1]
        start = rng.uniform(0, 360)
        draw.arc((cx - r, cy - r, cx + r, cy + r), start, start + 34,
                 fill=g["accent"] + (215,), width=ss * 2)
    img = _scanlines(Image, ImageDraw, img, g["ground"])
    draw = ImageDraw.Draw(img, "RGBA")   # the composite is a NEW image

    # typesetting: the seed's own face, words with weight, lower block
    t_size = int(w / (11 if portrait else 16))
    s_size = max(18 * ss, t_size // 3)
    f_title = ImageFont.truetype(io.BytesIO(ttf), t_size)
    f_sub = ImageFont.truetype(io.BytesIO(ttf), s_size)
    f_foot = ImageFont.truetype(io.BytesIO(ttf), max(14 * ss, t_size // 5))
    margin = int(w * 0.07)
    y = int(h * (0.62 if portrait else 0.58))
    for line in title.split("\n"):
        draw.text((margin, y), line, font=f_title, fill=g["ink"] + (255,))
        y += int(t_size * 1.18)
    if subtitle:
        y += int(s_size * 0.6)
        for line in subtitle.split("\n"):
            draw.text((margin, y), line, font=f_sub, fill=g["soft"] + (255,))
            y += int(s_size * 1.35)

    mint_id = face["receipt"]["mint_id"]
    copy_sha = hashlib.sha256(
        (title + "\n" + subtitle).encode("utf-8")).hexdigest()
    foot = f"zentropy labs   seed {seed}   mint {mint_id[:8]}"
    draw.text((margin, h - int(h * 0.05) - f_foot.size), foot,
              font=f_foot, fill=g["soft"] + (200,))

    img = img.resize((W, H), Image.LANCZOS).convert("RGB")
    img = img.filter(ImageFilter.SMOOTH_MORE)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()

    out = {"refused": False, "refusals": [],
           "png_b64": base64.b64encode(png).decode("ascii")}
    receipt = {
        "schema": SCHEMA,
        "seed": seed,
        "format": fmt,
        "size": [W, H],
        "ground": ground,
        "accent": bool(accent),
        "orb": orb,
        "density": round(density, 3),
        "copy_sha256": copy_sha,
        "face_mint_id": mint_id,
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "note": "plate, face, and copy compose deterministically: re-run "
                "with the same inputs and the hashes hold",
    }

    # A print-ready PDF: the composed plate at 150 dpi, standard for a poster
    # heading to a printer. Same pixels as the PNG, wrapped for print.
    if want_pdf:
        import re
        pbuf = io.BytesIO()
        img.save(pbuf, "PDF", resolution=150.0)
        # PIL stamps a live /CreationDate; pin it to a fixed epoch (same byte
        # length, so the xref offsets hold) to keep the studio's promise: the
        # same inputs make the same bytes, PDF included.
        pdf = re.sub(rb"D:\d{14}", b"D:20240101000000", pbuf.getvalue())
        out["pdf_b64"] = base64.b64encode(pdf).decode("ascii")
        receipt["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()

    # A scalable SVG container: the composition embedded at the poster's
    # viewBox so it scales without re-rasterizing on the page. Honest about
    # what it is: the plate's line-work is raster, so this wraps the render
    # rather than re-deriving it as vector paths.
    if want_svg:
        data_uri = "data:image/png;base64," + out["png_b64"]
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<title>{_xesc(title)}</title>'
            f'<image href="{data_uri}" x="0" y="0" '
            f'width="{W}" height="{H}"/></svg>'
        ).encode("utf-8")
        out["svg_b64"] = base64.b64encode(svg).decode("ascii")
        receipt["svg_sha256"] = hashlib.sha256(svg).hexdigest()
        receipt["svg_note"] = ("scalable container around the raster "
                               "composition, not vector line-work")

    out["receipt"] = receipt
    return out


def _xesc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
