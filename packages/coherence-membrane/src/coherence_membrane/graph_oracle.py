"""graph_oracle -- the first Graph-plane reconcile criteria (worked, attributed).

Three Certificate-emitting Criterion factories, harvested and attributed from the
3cycle YouTube corpus (study + cite, never strip). Each `judge` is TOTAL: malformed
input, an over-cap graph, or any internal error degrades to UNVERIFIABLE -- NEVER a
crash and NEVER a false VERIFIED (the cardinal soundness invariant). Every VERIFIED
Certificate carries a re-checkable witness (a path/cycle, or spanning edges + a cut)
so a third party re-derives the verdict without trusting this code.

Each criterion is consumed unchanged by the generic reconcile() spine -- they are
real reconciles, not a bespoke pipeline (proven by the reconcile-equivalence test).

Bounds are explicit (node/edge/depth caps); exceeding a cap is UNVERIFIABLE WITH A
REASON, never a silent drop. Deterministic: the Graph substrate fixes node/edge
order, so the same claim yields the same Certificate.
"""
from __future__ import annotations

from typing import Optional

from .certificate import Certificate, Verdict
from .composition import compose
from .graph import Edge, Graph, _norm_node
from .graph_claims import BottleneckClaim, ClosureClaim, ReachabilityClaim
from .graph_search import connects_all, cut_sides, find_cycle_through, spans, tree_jump_edges
from .reconcile import Criterion

# Claims re-exported from graph_claims so coherence_membrane.graph_oracle.<Claim> and
# the package __init__ keep working unchanged after the pure split.
__all__ = ["ReachabilityClaim", "BottleneckClaim", "ClosureClaim",
           "reachability_criterion", "bottleneck_criterion", "closure_certificate"]

# Default hard caps. Conservative on purpose: a re-check that cannot be cheaply
# re-run by a third party is UNVERIFIABLE-in-practice, not VERIFIED.
DEFAULT_MAX_NODES = 4096
DEFAULT_MAX_EDGES = 16384


def _over_cap(g: Graph, max_nodes: int, max_edges: int) -> Optional[str]:
    if not isinstance(g, Graph):
        return "subject is not a Graph"
    if g.node_count() > max_nodes:
        return f"node count {g.node_count()} > cap {max_nodes}"
    if g.edge_count() > max_edges:
        return f"edge count {g.edge_count()} > cap {max_edges}"
    return None


# --- R3.1 reachability --------------------------------------------------------


