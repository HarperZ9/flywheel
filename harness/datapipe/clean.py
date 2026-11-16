"""Table checks: the registry and the simple baselines. A clean pass means these checks did not fire."""
from __future__ import annotations

import statistics as st

from .clean_core import Flag, _column, _numcols, check_type, check_range, check_unit_factor, check_shift, check_exact_dup, check_near_dup
from .clean_relations import check_identity, check_label_centroid, check_label_fd, check_label_twin, check_runs
from .schema import Table

CHECKS = {"type": check_type, "range": check_range, "unit_factor": check_unit_factor, "shift": check_shift, "exact_dup": check_exact_dup,
          "near_dup": check_near_dup, "label_fd": check_label_fd, "label_centroid": check_label_centroid, "label_twin": check_label_twin, "identity": check_identity, "runs": check_runs}


def run_all(t: Table) -> list:
    out = []
    for fn in CHECKS.values():
        out.extend(fn(t))
    return out


def baseline_z(t: Table, z=3.0) -> list:
    """The simple baseline: three standard deviations per column, with mean and standard deviation."""
    out = []
    for i in _numcols(t):
        vals = [v for v in _column(t, i) if v is not None]
        if len(vals) < 3:
            continue
        m, s = st.fmean(vals), st.pstdev(vals)
        if s == 0:
            continue
        for r, v in enumerate(_column(t, i)):
            if v is not None and abs(v - m) / s > z:
                out.append(Flag("baseline_z", r, i, ""))
    return out


def baseline_exact(t: Table) -> list:
    """The simple baseline for duplicates: whole-row hash, id columns included."""
    seen, out = set(), []
    for r, row in enumerate(t.rows):
        k = tuple(row)
        if k in seen:
            out.append(Flag("baseline_exact", r, None, ""))
        seen.add(k)
    return out
