"""cross_domain.py — one asymmetry, across fields we would never file together.

Every domain here has the same three parts: a surface representation, an INVARIANT
(the criterion) that a faithful transform must conserve, and the asymmetry that a
weak/self-authored surface check accepts a cheat the criterion-check rejects. It is
the operator's transpile-conservation principle (a lossy transform conserves the
CRITERION, not the bits) shown to recur in seven unconnected fields:

  finance (double-entry net), music (pitch-class set), color science (luminance),
  formal grammar (bracket balance), geometry (orientation sign), dimensional
  physics (unit signature), and algorithms (sort = multiset conservation).

HONEST framing, stated up front because the adversary already made the point and it
stands: this recurrence is EXPECTED, not a discovered law. ANY domain with a
computable invariant admits this structure; finding it in seven is finding it in
fifty. The value is REACH (one reusable lens, many substrates) and a demonstration
that the externalization discipline transports, not evidence of a hidden unity. Do
not read the shared shape as corroboration of anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Domain:
    name: str
    field: str                  # the field it comes from (deliberately unconnected)
    criterion: Callable         # x -> hashable invariant (the thing conserved)
    faithful: Callable          # x -> x'  (a lossy transform that CONSERVES the criterion)
    cheat: Callable             # x -> x'  (a transform that BREAKS the criterion)
    surface: Callable           # (x, x') -> bool  (a weak/self-authored check the cheat passes)
    sample: object


def _signed_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s


def _balanced(s: str) -> tuple[bool, int]:
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return (False, depth)
    return (depth == 0, depth)


def _lum(pixels) -> int:
    # mean perceptual luminance (Rec.601), rounded — the conserved criterion
    return round(sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels))


DOMAINS = [
    Domain("double_entry", "finance",
           criterion=lambda e: sum(e),
           faithful=lambda e: list(reversed(e)),            # reorder: net unchanged
           cheat=lambda e: e[:-1],                          # drop a line: net changes
           surface=lambda x, y: x[0] == y[0],               # "first entry matches"
           sample=[100, -40, -60]),
    Domain("pitch_class", "music",
           criterion=lambda ns: frozenset(n % 12 for n in ns),
           faithful=lambda ns: [n + 12 for n in ns],        # octave up: pc-set unchanged
           cheat=lambda ns: [ns[0], ns[1] + 1, ns[2]],       # shift a note: pc-set changes
           surface=lambda x, y: x[0] == y[0],               # "root note matches"
           sample=[0, 4, 7]),                                # C major triad
    Domain("luminance", "color-science",
           criterion=_lum,
           faithful=lambda px: list(reversed(px)),          # reorder: loses position, mean lum EXACT
           cheat=lambda px: [(r + 25, g + 25, b + 25) for r, g, b in px],  # brighten: lum changes
           surface=lambda x, y: len(x) == len(y),           # "same pixel count"
           sample=[(100, 100, 100), (120, 120, 120), (80, 80, 80)]),
    Domain("bracket_balance", "formal-grammar",
           criterion=_balanced,
           faithful=lambda s: s.replace("(", "( ").replace(")", " )"),  # whitespace: balance same
           cheat=lambda s: s[:-1],                          # drop close: unbalanced
           surface=lambda x, y: y.startswith("("),          # "starts with ("
           sample="(a(b)c)"),
    Domain("orientation", "geometry",
           criterion=lambda p: 1 if _signed_area(p) > 0 else -1,
           faithful=lambda p: [(x + 10, y + 10) for x, y in p],  # translate: orientation same
           cheat=lambda p: list(reversed(p)),               # reverse winding: orientation flips
           surface=lambda x, y: set(x) == set(y),           # "same vertex set"
           sample=[(0, 0), (4, 0), (4, 3)]),
    Domain("dimensions", "dimensional-physics",
           criterion=lambda q: q[1],                        # (value, (L,M,T)) -> dim signature
           faithful=lambda q: (q[0] * 3.6, q[1]),           # m/s -> km/h: dims unchanged
           cheat=lambda q: (q[0] + 2.0, (0, 0, 1)),          # add a time to a velocity: dims change
           surface=lambda x, y: y[0] > 0,                   # "value is positive"
           sample=(5.0, (1, 0, -1))),                        # a velocity
    Domain("multiset", "algorithms",
           criterion=lambda xs: tuple(sorted(xs)),
           faithful=lambda xs: sorted(xs),                  # a correct sort: multiset conserved
           cheat=lambda xs: sorted(set(xs)),                # dedupe-sort: drops an element
           surface=lambda x, y: all(a <= b for a, b in zip(y, y[1:])),  # "output is non-decreasing"
           sample=[3, 1, 2, 1]),
]


def run_domain(d: Domain) -> dict:
    x = d.sample
    faithful, cheat = d.faithful(x), d.cheat(x)
    cx = d.criterion(x)
    return {
        "name": d.name, "field": d.field,
        "faithful_conserves": d.criterion(faithful) == cx,
        "cheat_breaks": d.criterion(cheat) != cx,
        # the asymmetry: the weak surface check says fine, the criterion says broken
        "surface_misses_cheat": d.surface(x, cheat) and d.criterion(cheat) != cx,
    }


def run_all() -> dict:
    per = [run_domain(d) for d in DOMAINS]
    ok = sum(1 for p in per
             if p["faithful_conserves"] and p["cheat_breaks"] and p["surface_misses_cheat"])
    return {"n_domains": len(DOMAINS), "fields": sorted({p["field"] for p in per}),
            "asymmetry_holds": ok, "coverage": round(ok / len(DOMAINS), 3),
            "per_domain": per,
            "honest_note": "recurrence is expected for any domain with a computable "
                           "invariant; this is reach, not a discovered law"}
