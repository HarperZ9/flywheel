"""The study spec: load, resolve paths against the spec's folder, check its shape, hash its plan.

The plan is the part a preregistration freezes: analysis, controls and verdict rules. Changing any
of them after the lock is written changes plan_sha256 and the stage refuses to score.
"""
import json
from pathlib import Path

from . import SPEC_SCHEMA
from .hashing import FORM, sha256_json

REQUIRED = ("schema", "id", "title", "prereg", "seed", "analysis", "controls", "verdicts", "ledger")


class SpecError(ValueError):
    pass


def _resolve(base, p):
    q = Path(p)
    return (q if q.is_absolute() else (base / q)).resolve()


def _unit_problems(where, unit):
    if not isinstance(unit, dict) or ":" not in str(unit.get("unit", "")):
        return [f"{where}: needs unit 'file.py:function'"]
    return []


def problems(spec):
    out = [f"missing field {k}" for k in REQUIRED if k not in spec]
    if spec.get("schema") != SPEC_SCHEMA:
        out.append(f"schema must be {SPEC_SCHEMA}")
    out += _unit_problems("analysis", spec.get("analysis"))
    names = set()
    for i, c in enumerate(spec.get("controls", [])):
        out += _unit_problems(f"controls[{i}]", c)
        if not c.get("name") or c["name"] in names:
            out.append(f"controls[{i}]: needs a unique name")
        names.add(c.get("name"))
        if not c.get("compare"):
            out.append(f"controls[{i}]: needs compare, the analysis value its null is read against")
    if not spec.get("controls"):
        out.append("controls: at least one control; a result with no control is not scored")
    for name, rules in spec.get("verdicts", {}).items():
        if not isinstance(rules, list) or not rules:
            out.append(f"verdicts.{name}: needs a non-empty rule list")
    return out


def load(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    bad = problems(spec)
    if bad:
        raise SpecError("; ".join(bad))
    base = path.parent
    spec["_path"] = str(path)
    spec["_base"] = str(base)
    spec["_prereg_path"] = str(_resolve(base, spec["prereg"]["path"]))
    spec["_lock_path"] = str(_resolve(base, spec["prereg"].get("lock", "prereg.lock.json")))
    spec["_inputs"] = [str(_resolve(base, i["path"])) for i in spec.get("inputs", [])]
    spec["_code"] = [str(_resolve(base, c)) for c in spec.get("code", [])]
    spec["_out"] = str(_resolve(base, spec.get("out", "out")))
    spec["_ledger_path"] = str(_resolve(base, spec["ledger"]["path"]))
    spec["_reproduce_source"] = (str(_resolve(base, spec["reproduce"]["source"]))
                                 if spec.get("reproduce") else None)
    return spec


def unit_path(spec, unit):
    file, func = unit.rsplit(":", 1)
    return _resolve(Path(spec["_base"]), file), func


def plan_sha256(spec, form=FORM):
    plan = {k: spec[k] for k in ("analysis", "controls", "verdicts", "seed")}
    return sha256_json(plan, form)
