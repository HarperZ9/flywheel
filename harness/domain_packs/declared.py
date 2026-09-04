"""declared.py -- a domain pack declared as a document.

Three packs ship in this package. The defect they exist to catch reaches every
regulated domain, not three of them. A treatment plant reads a dosing table. A
grid study reads an ampacity table with a temperature correction applied. An
emissions report reads a global warming potential that changed between one
assessment report and the next. None of that is knowledge this package has, and
"wait until someone adds a pack for it" is the wrong shape of answer for a
domain nobody here has heard of.

So a pack can arrive as a document. It names the fields an answer in that
domain has, the kind of authority that decides each one, the method the domain
mandates, and the failure each template exists to stop. The loader refuses
anything that would turn the document itself into an authority.

The refusal that carries the design is the value-shaped key. A declaration with
a maximum, a rate, a limit or a table inside it would be a pack shipping domain
data, which is the exact failure this feature catches, arriving as a config
file. A tolerance is allowed, because it says how close a recomputation has to
land, which is a property of the check rather than a fact about the domain.

    {"schema": "flywheel.domain-pack-declaration/v1",
     "name": "water",
     "describes": "treatment answers: dosing, residual, contact time",
     "caution": "This pack holds no treatment data ...",
     "templates": {
       "dose": {"authority": "TABLE", "method": "jar-test-table",
                "catches": "a computed dose used where the plant tables it"}}}

Every template has to say what it catches. One that cannot is a template no
reviewer can argue with, and a pack full of those reads as coverage while
checking nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..contract_terms import AUTHORITIES, CRITICAL, CRITICALITIES
from .pack import Pack, Template

SCHEMA = "flywheel.domain-pack-declaration/v1"

_TOP = ("schema", "name", "describes", "caution", "templates")
_TEMPLATE = ("authority", "criticality", "method", "tolerance", "unit",
             "describes", "catches")
# Keys that would make the document decide a value rather than describe a
# check. Refused by name, because a number under `unit` is a different mistake
# from a number under `maximum` and only one of them is a pack overreaching.
_VALUE_SHAPED = ("value", "values", "max", "maximum", "min", "minimum",
                 "limit", "limits", "ceiling", "floor", "threshold", "range",
                 "table", "tables", "data", "constant", "constants", "rate",
                 "rates", "factor", "factors", "schedule", "default")
_SCALAR = (str, int, float, bool)


def _refuse(message: str) -> None:
    raise ValueError(message)


def _value_shaped(name: str) -> bool:
    lowered = str(name).lower()
    return any(lowered == word or lowered.endswith("_" + word)
               for word in _VALUE_SHAPED)


def _tolerance(key: str, spec: dict) -> float:
    given = spec.get("tolerance", 0.0)
    # A bool passes isinstance(int), and `"tolerance": true` read as 1.0 would
    # be a wide tolerance nobody wrote down.
    if isinstance(given, bool) or not isinstance(given, (int, float)):
        _refuse(f"template {key!r} gives a tolerance that is not a number")
    return float(given)


def _template(key: str, spec: object) -> Template:
    if not isinstance(spec, dict):
        _refuse(f"template {key!r} is not an object")
    for name, value in spec.items():
        if _value_shaped(name):
            _refuse(f"template {key!r} declares {name!r}; a pack carries the "
                    f"shape of a check and never the value it checks against, "
                    f"which is the caller's to supply and to name")
        if name not in _TEMPLATE:
            _refuse(f"template {key!r} declares {name!r}, which nothing reads; "
                    f"known: {', '.join(_TEMPLATE)}")
        if not isinstance(value, _SCALAR):
            _refuse(f"template {key!r} gives {name!r} a "
                    f"{type(value).__name__} where a scalar belongs")
    authority = spec.get("authority", "")
    if authority not in AUTHORITIES:
        _refuse(f"template {key!r} names authority {authority!r}; "
                f"known: {', '.join(AUTHORITIES)}")
    criticality = spec.get("criticality", CRITICAL)
    if criticality not in CRITICALITIES:
        _refuse(f"template {key!r} names criticality {criticality!r}; "
                f"known: {', '.join(CRITICALITIES)}")
    catches = str(spec.get("catches", "")).strip()
    if not catches:
        _refuse(f"template {key!r} does not say what it catches, so nobody "
                f"reviewing this pack can tell whether it is worth having")
    return Template(key, authority, criticality=criticality,
                    method=str(spec.get("method", "")),
                    tolerance=_tolerance(key, spec),
                    unit=str(spec.get("unit", "")),
                    describes=str(spec.get("describes", "")),
                    catches=catches)


def declared_pack(document: object, *, shipped=()) -> Pack:
    """A Pack from a declaration, or a refusal that says which rule it broke.

    `shipped` names the packs already in the registry. A declaration that took
    one of those names would put an unreviewed pack behind a reviewed name, and
    a reader of the resulting contract could not tell which one decided it.
    """
    if not isinstance(document, dict):
        _refuse("a pack declaration is a JSON object")
    if document.get("schema") != SCHEMA:
        _refuse(f"a pack declaration carries schema {SCHEMA!r}, this one "
                f"carries {document.get('schema')!r}")
    for name in document:
        if name not in _TOP:
            _refuse(f"the declaration carries {name!r}, which nothing reads; "
                    f"known: {', '.join(_TOP)}")
    name = str(document.get("name", "")).strip()
    if not name:
        _refuse("a pack declaration needs a name")
    if name in set(shipped):
        _refuse(f"{name!r} is a pack that ships here, so a declaration must "
                f"not take its name")
    caution = str(document.get("caution", "")).strip()
    if not caution:
        _refuse("a pack declaration needs a caution saying what it does not "
                "decide, because that is the line a reader has to act on")
    templates = document.get("templates")
    if not isinstance(templates, dict) or not templates:
        _refuse("a pack declaration needs at least one template")
    return Pack(name=name, describes=str(document.get("describes", "")),
                caution=caution,
                templates={key: _template(key, spec)
                           for key, spec in templates.items()})


def read_pack(path, *, shipped=()) -> Pack:
    """A declared pack read off disk.

    A malformed document is a refusal rather than a pack with holes in it. A
    pack that loaded with half its templates dropped would report a shorter
    contract as a passing one.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path} is not readable as JSON: {exc}") from None
    return declared_pack(document, shipped=shipped)