def reachability_criterion(*, max_nodes: int = DEFAULT_MAX_NODES,
                           max_edges: int = DEFAULT_MAX_EDGES) -> Criterion:
    """Decide a reachability property on a state graph via a cycle through a labelled
    node (the de Bruijn construction): VERIFIED-with-witness when the claim matches a
    re-checkable cycle/closure, REFUTED when it contradicts it, UNVERIFIABLE over the
    node/edge cap or on malformed input.

    Source (study + cite, never strip): 3cycle (@3cycle), "Prescribing the Death of a
    Cellular Automaton", video id `nGespkZpUNo` -- recasts a CA-death/recurrence
    question as a de Bruijn-graph reachability decision, a sound+complete alternative
    to a SAT encoding on the bounded fragment.

    The judge is TOTAL (never raises). On `expect_cycle=True`: VERIFIED iff a simple
    cycle through `label_node` is found within budget -- the cycle (node list, first ==
    last) is carried in evidence so a third party re-checks every edge exists; REFUTED
    iff the bounded search proves NO such cycle (closure). On `expect_cycle=False` the
    verdicts swap (VERIFIED = absence proven, witness = the closure). A budget hit ->
    UNVERIFIABLE (reason carried), never a fabricated cycle or a false absence."""
    def judge(form) -> Certificate:
        oracle = "graph-reachability-debruijn-v1"
        try:
            if not isinstance(form, ReachabilityClaim):
                return Certificate("reachability (bad claim)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", "expected a ReachabilityClaim"),))
            g = form.graph
            cap = _over_cap(g, max_nodes, max_edges)
            if cap is not None:
                return Certificate("reachability (over cap)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", cap),))
            node = _norm_node(form.label_node)
            if node not in set(g.nodes):
                return Certificate(f"reachability: cycle through {node!r}",
                                   Verdict.UNVERIFIABLE, oracle,
                                   (("reason", f"label node {node!r} not in graph"),))
            cycle = find_cycle_through(g, node, max_nodes=max_nodes)
            # find_cycle_through returns None for BOTH "no cycle" and "budget hit"; the
            # cap is enforced above (node_count <= max_nodes) so within-budget BFS over
            # <= max_nodes nodes cannot hit the per-search cap before exhausting -- a None
            # here is therefore a real closure (no cycle), not a budget abort.
            exists = cycle is not None
            verdict = Verdict.VERIFIED if exists == form.expect_cycle else Verdict.REFUTED
            if exists:
                witness = ("cycle", "->".join(cycle))
                claim = f"cycle through {node!r} exists" if form.expect_cycle \
                    else f"cycle through {node!r} exists (claim said none)"
            else:
                witness = ("closure", f"no simple cycle through {node!r} (BFS exhausted)")
                claim = f"no cycle through {node!r}" if not form.expect_cycle \
                    else f"no cycle through {node!r} (claim said one exists)"
            return Certificate(form.claim or claim, verdict, oracle,
                               (("expect_cycle", str(form.expect_cycle)),
                                ("found_cycle", str(exists)), witness))
        except Exception as exc:  # TOTAL: never propagate
            return Certificate("reachability (error)", Verdict.UNVERIFIABLE, oracle,
                               (("reason", repr(exc)),))

    return Criterion("graph-reachability", judge)


# --- R3.2 bottleneck spanning tree --------------------------------------------


