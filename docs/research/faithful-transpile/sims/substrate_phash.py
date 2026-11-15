"""Substrate 2 — perceptual hashing: image identity survives ~24000x bit-loss.

Tests the transpile-conservation principle on a REAL, non-synthetic substrate (PIL images ->
64/256-bit hashes). Shares NO math with the linear toy, so agreement is independent evidence.

The substrate: a ~256x256 RGB image (~1.5M bits) -> a small perceptual signature. Three CRITERIA,
each its own invariant + its own external witness (distance to the ORIGINAL — computable only with
the external reference, never from the transformed artifact alone):
  identity   : dHash 8x8 (64 bits)        — "same scene, coarse spatial structure"
  fine_detail: dHash 16x16 (256 bits)     — "fine structure / legibility"
  color_mood : 4x4 RGB thumbnail (48 vals)— "overall color/brightness"

Transforms (substrate conversions), each lossy in bytes:
  jpeg_q20      : recompress hard           — faithful to ALL (only bytes change)
  downscale_8x  : shrink 8x then back       — faithful to identity, LOSSY to fine_detail
  block_shuffle : permute 32px blocks       — UNFAITHFUL to identity, faithful to color_mood
  different_scene: a genuinely different img — unfaithful to everything (the "actually changed" control)

CLAIMS (each can fall):
 (1) lossy-but-faithful: a faithful transform keeps its criterion's invariant though the bytes are
     almost entirely gone; an unfaithful one (same substrate) destroys it.
 (2) internal blindness: a WITHIN-artifact statistic (the transformed hash's own bit-balance) does
     NOT separate faithful from unfaithful; only distance-to-external-reference does.
 (3) criterion-relativity: one transform is faithful to one criterion and lossy to another at once.

Stdlib + PIL only, deterministic.
"""
from __future__ import annotations
import io, math
from PIL import Image, ImageDraw, ImageFilter

SZ = 256


