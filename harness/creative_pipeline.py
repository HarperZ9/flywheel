"""creative_pipeline.py: the studio's stations, composed as one line.

A pipeline is an ordered list of stages; the image flows stage to stage
and every stage appends its receipt to a hash chain, so the final still
carries the provenance of the WHOLE line: which plate, which kernel,
which treatment, in which order, under which seeds. Sources start the
line (plate, wireframe, harmonograph), transforms bend it (the telos
raster kernels, run by the lane's own module), treatments finish it
(film frame, and the chain closes with one pipeline id.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json

SCHEMA = "flywheel.creative-pipeline/v1"

SOURCES = ("plate", "wireframe", "harmonograph", "field")
TRANSFORMS = ("dither", "pixel_sort", "film_frame")
MAX_STAGES = 8


def _plate_rgb(args):
    from PIL import Image
    from .raster_fx import _plate_gray
    g = _plate_gray(int(args.get("seed", 58)),
                    max(64, min(1600, int(args.get("width", 640)))),
                    max(64, min(1600, int(args.get("height", 400)))),
                    args.get("ground", "dark"))
    return g.convert("RGB"), {"op": "plate", "seed": int(args.get("seed", 58)),
                              "ground": args.get("ground", "dark")}


def _field(args):
    from .field_studio import field_study
    img, receipt = field_study(
        seed=int(args.get("seed", 58)),
        width=int(args.get("width", 640)), height=int(args.get("height", 400)),
        sources=int(args.get("sources", 3)),
        levels=int(args.get("levels", 9)))
    if img is None:
        raise ValueError(receipt["error"])
    return img, receipt


def _wireframe(args):
    from .retro_cgi import render_wireframe
    img, receipt = render_wireframe(
        primitive=args.get("primitive", "cube"),
        seed=int(args.get("seed", 58)),
        width=int(args.get("width", 640)), height=int(args.get("height", 400)),
        ground=args.get("ground", "dark"))
    if img is None:
        raise ValueError(receipt["error"])
    return img, receipt


def _harmonograph(args):
    from PIL import Image, ImageDraw
    from .telos_kernels import run_kernel
    out = run_kernel("plotter.harmonograph-path", {
        "samples": int(args.get("samples", 900)),
        "x": args.get("x") or {"frequency": 3, "damping": 0.004},
        "y": args.get("y") or {"frequency": 4, "phase": 1.5707,
                               "damping": 0.0044}})
    if "error" in out:
        raise ValueError(out["error"])
    r = out["result"]
    w = max(64, min(1600, int(args.get("width", 640))))
    h = max(64, min(1600, int(args.get("height", 400))))
    ground = (11, 14, 15) if args.get("ground", "dark") == "dark" \
        else (244, 243, 239)
    ink = (238, 241, 238) if args.get("ground", "dark") == "dark" \
        else (11, 12, 14)
    img = Image.new("RGB", (w, h), ground)
    d = ImageDraw.Draw(img)
    s = min(w, h) * 0.44
    pts = [(w / 2 + p["x"] * s, h / 2 - p["y"] * s) for p in r["points"]]
    d.line(pts, fill=ink, width=1)
    return img, {"op": "harmonograph", "lane": "telos",
                 "kernel_receipt_hash": r["receipt_hash"],
                 "n_points": len(pts)}


def _raster(kernel_id):
    def stage(img, args):
        from PIL import Image
        from .raster_fx import apply_fx
        buf = io.BytesIO()
        img.convert("L").save(buf, "PNG")
        out = apply_fx(kernel_id,
                       {"kind": "png_b64",
                        "data": base64.b64encode(buf.getvalue()).decode()},
                       args or {})
        if out.get("refused"):
            raise ValueError("; ".join(out["refusals"]))
        nxt = Image.open(io.BytesIO(base64.b64decode(out["png_b64"])))
        return nxt.convert("RGB"), {
            "op": kernel_id, "lane": "telos",
            "kernel_receipt_hash": out["receipt"]["kernel_receipt_hash"]}
    return stage


def _film(img, args):
    from .film_media import film_frame
    return film_frame(img, seed=int(args.get("seed", 58)),
                      grain=float(args.get("grain", 0.5)),
                      vignette=float(args.get("vignette", 0.5)),
                      letterbox=bool(args.get("letterbox", True)),
                      title=str(args.get("title", "")),
                      subtitle=str(args.get("subtitle", "")))


_OPS = {"plate": _plate_rgb, "wireframe": _wireframe,
        "field": _field,
        "harmonograph": _harmonograph,
        "dither": _raster("raster.ordered-dither"),
        "pixel_sort": _raster("raster.pixel-sort-rows"),
        "film_frame": _film}


def run_pipeline(stages: list) -> dict:
    """Ordered stages in, one still and one chained receipt out."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return {"refused": True,
                "refusals": ["the pipeline needs Pillow on the engine side"]}
    if not isinstance(stages, list) or not stages:
        return {"refused": True, "refusals": ["give the pipeline at least "
                                              "one stage"]}
    if len(stages) > MAX_STAGES:
        return {"refused": True,
                "refusals": [f"a line longer than {MAX_STAGES} stages is a "
                             "workflow, not a pipeline"]}
    first = (stages[0] or {}).get("op", "")
    if first not in SOURCES:
        return {"refused": True,
                "refusals": [f"the first stage must be a source "
                             f"({', '.join(SOURCES)}); got {first!r}"]}
    img = None
    chain = "genesis"
    trail = []
    for i, spec in enumerate(stages):
        op = (spec or {}).get("op", "")
        args = spec.get("args") if isinstance(spec.get("args"), dict) else {}
        fn = _OPS.get(op)
        if fn is None:
            return {"refused": True,
                    "refusals": [f"stage {i}: unknown op {op!r}; ops: "
                                 + ", ".join(sorted(_OPS))]}
        if i > 0 and op in SOURCES:
            return {"refused": True,
                    "refusals": [f"stage {i}: {op} is a source and can only "
                                 "start the line"]}
        try:
            img, receipt = fn(args) if op in SOURCES else fn(img, args)
        except (ValueError, OSError) as e:
            return {"refused": True, "refusals": [f"stage {i} ({op}): {e}"]}
        stage_sha = hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        chain = hashlib.sha256(f"{chain}:{stage_sha}".encode()).hexdigest()
        trail.append({**receipt, "stage_sha256": stage_sha,
                      "chain": chain[:16]})

    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()
    return {"refused": False, "refusals": [],
            "png_b64": base64.b64encode(png).decode("ascii"),
            "receipt": {"schema": SCHEMA,
                        "n_stages": len(trail),
                        "stages": trail,
                        "png_sha256": hashlib.sha256(png).hexdigest(),
                        "pipeline_id": chain[:16],
                        "note": "each stage hash folds into the chain, so "
                                "the pipeline id witnesses the whole line "
                                "in order"}}
