"""Label and relation checks: dependencies, centroids, twins, declared identities, runs."""
from __future__ import annotations

import collections
import math
import statistics as st

from .clean_core import Flag, _column, _numcols, col_stats
from .schema import Table, is_missing, num


def check_label_fd(t: Table, hold=0.90) -> list:
    """A label that almost always determines another column: the rare exceptions are flagged. El to Z is the plain case."""
    out, labs = [], t.idx("label")
    others = [i for i, c in enumerate(t.columns) if c.kind in ("label", "num") and t.columns[i].plaus != "skip"]
    for a in labs:
        for b in others:
            if a == b:
                continue
            maps = collections.defaultdict(collections.Counter)
            for row in t.rows:
                if a < len(row) and b < len(row) and not is_missing(row[a]) and not is_missing(row[b]):
                    maps[row[a]][row[b]] += 1
            total = sum(sum(c.values()) for c in maps.values())
            if not total or len(maps) < 2 or total < 2 * len(maps):
                continue
            agree = sum(c.most_common(1)[0][1] for c in maps.values())
            if agree / total < hold or agree == total:
                continue
            for r, row in enumerate(t.rows):
                if a < len(row) and b < len(row) and row[a] in maps and not is_missing(row[b]) and row[b] != maps[row[a]].most_common(1)[0][0]:
                    out.append(Flag("label_fd", r, a, f"{t.columns[a].name} {row[a]} usually has {t.columns[b].name} {maps[row[a]].most_common(1)[0][0]}"))
    return out


def check_label_centroid(t: Table, ratio=0.7, min_n=5) -> list:
    """Content sits nearer another label's profile than its own. It assumes most rows under a label are right."""
    if not t.group:
        return []
    g = [c.name for c in t.columns].index(t.group)
    nums = _numcols(t)
    stats = {i: col_stats(_column(t, i)) for i in nums}
    members = collections.defaultdict(list)
    for r, row in enumerate(t.rows):
        if g < len(row) and not is_missing(row[g]):
            members[row[g]].append(r)
    cent = {}
    for lab, rs in members.items():
        if len(rs) >= min_n:
            cent[lab] = {i: st.median([x for x in (num(t.rows[r][i]) if i < len(t.rows[r]) else None for r in rs) if x is not None] or [stats[i][0]]) for i in nums}
    if len(cent) < 2:
        return []
    out = []
    for r, row in enumerate(t.rows):
        lab = row[g] if g < len(row) else None
        if lab not in cent:
            continue
        def dist(c):
            d = [((num(row[i]) - c[i]) / stats[i][1]) ** 2 for i in nums if i < len(row) and num(row[i]) is not None]
            return math.sqrt(sum(d) / len(d)) if d else 0.0
        own = dist(cent[lab])
        best = min((dist(c), l) for l, c in cent.items() if l != lab)
        if best[0] < ratio * own and own > 0.5:
            out.append(Flag("label_centroid", r, g, f"nearer {best[1]} ({best[0]:.2f}) than {lab} ({own:.2f})"))
    return out


def check_label_twin(t: Table) -> list:
    """Same numeric content under different labels. This is the PRJNA693350 finding reduced to its shape."""
    nums, labs = _numcols(t), t.idx("label")
    if len(nums) < 2 or not labs:
        return []
    seen, out = {}, []
    for r, row in enumerate(t.rows):
        k = tuple(row[i].strip() if i < len(row) else "" for i in nums)
        if sum(num(c) is not None for c in k) < 2:
            continue
        lab = tuple(row[i] if i < len(row) else "" for i in labs)
        if k in seen and seen[k][1] != lab:
            out.append(Flag("label_twin", r, None, f"content equals row {seen[k][0]}, label differs"))
        seen.setdefault(k, (r, lab))
    return out


def check_identity(t: Table) -> list:
    """Declared relations between columns, such as A = N + Z. A relation is knowledge the table does not carry, so it must be declared."""
    out, names = [], {c.name: i for i, c in enumerate(t.columns)}
    for label, fn, tol in getattr(t, "identities", []) or []:
        for r, row in enumerate(t.rows):
            def get(name, row=row):
                v = num(row[names[name]]) if names[name] < len(row) else None
                if v is None:
                    raise KeyError(name)
                return v
            try:
                gap = fn(get)
            except KeyError:
                continue
            if abs(gap) > tol:
                out.append(Flag("identity", r, None, f"{label} off by {gap:.3g}"))
    return out


def check_runs(t: Table, length=5) -> list:
    """Blocks: a stuck value, or a run of rows printed with fewer decimals than the column's usual. One row looks fine; the run does not."""
    out = []
    for i in _numcols(t):
        cells = [row[i].strip() if i < len(row) else "" for row in t.rows]
        decs = [len(c.split(".")[1]) if "." in c else 0 for c in cells]
        usual = collections.Counter(decs).most_common(1)[0][0] if decs else 0
        start = 0
        for r in range(1, len(cells) + 1):
            if r == len(cells) or cells[r] != cells[start]:
                if r - start >= length and num(cells[start]) is not None and "." in cells[start] and len(set(cells)) > 20:
                    out += [Flag("runs", k, i, f"stuck at {cells[start]} for {r - start} rows") for k in range(start, r)]
                start = r
        begin = None
        for r in range(len(cells) + 1):
            low = r < len(cells) and decs[r] < usual and num(cells[r]) is not None
            if low and begin is None:
                begin = r
            elif not low and begin is not None:
                if r - begin >= length and usual >= 2 and decs.count(usual) >= 0.9 * len(decs):
                    out += [Flag("runs", k, i, f"{r - begin} rows print fewer decimals than the usual {usual}") for k in range(begin, r)]
                begin = None
    return out
