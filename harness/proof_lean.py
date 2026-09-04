"""proof_lean.py -- the checked answer as a Lean 4 file a kernel can re-check.

A model's output is a probability distribution that happened to land on some
numbers. A proof is not. This module writes the part of a checked answer that a
proof assistant can settle without trusting anything: the arithmetic the
contract states, and the method and source the contract requires against the
ones the answer states.

What cannot be settled that way is not smuggled in. Every value an external
authority decided enters as a named axiom, so `#print axioms confirmed`
enumerates the exact set of outside facts the answer rests on. A file whose
obligations close with no axioms rests on nothing but the kernel. A file that
lists three sources rests on those three, by name, in the artifact itself. A
file where an obligation did not close reports `sorryAx`, which is the same
sentence in the language a prover already speaks.

That division is the whole point. An answer is not made true by being written
down in Lean. What Lean adds is that the deterministic half is now checked by
something with no opinion, and the non-deterministic half is now enumerable
instead of invisible.

Field values are carried as integers in one fixed-point scale, because `decide`
settles integer arithmetic in the kernel and floating point is not an ordered
field. The scale is the widest number of decimal places any field needs. A
value that scale cannot hold exactly is dropped rather than rounded, and named
in `unrepresentable`, because a rounded number in a proof is a proof about a
number nobody stated.
"""
from __future__ import annotations

import hashlib
import json
import keyword
import re

from .contract_terms import RECOMPUTE, TABLE
from .proof_relations import MAX_SCALE, claims, fixed_point, numeric, places
from .verdict import Verdict

NAMESPACE = "Flywheel.Answer"
# Every declaration a field name gives rise to. All of them are claimed at
# once, so a contract holding both `tax` and `tax_source` cannot end up with
# two declarations of the same name and a file that will not parse.
SUFFIXES = ("_source", "_method", "_unit", "_decided")
RESERVED = {"Decided", "assumed_sources", "unconfirmed", "unrepresentable",
            "confirmed"}
RELATION = re.compile(r"^relation_\d+[a-z]*$")
LEAN_KEYWORDS = {"def", "theorem", "axiom", "end", "namespace", "open", "where",
                 "match", "with", "fun", "let", "have", "show", "from", "by",
                 "do", "if", "then", "else", "deriving", "structure", "class",
                 "instance", "example", "variable", "universe", "section",
                 "mutual", "partial", "unsafe", "private", "protected", "this"}


def identifier(name: str, taken: set[str]) -> str:
    """A Lean name for a field, distinct from every name already spoken for."""
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name) or "field"
    if ident[0].isdigit():
        ident = f"f_{ident}"
    while (ident in LEAN_KEYWORDS or keyword.iskeyword(ident) or ident in taken
           or ident in RESERVED or RELATION.match(ident)
           or any(f"{ident}{suffix}" in taken for suffix in SUFFIXES)):
        ident = f"{ident}_"
    taken.add(ident)
    taken.update(f"{ident}{suffix}" for suffix in SUFFIXES)
    return ident


def scale_of(answer: dict) -> int:
    """One scale for the whole file, so no sum ever mixes cents with dollars.

    A field wider than MAX_SCALE is left out of the vote rather than capped
    into it. One float's rounding tail would otherwise set the scale for every
    other field, and the file would carry `12` as `12000000000` to make room
    for a value it goes on to drop anyway.
    """
    widths = [width for claim in answer.values()
              if isinstance(claim, dict) and numeric(claim.get("value"))
              for width in [places(claim["value"])] if width <= MAX_SCALE]
    return max(widths, default=0)