def bottleneck_criterion(*, max_nodes: int = DEFAULT_MAX_NODES,
                         max_edges: int = DEFAULT_MAX_EDGES) -> Criterion:
    """Re-check a claimed minimax (bottleneck) spanning structure in O(E): the claimed
    `spanning` edges must (1) connect every node, (2) have max weight == `bottleneck`,
    and (3) `bottleneck` must be MINIMAL -- proven by a cut witness: deleting every edge
    with weight < `bottleneck` must DISCONNECT the graph (so no spanning structure can
    have a smaller max weight). VERIFIED iff all three checks pass with a carried
    witness; REFUTED iff a check fails; UNVERIFIABLE over cap / malformed.

    Source (study + cite, never strip): 3cycle (@3cycle), "Bottleneck Spanning Trees:
    A Graph Theory Breakthrough?", video id `sUMAV8lnPcA` -- the minimax spanning
    arborescence (Camerini; Gabow-Tarjan) and its cheap, re-checkable certificate. We
    re-check the certificate (the cheap direction); we do NOT recompute the optimum.

    The judge is TOTAL. The witness carries the spanning edges, the bottleneck value,
    and the cut (the two sides the sub-bottleneck edges fail to connect), so a third
    party re-derives minimality independently.

    SOUNDNESS -- checker disjoint from its own primitive (cf. crosscheck.py, spec
    §16.1): the two load-bearing connectivity questions (is the claimed set spanning?
    do edges below `b` disconnect?) are decided TWICE, by two genuinely independent
    kernels -- union-find `spans()` AND BFS-reachability `connects_all()`, which share
    no helper. Both must AGREE; a disagreement is a CAUGHT BUG in one kernel ->
    UNVERIFIABLE with a `discrepancy` reason, NEVER a guess and never a false VERIFIED.
    A single connectivity kernel would hide its own bug from the re-checker; two do
    not (the trusted base shrinks to 'they are not both wrong the same way')."""
    def judge(form) -> Certificate:
        oracle = "graph-bottleneck-mst-v1"
        try:
            if not isinstance(form, BottleneckClaim):
                return Certificate("bottleneck (bad claim)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", "expected a BottleneckClaim"),))
            g = form.graph
            cap = _over_cap(g, max_nodes, max_edges)
            if cap is not None:
                return Certificate("bottleneck (over cap)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", cap),))
            if g.node_count() == 0:
                return Certificate("bottleneck (empty graph)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", "empty graph has no spanning structure"),))
            b = float(form.bottleneck)
            spanning = tuple(g._canon(e) for e in form.spanning)
            real = set(g.edges)
            # (0) every claimed spanning edge must be a real edge.
            missing = [e for e in spanning if e not in real]
            if missing:
                return Certificate("bottleneck: spanning uses non-edges", Verdict.REFUTED, oracle,
                                   (("reason", f"claimed edges not in graph: {missing}"),))
            # weights: an unweighted edge counts as weight 1.0 (uniform); resolve all.
            def wt(e: Edge) -> float:
                w = g.weight(*e)
                return 1.0 if w is None else w
            # (1) spanning: the claimed edges connect all nodes. Decided by TWO
            # disjoint kernels (union-find AND BFS); they must agree, else a kernel
            # bug is caught as UNVERIFIABLE -- never a guess, never a false VERIFIED.
            uf_spans = spans(g.nodes, spanning) is not None
            bfs_spans = connects_all(g.nodes, spanning)
            if uf_spans != bfs_spans:
                return Certificate("bottleneck (connectivity discrepancy)",
                                   Verdict.UNVERIFIABLE, oracle,
                                   (("discrepancy",
                                     "spanning check disagrees: "
                                     f"union-find={uf_spans} bfs={bfs_spans}"),
                                    ("question", "is the claimed set spanning?")))
            if not uf_spans:  # both kernels agree the claim does not span
                return Certificate("bottleneck: not spanning", Verdict.REFUTED, oracle,
                                   (("reason", "claimed edges do not connect all nodes"),))
            # (2) bottleneck value: max spanning weight must equal the claim.
            if spanning:
                actual_max = max(wt(e) for e in spanning)
                if actual_max != b:
                    return Certificate("bottleneck: wrong value", Verdict.REFUTED, oracle,
                                       (("claimed_bottleneck", repr(b)),
                                        ("actual_max_spanning_weight", repr(actual_max))))
            elif g.node_count() > 1:
                return Certificate("bottleneck: no edges but >1 node", Verdict.REFUTED, oracle,
                                   (("reason", "cannot span >1 node with no edges"),))
            # (3) minimality cut witness: edges strictly below b must NOT connect the
            # graph (else a smaller bottleneck would exist). Decided by the SAME two
            # disjoint kernels and cross-checked -- a disagreement here is likewise a
            # caught kernel bug (UNVERIFIABLE), not a guessed minimality verdict.
            below = tuple(e for e in g.edges if wt(e) < b)
            uf_below_spans = spans(g.nodes, below) is not None
            bfs_below_spans = connects_all(g.nodes, below)
            if uf_below_spans != bfs_below_spans:
                return Certificate("bottleneck (minimality discrepancy)",
                                   Verdict.UNVERIFIABLE, oracle,
                                   (("discrepancy",
                                     "below-b spanning check disagrees: "
                                     f"union-find={uf_below_spans} bfs={bfs_below_spans}"),
                                    ("question", "do edges below b disconnect the graph?")))
            if uf_below_spans and g.node_count() > 1:
                # sub-bottleneck edges already span -> b is NOT minimal -> claim false.
                return Certificate("bottleneck: not minimal", Verdict.REFUTED, oracle,
                                   (("reason", "edges below b already span -- smaller bottleneck exists"),
                                    ("claimed_bottleneck", repr(b))))
            cut = cut_sides(g.nodes, below)
            witness = (
                ("spanning_edges", ";".join(f"{u}-{v}" for u, v in spanning)),
                ("bottleneck", repr(b)),
                ("cut", f"{sorted(cut[0])} | {sorted(cut[1])}"),
            )
            return Certificate(form.claim or f"bottleneck == {b!r} (minimax spanning)",
                               Verdict.VERIFIED, oracle, witness)
        except Exception as exc:
            return Certificate("bottleneck (error)", Verdict.UNVERIFIABLE, oracle,
                               (("reason", repr(exc)),))

    return Criterion("graph-bottleneck", judge)


