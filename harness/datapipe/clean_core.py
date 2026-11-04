"""Stage 5, clean: table checks. Each check returns flags and deletes nothing.

Flag means a reader should look. No flag means no check here fired, and it never means the value is true.
"""
from __future__ import annotations

import collections
import math
import statistics as st

from .schema import Table, is_missing, num

Flag = collections.namedtuple("Flag", "check row col detail")
FENCE = 5.0
FACTORS = {"1e3": 1e3, "1e-3": 1e-3, "100": 100.0, "0.01": 0.01, "10": 10.0, "0.1": 0.1, "1e6": 1e6, "1e-6": 1e-6, "2.54": 2.54, "1/2.54": 1 / 2.54,
           "25.4": 25.4, "1/25.4": 1 / 25.4, "0.3048": 0.3048, "1/0.3048": 1 / 0.3048, "2.2046": 2.2046, "1/2.2046": 1 / 2.2046, "1.8": 1.8, "1/1.8": 1 / 1.8}
OFFSETS = (273.15, -273.15)


def col_stats(values) -> tuple:
    """Median and a robust scale. MAD first, then the spread, then 1, so a constant column stays usable."""
    v = [x for x in values if x is not None]
    if not v:
        return 0.0, 1.0
    med = st.median(v)
    mad = st.median(abs(x - med) for x in v) * 1.4826
    if mad <= 0:
        mad = st.pstdev(v) if len(v) > 1 else 0.0
    return med, mad if mad > 0 else (abs(med) * 0.01 or 1.0)


def _numcols(t: Table) -> list:
    return t.idx("num")


def _column(t: Table, i: int) -> list:
    return [num(r[i]) if i < len(r) else None for r in t.rows]


def check_type(t: Table) -> list:
    out = []
    for i in _numcols(t):
        for r, row in enumerate(t.rows):
            cell = row[i] if i < len(row) else None
            if not is_missing(cell) and num(cell) is None:
                out.append(Flag("type", r, i, f"{cell!r} in a numeric column"))
    for i in t.idx("label"):
        vals = [row[i] for row in t.rows if i < len(row) and not is_missing(row[i])]
        if vals and sum(num(v) is None for v in vals) > 0.9 * len(vals):
            for r, row in enumerate(t.rows):
                if i < len(row) and not is_missing(row[i]) and num(row[i]) is not None:
                    out.append(Flag("type", r, i, f"number {row[i]!r} in a label column"))
    return out


def check_range(t: Table) -> list:
    out = []
    for i in _numcols(t):
        pl = t.columns[i].plaus
        if not pl:
            continue
        for r, v in enumerate(_column(t, i)):
            if v is not None and not pl[0] <= v <= pl[1]:
                out.append(Flag("range", r, i, f"{v} outside {pl}"))
    return out


def _groups(t: Table):
    if t.group:
        g = [c.name for c in t.columns].index(t.group)
        return [row[g] if g < len(row) else "" for row in t.rows]
    return [""] * len(t.rows)


def check_unit_factor(t: Table) -> list:
    """A value sits far from its peers and the ratio or offset matches a common conversion."""
    out, grp = [], _groups(t)
    for i in _numcols(t):
        col = _column(t, i)
        members = collections.defaultdict(list)
        for g, v in zip(grp, col):
            members[g].append(v)
        stats = {g: col_stats(vs) for g, vs in members.items()}
        pos = [abs(x) for x in col if x]
        logs = [math.log(x) for x in pos]
        log_scale = col_stats(logs)[1] if logs else 1.0
        for r, v in enumerate(col):
            if not v:
                continue
            med, sc = stats[grp[r]]
            if abs(v - med) / sc <= FENCE or med == 0:
                continue
            if t.columns[i].dimension == "temperature" and any(abs((v - med) - o) < 3 * sc for o in OFFSETS):
                out.append(Flag("unit_factor", r, i, "offset of 273.15 from peers"))
                continue
            ratio = v / med
            if ratio <= 0:
                continue
            for name, f in FACTORS.items():
                if abs(math.log(ratio) - math.log(f)) < min(0.25, 2 * sc / abs(med) + 0.02) and abs(math.log(abs(v)) - st.median(logs)) > 3 * log_scale:
                    out.append(Flag("unit_factor", r, i, f"ratio to peers near {name}"))
                    break
    return out


def _cost(cell, stats, is_num) -> float:
    if is_missing(cell):
        return 1.0
    v = num(cell)
    if is_num:
        return 8.0 if v is None else min(abs(v - stats[0]) / stats[1], 8.0)
    return 8.0 if v is not None else 0.0


def check_shift(t: Table) -> list:
    """Compare the row as printed with the row moved one column left or right, scored against each column's own profile."""
    kinds = [c.kind for c in t.columns]
    use = [i for i, k in enumerate(kinds) if k in ("num", "label")]
    stats = {i: col_stats(_column(t, i)) for i in use if kinds[i] == "num"}
    out = []
    n = len(kinds)
    for r, row in enumerate(t.rows):
        row = list(row) + [""] * (n - len(row))
        if len(row) > n:
            out.append(Flag("shift", r, None, f"{len(row)} cells for {n} columns"))
            continue
        asis = sum(_cost(row[i], stats.get(i), kinds[i] == "num") for i in use)
        if asis < 6:
            continue
        for s in (1, -1):
            shifted = sum(_cost(row[i + s] if 0 <= i + s < n else "", stats.get(i), kinds[i] == "num") for i in use)
            if shifted + 6 < asis:
                out.append(Flag("shift", r, None, f"fits better moved {s:+d}: {shifted:.1f} against {asis:.1f}"))
                break
    return out


def _key_cols(t: Table) -> list:
    return [i for i, c in enumerate(t.columns) if c.kind in ("num", "label", "text")]


def check_exact_dup(t: Table) -> list:
    seen, out, keys = {}, [], _key_cols(t)
    for r, row in enumerate(t.rows):
        k = tuple(row[i].strip() if i < len(row) else "" for i in keys)
        if k in seen:
            out.append(Flag("exact_dup", r, None, f"same as row {seen[k]}"))
        else:
            seen[k] = r
    return out


def check_near_dup(t: Table, tol=0.012) -> list:
    """All numeric cells within tol of the column's robust scale and all labels equal. Sorted window on the scaled sum."""
    nums, labs = _numcols(t), t.idx("label")
    if len(nums) < 2:
        return []
    stats = {i: col_stats(_column(t, i)) for i in nums}
    vec = []
    for r, row in enumerate(t.rows):
        v = [num(row[i]) if i < len(row) else None for i in nums]
        if sum(x is not None for x in v) >= max(2, len(nums) - 1):
            z = [None if x is None else x / stats[i][1] for x, i in zip(v, nums)]
            vec.append((sum(x for x in z if x is not None), r, z, tuple(row[i] if i < len(row) else "" for i in labs)))
    vec.sort(key=lambda x: x[0])
    out, flagged = [], set()
    width = tol * len(nums)
    for a in range(len(vec)):
        b = a + 1
        while b < len(vec) and vec[b][0] - vec[a][0] <= width:
            if vec[a][3] == vec[b][3] and all((x is None and y is None) or (x is not None and y is not None and abs(x - y) <= tol) for x, y in zip(vec[a][2], vec[b][2])):
                later = max(vec[a][1], vec[b][1])
                if later not in flagged:
                    flagged.add(later)
                    out.append(Flag("near_dup", later, None, f"close to row {min(vec[a][1], vec[b][1])}"))
            b += 1
    return out
