"""audit_checkers.py -- fault-injection audit of both certificate checker
families, emitted as a TPR/FPR/Youden-J receipt.

Roadmap item: "Fault-injection audit of both checker families with a
TPR/FPR/Youden-J receipt" (docs/superpowers/specs/2026-07-27-frontier-
optimization-roadmap.md). Generates known-bad certificates (named fault
classes, see audit_mutations.py) plus known-good ones, runs BOTH
independently written checkers per family over the labeled set, and emits a
receipt carrying TPR, FPR, and Youden's J per family and per checker.

CRITICAL INVARIANT: this module only CALLS the checkers in
harness/certificates/. It never edits them. `git status` after a run must
show no change under harness/certificates/, or the frozen preregistration for
that family is invalid.

TPR = of the known-BAD certificates, the fraction the checker REFUSES (any
verdict other than PASS -- FAIL or UNVERIFIABLE both count as a refusal, since
neither lets a bad certificate stand as accepted).
FPR = of the known-GOOD certificates, the fraction the checker refuses anyway.
Youden's J = TPR - FPR = TPR + (1 - FPR) - 1.
Every rate is reported beside its denominator (n_bad, n_good); a rate without
one is not a result.

Usage: python scripts/audit_checkers.py [--n-good 30] [--seed 20260727]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_mutations import (                                     # noqa: E402
    CROSSING_FAULTS, ZARANKIEWICZ_FAULTS, cr_known_good_certs,
    zk_known_good_certs,
)
from harness.certificates.crossing import CrossingOracle           # noqa: E402
from harness.certificates.crossing_independent import (            # noqa: E402
    IndependentCrossingOracle,
)
from harness.certificates.independent import (                     # noqa: E402
    IndependentZarankiewiczOracle,
)
from harness.certificates.zarankiewicz import ZarankiewiczOracle   # noqa: E402

SCHEMA = "flywheel.fault-injection-audit/v1"
DEFAULT_SEED = 20260727
DEFAULT_N_GOOD = 30

DOES_NOT_PROVE = [
    "J measured on injected faults does not bound the false-positive rate on "
    "the natural candidate distribution: a policy that has learned to game "
    "the checker produces a different error profile than a hand-written "
    "mutation, and this battery says nothing about that profile.",
    "the fault classes are the ones we thought to write, so a fault class "
    "nobody imagined here is not measured; absence of a slip on this "
    "battery is not proof of resistance to an unenumerated attack.",
    "several fault classes exercise structural validation code SHARED "
    "between the primary and held-out checker (both call the same "
    "_well_formed / well_formed / general_position helpers), so agreement "
    "there is not independent confirmation; only 'added_k22' (zarankiewicz) "
    "and 'undercounted_crossing_total' (crossing) exercise the genuinely "
    "separate predicate algorithms the two checkers were written twice for.",
    "an exact symbolic oracle should score J=1 on an exact predicate; a "
    "perfect score here validates this audit instrument, not that the "
    "oracle resists attacks harder than the ones it was asked to withstand.",
]


def _verdicts(checker, certs: list) -> list:
    return [checker.verify(json.dumps(c), None).verdict() for c in certs]


def _rates(good_verdicts: list, bad_verdicts: list) -> dict:
    """TPR/FPR/J plus the confusion counts, each beside its denominator.

    'Refused' means any verdict other than PASS: FAIL and UNVERIFIABLE both
    count, since neither lets a bad or unverifiable certificate stand as
    accepted.
    """
    n_good, n_bad = len(good_verdicts), len(bad_verdicts)
    fp = sum(1 for v in good_verdicts if v != "PASS")
    tp = sum(1 for v in bad_verdicts if v != "PASS")
    tn, fn = n_good - fp, n_bad - tp
    tpr = tp / n_bad if n_bad else 0.0
    fpr = fp / n_good if n_good else 0.0
    return {"n_good": n_good, "n_bad": n_bad, "tp": tp, "fn": fn,
            "fp": fp, "tn": tn, "tpr": tpr, "fpr": fpr, "youden_j": tpr - fpr}


def _checker_result(checker, good: list, bad_by_class: dict) -> dict:
    good_v = _verdicts(checker, good)
    bad_v: list = []
    by_class: dict = {}
    for fault_name, bad_certs in bad_by_class.items():
        v = _verdicts(checker, bad_certs)
        bad_v.extend(v)
        caught = sum(1 for x in v if x != "PASS")
        by_class[fault_name] = {"n": len(v), "caught": caught,
                                 "slipped_through": len(v) - caught}
    rates = _rates(good_v, bad_v)
    rates["oracle_type"] = checker.oracle_type
    rates["by_fault_class"] = by_class
    return rates


def _family_report(family: str, good: list, faults: list,
                    primary, held_out) -> tuple:
    bad_by_class = {name: [mut(c) for c in good] for name, mut in faults}
    n_bad = sum(len(v) for v in bad_by_class.values())
    checkers = {
        "primary": _checker_result(primary, good, bad_by_class),
        "held_out": _checker_result(held_out, good, bad_by_class),
    }
    slipped_through = []
    for checker_name, result in checkers.items():
        for fault_name, stats in result["by_fault_class"].items():
            if stats["slipped_through"]:
                slipped_through.append({
                    "family": family, "checker": checker_name,
                    "fault_class": fault_name,
                    "count": stats["slipped_through"]})
    fam = {"fault_classes": [name for name, _ in faults],
           "n_good": len(good), "n_bad": n_bad, "checkers": checkers}
    return fam, slipped_through


def run_audit(n_good: int = DEFAULT_N_GOOD, seed: int = DEFAULT_SEED) -> dict:
    """The whole audit, a pure function of (n_good, seed): no wall clock, no
    unseeded randomness, so two calls with the same arguments agree exactly."""
    zk_good = zk_known_good_certs(n_good, seed)
    cr_good = cr_known_good_certs(n_good, seed)

    zk_fam, zk_slips = _family_report(
        "zarankiewicz", zk_good, ZARANKIEWICZ_FAULTS,
        ZarankiewiczOracle(), IndependentZarankiewiczOracle())
    cr_fam, cr_slips = _family_report(
        "rectilinear_crossing", cr_good, CROSSING_FAULTS,
        CrossingOracle(), IndependentCrossingOracle())

    return {
        "schema": SCHEMA,
        "seed": seed,
        "n_good_per_family": n_good,
        "families": {"zarankiewicz": zk_fam, "rectilinear_crossing": cr_fam},
        "slipped_through": zk_slips + cr_slips,
        "does_not_prove": DOES_NOT_PROVE,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-good", type=int, default=DEFAULT_N_GOOD)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default="artifacts/audit")
    a = ap.parse_args(argv)

    receipt = run_audit(n_good=a.n_good, seed=a.seed)
    receipt = dict(receipt)
    receipt["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out / f"fault_injection_audit_{stamp}.json"
    path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")

    for fam_name, fam in receipt["families"].items():
        for checker_name, c in fam["checkers"].items():
            print(f"{fam_name}/{checker_name}: "
                  f"TPR={c['tpr']:.3f} (n_bad={c['n_bad']}) "
                  f"FPR={c['fpr']:.3f} (n_good={c['n_good']}) "
                  f"J={c['youden_j']:.3f}")
    if receipt["slipped_through"]:
        print("SLIPPED THROUGH -- a fault that was NOT refused:")
        for s in receipt["slipped_through"]:
            print(f"  {s['family']}/{s['checker']}/{s['fault_class']}: "
                  f"{s['count']}")
    else:
        print("no injected fault slipped through either checker")
    print(f"artifact: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
