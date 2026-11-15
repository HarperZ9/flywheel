"""The composite loop -- generate -> render -> perceive -> reconcile, with REAL organs on both halves.

The atelier (generate-mind) produces a real artifact; it is rasterized (the atelier emits a point-recipe;
we draw it with coherence-membrane's own zero-dep PNG encoder -- no SVG engine, no PIL); the eye
(perceive-mind) perceives THAT rendered artifact into a witnessed Observation; and a CompositeJudge
scores each candidate on BOTH halves -- studio-engine's generative fitness AND the eye's perception
quality. The center then selects the best under the human's named criterion (which may weight generative
and perceptual dimensions together) and emits the spine Certificate. This is the render->critique creative
loop, both senses real and meeting in one verdict.

A World is rendered faithfully whichever substrate the generator uses:
  * point-recipe (phyllotaxis / attractor / harmonograph) -- the recipe's OWN points, reproduced via
    studio_engine's `eval_recipe` and fit to the canvas (every mode, not just spiral);
  * glsl-fragment (gyroid / quasicrystal / flowfield / metaballs / turbulence / rings / moire) -- the
    verified strand field expr, parsed back out of the shipped fragment and evaluated per pixel, colored
    over the engine-witnessed value range. The pixels ARE the math the engine verified -- not a proxy.
studio_engine is optional (lazy import); the strand backends are imported inside the rasterizer.
"""
from __future__ import annotations
import json
import math

from ..certificate import Certificate, Verdict
from ..pngencode import encode_png
from ..organs.visual import VisualArtifactOrgan
from .atelier import AtelierJudge, summarize_world, _require_studio, _seed
from .eye import EyeJudge, summarize_observation
from .criterion import CriterionSpec
from .loop import witness_candidates

COMPOSITE_DIMS = ("fitness", "structure", "perceived", "decoded", "confidence")

_FIELD_MARKER = "float field(float u, float v, float t){ return "
_RAMP = ((45, 212, 191), (122, 92, 255), (251, 191, 36))   # teal -> violet -> amber (engine palette feel)


def _ramp(n: float):
    """Map a normalized field value in [0,1] onto the 3-stop ramp."""
    n = 0.0 if n < 0.0 else 1.0 if n > 1.0 else n
    if n <= 0.5:
        a, b, f = _RAMP[0], _RAMP[1], n / 0.5
    else:
        a, b, f = _RAMP[1], _RAMP[2], (n - 0.5) / 0.5
    return tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


def _field_expr_src(source: str) -> str | None:
    """Extract the strand field expression from a shipped GLSL fragment (between `return ` and `;`)."""
    i = source.find(_FIELD_MARKER)
    if i < 0:
        return None
    start = i + len(_FIELD_MARKER)
    end = source.find(";", start)
    return source[start:end] if end > start else None


def _rasterize_field(rp, size: int) -> bytes:
    """Evaluate the verified strand field expr per pixel, colored over the witnessed value range."""
    from studio_engine.strand import glsl as _glsl, expr as _ex
    e = _glsl.parse_glsl(_field_expr_src(rp.source))
    t0 = float((rp.uniforms.get("u_time") or {}).get("default", 0.0))
    vr = rp.value_range or []
    lo, hi = (float(vr[0]), float(vr[1])) if len(vr) == 2 and vr[1] > vr[0] else (-1.0, 1.0)
    span = hi - lo
    grid = bytearray(size * size * 3)
    for py in range(size):
        v = 2.0 * ((py + 0.5) / size) - 1.0
        for px in range(size):
            u = 2.0 * ((px + 0.5) / size) - 1.0
            val = _ex.eval_expr(e, {"u": u, "v": v, "t": t0})
            r, g, b = _ramp((val - lo) / span)
            j = (py * size + px) * 3
            grid[j], grid[j + 1], grid[j + 2] = r, g, b
    return encode_png(size, size, bytes(grid), 3)


def _rasterize_points(rp, size: int) -> bytes:
    """Reproduce the recipe's OWN points (any mode) and fit them to the canvas, preserving aspect."""
    from studio_engine.strand import recipe as _recipe
    grid = bytearray(b"\xf7" * (size * size * 3))   # light background

    def plot(x: int, y: int, rgb):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 3
            grid[i], grid[i + 1], grid[i + 2] = rgb

    try:
        pts = _recipe.eval_recipe(rp.recipe or {})
    except Exception:
        pts = []
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        span = max(maxx - minx, maxy - miny) or 1.0
        s = (size * 0.86) / span                     # uniform scale -> preserve the real aspect ratio
        n = len(pts)
        for x, y, idx in pts:
            px = int(size / 2.0 + (x - cx) * s)
            py = int(size / 2.0 + (y - cy) * s)
            c = int(255 * idx / max(1, n))
            plot(px, py, (20, c, 255 - c))
    return encode_png(size, size, bytes(grid), 3)


def rasterize_world(world, size: int = 128) -> bytes:
    """Draw the atelier's generated artifact to a PNG (zero-dep), faithful to its substrate.

    Fields (glsl-fragment) render the verified expr per pixel; point recipes render their own points.
    So the eye perceives the REAL artifact for every generator -- gyroid and quasicrystal included."""
    rp = world.layers[0].render_program
    if getattr(rp, "target", None) == "glsl-fragment" and _field_expr_src(rp.source or ""):
        return _rasterize_field(rp, size)
    return _rasterize_points(rp, size)


