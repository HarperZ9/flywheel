from __future__ import annotations

def merge_tallies(a: dict, b: dict) -> dict:
    out = {}
    for d in (a, b):
        for k, v in d.items():
            if not isinstance(v, int) or isinstance(v, bool):  # `bool` is a subclass of `int`; reject it
                raise ValueError(f"non-integer count: {v!r}")
            prev = out.get(k, 0)
            out[k] = prev + v
    for k in list(out):
        if out[k] == 0:
            del out[k]
    surviving_a = {k: out[k] for k in a if k in out}
    only_b = {k: out[k] for k in b if k not in a and k in out}
    return dict(surviving_a, **only_b)  # preserves `a`'s iteration order then appends the disjoint keys from `b`
