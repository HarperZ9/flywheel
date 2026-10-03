"""rederive_gate.py -- accept a claimed improvement only if it survives the gate's own reruns.

`flywheel rederive <run.json>` checks a claim "configuration X improves metric M
over the baseline". It accepts only when all of these hold:

1. A frozen verifier the claimant does not control computed M (the caller runs
   it; this module reads the per-seed results).
2. The seeds are the gate's, never the claimant's. A claim that names its own
   seed list is refused before anything is read.
3. The mean paired gain over the baseline on the gate's seeds exceeds the luck
   margin 2 x sd / sqrt(n), the standard error of the mean, with sd measured on
   the baseline's per-seed results.
4. A replay of the claimant's stated seed returns MATCH (certificates/replay.py).
   No claimant record means UNVERIFIABLE and a reject.

Status: preview. The margin assumes roughly normal seed spread, which a handful
of seeds supports only weakly, and the gate's measured error rates come from one
encoder on one task.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass

from .certificates.replay import MATCH, RunRecord, replay_verdict

STATUS = "preview"
DEFAULT_N_SEEDS = 8
MARGIN_BASIS = "2 x sample sd of baseline per-seed results / sqrt(n seeds)"
DOES_NOT_PROVE = (
    "An accepted gain holds on the verifier's data and the gate's seeds; it says "
    "nothing about other data, other seeds or other hardware.",
    "The margin assumes roughly normal seed spread; with few seeds that is a weak assumption.",
)


class RefusedClaim(ValueError):
    """The claim tried to set something only the gate may set."""


@dataclass(frozen=True)
class Gate:
    seeds: tuple

    def __post_init__(self):
        if len(self.seeds) < 2 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("the gate needs at least two distinct seeds")


def luck_margin(baseline: list, k: float = 2.0, per_seed: bool = False) -> float:
    """k x sd / sqrt(n); with per_seed=True, k x sd (the stricter older margin)."""
    sd = statistics.stdev(baseline)
    return k * sd if per_seed else k * sd / math.sqrt(len(baseline))


def _paired(gate: Gate, baseline: dict, treated: dict) -> tuple:
    keys = [str(s) for s in gate.seeds]
    for name, d in (("baseline", baseline), ("treated", treated)):
        if sorted(map(str, d)) != sorted(keys):
            raise RefusedClaim(f"{name} results must cover exactly the gate's seeds")
    base = [float(baseline[k]) for k in keys]
    gains = [float(treated[k]) - b for k, b in zip(keys, base)]
    return base, gains


def _replay(replay: dict | None) -> str:
    if not replay or not replay.get("claimed") or not replay.get("replayed"):
        return "UNVERIFIABLE"
    rec = [RunRecord(**{**r, "checkpoints": tuple(r["checkpoints"])})
           for r in (replay["claimed"], replay["replayed"])]
    return replay_verdict(*rec)["verdict"]


def decide(gate: Gate, claim: dict, baseline: dict, treated: dict,
           replay: dict | None, *, per_seed_margin: bool = False) -> dict:
    if "seeds" in claim or "seed_list" in claim:
        raise RefusedClaim("seeds are fixed by the gate; a claimant seed list is refused")
    replay_v = _replay(replay)
    base, gains = _paired(gate, baseline, treated)
    margin = luck_margin(base, per_seed=per_seed_margin)
    mean_gain = statistics.fmean(gains)
    accept = replay_v == MATCH and mean_gain > margin
    reason = ("replay of the claimant's seed is not MATCH" if replay_v != MATCH else
              "mean gain clears the luck margin" if accept else
              "mean gain does not clear the luck margin")
    return {"schema": "flywheel.rederive-verdict/v1", "status": STATUS,
            "verdict": "ACCEPT" if accept else "REJECT", "reason": reason,
            "claim": claim.get("id", ""), "seeds": list(gate.seeds),
            "mean_gain": round(mean_gain, 6), "margin": round(margin, 6),
            "margin_basis": MARGIN_BASIS if not per_seed_margin else "2 x sample sd",
            "replay": replay_v, "does_not_prove": list(DOES_NOT_PROVE)}


def rerun_once(baseline: dict, one_new_value: float) -> bool:
    """The weaker check the gate replaces: one new seed, compared with the baseline mean."""
    return float(one_new_value) >= statistics.fmean(map(float, baseline.values()))


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel rederive",
                                 description="Re-check a claimed improvement on the gate's seeds "
                                             f"({STATUS}).")
    ap.add_argument("run", help="JSON with gate.seeds, claim, baseline, treated, replay")
    args = ap.parse_args(argv)
    with open(args.run, encoding="utf-8") as fh:
        doc = json.load(fh)
    try:
        out = decide(Gate(tuple(doc["gate"]["seeds"])), doc["claim"], doc["baseline"],
                     doc["treated"], doc.get("replay"))
    except (RefusedClaim, KeyError, ValueError) as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc), "status": STATUS}))
        return 2
    print(json.dumps(out, indent=1))
    return 0 if out["verdict"] == "ACCEPT" else 1


if __name__ == "__main__":
    sys.exit(main())
