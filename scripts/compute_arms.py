#!/usr/bin/env python3
"""compute_arms.py -- the arms of section 4, computed offline from the cache.

Same two refusals as compute_endpoint, imported from it rather than restated:
no run_end means no arms, and a missing pair stops the run. Section 7 allows one
confirmatory pass with no interim analysis, and a tool that reads outcomes has
to be unable to run early rather than merely disinclined to.

WHAT THIS DOES NOT DECIDE. The oracle is the scorer in every arm. The only
question an arm asks is whether the oracle also got to be the SELECTOR, and
whether that earned anything. `harness/pool_arms.py` holds that distinction and
`paired()` enforces it on `scored_by`, so this driver just supplies pools and
accept functions and writes down what came back.

Every accept function here is BOUND to the instance the candidate was asked
about. That is not a detail: an unbound accept scores a certificate for a 2x2
problem as a clean PASS against a 28x39 instance, which would inflate every arm
by exactly the candidates that answered an easier question.

Stdlib only. No GPU, no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.certificates.crossing import CrossingOracle              # noqa: E402
from harness.certificates.crossing_independent import (               # noqa: E402
    IndependentCrossingOracle)
from harness.certificates.independent import (                        # noqa: E402
    IndependentZarankiewiczOracle)
from harness.certificates.zarankiewicz import ZarankiewiczOracle      # noqa: E402
from harness.pool import Pool                                         # noqa: E402
from harness.pool_arms import (                                       # noqa: E402
    SCHEMA, best_of_k, paired, pass_at_k, placebo_of_k, random_of_k, single)
from harness.verdict import Verdict                                   # noqa: E402

PRIMARY = {"zarankiewicz": ZarankiewiczOracle,
           "rectilinear_crossing": CrossingOracle}
HELD_OUT_CHECKER = {"zarankiewicz": IndependentZarankiewiczOracle,
                    "rectilinear_crossing": IndependentCrossingOracle}

# NOT pinned by the preregistration. Section 4 says "seeded coin" and fixes no
# value, so these are declared here and reported in the output rather than
# chosen silently at the point of use.
SELECTION_SEED = 20260726
PLACEBO_SEED = 20260727


_CE = None


def _load_compute_endpoint():
    """Loaded ONCE and cached. Two importlib loads of one file produce two
    module objects and therefore two distinct EndpointGate classes, so a raise
    from one is not caught by an except naming the other. That turned a clean
    refusal into a traceback and exit 1, which reads as a crash rather than as
    the protocol working."""
    global _CE
    if _CE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "compute_endpoint", REPO / "scripts" / "compute_endpoint.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CE = mod
    return _CE


def make_accept(oracle, instances: dict):
    """accept(text, task_id) -> bool, bound to the instance that was asked."""
    def accept(text: str, task_id: str) -> bool:
        return oracle.verify(text, task=instances[task_id]).verdict_ is Verdict.PASS
    return accept


def observed_accept_rate(pool, accept) -> float:
    """The oracle's accept rate over every cached candidate in this pool.

    The placebo arm is matched on this, so it has to be measured rather than
    assumed. A placebo tuned to some other number would be a straw control.
    """
    total = hits = 0
    for task_id in pool.task_ids():
        for _, text in pool.candidates(task_id):
            total += 1
            hits += 1 if accept(text, task_id) else 0
    return (hits / total) if total else 0.0


def arms_for_pool(pool, accept, held_out_accept) -> dict:
    """Every arm of section 4 over one pool, plus the comparisons.

    Both `paired` calls are kept, including the one that gets refused. The
    refusal is the evidence that the rule is enforced in code, and deleting the
    call would leave a reader to take the enforcement on trust.
    """
    rate = observed_accept_rate(pool, accept)
    arms = {
        "single": single(pool, accept),
        "best_of_k_self_scored": best_of_k(pool, accept),
        "best_of_k_held_out": best_of_k(pool, accept, score=held_out_accept),
        "random_of_k": random_of_k(pool, accept, seed=SELECTION_SEED),
        "placebo_of_k": placebo_of_k(pool, accept, seed=PLACEBO_SEED,
                                     accept_rate=rate),
        "pass_at_k": pass_at_k(pool, accept),
    }
    return {
        "arms": arms,
        "observed_accept_rate": round(rate, 6),
        "selection_seed": SELECTION_SEED, "placebo_seed": PLACEBO_SEED,
        "comparisons": {
            # The legitimate one: a selection-free control against an arm whose
            # scorer was written independently of its selector.
            "random_vs_best_held_out": paired(arms["random_of_k"],
                                              arms["best_of_k_held_out"]),
            # Kept so the refusal is visible in the record.
            "random_vs_best_self_scored": paired(arms["random_of_k"],
                                                 arms["best_of_k_self_scored"]),
        },
        "does_not_prove": [
            "NOT_PROVES_UPLIFT_FROM_A_SELF_SCORED_ARM: an arm whose selector is "
            "the function that scores it cannot lose, and the recorded refusal "
            "of that comparison is the point rather than an omission.",
            "NOT_PROVES_A_SIZE_TREND: these are per-rung numbers and no "
            "cross-rung difference is computed anywhere in this file.",
        ],
    }


def compute(pool_root: Path, journal: Path, families, rungs) -> dict:
    ce = _load_compute_endpoint()
    ce.require_run_end(journal)
    ce.require_every_pair(pool_root, families, rungs)
    fill = ce._load("run_demo_pool")
    report = {"schema": SCHEMA, "pool_root": pool_root.name, "families": {}}
    for family in families:
        primary, held = PRIMARY[family](), HELD_OUT_CHECKER[family]()
        if type(primary) is type(held):
            raise ce.EndpointGate(
                f"{family}: the held-out checker is the same implementation as "
                "the primary one, which is not independence and would "
                "manufacture the appearance of a held-out check")
        instances = {fill.task_id_for(family, inst): inst
                     for inst in fill.build_instances(family)}
        accept = make_accept(primary, instances)
        held_accept = make_accept(held, instances)
        per_rung = {}
        for rung in rungs:
            pool = Pool(pool_root / family / rung.replace(":", "_"))
            per_rung[rung] = arms_for_pool(pool, accept, held_accept)
        report["families"][family] = {
            "primary_checker": type(primary).__module__,
            "held_out_checker": type(held).__module__,
            "per_rung": per_rung,
        }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool-root", default=str(REPO / "artifacts" / "pool"))
    ap.add_argument("--journal", default=None)
    ap.add_argument("--out", default=str(REPO / "artifacts" / "endpoint"))
    args = ap.parse_args(argv)

    pool_root = Path(args.pool_root)
    journal = (Path(args.journal) if args.journal
               else pool_root / "confirmatory-journal.jsonl")
    ce = _load_compute_endpoint()
    walk = ce._load("run_confirmatory")
    try:
        report = compute(pool_root, journal, walk.FAMILIES, walk.RUNGS)
    except ce.EndpointGate as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "arms-report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    for family, block in report["families"].items():
        for rung, r in block["per_rung"].items():
            p = r["comparisons"]["random_vs_best_held_out"]
            print(f"{family} @ {rung}: accept_rate={r['observed_accept_rate']} "
                  f"discordant={p['discordant']} p={p.get('p_exact')}")
    print(f"report -> {out / 'arms-report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
