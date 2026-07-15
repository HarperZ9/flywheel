"""benchmark_hygiene.py -- the defect gate for formal statement sets.

Five published Lean benchmarks were found carrying 398 certified
defective statements (lean-invention dossier, 2026-07-14): holes
admitted with `sorry` wearing theorem names, and acceptance smuggled
through nonstandard axioms. This gate screens a statement list for the
two mechanical defect classes before anything enters a lane here.
It is deliberately narrow: a statement it passes is not certified
correct (the kernel does that); a statement it flags is certified
suspect, with its reason named. Comments are stripped before matching
so a mention of sorry is not a hole, and an identifier containing the
word is not one either.
"""
from __future__ import annotations

import re

SCHEMA = "flywheel.benchmark-hygiene/v1"

_COMMENT_LINE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK = re.compile(r"/-.*?-/", re.S)

# defect class -> pattern. Beyond admitted holes (sorry/axiom), several Lean 4
# constructs move the decision OUTSIDE the re-checked kernel term yet still
# exit 0 with no error: the `admit` tactic (an unnamed hole), `sorryAx`, and
# the kernel-bypass escape hatches (native_decide trusts compiled code,
# debug.skipKernelTC disables re-typechecking, @[implemented_by] swaps the
# implementation). A proof of False via any of these must be refused BEFORE
# the exit code is trusted, or the oracle accepts a non-kernel-decided claim.
_DEFECTS = (
    ("sorry", re.compile(r"(?<![A-Za-z0-9_])sorry(?![A-Za-z0-9_])")),
    ("sorryAx", re.compile(r"(?<![A-Za-z0-9_])sorryAx(?![A-Za-z0-9_])")),
    ("admit", re.compile(r"(?<![A-Za-z0-9_])admit(?![A-Za-z0-9_])")),
    ("axiom", re.compile(r"(?<![A-Za-z0-9_])axiom(?![A-Za-z0-9_])")),
    ("native_decide",
     re.compile(r"(?<![A-Za-z0-9_])native_decide(?![A-Za-z0-9_])")),
    ("skip_kernel_tc",
     re.compile(r"debug\.skipKernelTC")),
    ("implemented_by",
     re.compile(r"implemented_by")),
)


def _strip_comments(code: str) -> str:
    return _COMMENT_LINE.sub("", _COMMENT_BLOCK.sub("", code or ""))


def screen_statements(statements: list) -> dict:
    """Screen a list of Lean statements for constructs that let a proof be
    accepted without the kernel actually deciding it. Every flag names its
    statement index, defect class, and a trimmed excerpt."""
    flagged = []
    for i, stmt in enumerate(statements):
        body = _strip_comments(str(stmt))
        defect = None
        for name, pat in _DEFECTS:
            if pat.search(body):
                defect = name
                break
        if defect:
            flagged.append({"index": i, "defect": defect,
                            "statement": str(stmt)[:200]})
    return {"schema": SCHEMA, "total": len(statements),
            "clean": len(statements) - len(flagged), "flagged": flagged,
            "note": "passing this gate certifies nothing correct (the "
                    "kernel does that); a flag certifies a statement "
                    "suspect, with its defect named"}
