"""conjecture_forge.py -- generation under witness: propose, judge, keep.

The invention loop's depth question: can the loop produce a conjecture
nobody seeded? This is the mechanized, honest version of the answer: a
deterministic enumeration over a linear Nat-arithmetic grammar PROPOSES
universally quantified equations; the Lean kernel (or an injected judge)
is the sole acceptance authority; novelty is CORPUS-RELATIVE, measured
by normalized-statement hash against everything the store already holds,
so the forge never re-proposes the corpus. A refused conjecture is a
count, never a stored fact. A DECLARED kernel (no toolchain) yields no
claims at all. Novelty here means "absent from the corpus", nothing
grander -- the receipt says so.
"""
from __future__ import annotations

import hashlib
import re

SCHEMA = "flywheel.conjecture-forge/v1"

# The proposal grammar: linear Nat arithmetic with truncated subtraction
# and min/max, chosen so `omega` is a decision procedure for every true
# statement -- a refusal is then evidence against the conjecture, not a
# tactic gap. False pairs (n + m = n) are generated and must be refused.
_EXPRS = [
    "n", "m", "0", "1", "2",
    "n + m", "m + n", "n + n", "m + m",
    "n + 0", "0 + n", "m + 1", "1 + m",
    "n * 2", "2 * n", "m * 1", "1 * m", "n * 0",
    "n + m + n", "n + n + m", "m + n + m",
    "(n + m) * 2", "n * 2 + m * 2",
    "n - n", "m - m", "n + m - m", "m + n - n",
    "min n m + max n m", "max n m + min n m", "min n n", "max m m",
]

_TACTIC = "omega"


def _statement(lhs: str, rhs: str) -> str:
    name = hashlib.sha256(f"{lhs}={rhs}".encode()).hexdigest()[:8]
    return (f"theorem cj_{name} (n m : Nat) : {lhs} = {rhs} "
            f":= by {_TACTIC}")


def _all_statements() -> list:
    out = []
    for i in range(len(_EXPRS)):
        for j in range(i + 1, len(_EXPRS)):
            out.append(_statement(_EXPRS[i], _EXPRS[j]))
    return out


def enumerate_conjectures(k: int, *, offset: int = 0) -> list:
    """The first `k` proposals after `offset`, in a fixed order: the same
    call always names the same conjectures (receipts need determinism)."""
    return _all_statements()[offset:offset + k]


def normalize_statement(stmt: str) -> str:
    """Alpha- and name-invariant canonical form: the theorem name is
    dropped and bound variables are renamed v0, v1, ... in order of first
    appearance in the body, so `n + m = m + n` and `x + y = y + x` hash
    identically while `n + m = m + m` stays distinct."""
    m = re.match(r"theorem\s+\S+\s*\(([^:)]+):[^)]*\)\s*:\s*(.+?)\s*:=",
                 stmt)
    if not m:
        body = re.sub(r"^theorem\s+\S+\s*:?", "", stmt).strip()
        return re.sub(r"\s+", " ", body)
    binders = m.group(1).split()
    body = m.group(2)
    order = []
    for tok in re.findall(r"[A-Za-z_]\w*", body):
        if tok in binders and tok not in order:
            order.append(tok)
    for idx, var in enumerate(order):
        body = re.sub(rf"\b{re.escape(var)}\b", f"v{idx}", body)
    return re.sub(r"\s+", " ", body).strip()


def _statement_sha(stmt: str) -> str:
    return hashlib.sha256(normalize_statement(stmt).encode()).hexdigest()


def _corpus_hashes() -> set:
    from .store import get_entity, query_entities
    hashes = set()
    for meta in query_entities(kind="theorem", limit=1000):
        e = get_entity(meta["eid"])
        if e:
            hashes.add(_statement_sha(e["data"].get("statement", "")))
    return hashes


def forge_round(k: int = 20, *, kernel=None, offset: int = 0) -> dict:
    """One turn of generation under witness: propose up to `k` conjectures
    the corpus does not hold, let the kernel judge every one, chain the
    survivors into the store. Returns the round's receipt."""
    from .store import put_entity
    if kernel is None:
        from .lean_oracle import lean_check
        kernel = lean_check
    corpus = _corpus_hashes()
    proposals = []
    for stmt in _all_statements()[offset:]:
        if len(proposals) >= k:
            break
        if _statement_sha(stmt) in corpus:
            continue
        proposals.append(stmt)
    accepted, refused, declared = [], 0, 0
    for stmt in proposals:
        v = kernel(stmt)
        if v.get("passed") is True:
            sha = _statement_sha(stmt)
            put_entity("theorem",
                       {"statement": stmt, "statement_sha256": sha,
                        "verdict": "kernel-accepted", "tactic": _TACTIC,
                        "novelty": "corpus-relative",
                        "kernel_output": str(v.get("kernel_output",
                                                   ""))[:500]},
                       eid=sha[:24])
            accepted.append({"statement": stmt, "statement_sha256": sha,
                             "verdict": {"passed": True,
                                         "toolchain": v.get("toolchain",
                                                            "")}})
        elif v.get("passed") is False:
            refused += 1
        else:
            declared += 1
    return {"schema": SCHEMA, "proposed": len(proposals),
            "accepted": accepted, "refused": refused, "declared": declared,
            "corpus_size": len(corpus),
            "note": "acceptance decided solely by the kernel; novelty is "
                    "corpus-relative (absent from the store), nothing "
                    "grander; a declared kernel yields no claims"}
