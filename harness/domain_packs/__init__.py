"""domain_packs -- contract shapes for domains where a wrong answer costs.

Tax was the example that started this, and tax is not the point. The same
defect reaches every regulated answer: a value that is arithmetically fine and
bound to the wrong authority. The rate schedule instead of the tax table.
Cockcroft-Gault instead of CKD-EPI. Calendar days instead of court days.
Pounds instead of kilograms.

A pack names the fields such an answer has, the authority kind that decides
each one, the method the domain mandates, and how much each field's failure
matters. It supplies no domain data. Read `pack.py` for why that rule is the
load-bearing one.

    from harness.domain_packs import load_pack, contract_from, unsupplied

    pack = load_pack("medicine")
    contract = contract_from(pack, [
        {"use": "dose", "name": "dose", "source": "formulary:2026-03"},
        {"use": "dose_unit", "name": "dose", "source": "formulary:2026-03"},
        {"use": "maximum", "name": "dose", "source": "formulary:max-daily"},
    ])
    unsupplied(contract, authorities)   # what will hold, before running

The last call is the one that earns the package. It answers "what does nothing
in this system actually check" before an attempt is made, rather than after.
"""
from __future__ import annotations

from . import finance, law, medicine, units
from .pack import Pack, Template, contract_from, field_spec, unsupplied

PACKS: dict[str, Pack] = {p.name: p for p in
                          (finance.PACK, medicine.PACK, law.PACK)}

__all__ = ["PACKS", "Pack", "Template", "contract_from", "field_spec",
           "load_pack", "pack_names", "pack_report", "unsupplied", "units",
           "finance", "medicine", "law"]


def pack_names() -> list[str]:
    return sorted(PACKS)


def load_pack(name: str) -> Pack:
    try:
        return PACKS[name]
    except KeyError:
        raise LookupError(f"no domain pack named {name!r}; "
                          f"known: {pack_names()}") from None


def pack_report(pack: Pack) -> str:
    """What a pack declares, and what it refuses to decide.

    The caution prints first. A reader who takes one thing from this output
    should take that.
    """
    lines = [f"{pack.name}: {pack.describes}", "", pack.caution, ""]
    width = max(len(k) for k in pack.templates)
    for key in sorted(pack.templates):
        tpl = pack.templates[key]
        mandate = f" via {tpl.method}" if tpl.method else ""
        lines.append(f"  {key:<{width}}  {tpl.authority:<9} "
                     f"{tpl.criticality}{mandate}")
        lines.append(f"  {'':<{width}}  catches: {tpl.catches}")
    return "\n".join(lines)
