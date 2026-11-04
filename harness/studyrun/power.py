"""Power gate (upgrade 2026-11-02, F675 `gatefromsmoke`): a verdict binds only if the lock records its
simulated power at or above a stated bar. Every other verdict is reported, and marked non-binding.

F675 locked two first-difference gates that its own smoke run showed were weak; both failed by 0.016
and 0.017, and the kill rule fired on an underpowered arm. Here the stage computes power itself, by
applying the locked verdict rules to simulated results, so the number cannot be typed in by hand.

Spec field, frozen by the lock (ext_sha256):
  "power": {
    "bar": 0.8,                         simulated pass rate a binding verdict needs
    "use": "point",                     or "wilson_lower": the Wilson 95% lower bound must clear the bar
    "simulations": "power_sims.json",   result-shaped runs, grouped by world
    "verdicts": {"A_rev_hp": "rev_m", "A_null_hp": "null"}
  }
power_sims.json: {"rev_m": [{"analysis": {...}, "controls": {...}}, ...], "null": [...]}. Each world holds
runs of the real analysis code on planted data where that verdict should PASS (for a null gate, the
null world). A verdict missing from "verdicts" is non-binding. A run where the verdict is UNTESTABLE
counts as not passing. If a verdict path resolves in no run of its world, the lock is refused: that is
the F674 dotted-key failure, caught before the data.
"""
import json
import math
from pathlib import Path

from .hashing import sha256_file
from .verdict import judge, unresolved

USES = ("point", "wilson_lower")


def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def problems(cfg, verdict_names):
    out = []
    if not isinstance(cfg, dict):
        return ["power: must be an object"]
    if not isinstance(cfg.get("bar"), (int, float)) or not 0 < cfg["bar"] <= 1:
        out.append("power.bar: a number in (0, 1]")
    if cfg.get("use", "point") not in USES:
        out.append(f"power.use: one of {USES}")
    if not cfg.get("simulations"):
        out.append("power.simulations: path to the simulated runs")
    for name in (cfg.get("verdicts") or {}):
        if name not in verdict_names:
            out.append(f"power.verdicts.{name}: no such verdict")
    return out


def assess(spec, sims_path):
    """At lock time: simulated power per verdict and the binding decision. Returns (record, problems)."""
    cfg = spec["power"]
    sims = json.loads(Path(sims_path).read_text(encoding="utf-8"))
    bar, use = cfg["bar"], cfg.get("use", "point")
    rows, bad = {}, []
    for name in spec["verdicts"]:
        world = (cfg.get("verdicts") or {}).get(name)
        if world is None:
            rows[name] = {"binding": False, "why_nonbinding": "no simulated power recorded at the lock"}
            continue
        runs = sims.get(world)
        if not isinstance(runs, list) or not runs:
            bad.append(f"power: world '{world}' for {name} has no simulated runs in {Path(sims_path).name}")
            continue
        rules = {name: spec["verdicts"][name]}
        miss, why_of = {}, {}
        for r in runs:
            for path in {p for _, p, _w in unresolved(r, rules)}:
                miss[path] = miss.get(path, 0) + 1
            for _, path, why in unresolved(r, rules):
                why_of.setdefault(path, why)
        for p, k in miss.items():
            if k == len(runs):
                bad.append(f"power: {name} reads {p}, which resolves in no simulated run ({why_of[p]})")
        passes = sum(1 for r in runs if judge(r, rules)[name]["verdict"] == "PASS")
        lo, hi = wilson(passes, len(runs))
        est = passes / len(runs) if use == "point" else lo
        row = {"world": world, "n": len(runs), "passes": passes, "power": passes / len(runs),
               "wilson95": [lo, hi], "bar": bar, "use": use, "binding": est >= bar}
        if not row["binding"]:
            row["why_nonbinding"] = f"simulated power {est:.3f} ({use}) under the bar {bar}"
        rows[name] = row
    rec = {"bar": bar, "use": use, "simulations": str(sims_path), "simulations_sha256": sha256_file(sims_path),
           "verdicts": rows}
    return rec, bad


def binding_map(lock_power):
    """{name: {"binding": bool, "power": x, "why_nonbinding": ...}} for verdict.judge, from the lock."""
    out = {}
    for name, row in (lock_power or {}).get("verdicts", {}).items():
        b = {"binding": bool(row.get("binding"))}
        if "power" in row:
            b["power"] = row["power"]
        if row.get("why_nonbinding"):
            b["why_nonbinding"] = row["why_nonbinding"]
        out[name] = b
    return out