class CompositeJudge:
    """Scores each candidate on BOTH halves: generative fitness (from the World, via AtelierJudge) and
    perception quality (from the Observation of its render, via EyeJudge). The two senses meet here."""

    def __init__(self, world_store: dict, obs_store: dict):
        self._gen = AtelierJudge(world_store)
        self._eye = EyeJudge(obs_store)

    def score(self, candidate: str, subject_views, dims=COMPOSITE_DIMS) -> dict:
        merged = {**self._gen.score(candidate, subject_views, ("fitness", "structure", "passes_fitness")),
                  **self._eye.score(candidate, subject_views, ("perceived", "decoded", "confidence"))}
        return {d: merged.get(d, 0.0) for d in dims}


def composite_reconcile(brief: str, criterion: CriterionSpec, *, generator: str = "phyllotaxis",
                        seeds=(1, 2, 3), max_steps: int = 8, size: int = 128,
                        eye_organ=None, dims=COMPOSITE_DIMS):
    """Generate several artifacts, render+perceive each, judge on both halves, select under the criterion.
    Each candidate is a real generated World AND a real witnessed perception of its render."""
    se = _require_studio()
    eye_organ = eye_organ or VisualArtifactOrgan()
    world_store: dict = {}
    obs_store: dict = {}
    candidates: dict[str, str] = {}
    for s in seeds:
        world = se.simulate(seed=(_seed(brief) ^ int(s)), generator=generator, max_steps=max_steps)
        png = rasterize_world(world, size)
        observed = eye_organ.observe(png)
        obs = observed[0] if observed else None
        text = (f"[composite:{generator}#{s}] atelier generated {summarize_world(world)} "
                f"|| eye perceives {summarize_observation(obs) if obs is not None else 'nothing'}")
        world_store[text] = world
        if obs is not None:
            obs_store[text] = obs
        candidates[f"{generator}#{s}"] = text
    return witness_candidates(candidates, {"brief": brief}, criterion, CompositeJudge(world_store, obs_store), dims)


def _variant_seed(base: int, r: int, i: int) -> int:
    return (base ^ (r * 1000003) ^ (i * 97)) & 0x7FFFFFFF


def iterative_refine(brief: str, criterion: CriterionSpec, *, generator: str = "phyllotaxis",
                     rounds: int = 5, variants: int = 4, patience: int = 2, max_steps: int = 8,
                     size: int = 128, eye_organ=None, dims=COMPOSITE_DIMS) -> Certificate:
    """The true loop: generate -> render -> perceive -> (the composite score, which INCLUDES the eye's
    perception, drives the next generation) -> regenerate around the current best -> repeat. Hill-climbs
    the named criterion until no round improves it (patience). The eye's perception genuinely feeds back
    -- a variant the eye perceives poorly scores lower and is not adopted. Returns a Certificate carrying
    the refined winner + the witnessed trajectory (monotone non-decreasing by construction).
    """
    se = _require_studio()
    eye_organ = eye_organ or VisualArtifactOrgan()
    world_store: dict = {}
    obs_store: dict = {}
    candidates: dict[str, str] = {}

    def make(label: str, seed: int) -> None:
        world = se.simulate(seed=seed, generator=generator, max_steps=max_steps)
        png = rasterize_world(world, size)
        observed = eye_organ.observe(png)
        obs = observed[0] if observed else None
        text = (f"[{label}] atelier generated {summarize_world(world)} "
                f"|| eye perceives {summarize_observation(obs) if obs is not None else 'nothing'}")
        world_store[text] = world
        if obs is not None:
            obs_store[text] = obs
        candidates[label] = text

    def weighted(label: str) -> float:
        judge = CompositeJudge(world_store, obs_store)
        return criterion.score(judge.score(candidates[label], {"brief": brief}, dims))

    base = _seed(brief)
    make("r0", base)
    cur_label, cur_seed, cur_w = "r0", base, weighted("r0")
    trajectory = [round(cur_w, 6)]
    improvements = stale = rounds_run = 0
    for r in range(1, rounds + 1):
        rounds_run = r
        improved = False
        for i in range(variants):
            label = f"r{r}.{i}"
            seed = _variant_seed(cur_seed, r, i)         # explore AROUND the current best
            make(label, seed)
            w = weighted(label)
            if w > cur_w + 1e-9:                          # adopt only improvements -> monotone climb
                cur_label, cur_seed, cur_w, improved = label, seed, w, True
        trajectory.append(round(cur_w, 6))
        if improved:
            improvements += 1
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break

    final = CompositeJudge(world_store, obs_store).score(candidates[cur_label], {"brief": brief}, dims)
    evidence = (
        ("criterion", criterion.name),
        ("criterion_dims", json.dumps(criterion.normalized().dims)),
        ("winner", cur_label),
        ("winner_weighted", str(round(cur_w, 6))),
        ("rounds_run", str(rounds_run)),
        ("improvements", str(improvements)),
        ("trajectory", json.dumps(trajectory)),
        ("final_scores", json.dumps(final)),
    )
    return Certificate(f"refined best under '{criterion.name}' over {rounds_run} rounds (+{improvements} improvements)",
                       Verdict.VERIFIED, "neutral-center-refine-v1", evidence)


def trajectory_of(cert: Certificate) -> list:
    return json.loads(dict(cert.evidence).get("trajectory", "[]"))
