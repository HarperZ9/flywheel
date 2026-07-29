"""qa_mutations.py -- the attack corpus: what a checker must refuse.

Split out of oracle_qa.py when that module crossed the 300-line gate. The
boundary is real rather than cosmetic: this module GENERATES attacks and knows
nothing about grading, while oracle_qa.py grades and knows nothing about how an
attack is built. Either can be replaced without touching the other.

TYPE_CONFUSION exists because of a real find: bool subclasses int in Python, so
`[[true, 0]]` was accepted with True read as row 1 until the Zarankiewicz checker
was hardened. That mutation is now a permanent regression probe.

One discipline the mutation engine owes the battery: a mutant must actually be
invalid. An earlier version emitted an ADD_EDGE mutant on a non-extremal base,
which left the graph legitimately K22-free, so a correct PASS was scored as a
false accept. Another normalized edge_count after mutating it, silently undoing
the string-count variant. A battery that neutralizes or miscounts its own mutants
reports an n it never tested, which is exactly the overstatement the Wilson bound
exists to prevent.
"""
from __future__ import annotations

import json
from enum import Enum

_MASK = (1 << 32) - 1


class QAError(ValueError):
    """A battery that would report more than it measured."""


# Which classes need a graph-shaped certificate (m, n, edges) and which are
# universal. A family that is not graph-shaped simply skips the graph classes and
# is still graded on the universal ones, rather than being locked out of a card.
class MutationClass(str, Enum):
    ADD_EDGE = "ADD_EDGE"                    # near miss: one edge too many
    DUPLICATE_EDGE = "DUPLICATE_EDGE"        # inflate the count by repetition
    INDEX_OUT_OF_RANGE = "INDEX_OUT_OF_RANGE"
    NEGATIVE_INDEX = "NEGATIVE_INDEX"
    COUNT_OVERCLAIM = "COUNT_OVERCLAIM"      # claim more than you exhibit
    TYPE_CONFUSION = "TYPE_CONFUSION"        # bool-as-int, float-as-int, str-as-int
    TRAILING_GARBAGE = "TRAILING_GARBAGE"    # smuggle bytes after the object
    STRUCTURE_ABUSE = "STRUCTURE_ABUSE"      # nested or wrong-arity edges


# BIPARTITE-ONLY: these need per-family semantics, not just a vertex set.
# ADD_EDGE needs a reference predicate to know the addition actually broke the
# property. DUPLICATE_EDGE assumes a repeated edge INFLATES a declared count; in
# a family that normalises duplicates away it would emit a valid certificate as a
# mutant, which is the neutralised-mutant trap this module already carries scars
# from.
BIPARTITE_CLASSES = frozenset({
    MutationClass.ADD_EDGE,
    MutationClass.DUPLICATE_EDGE,
})

# VERTEX-INDEXED: any family whose certificate carries a vertex count and an edge
# list. These attack the INDEX SPACE, which is family-independent: an endpoint
# outside the declared vertex range is invalid whatever the predicate is. The
# gate used to require a bipartite `m`, so a general graph with n vertices and an
# edge list skipped all three and earned a card on two classes.
VERTEX_INDEXED_CLASSES = frozenset({
    MutationClass.INDEX_OUT_OF_RANGE,
    MutationClass.NEGATIVE_INDEX,
    MutationClass.STRUCTURE_ABUSE,
})

GRAPH_CLASSES = BIPARTITE_CLASSES | VERTEX_INDEXED_CLASSES

# Universal: these attack the ENCODING rather than the graph, so every family
# needs them. TRAILING_GARBAGE and TYPE_CONFUSION are the two that found real
# defects (the bool-as-int accept, and a mutation the battery neutralized).
UNIVERSAL_CLASSES = frozenset(MutationClass) - GRAPH_CLASSES


def _lcg(state: int) -> int:
    return (1664525 * state + 1013904223) & _MASK


def _reference_free(m: int, n: int, edges) -> bool:
    """Ground truth for the semantic near-miss class, taken as the AGREEMENT of
    both independent predicates.

    Honest bound: for the ADD_EDGE class this makes the battery a test of the
    pipeline AROUND the predicate (parsing, the envelope, well-formedness,
    counting) rather than of the predicate itself. The predicate's correctness is
    evidenced elsewhere: the Fano plane extremal control and exhaustive agreement
    over all 512 subgraphs of K_3,3. A battery cannot bootstrap the correctness of
    the mathematics it uses to build its own mutants, and pretending otherwise
    would be the circularity this whole design exists to avoid.
    """
    from .certificates.zarankiewicz import k22_free
    from .certificates.independent import k22_free_by_row_pairs
    a = k22_free(m, n, edges)
    b = k22_free_by_row_pairs(m, n, edges)
    if a != b:
        raise QAError(
            "the two reference predicates disagree while building a mutant; "
            "the battery cannot establish ground truth and refuses to guess")
    return a


def _load(cert_text: str) -> dict:
    return json.loads(cert_text)


def _dump(obj: dict) -> str:
    return json.dumps(obj)