def _string(value) -> str:
    out = []
    for char in str(value):
        point = ord(char)
        if char in ('"', "\\"):
            out.append("\\" + char)
        elif char in "\n\r\t":
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[char])
        elif point < 0x20 or point == 0x7F:
            out.append(f"\\x{point:02x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _defs(answer: dict, names: dict, values: dict, scale: int) -> list[str]:
    """The answer, as definitions. Nothing here is an authority's value."""
    out: list[str] = []
    for field, ident in names.items():
        claim = answer[field]
        if field in values:
            kind, literal = values[field]
            times = f", times 10^{scale}" if kind == "Int" and scale else ""
            out += [f"/-- `{field}`, as the answer states it{times}. -/",
                    f"def {ident} : {kind} := {literal}", ""]
        for key in ("source", "method", "unit"):
            stated = claim.get(key)
            if isinstance(stated, str) and stated:
                out += [f"/-- the {key} the answer states for `{field}`. -/",
                        f"def {ident}_{key} : String := {_string(stated)}", ""]
    return out


def _agreements(rows: list[dict], quantities: dict) -> list[tuple[str, str, str]]:
    """One axiom per value an outside source decided.

    An axiom rather than a theorem, because that is what it is. The check ran
    outside Lean, and pretending otherwise would put a kernel's name on a
    subprocess's word. `#print axioms` then lists every source by name.
    """
    out = []
    for row in rows:
        ident = quantities.get(row["field"])
        if ident is None or row["verdict"] != Verdict.PASS.value:
            continue
        if row["authority"] not in (TABLE, RECOMPUTE):
            continue
        out.append((f"{ident}_decided",
                    f"Decided {_string(row['source'])} {ident}",
                    f"{row['source']} was consulted and agreed with "
                    f"`{row['field']}`."))
    return out


def _mandates(contract, answer: dict, names: dict) -> list[tuple[str, str, str]]:
    """What the contract requires, met by what the answer states.

    Both halves are literals in this file and they came from two different
    documents. Where they differ the kernel refuses the obligation, which is
    the point: a source the answer merely asserts is not a source it used.
    """
    out = []
    for field in contract or []:
        ident = names.get(field.get("name"))
        claim = answer.get(field.get("name"))
        if ident is None or not isinstance(claim, dict):
            continue
        for key in ("method", "source"):
            required = field.get(key) or ""
            if not required or not claim.get(key):
                continue
            out.append((f"{ident}_{key}_as_required",
                        f"{ident}_{key} = {_string(required)}",
                        f"the contract requires {key} {required} for "
                        f"`{field['name']}`."))
    return out


def _obligations(relations, quantities: dict, scale: int) -> list[tuple[str, str, str]]:
    """The arithmetic the contract states, one theorem per comparison."""
    out = []
    for index, relation in enumerate(relations or [], start=1):
        for part, claim in enumerate(claims(relation, quantities, scale)):
            suffix = "abcdefgh"[part] if part else ""
            out.append((f"relation_{index}{suffix}", claim, relation))
    return out


def digest(answer: dict) -> str:
    return hashlib.sha256(json.dumps(answer, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _confirmed(obligations: list[tuple[str, str, str]]) -> list[str]:
    """Every obligation at once, so one `#print axioms` names the whole surface.

    The conjunction is proved from the declarations above it rather than from
    scratch, so an obligation the kernel refused arrives here as `sorryAx` and
    the trust surface says so in a prover's own vocabulary.
    """
    doc = ["/-- Every obligation this file states, together. `#print axioms`",
           "    on this name lists exactly what the answer rests on. -/"]
    if not obligations:
        return doc + ["theorem confirmed : True := trivial", ""]
    claim_lines = [f"    ({claim})" if first else f"    ∧ ({claim})"
                   for first, (_, claim, _) in
                   ((index == 0, item) for index, item in enumerate(obligations))]
    names = [name for name, _, _ in obligations]
    proof = names[0] if len(names) == 1 else "⟨" + ", ".join(names) + "⟩"
    return (doc + ["theorem confirmed :"] + claim_lines
            + ["    :=", f"  {proof}", ""])


def lean_source(report: dict, answer: dict, contract=None, *, relations=(),
                namespace: str = NAMESPACE) -> str:
    """The whole file. Deterministic: same inputs, same bytes."""
    scale = scale_of(answer)
    taken: set[str] = set()
    names: dict[str, str] = {}
    quantities: dict[str, str] = {}
    values: dict[str, tuple[str, str]] = {}
    unrepresentable: list[str] = []
    for field, claim in answer.items():
        if not isinstance(claim, dict):
            continue
        names[field] = identifier(field, taken)
        value = claim.get("value")
        if numeric(value):
            literal = fixed_point(value, scale)
            if literal is None:
                unrepresentable.append(field)
            else:
                quantities[field] = names[field]
                values[field] = ("Int", literal)
        elif isinstance(value, str):
            values[field] = ("String", _string(value))

    rows = report.get("fields", [])
    agreements = _agreements(rows, quantities)
    obligations = (agreements + _mandates(contract, answer, names)
                   + _obligations(relations, quantities, scale))
    axioms = {name for name, _, _ in agreements}
    sources = sorted({row["source"] for row in rows
                      if row["field"] in quantities
                      and row["verdict"] == Verdict.PASS.value
                      and row["authority"] in (TABLE, RECOMPUTE)})
    unconfirmed = [row["field"] for row in rows
                   if row["verdict"] != Verdict.PASS.value]

    head = [
        "/-",
        "  Flywheel output validation, as obligations a kernel can re-check.",
        "  Generated. Do not edit: regenerate it from the answer instead.",
        "",
        f"  verdict  {report.get('verdict', '')}",
        f"  release  {report.get('release', '')}",
        f"  fields   {report.get('passed', 0)} of {report.get('checked', 0)} confirmed",
        f"  answer   sha256:{digest(answer)}",
        f"  scale    10^{scale}, so every quantity below is an integer",
        "",
        "  What this file settles: the relations the contract states, and the",
        "  method and source the contract requires against the ones the answer",
        "  states. What it assumes: every value an outside source decided,",
        "  entered below as a named axiom. `lean` on this file closes the",
        "  first half or refuses it, and prints the second half by name.",
        "-/",
        f"namespace {namespace}",
        "",
    ]
    if axioms:
        head += [
            "/-- `Decided s v` records that the source named `s` decided `v`.",
            "    It has no constructor. It is introduced only by an axiom naming",
            "    a check that ran outside this file. -/",
            "axiom Decided : String → Int → Prop",
            "",
        ]

    body = _defs(answer, names, values, scale)
    for name, claim, why in obligations:
        keyword_ = "axiom" if name in axioms else "theorem"
        closing = "" if name in axioms else " := by decide"
        body += [f"/-- {why} -/", f"{keyword_} {name} : {claim}{closing}", ""]
    body += _confirmed(obligations)

    tail = [
        "/-- Sources this file assumes decided a value. -/",
        f"def assumed_sources : List String := "
        f"[{', '.join(_string(source) for source in sources)}]",
        "",
        "/-- Fields the check did not confirm. No obligation is emitted for these. -/",
        f"def unconfirmed : List String := "
        f"[{', '.join(_string(field) for field in unconfirmed)}]",
        "",
        "/-- Fields dropped because this scale cannot hold their value exactly. -/",
        f"def unrepresentable : List String := "
        f"[{', '.join(_string(field) for field in unrepresentable)}]",
        "",
        "#print axioms confirmed",
        "",
        f"end {namespace}",
    ]
    return "\n".join(head + body + tail) + "\n"
