"""adversarial_corpus.py — the false-accept gate for the transitive witness.

A verifier is only credible if it can FAIL: if there exist inputs it SHOULD
reject and does. The live weakness this attacks (from the crucible dogfood note:
"872/875 deviations author-supplied 0.0, refutations never execute") is a
verifier whose refutation path never actually runs — a theatrical MATCH.

This corpus is a registry of crafted DAGs, each trying to smuggle a FALSE MATCH
through the transitive-witness closure. Two obligations, and the second is what
makes it non-theatrical:

  1. SOUNDNESS: the real closure returns false_accepts == 0 over the whole corpus
     AND does not over-reject the controls (a verifier that rejects everything is
     trivially "safe" and useless).
  2. DISCRIMINATION (anti-theatre): deliberately WEAKENED closures MUST be caught
     — `naive_closure` (outcome-only, the norm the Trust-but-Verify survey
     describes) and `depth_limited_closure` (checks grounding but only k hops).
     If the corpus passed against a broken closure too, it would assert nothing.

The attack taxonomy (ways a false MATCH sneaks in): drifted ancestor, deep drift
(depth evasion), cycle laundering (mutual circular support with no external
anchor), dangling grounding (cite an ancestor you cannot produce), forged/absent
receipt, glut laundering (a drifted node's descendant claiming MATCH), and an
unverifiable ancestor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .transitive_witness import (DepNode, transitive_verdicts, MATCH, DRIFT,
                                 UNVERIFIABLE)


@dataclass
class Attack:
    name: str
    kind: str                       # "false-accept" | "control"
    nodes: list[DepNode]
    target: str                     # the node whose verdict is under test
    expect_not: str = MATCH         # false-accept: target must NOT be this
    why: str = ""


def corpus() -> list[Attack]:
    """The attack registry. Extend by appending; every false-accept attack's
    target MUST be refused (not MATCH) by a sound closure."""
    def chain(prefix, n, root_local):
        # root(root_local) <- s1 <- s2 <- ... <- sn, all sink locals MATCH
        nodes = [DepNode(f"{prefix}0", local=root_local)]
        for i in range(1, n + 1):
            nodes.append(DepNode(f"{prefix}{i}", local=MATCH, deps=[f"{prefix}{i-1}"]))
        return nodes

    attacks: list[Attack] = [
        Attack("drifted_ancestor", "false-accept",
               [DepNode("R", local=MATCH), DepNode("A", local=DRIFT, deps=["R"]),
                DepNode("B", local=MATCH, deps=["A"])],
               target="B", why="descendant of a 1-hop drift claims MATCH"),
        Attack("deep_drift_depth_evasion", "false-accept",
               chain("d", 6, DRIFT), target="d6",
               why="drift 6 hops upstream; a depth-limited closure misses it"),
        Attack("cycle_laundering", "false-accept",
               [DepNode("A", local=MATCH, deps=["B"]),
                DepNode("B", local=MATCH, deps=["A"])],
               target="A", why="mutual circular grounding, no external anchor"),
        Attack("dangling_grounding", "false-accept",
               [DepNode("B", local=MATCH, deps=["ghost"])],
               target="B", why="cites an ancestor not present in the DAG"),
        Attack("no_receipt", "false-accept",
               [DepNode("X", local=MATCH, has_receipt=False)],
               target="X", why="asserts MATCH with no receipt"),
        Attack("glut_launder", "false-accept",
               [DepNode("G", local=DRIFT), DepNode("H", local=MATCH, deps=["G"])],
               target="H", why="descendant of a glut claims MATCH"),
        Attack("unverifiable_ancestor", "false-accept",
               [DepNode("U", local=UNVERIFIABLE), DepNode("V", local=MATCH, deps=["U"])],
               target="V", why="grounded on an unconfirmable ancestor"),
        # controls: a sound closure MUST return MATCH (no over-rejection)
        Attack("clean_chain", "control", chain("c", 4, MATCH), target="c4",
               expect_not="", why="fully-MATCH path must be conserved"),
        Attack("clean_diamond", "control",
               [DepNode("T", local=MATCH), DepNode("L", local=MATCH, deps=["T"]),
                DepNode("Rt", local=MATCH, deps=["T"]),
                DepNode("Bt", local=MATCH, deps=["L", "Rt"])],
               target="Bt", why="MATCH must compose across a diamond"),
    ]
    return attacks


# --- deliberately weakened strawmen (must be CAUGHT by the corpus) -----------

def naive_closure(nodes: list[DepNode]) -> dict[str, str]:
    """Outcome-only: return each node's own re-witness verdict, ignoring grounding
    and receipts entirely. The norm the Trust-but-Verify survey describes."""
    return {n.id: n.local for n in nodes}


def depth_limited_closure(nodes: list[DepNode], max_depth: int = 1) -> dict[str, str]:
    """Checks grounding but only `max_depth` hops — a plausible partial fix that
    still lets deep drift and cycles through."""
    by_id = {n.id: n for n in nodes}

    def resolve(nid: str, depth: int) -> str:
        n = by_id.get(nid)
        if n is None:
            return UNVERIFIABLE
        if not n.has_receipt:
            return UNVERIFIABLE
        if n.local != MATCH:
            return n.local
        if depth >= max_depth:
            return MATCH                      # stop recursing -> the bug
        dep_vs = [resolve(d, depth + 1) for d in n.deps]
        return MATCH if all(v == MATCH for v in dep_vs) else UNVERIFIABLE

    return {n.id: resolve(n.id, 0) for n in nodes}


# --- the gate ---------------------------------------------------------------

def run_corpus(closure_fn, attacks: list[Attack] | None = None) -> dict:
    """Run a closure against the corpus. Returns the false-accept count (served a
    MATCH it must refuse), the over-reject count (refused a control it must pass),
    and per-attack detail. A sound closure scores 0/0."""
    attacks = attacks if attacks is not None else corpus()
    false_accepts, over_rejects = [], []
    per = {}
    for a in attacks:
        verdicts = closure_fn(a.nodes)
        v = verdicts.get(a.target)
        if a.kind == "false-accept":
            bad = (v == MATCH)                # accepted something it must refuse
            if bad:
                false_accepts.append(a.name)
        else:                                 # control
            bad = (v != MATCH)                # refused something it must pass
            if bad:
                over_rejects.append(a.name)
        per[a.name] = {"kind": a.kind, "target_verdict": v, "caught": bad}
    n_fa = sum(1 for a in attacks if a.kind == "false-accept")
    return {"false_accepts": len(false_accepts),
            "false_accept_names": false_accepts,
            "over_rejects": len(over_rejects),
            "over_reject_names": over_rejects,
            "n_false_accept_attacks": n_fa,
            "false_accept_rate": round(len(false_accepts) / max(n_fa, 1), 3),
            "per_attack": per}


def gate_report(result: dict) -> str:
    fa, orj = result["false_accepts"], result["over_rejects"]
    status = "SOUND" if (fa == 0 and orj == 0) else "FAILED"
    return (f"adversarial false-accept gate: {status} — "
            f"{fa}/{result['n_false_accept_attacks']} false-accepts, "
            f"{orj} over-rejects")
