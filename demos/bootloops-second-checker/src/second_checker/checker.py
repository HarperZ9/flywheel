"""Clean-room checker for RECEIPT witness format v1.0.

Written from WITNESS_FORMAT.md (BootLoops tools/trust/receipt, v1.0) only.
It shares no code with BootLoops' core.py and imports nothing from it.

The identity under test, per witness, at one (point, prime):

    sum_i lam[i] * R_i  ==  e_t - sum_m c[m] * e_m      (mod p)

Verdicts:
    PASS       the identity holds exactly (and, in table mode, the claimed row
               equals the certified row)
    FAIL       well formed, but the identity or a table/fingerprint check fails
    MALFORMED  the witness cannot be interpreted (CLI exit code 2)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

PASS, FAIL, MALFORMED = "PASS", "FAIL", "MALFORMED"


class Malformed(ValueError):
    """Raised when a witness or a system cannot be interpreted."""


@dataclass
class Witness:
    p: int
    target: int
    c: dict[int, int]          # normalized mod p, zeros dropped
    lam: dict[int, int]        # row index -> multiplier, normalized, zeros dropped
    n_rows: int
    fingerprint: str | None = None
    raw: Mapping = field(default_factory=dict, repr=False)


@dataclass
class Verdict:
    verdict: str
    reason: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict == PASS


def _as_int(value, what: str) -> int:
    """Accept JSON integers and base-10 integer strings. Reject bools and floats."""
    if isinstance(value, bool):
        raise Malformed(f"{what}: boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 10)
        except ValueError as exc:
            raise Malformed(f"{what}: {value!r} is not an integer") from exc
    raise Malformed(f"{what}: {type(value).__name__} is not an integer")


def _check_version(obj: Mapping) -> None:
    if "receipt_version" not in obj:
        raise Malformed("missing receipt_version")
    ver = obj["receipt_version"]
    if not isinstance(ver, str):
        raise Malformed(f"receipt_version must be a string, got {type(ver).__name__}")
    major = ver.split(".", 1)[0]
    if major != "1":
        raise Malformed(f"unsupported receipt_version {ver!r}")


def parse_witness(obj: Mapping) -> Witness:
    """Validate the required fields and normalize values mod p."""
    if not isinstance(obj, Mapping):
        raise Malformed("witness is not a JSON object")
    _check_version(obj)
    for key in ("p", "target", "c", "lam"):
        if key not in obj:
            raise Malformed(f"missing required field {key!r}")
    p = _as_int(obj["p"], "p")
    if p <= 1:
        raise Malformed(f"p must be > 1, got {p}")
    target = obj["target"]
    if not isinstance(target, Mapping) or "col" not in target:
        raise Malformed("target.col missing")
    t = _as_int(target["col"], "target.col")

    c_raw = obj["c"]
    if not isinstance(c_raw, Mapping):
        raise Malformed("c is not an object")
    c: dict[int, int] = {}
    for k, v in c_raw.items():
        col = _as_int(k, "c key")
        if col in c:
            raise Malformed(f"duplicate c column {col}")
        val = _as_int(v, f"c[{k}]") % p
        c[col] = val
    c = {k: v for k, v in c.items() if v}

    lam_raw = obj["lam"]
    if not isinstance(lam_raw, Mapping):
        raise Malformed("lam is not an object")
    for key in ("n_rows", "idx", "val"):
        if key not in lam_raw:
            raise Malformed(f"lam.{key} missing")
    n_rows = _as_int(lam_raw["n_rows"], "lam.n_rows")
    if n_rows < 0:
        raise Malformed("lam.n_rows negative")
    idx, val = lam_raw["idx"], lam_raw["val"]
    if not isinstance(idx, list) or not isinstance(val, list):
        raise Malformed("lam.idx and lam.val must be arrays")
    if len(idx) != len(val):
        raise Malformed("lam.idx and lam.val lengths differ")
    lam: dict[int, int] = {}
    for i_raw, v_raw in zip(idx, val):
        i = _as_int(i_raw, "lam.idx entry")
        if i < 0 or i >= n_rows:
            raise Malformed(f"lam.idx {i} out of range [0, {n_rows})")
        if i in lam:
            raise Malformed(f"duplicate lam.idx {i}")
        lam[i] = _as_int(v_raw, "lam.val entry") % p
    lam = {k: v for k, v in lam.items() if v}

    fp = None
    system = obj.get("system")
    if isinstance(system, Mapping) and system.get("fingerprint"):
        fp = str(system["fingerprint"])
    return Witness(p=p, target=t, c=c, lam=lam, n_rows=n_rows, fingerprint=fp, raw=obj)


def parse_row(obj, p: int, where: str = "row") -> dict[int, int]:
    """One system row: {col_id: value}. Values reduced mod p, zeros dropped."""
    if not isinstance(obj, Mapping):
        raise Malformed(f"{where} is not a JSON object")
    row: dict[int, int] = {}
    for k, v in obj.items():
        col = _as_int(k, f"{where} key")
        if col in row:
            raise Malformed(f"{where}: duplicate column {col}")
        row[col] = _as_int(v, f"{where}[{k}]") % p
    return {k: v for k, v in row.items() if v}


def expected_vector(w: Witness) -> dict[int, int]:
    """e_t - sum_m c[m] e_m, as a sparse vector mod p (additive merge)."""
    out: dict[int, int] = {w.target: 1 % w.p}
    for m, cm in w.c.items():
        out[m] = (out.get(m, 0) - cm) % w.p
    return {k: v for k, v in out.items() if v}


def residual(rows: list[Mapping[int, int]], w: Witness) -> dict[int, int]:
    """sum_i lam[i] * R_i mod p, accumulated sparsely, zeros dropped."""
    acc: dict[int, int] = {}
    p = w.p
    for i, li in w.lam.items():
        for col, v in rows[i].items():
            acc[col] = (acc.get(col, 0) + li * v) % p
    return {k: v for k, v in acc.items() if v}


def normalize_claimed(row: Mapping, p: int) -> dict[int, int]:
    return parse_row(row, p, where="claimed row")


def verify(rows: list[Mapping[int, int]], w: Witness, *,
           claimed: Mapping | None = None,
           system_fingerprint: str | None = None) -> Verdict:
    """Apply the normative semantics (steps 1 to 6) to one parsed witness.

    `rows` must already be reduced mod w.p (see parse_row). The caller passes
    `system_fingerprint` only if it computed one itself; this checker does not
    define the fingerprint serialization (the spec does not fix the bytes).
    """
    if len(rows) != w.n_rows:
        return Verdict(FAIL, "lam n_rows mismatch",
                       {"n_rows_witness": w.n_rows, "n_rows_system": len(rows)})
    if w.fingerprint and system_fingerprint and w.fingerprint != system_fingerprint:
        return Verdict(FAIL, "system fingerprint mismatch")
    r = residual(rows, w)
    e = expected_vector(w)
    if r != e:
        diff_cols = sorted(set(r) ^ set(e) | {k for k in set(r) & set(e) if r[k] != e[k]})
        return Verdict(FAIL, "identity failed",
                       {"n_diff_cols": len(diff_cols), "first_diff_cols": diff_cols[:5]})
    if claimed is not None:
        cc = normalize_claimed(claimed, w.p)
        if cc != w.c:
            return Verdict(FAIL, "claimed table row != certified row")
    return Verdict(PASS)


def verify_obj(rows, obj: Mapping, **kw) -> Verdict:
    """Parse then verify; MALFORMED instead of raising."""
    try:
        w = parse_witness(obj)
    except Malformed as exc:
        return Verdict(MALFORMED, str(exc))
    try:
        reduced = [parse_row(r, w.p, where=f"row {i}") if not _is_reduced(r, w.p) else r
                   for i, r in enumerate(rows)]
        return verify(reduced, w, **kw)
    except Malformed as exc:
        return Verdict(MALFORMED, str(exc))


def _is_reduced(row, p: int) -> bool:
    return all(isinstance(k, int) and isinstance(v, int) and not isinstance(v, bool)
               and 0 < v < p for k, v in row.items())
