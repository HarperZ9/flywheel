"""AtelierMind -- the atelier (studio-engine) wired as the center's GENERATE mind.

The atelier is the generative half of the reconcile (the eye is the perceptive half). Here it plugs
into the center behind the `Mind` interface: instead of *reasoning* a text proposal, it GENERATES a
real artifact (a studio-engine World/Scene -- phyllotaxis, gyroid, quasicrystal, …) from a seed derived
from the subject view, and contributes a faithful text representation of that generated artifact as its
proposal. On reconcile, it regenerates informed by the other minds' deposits (perturbed seed / chosen
generator). Its sense IS generation.

Optional dependency: `studio_engine`. The center core does not require it; importing this module without
studio_engine raises a clear error only when an AtelierMind is actually used.
"""
from __future__ import annotations
import json
import zlib


def _require_studio():
    try:
        import studio_engine as se  # noqa: F401
        return se
    except ImportError as e:  # pragma: no cover - environment-dependent
        raise ImportError(
            "AtelierMind needs the `studio_engine` package on the path "
            "(the atelier / studio-engine repo). Install or add it to PYTHONPATH."
        ) from e


def _seed(text: str) -> int:
    return zlib.adler32(text.strip().encode("utf-8")) & 0x7FFFFFFF


def summarize_world(world) -> str:
    """A faithful, deterministic text representation of a generated World: its title, each layer's
    generator + recipe (the generative parameters that ARE the artifact), and its palette."""
    parts = [f"title={world.title!r}"]
    for layer in world.layers:
        rp = getattr(layer, "render_program", None)
        if rp is not None:
            recipe = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rp.recipe.items()}
            parts.append(f"layer[{layer.role or layer.organ_id}] generator={rp.generator} "
                         f"recipe={json.dumps(recipe, sort_keys=True)}")
    if getattr(world, "palette", None):
        parts.append(f"palette={list(world.palette)[:6]}")
    return "; ".join(parts)


class AtelierMind:
    """A center Mind whose proposals are real studio-engine generations.

    `store` (a dict proposal_text -> World) lets the matching AtelierJudge retrieve the ACTUAL
    generated artifact and score it on studio-engine's own criteria (rather than scoring text)."""

    def __init__(self, name: str = "atelier", generator: str = "phyllotaxis", max_steps: int = 8,
                 store: dict | None = None):
        self.name = name
        self.channel = "generate"
        self.generator = generator
        self.max_steps = max_steps
        self.store = store if store is not None else {}

    def _propose(self, prefix: str, seed: int) -> str:
        se = _require_studio()
        world = se.simulate(seed=seed, generator=self.generator, max_steps=self.max_steps)
        text = f"{prefix} {summarize_world(world)}"
        self.store[text] = world      # register the real artifact for the judge to retrieve
        return text

    def perceive_and_propose(self, view: str) -> str:
        return self._propose("[generate] atelier proposes a generated artifact:", _seed(view))

    def reconcile(self, own_view: str, others_deposits: list[str]) -> str:
        seed = _seed(own_view + " || " + " | ".join(others_deposits))   # the meeting changes the seed
        return self._propose("[generate|reconciled] atelier regenerates, informed by the other minds:", seed)


# Generative dimensions the AtelierJudge can report -- read from studio-engine's OWN witness of the
# artifact (the multi-axis+novelty final_score and the structural-fitness certificate it ships with).
GEN_DIMS = ("fitness", "structure", "passes_fitness")


class AtelierJudge:
    """The matching EXTERNAL judge for generated artifacts: scores each candidate on studio-engine's
    OWN evaluation of the real artifact (not on its text). Retrieves the World from the shared store;
    a candidate that is not a generated artifact (not in the store) scores 0 on every generative
    dimension -- a text proposal has no generative fitness, and the judge says so rather than guessing."""

    def __init__(self, store: dict):
        self.store = store

    def score(self, candidate: str, subject_views, dims=GEN_DIMS) -> dict:
        world = self.store.get(candidate)
        if world is None:
            return {d: 0.0 for d in dims}
        final_score = float(getattr(getattr(world, "receipt", None), "final_score", 0.0) or 0.0)
        cert = getattr(world, "certificate", None) or {}
        evidence = dict(cert.get("evidence", []) or [])
        try:
            deviation = float(evidence.get("deviation", 1.0))
        except (TypeError, ValueError):
            deviation = 1.0
        full = {
            "fitness": max(0.0, min(1.0, final_score)),                 # studio-engine's overall score
            "structure": max(0.0, min(1.0, 1.0 - deviation)),           # 1 - structural-fitness deviation
            "passes_fitness": 1.0 if cert.get("verdict") == "verified" else 0.0,
        }
        return {d: full.get(d, 0.0) for d in dims}
