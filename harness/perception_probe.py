"""perception_probe.py — does the transpiler grant a model USABLE perception?

The flywheel seam the workspace paper opens: a text model has no native
perception of a spatial scene, but the transpiler encodes one into a carrier it
can read. Perception is REAL only if the encoding CONSERVES the task criterion
(here: locate/disambiguate objects) — not if it merely dumps bytes.

This module is the model-independent precondition: it proves the criterion-
conserving encoding (recursive grid labels, depth 2, ~14.3 bits) keeps every
object distinct and decodable within tolerance, while a naive coarse encoding
(depth 1, ~7.2 bits) COLLAPSES nearby objects to one label — the criterion is
lost, so no reader (model or human) could disambiguate them. The behavioral
model measurement (does the served model answer locate-queries better under the
conserving encoding?) layers on top via `scene_query` + a ServeProposer.

Composes with transpile.py (grid_label/grid_center/criterion_conserved) and feeds
the flywheel: a perception layer whose fidelity is itself witnessed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .transpile import grid_label, grid_center, grid_cell_size, label_bits

_COLS, _ROWS = 16, 9


@dataclass
class Scene:
    w: int
    h: int
    objects: list[tuple[str, float, float]]   # (name, x, y)
    target: str


def make_scene(seed: int, *, w: int = 512, h: int = 288, n: int = 5) -> Scene:
    rng = random.Random(seed)
    names = ["target", "alpha", "beta", "gamma", "delta", "epsilon", "zeta"][:n]
    objs = [(nm, rng.uniform(0, w - 1), rng.uniform(0, h - 1)) for nm in names]
    return Scene(w, h, objs, "target")


def _encode(scene: Scene, depth: int) -> str:
    return "\n".join(
        f"{nm}: {grid_label(x, y, scene.w, scene.h, cols=_COLS, rows=_ROWS, depth=depth)}"
        for nm, x, y in scene.objects)


def conserving_encode(scene: Scene) -> str:
    """Depth-2 recursive grid labels — conserves the locate criterion (~14.3 b)."""
    return _encode(scene, depth=2)


def naive_encode(scene: Scene) -> str:
    """Depth-1 coarse labels (~7.2 b) — nearby objects collapse to one cell."""
    return _encode(scene, depth=1)


def _labels(encoding: str) -> dict[str, str]:
    out = {}
    for ln in encoding.splitlines():
        nm, lab = ln.split(": ", 1)
        out[nm] = lab
    return out


def labels_distinct(encoding: str) -> bool:
    labs = list(_labels(encoding).values())
    return len(set(labs)) == len(labs)


def collapsed_pairs(encoding: str) -> list[tuple[str, str]]:
    """Object pairs that share a label — the criterion is LOST for them."""
    items = list(_labels(encoding).items())
    return [(a[0], b[0]) for i, a in enumerate(items) for b in items[i + 1:]
            if a[1] == b[1]]


def decode_locate(encoding: str, name: str, w: int, h: int) -> tuple[float, float] | None:
    lab = _labels(encoding).get(name)
    if lab is None:
        return None
    return grid_center(lab, w, h, cols=_COLS, rows=_ROWS)


def locate_error(scene: Scene, encoding: str) -> float:
    """Mean L-inf decode error over all objects (pixels)."""
    errs = []
    for nm, x, y in scene.objects:
        p = decode_locate(encoding, nm, scene.w, scene.h)
        if p is None:
            errs.append(float("inf"))
        else:
            errs.append(max(abs(p[0] - x), abs(p[1] - y)))
    return sum(errs) / len(errs) if errs else float("inf")


def scene_query(scene: Scene, encoding: str) -> dict:
    """A locate task for the model: given the encoding, name the object nearest
    a probe point. The ground-truth answer is computed from true coords; a reader
    can only answer correctly if the encoding disambiguates the objects."""
    probe = (scene.objects[0][1], scene.objects[0][2])   # near the target
    truth = min(scene.objects, key=lambda o: max(abs(o[1] - probe[0]), abs(o[2] - probe[1])))[0]
    prompt = (f"A {scene.w}x{scene.h} scene has objects at grid labels (cols A-P, "
              f"rows 1-9, '.' = sub-cell):\n{encoding}\n\nWhich object is at grid "
              f"label {grid_label(probe[0], probe[1], scene.w, scene.h, cols=_COLS, rows=_ROWS, depth=2)}? "
              f"Answer with ONLY the object name.")
    return {"prompt": prompt, "answer": truth}


def reasoning_encode(scene: Scene) -> str:
    """Reasoning-friendly: the conserving label PLUS its decoded coordinates (from
    grid_center, so still transpile-derived within the conservation tolerance).
    Tests whether the opaque-label FORMAT was the bottleneck for flexible use."""
    lines = []
    for nm, x, y in scene.objects:
        lab = grid_label(x, y, scene.w, scene.h, cols=_COLS, rows=_ROWS, depth=2)
        cx, cy = grid_center(lab, scene.w, scene.h, cols=_COLS, rows=_ROWS)
        lines.append(f"{nm}: {lab} (x={int(cx)}, y={int(cy)})")
    return "\n".join(lines)


def raw_encode(scene: Scene) -> str:
    """Control: full-precision raw coordinates, no transpile. Isolates whether the
    model can do the spatial reasoning AT ALL (format-independent)."""
    return "\n".join(f"{nm}: (x={int(x)}, y={int(y)})" for nm, x, y in scene.objects)


def _quadrant(x: float, y: float, w: int, h: int) -> str:
    return ("top" if y < h / 2 else "bottom") + "-" + ("left" if x < w / 2 else "right")


def flexible_queries(scene: Scene, encoding: str) -> dict:
    """The flexible-generalization marker: FOUR distinct functions over ONE
    encoding. If the model handles the SET (not just locate), the representation
    is workspace-loaded — usable across functions, not merely copyable. Each
    answer is ground-truth from the true coords."""
    w, h, objs = scene.w, scene.h, scene.objects
    tgt = objs[0]
    others = objs[1:]
    nearest = min(others, key=lambda o: (o[1] - tgt[1]) ** 2 + (o[2] - tgt[2]) ** 2)[0]
    left = sum(1 for _, x, _ in objs if x < w / 2)
    quad = _quadrant(tgt[1], tgt[2], w, h)
    header = (f"A {w}x{h} scene (x: 0..{w}, y: 0..{h}), objects encoded as:\n"
              f"{encoding}\n\n")
    return {
        "nearest": {"prompt": header + "Which object is spatially nearest to "
                    "'target'? Answer ONLY the object name.", "answer": nearest},
        "count_left": {"prompt": header + "How many objects are in the LEFT half "
                       "(columns A-H)? Answer ONLY a number.", "answer": str(left)},
        "quadrant": {"prompt": header + "Which quadrant is 'target' in: top-left, "
                     "top-right, bottom-left, or bottom-right? Answer ONLY the "
                     "quadrant.", "answer": quad},
    }


def conservation_gap(seed: int) -> dict:
    """One scene's witness: conserving vs naive on distinctness + decode error."""
    s = make_scene(seed)
    c, n = conserving_encode(s), naive_encode(s)
    return {"seed": seed,
            "conserving": {"distinct": labels_distinct(c), "err": round(locate_error(s, c), 1),
                           "bits": round(label_bits(_COLS, _ROWS, 2), 1)},
            "naive": {"distinct": labels_distinct(n), "err": round(locate_error(s, n), 1),
                      "collapsed": collapsed_pairs(n), "bits": round(label_bits(_COLS, _ROWS, 1), 1)}}
