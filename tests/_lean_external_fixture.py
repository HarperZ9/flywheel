"""A hermetic stand-in for lean4export and nanoda in injected-runner tests.

`answer(argv, ...)` returns what the injected runner should reply to an
external-kernel step, or None when argv is not one. The export is a minimal
valid lean4export 3.1.0 file: `True` as an inductive and the pinned theorem
stating it.
"""
import json

ACCEPT = (0, "theorem t : True := _\n\nChecked 2 declarations with no errors")


def export(theorem: str, githash: str, *, kind: str = "thm",
           prop: str = "True") -> str:
    rows = [
        {"meta": {"exporter": {"name": "lean4export", "version": "3.1.0"},
                  "format": {"version": "3.1.0"},
                  "lean": {"githash": githash, "version": "4.34.1"}}},
        {"in": 1, "str": {"pre": 0, "str": prop}},
        {"in": 2, "str": {"pre": 0, "str": theorem}},
        {"ie": 0, "sort": 0},
        {"ie": 1, "const": {"name": 1, "us": []}},
        {"inductive": {"types": [{
            "name": 1, "levelParams": [], "type": 0, "numParams": 0,
            "numIndices": 0, "all": [1], "ctors": [], "numNested": 0,
            "isRec": False, "isUnsafe": False, "isReflexive": False}],
            "ctors": [], "recs": []}},
        {kind: {"name": 2, "levelParams": [], "type": 1, "value": 1,
                "all": [2]}},
    ]
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def answer(argv, *, githash: str, nanoda=ACCEPT, candidate=None,
           missing: bool = False):
    """The reply to an external-kernel step, or None for any other argv.
    `missing` raises OSError for nanoda, the way a missing binary does."""
    if not argv or argv[0] not in ("lean4export", "nanoda_bin"):
        return None
    if argv[0] == "nanoda_bin":
        if missing:
            raise OSError("nanoda_bin not found")
        return (0, "nanoda_bin 0.4.19") if argv[1] == "--help" else nanoda
    theorem = argv[-1]
    if argv[1] == "Candidate" and candidate is not None:
        return candidate
    return 0, export(theorem, githash)
