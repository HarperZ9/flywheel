"""The center, made runnable — criterion-named reconciliation, witnessed.

The flagship's core interaction: a subject's candidate forms are reconciled at a neutral center
against a CRITERION the human NAMES and weights for their domain. The center does not pick the
criterion; it hosts whichever is named, and emits a witnessed record of the verdict under it. The
same center serves the novel creator, the rigorous researcher, and the auditor — each standing behind
their own criterion. This is "I stand behind all of them," made into a program.

The candidates and their per-dimension scores are taken from the live two-mind demonstration
(`DEMO-two-minds.md`): two blind external judges scored the visual-solo, symbolic-solo, and the
meeting result on a fixed set of dimensions. Scores below are those judges' findings, normalized to
[0,1] (approximate; derived from the two judge passes — see DEMO-two-minds.md). The point is not the
exact numbers but that ONE center, given different named criteria, faithfully serves different domains.

Stdlib only, deterministic. No network, no model call — this is the witnessed-verdict core; the live
perception/reconcile rounds that produce the candidates are the subagent demo.
"""
from __future__ import annotations
import json

DIMENSIONS = ["novelty", "structure", "function", "completeness", "grounded"]

# Candidate forms from the demo, scored per dimension in [0,1] (from the two blind judge passes).
CANDIDATES = {
    "visual-solo (Witnessed Render)":      {"novelty": 0.90, "structure": 0.90, "function": 0.20,
                                            "completeness": 0.40, "grounded": 0.95},
    "symbolic-solo (Release Warden)":      {"novelty": 0.90, "structure": 0.30, "function": 0.90,
                                            "completeness": 0.40, "grounded": 0.90},
    "the meeting (Provenanced Render Ledger)": {"novelty": 0.40, "structure": 0.95, "function": 0.95,
                                            "completeness": 0.95, "grounded": 0.80},
}

# Named, domain-weighted criteria — the human's part. Each is a stance someone stands behind.
CRITERIA = {
    "creator (novel work)":      {"novelty": 0.55, "structure": 0.10, "function": 0.10,
                                  "completeness": 0.10, "grounded": 0.15},
    "researcher (rigor)":        {"novelty": 0.05, "structure": 0.25, "function": 0.25,
                                  "completeness": 0.25, "grounded": 0.20},
    "auditor (provenance)":      {"novelty": 0.00, "structure": 0.15, "function": 0.15,
                                  "completeness": 0.15, "grounded": 0.55},
    "balanced":                  {d: 0.20 for d in DIMENSIONS},
}


def reconcile(candidates, criterion_name, weights):
    """Score each candidate under the NAMED criterion; return a witnessed verdict record."""
    assert abs(sum(weights.values()) - 1.0) < 1e-9, "weights must sum to 1 (a stance is normalized)"
    scored = {name: round(sum(s[d] * weights[d] for d in DIMENSIONS), 4)
              for name, s in candidates.items()}
    winner = max(scored, key=scored.get)
    # the Certificate: names the criterion, its weights, the scores, the winner — nothing hidden.
    return {"criterion": criterion_name, "weights": weights, "scores": scored, "winner": winner}


def main():
    print("THE CENTER — one place, criterion named by the human, verdict witnessed.\n")
    print("candidate per-dimension scores (from the two blind judges, normalized):")
    for name, s in CANDIDATES.items():
        print(f"  {name:42s} " + "  ".join(f"{d}={s[d]:.2f}" for d in DIMENSIONS))
    print()
    certs = []
    print("the SAME center, under each named criterion the human stands behind:\n")
    print(f"  {'named criterion':26s}  winner")
    for cname, w in CRITERIA.items():
        cert = reconcile(CANDIDATES, cname, w)
        certs.append(cert)
        ranked = sorted(cert["scores"].items(), key=lambda kv: -kv[1])
        margin = ranked[0][1] - ranked[1][1]
        print(f"  {cname:26s}  {cert['winner']}  ({ranked[0][1]:.3f}, +{margin:.3f})")

    print("\nReading (narration matches the numbers above):")
    print("  - creator weights novelty heavily -> a SOLO wins; the meeting comes LAST, because")
    print("    converging on the whole truth is not novel.")
    print("  - researcher, auditor, AND balanced -> the MEETING wins: its lead on structure/function/")
    print("    completeness overwhelms even the auditor's heavy grounding weight (its one over-reach")
    print("    lowers grounded but does not cost it the verdict here).")
    print("  => the meeting (the conferred, whole form) is ROBUST across every criterion EXCEPT one")
    print("     that prizes novelty above wholeness — it loses only where boldness is the whole point.")
    print("  ONE center. The criterion is the human's, named and weighted per domain; the winner")
    print("  follows from it, witnessed. The center never picks 'best' -- it serves the named best.")

    out = "center-certificates.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"dimensions": DIMENSIONS, "candidates": CANDIDATES, "verdicts": certs}, f, indent=2)
    print(f"\nwitnessed verdicts written: {out}")
    print("(neutral place, non-neutral act: each verdict NAMES and OWNS its criterion — pluralism, not relativism.)")


if __name__ == "__main__":
    main()
