"""independent.py -- the same predicate, a different algorithm.

The bitset checker in zarankiewicz.py walks COLUMN pairs and popcounts a bitwise
AND. This one builds a map from unordered ROW pairs to a cover count: a K_{2,2}
exists iff some row pair is covered by two columns. Same mathematics, transposed
axis, different data structure, different failure modes. A bug in one is unlikely
to be mirrored in the other, which is the entire reason to write it twice.

`cross_check` runs both and returns UNDECIDED when they disagree, never the
majority side and never a coin flip. Two checkers is not a vote: a disagreement
means we do not know, and the fourth verdict exists to say exactly that. Both
verdicts are recorded in the excerpt so the disagreement can be investigated
rather than merely noted.

Cross-checking an oracle against itself, or against another instance of its own
class, is refused. Two copies of one implementation is not independence, and
accepting it would let a caller manufacture the appearance of a held-out check.

Honest bound: agreement between these two cannot reveal a SPEC-level exploit,
because both read the same grammar. That is what the mutation battery in
tests/test_independent_checker.py probes, and what oracle_qa exists to attack.
"""
from __future__ import annotations

import hashlib

from .base import CertificateOracle, Coverage, OutOfScope, canonical
from .zarankiewicz import SUPPORTED_ST, _well_formed
from ..oracle import OracleResult
from ..verdict import (
    Verdict, Execution, Attribution, UndecidedReason, is_dispositive,
)


class AgreementError(ValueError):
    """A cross-check that would not actually be independent."""


def k22_free_by_row_pairs(m: int, n: int, edges) -> bool:
    """True iff no K_{2,2}. Counts columns covering each unordered row pair.

    For each column, every pair of rows it touches is one cover of that pair. Two
    covers of the same pair is a four-cycle. This never builds a bitmask and
    never popcounts, so it shares no mechanism with the bitset scan.
    """
    rows_of_col: dict[int, list[int]] = {}
    for (r, c) in edges:
        rows_of_col.setdefault(c, []).append(r)

    covered: set[tuple[int, int]] = set()
    for c in sorted(rows_of_col):
        rows = sorted(rows_of_col[c])
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                pair = (rows[i], rows[j])
                if pair in covered:
                    return False
                covered.add(pair)
    return True


class IndependentZarankiewiczOracle(CertificateOracle):
    """The held-out checker. Same contract, different internals."""

    oracle_type = "zarankiewicz_certificate_independent"
    family = "zarankiewicz"
    scope_bounds = {"m_max": 64, "n_max": 64, "edges_max": 4096}

    # The instance fixes the bipartite shape and the forbidden subgraph. Without
    # this, a candidate asked for 64x64 could submit a valid 3x3 certificate and
    # earn PASS, because declared_parameters reads the CERTIFICATE.
    binding_keys = ("m", "n", "s", "t")

    family_not_proven = (
        "NOT_PROVES_OPTIMALITY: this verifies the SUBMITTED object. The optimal "
        "value for the instance is not computed, not bounded, and not claimed "
        "anywhere.",
    )

    def declared_parameters(self, cert: dict) -> dict:
        # s and t are declared because the instance BINDS them. A certificate
        # that does not say which forbidden subgraph it addresses has not
        # answered a question that names one.
        return {"m": int(cert["m"]), "n": int(cert["n"]),
                "s": cert.get("s"), "t": cert.get("t"),
                "edges": len(cert.get("edges", []))}

    def objective_of(self, cert: dict) -> str:
        return str(len(cert.get("edges", [])))

    def check(self, cert: dict) -> tuple[bool, str, Coverage]:
        exact = Coverage(predicate_exact=True, search_space_enumerated=True,
                         enumerated_fraction="1", stop_reason="complete",
                         guarantee_weakens_above=None)
        if (cert.get("s"), cert.get("t")) != SUPPORTED_ST:
            raise OutOfScope(
                f"this checker implements s=t=2, got s={cert.get('s')} "
                f"t={cert.get('t')}")

        ok, why = _well_formed(cert)
        if not ok:
            return False, why, exact

        m, n, edges = cert["m"], cert["n"], [tuple(e) for e in cert["edges"]]
        if not k22_free_by_row_pairs(m, n, edges):
            return False, (f"a row pair is covered twice: K_{{2,2}} present in "
                           f"the {m}x{n} graph"), exact
        return True, (f"no row pair covered twice on {m}x{n} with {len(edges)} "
                      f"edges, exhaustive over all covered pairs"), exact


def cross_check(primary: CertificateOracle, held_out: CertificateOracle,
                candidate: str, task=None) -> OracleResult:
    """Run both checkers. Agree, and the verdict stands. Disagree, and the answer
    is UNDECIDED with both verdicts on the record."""
    if primary is held_out or type(primary) is type(held_out):
        raise AgreementError(
            "a cross-check needs two DIFFERENT implementations; two copies of "
            "one checker is not independence and would manufacture the "
            "appearance of a held-out check")

    a = primary.verify(candidate, task)
    b = held_out.verify(candidate, task)

    if a.verdict() == b.verdict():
        return a

    if not (is_dispositive(a.verdict_) and is_dispositive(b.verdict_)):
        # One side could not decide at all. That gap dominates: we cannot claim a
        # cross-checked result when only one checker actually ran.
        nd = a if not is_dispositive(a.verdict_) else b
        return OracleResult(
            cmd=f"cross_check:{primary.family}",
            output_hash=nd.output_hash, rc=1,
            stdout_excerpt=(f"{primary.oracle_type}={a.verdict()} "
                            f"{held_out.oracle_type}={b.verdict()}; "
                            f"{nd.stdout_excerpt}"),
            verdict_=Verdict.UNVERIFIABLE,
            execution=Execution.COMPLETED,
            attribution=Attribution.ENVIRONMENT,
            unverifiable_reason=nd.unverifiable_reason,
            coverage=nd.coverage,
            does_not_prove=list(nd.does_not_prove) + ["NOT_PROVES_PREDICATE"])

    excerpt = (f"checkers disagree: {primary.oracle_type}={a.verdict()} "
               f"vs {held_out.oracle_type}={b.verdict()}. "
               f"primary said: {a.stdout_excerpt[:280]} "
               f"held-out said: {b.stdout_excerpt[:280]}")
    preimage = canonical({"cert": canonical(candidate), "a": a.verdict(),
                          "b": b.verdict(), "family": primary.family})
    return OracleResult(
        cmd=f"cross_check:{primary.family}",
        output_hash=hashlib.sha256(preimage.encode()).hexdigest()[:16],
        stdout_excerpt=excerpt[:1200], rc=1,
        verdict_=Verdict.UNDECIDED,
        execution=Execution.COMPLETED,
        attribution=Attribution.HARNESS,
        undecided_reason=UndecidedReason.HELD_OUT_DISAGREEMENT.value,
        coverage=a.coverage,
        does_not_prove=list(a.does_not_prove) + ["NOT_PROVES_PREDICATE"])
