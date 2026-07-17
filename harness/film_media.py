"""film_media.py: the film and print treatments, deterministically.

Flywheel's implementation of the film_media domain the telos creative
engine declares (shot/frame transforms, poster systems, film texture):
seeded grain, vignette, anamorphic letterbox, and a title card typeset
in the seed's own minted face. Every treatment is a pure function of
its inputs, so a still re-derives like everything else here.
"""
from __future__ import annotations

import io
import random


def film_frame(img, seed: int = 58, grain: float = 0.5,
               vignette: float = 0.5, letterbox: bool = True,
               title: str = "", subtitle: str = ""):
    """Apply the film treatment to a PIL image; returns (image, receipt)."""
    from PIL import Image, ImageDraw, ImageFont
    img = img.convert("RGB")
    w, h = img.size
    rng = random.Random(int(seed))
    grain = max(0.0, min(1.0, float(grain)))
    vignette = max(0.0, min(1.0, float(vignette)))

    if grain > 0:
        # seeded monochrome grain, applied as sparse luminance jitter
        px = img.load()
        n = int(w * h * 0.12 * grain)
        for _ in range(n):
            x, y = rng.randrange(w), rng.randrange(h)
            r, g, b = px[x, y]
            d = rng.randint(-26, 26)
            px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)),
                        max(0, min(255, b + d)))

    if vignette > 0:
        # radial falloff via a small mask, resized smooth
        m = Image.new("L", (64, 40), 0)
        mp = m.load()
        for y in range(40):
            for x in range(64):
                dx, dy = (x - 31.5) / 31.5, (y - 19.5) / 19.5
                fall = max(0.0, (dx * dx + dy * dy) ** 0.5 - 0.55)
                mp[x, y] = int(min(1.0, fall * 1.3) * 165 * vignette)
        mask = m.resize((w, h))
        img = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), img, mask)

    bar = 0
    if letterbox:
        # 2.39:1 anamorphic bars inside the existing frame
        target = int(w / 2.39)
        if target < h:
            bar = (h - target) // 2
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, w, bar), fill=(4, 5, 5))
            d.rectangle((0, h - bar, w, h), fill=(4, 5, 5))

    title = (title or "").strip().lower()
    subtitle = (subtitle or "").strip().lower()
    if title:
        from .typeface_forge import DEFAULTS, mint
        from .typeface_ttf import to_ttf
        face = mint({**DEFAULTS, "width": 0.85}, seed=int(seed))
        if not face["refused"]:
            supported = set(face["receipt"]["charset"]) | {" "}
            if not (set(title + subtitle) - supported):
                ttf = to_ttf(face, family=f"Film {seed}")
                d = ImageDraw.Draw(img)
                t_size = max(18, w // 16)
                ft = ImageFont.truetype(io.BytesIO(ttf), t_size)
                ty = h - bar - int(t_size * (2.6 if subtitle else 1.9))
                d.text((int(w * 0.06), ty), title, font=ft,
                       fill=(238, 241, 238))
                if subtitle:
                    fs = ImageFont.truetype(io.BytesIO(ttf), max(12, t_size // 3))
                    d.text((int(w * 0.06), ty + int(t_size * 1.25)),
                           subtitle, font=fs, fill=(170, 176, 178))

    receipt = {"op": "film_frame", "seed": int(seed),
               "grain": round(grain, 3), "vignette": round(vignette, 3),
               "letterbox_bar_px": bar,
               "title": title, "subtitle": subtitle}
    return img, receipt
