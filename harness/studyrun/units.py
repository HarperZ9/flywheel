"""Named units: load 'file.py:function' without writing bytecode, and summarise a control's null.

Unit contract.
  analysis(ctx) -> dict            ctx: {"params", "rng", "seed", "inputs", "state", "spec_id"}
  control(ctx, analysis) -> list | {"null": list, "meta": dict}
ctx["state"] is shared by the analysis and every control in one run (load data once). ctx["rng"] is one
generator for the whole run, used in spec order: analysis first, then controls in the listed order.
"""
import importlib.util
import math
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def load(path, func):
    path = Path(path).resolve()
    name = "studyrun_unit_" + "".join(c if c.isalnum() else "_" for c in str(path))
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    fn = getattr(mod, func, None)
    if not callable(fn):
        raise AttributeError(f"{path} has no function {func}")
    return fn


def make_rng(seed, kind="python"):
    """A generator for the run. 'numpy' gives numpy's default_rng(seed) when the analysis needs it."""
    if kind == "numpy":
        import numpy as np
        return np.random.default_rng(seed)
    return random.Random(seed)


def quantile(values, q):
    """Linear interpolation between order statistics (numpy's default, Hyndman-Fan type 7)."""
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def summarise(real, null, min_n=20):
    """Null summary in the runs2 form, with p = (count(null >= real) + 1) / (n + 1).

    A control that cannot fail is reported unusable: fewer than min_n values, or no spread.
    """
    vals = [float(x) for x in null]
    n = len(vals)
    out = {"n": n, "usable": True}
    if n:
        out.update({"mean": math.fsum(vals) / n, "q95": quantile(vals, .95), "q05": quantile(vals, .05),
                    "p_ge": (sum(1 for x in vals if x >= real) + 1) / (n + 1)})
    if n < min_n:
        out["usable"], out["why_unusable"] = False, f"{n} null values, fewer than {min_n}"
    elif max(vals) == min(vals):
        out["usable"], out["why_unusable"] = False, "null has no spread"
    return out