def scene(kind: str) -> Image.Image:
    img = Image.new("RGB", (SZ, SZ), (240, 240, 235))
    d = ImageDraw.Draw(img)
    if kind == "gradient":
        for y in range(SZ):
            d.line([(0, y), (SZ, y)], fill=(y, (2 * y) % 256, 255 - y))
    elif kind == "circles":
        for i, r in enumerate(range(20, 130, 18)):
            d.ellipse([SZ // 2 - r, SZ // 2 - r, SZ // 2 + r, SZ // 2 + r],
                      outline=(i * 40 % 256, 60, 200 - i * 20), width=6)
    elif kind == "checker":
        for r in range(0, SZ, 32):
            for c in range(0, SZ, 32):
                if (r // 32 + c // 32) % 2 == 0:
                    d.rectangle([c, r, c + 31, r + 31], fill=(30, 120, 180))
    elif kind == "text":
        for i, y in enumerate(range(20, 230, 26)):
            d.rectangle([20, y, 236, y + 14], fill=(20, 20, 20) if i % 2 else (90, 90, 90))
            for x in range(24, 232, 12):
                d.rectangle([x, y + 2, x + 6, y + 11], fill=(240, 240, 235))
    elif kind == "blobs":
        pts = [(40, 50), (180, 70), (90, 160), (200, 200), (130, 110)]
        for i, (x, y) in enumerate(pts):
            d.ellipse([x - 30, y - 30, x + 30, y + 30], fill=(200 - i * 30, i * 45 % 256, 120))
    return img


def _gray_resize(img, w, h):
    return list(img.convert("L").resize((w, h), Image.BILINEAR).getdata())


def dhash(img, size=8):
    px = _gray_resize(img, size + 1, size)
    bits = []
    for r in range(size):
        row = px[r * (size + 1):(r + 1) * (size + 1)]
        for c in range(size):
            bits.append(1 if row[c] > row[c + 1] else 0)
    return bits


def color_sig(img):
    """Order-INVARIANT global color histogram (4x4x4 = 64 RGB bins), normalized. This is the
    'color mood' invariant: it ignores WHERE pixels are, so a spatial scramble preserves it."""
    bins = [0] * 64
    for (r, g, b) in img.convert("RGB").getdata():
        bins[(r // 64) * 16 + (g // 64) * 4 + (b // 64)] += 1
    total = sum(bins) or 1
    return [x / total for x in bins]


def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y) / max(len(a), 1)


def color_dist(a, b):
    return 0.5 * sum(abs(p - q) for p, q in zip(a, b))   # total-variation distance, 0..1


# --- transforms -------------------------------------------------------------
def t_jpeg(img):
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=20); buf.seek(0)
    return Image.open(buf).convert("RGB")


def t_downscale(img):
    return img.resize((SZ // 8, SZ // 8), Image.BILINEAR).resize((SZ, SZ), Image.NEAREST)


def t_block_shuffle(img):
    """Scatter 16px blocks by a seeded permutation: destroys spatial identity, preserves the
    exact pixel multiset -> the global color histogram is conserved (criterion-relativity)."""
    import random as _r
    b = 16
    blocks = [(c, r) for r in range(0, SZ, b) for c in range(0, SZ, b)]
    src = list(blocks)
    dst = list(blocks)
    _r.Random(12345).shuffle(dst)
    out = Image.new("RGB", (SZ, SZ))
    for (sc, sr), (dc, dr) in zip(src, dst):
        out.paste(img.crop((sc, sr, sc + b, sr + b)), (dc, dr))
    return out


def t_different(_img):
    return scene("blobs")  # a genuinely different scene


def bit_balance(bits):
    """A WITHIN-artifact statistic: fraction of 1-bits in the transformed hash (no reference)."""
    return sum(bits) / len(bits)


def main():
    scenes = ["gradient", "circles", "checker", "text"]
    transforms = {"jpeg_q20": t_jpeg, "downscale_8x": t_downscale,
                  "block_shuffle": t_block_shuffle, "different_scene": t_different}
    bytes_per_img = SZ * SZ * 3 * 8
    print(f"image ~{bytes_per_img} bits -> identity dHash 64 bits  (~{bytes_per_img//64}x lossy)\n")
    print("transform         identity(0..1)  fine_detail   color_mood   [lower = invariant survived]")
    agg = {t: {"identity": [], "fine": [], "color": [], "balance": []} for t in transforms}
    for s in scenes:
        base = scene(s)
        b_id, b_fine, b_col = dhash(base, 8), dhash(base, 16), color_sig(base)
        for tname, tf in transforms.items():
            out = tf(base)
            agg[tname]["identity"].append(hamming(b_id, dhash(out, 8)))
            agg[tname]["fine"].append(hamming(b_fine, dhash(out, 16)))
            agg[tname]["color"].append(color_dist(b_col, color_sig(out)))
            agg[tname]["balance"].append(bit_balance(dhash(out, 8)))

    def mean(xs): return sum(xs) / len(xs)
    res = {}
    for t in transforms:
        res[t] = {k: mean(v) for k, v in agg[t].items()}
        r = res[t]
        print(f"  {t:15s}  {r['identity']:.3f}          {r['fine']:.3f}        {r['color']:.3f}")

    print("\n--- verdict on the falsifiers (substrate 2: perceptual hash) ---")
    # (1) lossy-but-faithful: jpeg keeps identity though bytes are gutted; different_scene destroys it.
    p1 = res["jpeg_q20"]["identity"] < 0.20 and res["different_scene"]["identity"] > 0.35
    print(f"(1) lossy-but-faithful: jpeg_q20 identity drift {res['jpeg_q20']['identity']:.3f} (survives) "
          f"vs different_scene {res['different_scene']['identity']:.3f} (destroyed)  -> {'HOLDS' if p1 else 'FALLS'}")
    # (2) internal blindness: the transformed hash's own bit-balance can't separate faithful/unfaithful.
    bal_faith = res["jpeg_q20"]["balance"]; bal_unfaith = res["different_scene"]["balance"]
    id_faith = res["jpeg_q20"]["identity"]; id_unfaith = res["different_scene"]["identity"]
    p2 = abs(bal_faith - bal_unfaith) < 0.15 and (id_unfaith - id_faith) > 0.2
    print(f"(2) internal blindness: within-hash bit-balance faithful {bal_faith:.2f} vs unfaithful "
          f"{bal_unfaith:.2f} (~same) while external identity-drift differs by "
          f"{id_unfaith-id_faith:.2f}  -> {'HOLDS' if p2 else 'FALLS'}")
    # (3) criterion-relativity: block_shuffle UNFAITHFUL to identity but FAITHFUL to color_mood;
    #     downscale faithful to identity but LOSSY to fine_detail.
    bs = res["block_shuffle"]; ds = res["downscale_8x"]
    p3a = bs["identity"] > 0.3 and bs["color"] < 0.15
    p3b = ds["identity"] < 0.25 and ds["fine"] > ds["identity"] + 0.05
    print(f"(3) criterion-relativity: block_shuffle identity-drift {bs['identity']:.3f} (unfaithful) "
          f"but color-drift {bs['color']:.3f} (faithful)  -> {'HOLDS' if p3a else 'FALLS'}")
    print(f"    downscale_8x identity {ds['identity']:.3f} (faithful) but fine_detail {ds['fine']:.3f} "
          f"(lossy)  -> {'HOLDS' if p3b else 'FALLS'}")
    allp = p1 and p2 and p3a and p3b
    print("\nSTICKS" if allp else "\nPARTIAL/FALLS", "— substrate 2 (perceptual hash, real images).")


if __name__ == "__main__":
    main()