def mutate(cert_text: str, cls: MutationClass, *, count: int,
           seed: int) -> list[str]:
    """Produce `count` mutants of one class. Deterministic in `seed`."""
    base = _load(cert_text)
    out: list[str] = []
    s = _lcg(seed * 2654435761 + len(cls.value))

    # GRAPH-SHAPED classes need m, n and edges. The universal classes below do
    # not, so reading those keys unconditionally locked every non-graph family out
    # of ever earning a QA card, which made it reward-ineligible via
    # QA_CARD_ABSENT. Found by running qa_battery against this repo's OWN second
    # oracle (matmul), which raised KeyError 'edges'.
    bipartite = all(k in base for k in ("m", "n", "edges"))
    vertex_indexed = "n" in base and isinstance(base.get("edges"), list)
    if cls in BIPARTITE_CLASSES and not bipartite:
        return []
    if cls in VERTEX_INDEXED_CLASSES and not vertex_indexed:
        return []
    m = base.get("m", 0)
    n = base.get("n", 0)
    edges = [tuple(e) for e in base.get("edges", [])]
    # The index bound is the row count for a bipartite family and the vertex
    # count for a general one.
    bound = m if bipartite else n

    def bump_count(d):
        """Keep a declared edge count consistent, if the family declares one.
        Inventing the key for a family that has none would add a field the
        checker ignores and weaken the mutant."""
        if "edge_count" in base:
            d["edge_count"] = len(edges) + 1

    for i in range(count):
        s = _lcg(s)
        d = json.loads(cert_text)
        if cls is MutationClass.ADD_EDGE:
            # A semantic near miss only exists if the base is EXTREMAL. Adding an
            # edge to a star leaves it K22-free, so emitting that as a mutant
            # would score a correct PASS as a false accept. Only keep additions
            # that both reference predicates agree have broken the property.
            present = set(edges)
            missing = [(r, c) for r in range(m) for c in range(n)
                       if (r, c) not in present]
            if not missing:
                continue
            chosen = None
            for k in range(len(missing)):
                r, c = missing[(s + k) % len(missing)]
                cand = edges + [(r, c)]
                if not _reference_free(m, n, cand):
                    chosen = (r, c)
                    break
            if chosen is None:
                continue                      # this base admits no near miss
            d["edges"] = [list(e) for e in edges] + [list(chosen)]
            d["edge_count"] = len(edges) + 1
        elif cls is MutationClass.DUPLICATE_EDGE:
            if not edges:
                continue
            e = edges[s % len(edges)]
            d["edges"] = [list(x) for x in edges] + [list(e)]
            d["edge_count"] = len(edges) + 1
        elif cls is MutationClass.INDEX_OUT_OF_RANGE:
            d["edges"] = [list(x) for x in edges] + [[bound + 1 + (s % 5), 0]]
            bump_count(d)
        elif cls is MutationClass.NEGATIVE_INDEX:
            d["edges"] = [list(x) for x in edges] + [[-1 - (s % 3), 0]]
            bump_count(d)
        elif cls is MutationClass.COUNT_OVERCLAIM:
            # Generic: inflate whatever integer count the certificate declares.
            count_key = next((k for k in ("edge_count", "rank", "count", "size",
                                          "weight", "n_triples", "crossings")
                              if isinstance(base.get(k), int)
                              and not isinstance(base.get(k), bool)), None)
            if count_key is None:
                continue
            d[count_key] = base[count_key] + 1 + (s % 40)
        elif cls is MutationClass.TYPE_CONFUSION:
            # KEY-AGNOSTIC. Attacks the ENCODING of whatever integer and list
            # fields a certificate declares, so it works for any family. The
            # graph-specific version reached for `edges` and locked non-graph
            # families out of a card entirely.
            #
            # Each variant owns any count it disturbs. An earlier version
            # normalized the count afterwards, which silently UNDID the
            # string-count variant and emitted a VALID certificate as a mutant. A
            # battery that neutralizes its own mutants reports an n it never
            # tested, which is the overstatement the Wilson bound exists to
            # prevent.
            int_keys = sorted(k for k, v in base.items()
                              if isinstance(v, int) and not isinstance(v, bool))
            list_keys = sorted(k for k, v in base.items() if isinstance(v, list))
            variants = []
            for k in int_keys[:2]:
                variants.append(lambda dd, k=k: dd.__setitem__(k, str(base[k])))
                variants.append(lambda dd, k=k: dd.__setitem__(k, float(base[k])))
                variants.append(lambda dd, k=k: dd.__setitem__(k, True))
            for k in list_keys[:2]:
                variants.append(lambda dd, k=k: dd.__setitem__(k, None))
                variants.append(lambda dd, k=k: dd.__setitem__(k, {"0": 0}))
                # bool inside a list: bool subclasses int in Python, so a naive
                # isinstance check reads True as 1. This is the variant that found
                # a real accept in the Zarankiewicz checker.
                variants.append(
                    lambda dd, k=k: dd.__setitem__(k, [True] + list(base[k])))
                variants.append(
                    lambda dd, k=k: dd.__setitem__(k, ["0"] + list(base[k])))
            if not variants:
                continue
            variants[i % len(variants)](d)
        elif cls is MutationClass.TRAILING_GARBAGE:
            out.append(_dump(d) + (" " * (i % 2)) + "; extra")
            continue
        elif cls is MutationClass.STRUCTURE_ABUSE:
            shapes = [[[0], 0], [0, 0, 0], [], [[[0, 0]], 0]]
            d["edges"] = [list(x) for x in edges] + [shapes[i % len(shapes)]]
            bump_count(d)
        out.append(_dump(d))
    return out


