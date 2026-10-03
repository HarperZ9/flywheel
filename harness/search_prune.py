"""search_prune.py -- stop a candidate that duplicates earlier ones, opt-in.

At checkpoints of 25, 50 and 75% of a candidate's length, its partial code is
normalized (comments and whitespace dropped, identifiers renamed in order of first
use). A candidate whose normalized prefix matches `m` earlier live candidates at
any checkpoint is pruned: it skips the oracle. At most `cap` candidates are
pruned per task, and a pruned candidate never removes the last live member of
its niche, because pruning needs `m` live members already there.

Off by default. The saving was estimated offline (0.772x tokens at m = 2 on one
model and one task family), not measured live. With a proposer that returns
whole completions, pruning saves oracle runs only; the tokens are already spent
and are recorded as `pruned_tokens` so the cost stays visible.
"""
from __future__ import annotations

import io
import keyword
import tokenize
from collections import Counter

CHECKPOINTS = (0.25, 0.5, 0.75)
DEFAULT_CAP = 3


def normalize(code: str) -> str:
    """Comments and whitespace dropped, names renamed in order of first use."""
    names: dict = {}
    out = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        toks = None
    if toks is None:
        return " ".join(code.split())
    for tok in toks:
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        text = tok.string
        if tok.type == tokenize.NAME and not keyword.iskeyword(text):
            text = names.setdefault(text, f"v{len(names)}")
        out.append(text)
    return " ".join(out)


def niche_keys(text: str) -> tuple:
    """The normalized prefix at each checkpoint of the candidate's own length."""
    return tuple(normalize(text[:max(1, int(len(text) * f))]) for f in CHECKPOINTS)


class DuplicatePruner:
    def __init__(self, m: int, cap: int = DEFAULT_CAP):
        if m < 1:
            raise ValueError("prune_m must be at least 1")
        self.m, self.cap = m, cap
        self.pruned = 0
        self._seen = [Counter() for _ in CHECKPOINTS]

    def check(self, text: str) -> bool:
        """True when this candidate should be pruned. Live candidates are counted."""
        keys = niche_keys(text)
        hit = any(self._seen[i][k] >= self.m for i, k in enumerate(keys))
        if hit and self.pruned < self.cap:
            self.pruned += 1
            return True
        for i, k in enumerate(keys):
            self._seen[i][k] += 1
        return False
