"""Toy units for the studyrun tests: a two-group mean difference with a label-shuffle control.

Data file: {"a": [numbers], "b": [numbers]}. Pure Python; uses the stage's random.Random.
"""
import json
from pathlib import Path


def _data(ctx):
    return json.loads(Path(ctx["inputs"][0]).read_text(encoding="utf-8"))


def mean_diff(ctx):
    d = _data(ctx)
    ctx["state"]["d"] = d
    return {"diff": sum(d["a"]) / len(d["a"]) - sum(d["b"]) / len(d["b"]), "n": len(d["a"]) + len(d["b"])}


def label_shuffle(ctx, analysis):
    d, rng = ctx["state"]["d"], ctx["rng"]
    pool, na = d["a"] + d["b"], len(d["a"])
    out = []
    for _ in range(int(ctx["params"].get("n", 500))):
        rng.shuffle(pool)
        out.append(sum(pool[:na]) / na - sum(pool[na:]) / (len(pool) - na))
    return out


def constant_null(ctx, analysis):
    """A control that cannot fail: every null value the same."""
    return [0.0] * int(ctx["params"].get("n", 500))


def tiny_null(ctx, analysis):
    """A control with too few draws to decide anything, like R5's C3."""
    return [0.0, 0.1]


def tamper_prereg(ctx):
    """Edits the PREREG mid-run, the case the second hash check exists for."""
    p = Path(ctx["params"]["prereg"])
    p.write_text(p.read_text(encoding="utf-8") + "\nedited after the run started\n", encoding="utf-8")
    return mean_diff(ctx)
