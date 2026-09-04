"""pack.py -- what a domain pack is.

A pack is a set of field templates and a warning. It is not a database.

The rule that shapes every pack in this package: a pack ships no authoritative
domain data. No formulary, no rate table, no case citation, no drug interaction
list. Inventing any of those would be the failure this whole feature exists to
catch, dressed up as a library.

What a pack ships instead:

    a template     the authority kind, criticality, and method mandate that a
                   field of this shape has in this domain
    a manifest     which sources the caller has to supply an authority for
    arithmetic     day counts, unit conversion, rounding, business days, all
                   of it computed from constants the caller passes in

The payoff is that a missing authority becomes loud. A critical field with no
authority resolves to AUTHORITY_UNAVAILABLE, which is UNVERIFIABLE, which holds
the release. Without a pack the same gap is an answer nobody thought to check.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field

from ..contract_terms import CRITICAL


@dataclass(frozen=True)
class Template:
    """A field spec with everything the domain already decides filled in.

    The caller supplies `name` and `source`. Everything else is what this kind
    of field is, in this domain, regardless of who is asking.
    """
    key: str
    authority: str
    criticality: str = CRITICAL
    method: str = ""
    tolerance: float = 0.0
    unit: str = ""
    describes: str = ""
    catches: str = ""   # the specific failure this template exists to stop


@dataclass(frozen=True)
class Pack:
    name: str
    describes: str
    caution: str
    templates: dict = _field(default_factory=dict)

    def template(self, key: str) -> Template:
        try:
            return self.templates[key]
        except KeyError:
            raise LookupError(
                f"pack {self.name!r} has no template {key!r}; "
                f"known: {sorted(self.templates)}") from None


def field_spec(pack: Pack, key: str, *, name: str, source: str, **overrides) -> dict:
    """One template plus the caller's binding, ready for `new_contract`.

    Overrides are allowed and are the caller's responsibility. A pack sets the
    default criticality high on purpose, and lowering it is a decision someone
    should have to write down.
    """
    tpl = pack.template(key)
    spec = {"name": name, "source": source, "authority": tpl.authority,
            "criticality": tpl.criticality, "method": tpl.method,
            "tolerance": tpl.tolerance,
            "describes": tpl.describes or f"{pack.name}:{key}"}
    spec.update(overrides)
    return spec


def contract_from(pack: Pack, requests: list[dict]) -> list[dict]:
    """Build a contract from a list of `{"use", "name", "source"}` requests."""
    from ..output_contract import new_contract
    specs = []
    for req in requests:
        req = dict(req)
        key = req.pop("use")
        specs.append(field_spec(pack, key, **req))
    return new_contract(specs)


def unsupplied(contract: list[dict], authorities: dict) -> list[dict]:
    """The fields whose source has no authority behind it, worst first.

    A pre-flight version of what `check_answer` would report anyway. Worth
    having separately because the answer to "will this hold" should be
    available before an expensive attempt, not only after it.
    """
    have = set(authorities or {})
    gaps = [{"field": f["name"], "source": f["source"],
             "criticality": f["criticality"]}
            for f in contract if f["source"] not in have]
    order = {CRITICAL: 0}
    return sorted(gaps, key=lambda g: order.get(g["criticality"], 1))
