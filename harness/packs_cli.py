"""packs_cli.py -- what each domain pack declares, and what it refuses to decide.

    flywheel packs                 list the packs
    flywheel packs medicine        what a medical answer has to satisfy
    flywheel packs law --json      the same, for a harness to read
    flywheel packs water.pack.json a pack declared as a document, not shipped

A path is accepted wherever a name is. The domains that ship here are three and
the domains this defect reaches are not, so a pack for one of the others is a
document the operator writes and points at.

The caution prints first in every case. A reader who takes one line from this
command should take the line that says the pack holds no domain data, because
the whole design rests on the authorities coming from somewhere nameable.
"""
from __future__ import annotations

import argparse
import json

from .domain_packs import load_pack, pack_names, pack_report


def as_json(name: str) -> dict:
    pack = load_pack(name)
    return {
        "name": pack.name,
        "describes": pack.describes,
        "caution": pack.caution,
        "templates": [{"use": key, "authority": tpl.authority,
                       "criticality": tpl.criticality, "method": tpl.method,
                       "unit": tpl.unit, "describes": tpl.describes,
                       "catches": tpl.catches}
                      for key, tpl in sorted(pack.templates.items())],
    }


def listing() -> str:
    lines = []
    for name in pack_names():
        pack = load_pack(name)
        lines.append(f"  {name:<9} {pack.describes}")
        lines.append(f"  {'':<9} {len(pack.templates)} field templates")
    lines.append("")
    lines.append("Every pack ships field shapes and arithmetic and no domain "
                 "data. The authorities are yours to supply.")
    lines.append("Point this at a declaration document for a domain that does "
                 "not ship here.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    parser.add_argument("name", nargs="?", default="",
                        help=f"one of: {', '.join(pack_names())}, or the path "
                             f"to a pack declaration")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.name:
        print(json.dumps(pack_names()) if args.json else listing())
        return 0
    try:
        text = (json.dumps(as_json(args.name), indent=2) if args.json
                else pack_report(load_pack(args.name)))
    except (LookupError, ValueError) as exc:
        # A declaration that broke a rule prints the rule it broke. Printing a
        # traceback here would bury the one line the author needs.
        print(str(exc))
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