# --- R3.3 closure certificate (composable jump-edges) -------------------------


def closure_certificate(*, max_nodes: int = DEFAULT_MAX_NODES,
                        max_edges: int = DEFAULT_MAX_EDGES) -> Criterion:
    """Certify a reachability fact on a TREE by precomputing serial transitive closure
    (ancestor jump-edges), so the certificate is constructible by ONE composition: the
    resulting Certificate is the proven lattice meet (composition.compose) over the
    per-edge steps along the unique root..dst path that must contain `src`. VERIFIED
    iff `src` is a proper ancestor of `dst` (each composed step is a real tree edge);
    REFUTED iff the precompute proves `src` does not reach `dst`; UNVERIFIABLE over cap,
    on a non-tree, or malformed.

    Source (study + cite, never strip): 3cycle (@3cycle), "Translating proofs between
    Nested Deduction and Hilbert Systems", video id `krU8nPF6CdY` -- serial transitive
    closure on a (proof) tree precomputes composable jump-edges so any reachability
    certificate is one composition; here that maps onto the project's composable
    Certificates via the proven meet.

    The judge is TOTAL. The composed Certificate carries each jump-edge step (oracle +
    verdict) in its evidence, so the composition is re-derivable end-to-end."""
    def judge(form) -> Certificate:
        oracle = "graph-closure-composed-v1"
        try:
            if not isinstance(form, ClosureClaim):
                return Certificate("closure (bad claim)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", "expected a ClosureClaim"),))
            g = form.graph
            cap = _over_cap(g, max_nodes, max_edges)
            if cap is not None:
                return Certificate("closure (over cap)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", cap),))
            chains = tree_jump_edges(g, form.root, max_nodes=max_nodes)
            if chains is None:
                return Certificate("closure (not a tree)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", "graph is not a tree rooted at root, or over cap"),))
            src, dst = _norm_node(form.src), _norm_node(form.dst)
            if dst not in chains or src not in set(g.nodes):
                return Certificate("closure (unknown endpoint)", Verdict.UNVERIFIABLE, oracle,
                                   (("reason", f"endpoint not in tree: src={src!r} dst={dst!r}"),))
            ancestors = chains[dst]  # root-first ancestor chain of dst (excludes dst)
            if src not in ancestors:
                # The precompute PROVES src is not on dst's ancestor path -> not reachable.
                claim = form.claim or f"{src!r} reaches {dst!r}"
                return Certificate(claim, Verdict.REFUTED, oracle,
                                   (("reason", f"{src!r} is not an ancestor of {dst!r}"),
                                    ("ancestors_of_dst", "->".join(ancestors) or "(root)")))
            # Build the path src -> ... -> dst from the ancestor chain and compose ONE
            # per-edge Certificate per hop (each a real tree edge -> VERIFIED step).
            tail = list(ancestors[ancestors.index(src):]) + [dst]
            steps = []
            for a, b in zip(tail, tail[1:]):
                ok = g.has_edge(a, b)
                steps.append(Certificate(
                    f"jump {a!r}->{b!r}",
                    Verdict.VERIFIED if ok else Verdict.REFUTED,
                    "graph-jump-edge-v1", (("edge", f"{a}->{b}"),)))
            composed = compose(steps, claim=form.claim or f"{src!r} reaches {dst!r} (composed jumps)")
            # Re-stamp with this criterion's oracle; carry the path + each step's verdict.
            evidence = (("path", "->".join(tail)),) + tuple(
                (f"step:{c.claim}", c.verdict.value) for c in steps)
            return Certificate(composed.claim, composed.verdict, oracle, evidence)
        except Exception as exc:
            return Certificate("closure (error)", Verdict.UNVERIFIABLE, oracle,
                               (("reason", repr(exc)),))

    return Criterion("graph-closure", judge)
