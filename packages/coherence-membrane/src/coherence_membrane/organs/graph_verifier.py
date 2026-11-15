"""GraphVerifierOrgan -- witnessed verification of an L0 Graph-plane claim.

The Graph plane's first organ: the model emits a graph claim (reachability /
bottleneck / closure) and the organ returns a sound Certificate carrying a
re-checkable witness. SOUNDNESS is the contract -- an over-cap / malformed / non-tree
claim is UNVERIFIABLE, NEVER a false VERIFIED. Inert and fail-closed: a foreign
subject yields [] and observe() never raises.

It is a thin perception shell over the three graph criteria (graph_oracle): the SAME
Criterion.judge the generic reconcile() spine calls, so the organ and a direct
reconcile() are provably equivalent (tests/test_graph_verifier.py)."""
from __future__ import annotations

from ..certificate import Verdict
from ..graph_oracle import (
    BottleneckClaim,
    ClosureClaim,
    ReachabilityClaim,
    bottleneck_criterion,
    closure_certificate,
    reachability_criterion,
)
from ..graph import Graph
from ..graph_ops import de_bruijn_graph
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult


class GraphVerifierOrgan:
    name = "graph-verifier"

    def __init__(self, *, max_nodes: int = 4096, max_edges: int = 16384):
        if max_nodes < 1 or max_edges < 1:
            raise ValueError("max_nodes and max_edges must be >= 1")
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        # one Criterion instance per claim type; the organ delegates to .judge so it
        # and the generic reconcile() spine share the EXACT same oracle.
        self._reach = reachability_criterion(max_nodes=max_nodes, max_edges=max_edges)
        self._bottleneck = bottleneck_criterion(max_nodes=max_nodes, max_edges=max_edges)
        self._closure = closure_certificate(max_nodes=max_nodes, max_edges=max_edges)

    def _criterion_for(self, subject):
        if isinstance(subject, ReachabilityClaim):
            return self._reach
        if isinstance(subject, BottleneckClaim):
            return self._bottleneck
        if isinstance(subject, ClosureClaim):
            return self._closure
        return None

    def observe(self, subject) -> list[Observation]:
        criterion = self._criterion_for(subject)
        if criterion is None:
            return []  # foreign subject -> inert
        claim = str(getattr(subject, "claim", "") or type(subject).__name__)
        try:
            cert = criterion.judge(subject)  # judge is TOTAL, but stay fail-closed
        except Exception as exc:  # belt-and-braces: an organ never raises
            return [self._obs(claim, "unverifiable", Status.UNVERIFIED, "low",
                              {"reason": f"malformed: {exc}"})]
        decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        text = cert.claim if isinstance(cert.claim, str) else str(cert.claim)
        return [self._obs(
            text, cert.verdict.value,
            Status.PASS if decided else Status.UNVERIFIED,
            "high" if decided else "low",
            {"oracle": cert.oracle, "verdict": cert.verdict.value, "claim": text,
             "evidence": [list(p) for p in cert.evidence],
             "identity_sha256": sha256_hex(text.encode())},
        )]

    def _obs(self, claim: str, verdict: str, status: Status, conf: str, data: dict) -> Observation:
        return Observation(self.name, claim, f"claim {verdict}", status,
                           Provenance.witness_bytes(claim, claim.encode(), conf), data)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []

        # A de Bruijn graph B(2,2) is strongly connected -> a cycle through any node.
        dbg = de_bruijn_graph(("0", "1"), 2)
        good = self.observe(ReachabilityClaim(dbg, "0", expect_cycle=True))[0]
        checks.append(Check(
            "verifies a reachability cycle with a witness",
            good.status == Status.PASS and good.data.get("verdict") == "verified"
            and any(k == "cycle" for k, _ in [tuple(p) for p in good.data.get("evidence", [])]),
            str(good.data.get("evidence", "")),
        ))

        # A DAG path a->b->c has NO cycle through 'a' -> claiming one must REFUTE.
        dag = Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")), directed=True)
        refute = self.observe(ReachabilityClaim(dag, "a", expect_cycle=True))[0]
        checks.append(Check(
            "refutes a false reachability claim (no such cycle)",
            refute.data.get("verdict") == "refuted",
            str(refute.data.get("evidence", "")),
        ))

        # Bottleneck: a 3-node weighted graph; the minimax spanning bottleneck is the
        # cheaper of the two edges needed to connect, with a real cut witness.
        wg = Graph(nodes=("x", "y", "z"),
                   edges=(("x", "y"), ("y", "z"), ("x", "z")),
                   weights=((("x", "y"), 1.0), (("y", "z"), 2.0), (("x", "z"), 5.0)))
        bgood = self.observe(BottleneckClaim(wg, (("x", "y"), ("y", "z")), 2.0))[0]
        checks.append(Check(
            "verifies a bottleneck spanning certificate (cut witness)",
            bgood.data.get("verdict") == "verified"
            and any(k == "cut" for k, _ in [tuple(p) for p in bgood.data.get("evidence", [])]),
            str(bgood.data.get("evidence", "")),
        ))

        # Bottleneck minimality: claiming b=5 when edges<5 already span must REFUTE.
        bbad = self.observe(BottleneckClaim(wg, (("x", "z"), ("y", "z")), 5.0))[0]
        checks.append(Check(
            "refutes a non-minimal bottleneck claim",
            bbad.data.get("verdict") == "refuted",
            str(bbad.data.get("evidence", "")),
        ))

        # Closure on a tree: root r -> a -> b ; r reaches b by composed jumps.
        tree = Graph(nodes=("r", "a", "b"), edges=(("r", "a"), ("a", "b")), directed=True)
        cgood = self.observe(ClosureClaim(tree, "r", "r", "b"))[0]
        checks.append(Check(
            "verifies a composed closure reachability certificate",
            cgood.data.get("verdict") == "verified"
            and any(k == "path" for k, _ in [tuple(p) for p in cgood.data.get("evidence", [])]),
            str(cgood.data.get("evidence", "")),
        ))

        # provenance digest must be full-width on a decided observation.
        checks.append(Check(
            "provenance digest full-width",
            good.provenance.digest.startswith("sha256:")
            and len(good.provenance.digest) == len("sha256:") + 64,
            good.provenance.digest,
        ))

        # over-cap -> UNVERIFIABLE, never a crash or a false verdict.
        tiny = GraphVerifierOrgan(max_nodes=1, max_edges=1)
        capped = tiny.observe(ReachabilityClaim(dbg, "0", expect_cycle=True))[0]
        checks.append(Check(
            "fail-closed over the node/edge cap (UNVERIFIABLE)",
            capped.status == Status.UNVERIFIED
            and capped.data.get("verdict") == "unverifiable",
            capped.data.get("verdict", ""),
        ))

        # foreign subject -> [] (inert).
        checks.append(Check("ignores a foreign subject", self.observe("nope") == [], "[]"))

        return SelftestResult(self.name, checks)
