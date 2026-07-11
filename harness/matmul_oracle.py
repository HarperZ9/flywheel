"""matmul_oracle.py -- exact symbolic verification of a bilinear matmul scheme.

The AlphaTensor / AlphaEvolve / Dumas-Pernet-Sedoglavic line is this project's
thesis in the wild: a SEARCH proposes a rank-R bilinear decomposition of the
matrix-multiplication tensor; an EXACT symbolic identity DISPOSES (do the R
rank-1 triples reconstruct the matmul tensor over the target ring?); the accept
authority is the tensor identity, never the learned proposer -- C2-clean by
construction. This gives the harness its first hard-symbolic, ring-parameterized
verification domain with an unambiguous public ground-truth ladder (Strassen-7,
Laderman-23), a class the pytest / exec / kernel oracles do not cover.

A "scheme" is JSON:
  {"n":2,"m":2,"p":2,
   "triples":[{"u":[..n*m..], "v":[..m*p..], "w":[..n*p..]}, ...]}
with rational coefficients. Flat index conventions:
  a-index (i,k) = i*m + k   over A (n x m)
  b-index (k,j) = k*p + j   over B (m x p)
  c-index (i,j) = i*p + j   over C (n x p)
Verify: reconstruct T_hat[a,b,c] = sum_r u_r[a] * v_r[b] * w_r[c] and check it
EXACTLY equals the matmul tensor T (T[a,b,c] = 1 iff a=(i,k), b=(k,j), c=(i,j)
share the same i,k,j). Exactness is over `Fraction`, so there is never a false
accept from numerical slop -- the value a random-matrix probe cannot promise.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from .oracle import OracleResult


def matmul_tensor(n: int, m: int, p: int) -> dict:
    """The exact n x m x p matrix-multiplication tensor as {(a,b,c): 1}."""
    T: dict[tuple[int, int, int], int] = {}
    for i in range(n):
        for k in range(m):
            for j in range(p):
                T[(i * m + k, k * p + j, i * p + j)] = 1
    return T


def _reconstruct(triples: list[dict], na: int, nb: int, nc: int) -> dict:
    """T_hat[a,b,c] = sum_r u_r[a] v_r[b] w_r[c], sparse over nonzero entries."""
    That: dict[tuple[int, int, int], Fraction] = {}
    for t in triples:
        u = [Fraction(x) for x in t["u"]]
        v = [Fraction(x) for x in t["v"]]
        w = [Fraction(x) for x in t["w"]]
        if len(u) != na or len(v) != nb or len(w) != nc:
            raise ValueError("triple has wrong coefficient-vector length")
        ua = [(a, ua_) for a, ua_ in enumerate(u) if ua_ != 0]
        vb = [(b, vb_) for b, vb_ in enumerate(v) if vb_ != 0]
        wc = [(c, wc_) for c, wc_ in enumerate(w) if wc_ != 0]
        for a, ua_ in ua:
            for b, vb_ in vb:
                uv = ua_ * vb_
                for c, wc_ in wc:
                    key = (a, b, c)
                    That[key] = That.get(key, Fraction(0)) + uv * wc_
    return {k: val for k, val in That.items() if val != 0}


def verify_scheme(scheme: dict) -> tuple[bool, str]:
    """Return (is_exact_matmul, reason). Pure symbolic identity check."""
    try:
        n, m, p = int(scheme["n"]), int(scheme["m"]), int(scheme["p"])
        triples = scheme["triples"]
        if not isinstance(triples, list) or not triples:
            return False, "no triples"
        na, nb, nc = n * m, m * p, n * p
        That = _reconstruct(triples, na, nb, nc)
    except (KeyError, ValueError, TypeError) as e:
        return False, f"malformed scheme: {e}"
    T = {k: Fraction(v) for k, v in matmul_tensor(n, m, p).items()}
    if That == T:
        return True, f"exact matmul tensor reproduced with rank {len(triples)}"
    missing = [k for k in T if k not in That]
    extra = [k for k in That if k not in T]
    wrong = [k for k in T if k in That and That[k] != T[k]]
    return False, (f"tensor mismatch: {len(missing)} missing, {len(extra)} extra, "
                   f"{len(wrong)} wrong-valued entries (rank {len(triples)})")


class MatMulSchemeOracle:
    """Verifies that a bilinear scheme (JSON string) computes n x m x p matmul
    EXACTLY over the rationals. No learned model; the tensor identity decides."""
    oracle_type = "matmul_bilinear"

    def verify(self, candidate: str, task=None) -> OracleResult:
        try:
            scheme = json.loads(candidate)
        except Exception as e:
            return OracleResult(passed=False, cmd="matmul_identity",
                                output_hash="parse_fail",
                                stdout_excerpt=f"json parse failed: {e}", rc=1)
        ok, reason = verify_scheme(scheme)
        h = hashlib.sha256(json.dumps(scheme, sort_keys=True, default=str)
                           .encode()).hexdigest()[:16]
        return OracleResult(passed=ok, cmd="matmul_identity",
                            output_hash=h if ok else f"mismatch_{h}",
                            stdout_excerpt=reason, rc=0 if ok else 1)


# --- ground-truth ladder + perturbations for calibration ---------------------

def naive_scheme(n: int, m: int, p: int) -> dict:
    """The trivial rank-(n*m*p) scheme: one multiply per (i,k,j). Always exact."""
    triples = []
    for i in range(n):
        for k in range(m):
            for j in range(p):
                u = [Fraction(0)] * (n * m); u[i * m + k] = Fraction(1)
                v = [Fraction(0)] * (m * p); v[k * p + j] = Fraction(1)
                w = [Fraction(0)] * (n * p); w[i * p + j] = Fraction(1)
                triples.append({"u": [str(x) for x in u],
                                "v": [str(x) for x in v],
                                "w": [str(x) for x in w]})
    return {"n": n, "m": m, "p": p, "triples": triples}


def strassen_scheme() -> dict:
    """Strassen's rank-7 scheme for 2x2x2 (known-good; the R<n^3 landmark)."""
    tr = [
        {"u": [1, 0, 0, 1], "v": [1, 0, 0, 1], "w": [1, 0, 0, 1]},   # M1
        {"u": [0, 0, 1, 1], "v": [1, 0, 0, 0], "w": [0, 0, 1, -1]},  # M2
        {"u": [1, 0, 0, 0], "v": [0, 1, 0, -1], "w": [0, 1, 0, 1]},  # M3
        {"u": [0, 0, 0, 1], "v": [-1, 0, 1, 0], "w": [1, 0, 1, 0]},  # M4
        {"u": [1, 1, 0, 0], "v": [0, 0, 0, 1], "w": [-1, 1, 0, 0]},  # M5
        {"u": [-1, 0, 1, 0], "v": [1, 1, 0, 0], "w": [0, 0, 0, 1]},  # M6
        {"u": [0, 1, 0, -1], "v": [0, 0, 1, 1], "w": [1, 0, 0, 0]},  # M7
    ]
    return {"n": 2, "m": 2, "p": 2, "triples": tr}


def perturb_scheme(scheme: dict, triple: int = 0, field: str = "w", pos: int = 0) -> dict:
    """Flip one coefficient -> a known-BAD scheme (breaks the tensor identity)."""
    import copy
    s = copy.deepcopy(scheme)
    vec = s["triples"][triple][field]
    vec[pos] = str(Fraction(vec[pos]) + 1)   # +1 breaks the exact identity
    return s


def drop_triple(scheme: dict, triple: int = 0) -> dict:
    """Remove one rank-1 term -> a known-BAD lower-rank scheme."""
    import copy
    s = copy.deepcopy(scheme)
    del s["triples"][triple]
    return s


def dumps(scheme: dict) -> str:
    return json.dumps(scheme, default=str)
