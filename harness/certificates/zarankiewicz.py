"""zarankiewicz.py -- exact K_{2,2}-free witness checking by bitset scan.

z(m, n; s, t) is the maximum number of edges in an m by n bipartite graph with no
complete bipartite K_{s,t} subgraph. A candidate submits a witness graph and
claims an edge count; this checks both exactly.

For s = t = 2 the predicate is "no two columns share two rows", equivalently "no
four-cycle". The scan represents each column as an integer bitmask over rows and
tests every column pair with a popcount of the AND. That is O(n^2) machine words
for n columns, which at the scope bounds here is milliseconds of integer work
with no floating point anywhere.

Order of checks matters. The declared count is validated BEFORE the predicate,
because overclaiming edges is the obvious way to game a maximization objective
and it should be named as that rather than reported as a graph property.

Nothing in this module executes candidate input. It reads integers.
"""
from __future__ import annotations

import json

from .base import CertificateOracle, Coverage, OutOfScope

SUPPORTED_ST = (2, 2)


class GeneratorError(ValueError):
    """An instance request outside the declared generator space."""


def edge_count(edges) -> int:
    return len(edges)


def encode(m: int, n: int, edges, s: int = 2, t: int = 2) -> str:
    """The wire form of a witness certificate."""
    return json.dumps({"m": m, "n": n, "s": s, "t": t,
                       "edges": [list(e) for e in edges],
                       "edge_count": len(edges)})


def k22_free(m: int, n: int, edges) -> bool:
    """True iff the bipartite graph on m rows and n columns has no K_{2,2}.

    Columns become row-bitmasks. Two columns sharing two or more rows are exactly
    a four-cycle, so the test is popcount(col_i AND col_j) < 2 for every pair.
    """
    cols = [0] * n
    for (r, c) in edges:
        cols[c] |= 1 << r
    for i in range(n):
        ci = cols[i]
        if ci == 0:
            continue
        for j in range(i + 1, n):
            shared = ci & cols[j]
            # bit_count is exact integer work; two shared rows close the cycle.
            if shared.bit_count() >= 2:
                return False
    return True


def _strict_int(v) -> bool:
    """An honest integer, and not a bool wearing one.

    In Python bool subclasses int, so isinstance(True, int) is True and a naive
    check reads `true` as row 1. That is a spec-level smuggling channel: it widens
    the accepted grammar beyond what the certificate format declares, and both
    independent checkers would share the hole because both read the same grammar.
    Found by the mutation battery, which is what that battery is for.
    """
    return isinstance(v, int) and not isinstance(v, bool)


def _well_formed(cert: dict) -> tuple[bool, str]:
    """Structural validation. Returns (ok, why_not)."""
    for key in ("m", "n", "s", "t", "edges", "edge_count"):
        if key not in cert:
            return False, f"missing field {key!r}"
    m, n = cert["m"], cert["n"]
    if not all(_strict_int(v) for v in (m, n, cert["edge_count"])):
        return False, ("m, n and edge_count must be integers "
                       "(a bool is not an integer here)")
    if m <= 0 or n <= 0:
        return False, "m and n must be positive"
    edges = cert["edges"]
    if not isinstance(edges, list):
        return False, "edges must be a list"
    seen = set()
    for e in edges:
        if not (isinstance(e, list) and len(e) == 2
                and all(_strict_int(x) for x in e)):
            return False, (f"malformed edge {e!r}: expected [row, col] integers "
                           "(a bool is not an integer here)")
        r, c = e
        if not (0 <= r < m and 0 <= c < n):
            return False, f"edge {e!r} out of range for {m}x{n}"
        if (r, c) in seen:
            return False, f"duplicate edge {e!r}"
        seen.add((r, c))
    if cert["edge_count"] != len(edges):
        return False, (f"declared edge_count {cert['edge_count']} does not match "
                       f"the {len(edges)} edges exhibited")
    return True, ""


class ZarankiewiczOracle(CertificateOracle):
    """Exact K_{2,2}-free witness checker. Data only; executes nothing."""

    oracle_type = "zarankiewicz_certificate"
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
            # Outside what this checker disposes. Raising here would read as a
            # candidate error, so signal it as a scope miss instead.
            raise OutOfScope(
                f"this checker implements s=t=2, got s={cert.get('s')} "
                f"t={cert.get('t')}")

        ok, why = _well_formed(cert)
        if not ok:
            return False, why, exact

        m, n, edges = cert["m"], cert["n"], [tuple(e) for e in cert["edges"]]
        if not k22_free(m, n, edges):
            return False, (f"witness contains a K_{{2,2}}: two columns share two "
                           f"rows in the {m}x{n} graph"), exact
        return True, (f"K_{{2,2}}-free on {m}x{n} with {len(edges)} edges, "
                      f"exhaustive over all {n * (n - 1) // 2} column pairs"), exact
