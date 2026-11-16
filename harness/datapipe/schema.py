"""Stage 4, structure. One record per value, JSON Lines, with the printed form kept beside the parsed number.

Every value carries unit, uncertainty, provenance, representation and licence. A record is valid when those
fields are present and consistent. Valid says the record is well formed; it says nothing about the value.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

SCHEMA = "datapipe.record/1"
MISSING = {"", "na", "n/a", "nan", "none", "null", "*", "-"}

# unit -> (dimension, factor to the SI unit of that dimension). Offsets (Celsius) are handled in the checks.
UNITS = {
    "1": ("dimensionless", 1.0), "percent": ("dimensionless", 0.01),
    "m": ("length", 1.0), "cm": ("length", 1e-2), "mm": ("length", 1e-3), "um": ("length", 1e-6), "nm": ("length", 1e-9),
    "g": ("mass", 1e-3), "kg": ("mass", 1.0),
    "s": ("time", 1.0), "h": ("time", 3600.0), "year": ("time", 3.156e7),
    "Hz": ("frequency", 1.0), "MHz": ("frequency", 1e6),
    "K": ("temperature", 1.0), "degC": ("temperature", 1.0),
    "Pa": ("pressure", 1.0), "kPa": ("pressure", 1e3), "MPa": ("pressure", 1e6), "mbar": ("pressure", 100.0), "cmHg": ("pressure", 1333.22),
    "MW": ("power", 1e6), "W": ("power", 1.0),
    "MeV": ("energy", 1.602e-13), "keV": ("energy", 1.602e-16), "eV": ("energy", 1.602e-19),
    "1/cm": ("inverse length", 100.0), "1/m": ("inverse length", 1.0),
    "m/s2": ("acceleration", 1.0), "gn": ("acceleration", 9.80665),
}


def is_missing(cell) -> bool:
    return cell is None or str(cell).strip().lower() in MISSING


def num(cell):
    """The number a printed cell holds, or None. A number that fails to parse is a finding for the type check."""
    if is_missing(cell):
        return None
    try:
        v = float(str(cell).strip().rstrip("#"))
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None


@dataclasses.dataclass
class Column:
    name: str
    kind: str = "num"  # num, label, id, text
    unit: str = "1"
    quantity: str = ""
    dimension: str = ""
    plaus: tuple | None = None  # plausible range for the quantity in the declared unit, written from the quantity's meaning


@dataclasses.dataclass
class Table:
    name: str
    source_id: str
    columns: list
    rows: list  # list of lists of printed strings
    file: str = ""
    file_sha256: str = ""
    licence: str = "unknown"
    basis: str = "unknown"
    tier: str = "measured raw"
    group: str = ""  # the label column that makes values comparable, if any

    def idx(self, kind) -> list:
        return [i for i, c in enumerate(self.columns) if c.kind == kind]

    def copy(self):
        new = dataclasses.replace(self, rows=[list(r) for r in self.rows])
        new.identities = getattr(self, "identities", [])  # set outside the dataclass fields, so replace drops it
        return new


def to_records(t: Table, uncertainties=None):
    """Long form. uncertainties maps a column name to (uncertainty column name, kind)."""
    uncertainties = uncertainties or {}
    by_name = {c.name: i for i, c in enumerate(t.columns)}
    for r, row in enumerate(t.rows):
        for i, c in enumerate(t.columns):
            if i >= len(row) or c.kind == "id":
                continue
            cell = row[i]
            unc = None
            if c.name in uncertainties:
                j, kind = by_name[uncertainties[c.name][0]], uncertainties[c.name][1]
                unc = dict(value=num(row[j]), kind=kind, printed=row[j])
            yield dict(schema=SCHEMA, id=f"{t.name}:{r}:{c.name}", source_id=t.source_id, table=t.name, row=r, field=c.name,
                       quantity=c.quantity or c.name, value=num(cell) if c.kind == "num" else cell, unit=c.unit if c.kind == "num" else None,
                       uncertainty=unc, representation=dict(printed=cell, missing=is_missing(cell)),
                       provenance=dict(file=t.file, file_sha256=t.file_sha256, locator=f"row {r}, column {c.name}", tier=t.tier),
                       licence=t.licence, basis=t.basis)


def validate(rec: dict) -> list:
    out = []
    for k in ("schema", "id", "source_id", "field", "representation", "provenance", "licence", "basis"):
        if k not in rec:
            out.append(f"{k} absent")
    if rec.get("schema") != SCHEMA:
        out.append("schema differs")
    if rec.get("unit") is not None and rec["unit"] not in UNITS:
        out.append(f"unit {rec['unit']!r} unknown")
    if isinstance(rec.get("value"), float) and "representation" in rec and num(rec["representation"].get("printed")) != rec["value"]:
        out.append("value differs from printed form")
    p = rec.get("provenance") or {}
    if not p.get("file") or not p.get("file_sha256"):
        out.append("provenance lacks file or hash")
    return out


def write_jsonl(records, path) -> int:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
            n += 1
    return n
