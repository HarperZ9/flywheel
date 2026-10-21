"""self_improve_units.py -- the smallest separable changes inside a harness edit.

The gate attributes an edit by leaving parts of it out. Attributing by file
lets a harmful line ride into the harness beside real fixes in the same file;
that happened once in 54 incumbents in the first head-to-head. So an edit is
split into change units at one of three granularities:

  line   every deleted line and every inserted line is its own unit
  hunk   every non-equal opcode of the line diff is one unit
  file   every changed file is one unit

A unit id names its file and position, e.g. `scripts/run.py#+3` (insert new
line 3), `scripts/run.py#-2` (delete old line 2), `scripts/run.py@1` (second
hunk) or `scripts/run.py#file`. Adding or removing a whole file is always one
`#file` unit. apply_units rebuilds the tree from the parent plus any subset of
units, so a leave-one-out candidate is well defined. A subset can produce text
that no longer runs; the gate then measures that, which is the point.

Standard library only.
"""
from __future__ import annotations

import difflib

from .self_improve_tree import Tree, component_of, validate

GRANULARITIES = ("line", "hunk", "file")


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _ops(a: str, b: str) -> list[tuple]:
    sm = difflib.SequenceMatcher(None, _lines(a), _lines(b), autojunk=False)
    return [op for op in sm.get_opcodes() if op[0] != "equal"]


def _file_units(path: str, a: str, b: str, granularity: str) -> list[str]:
    if granularity == "file":
        return [f"{path}#file"]
    out: list[str] = []
    for k, (tag, i1, i2, j1, j2) in enumerate(_ops(a, b)):
        if granularity == "hunk":
            out.append(f"{path}@{k}")
            continue
        if tag in ("replace", "delete"):
            out += [f"{path}#-{i}" for i in range(i1, i2)]
        if tag in ("replace", "insert"):
            out += [f"{path}#+{j}" for j in range(j1, j2)]
    return out


def change_units(parent: Tree, child: Tree, granularity: str = "line") -> list[str]:
    """Every unit of the parent->child edit, in path order."""
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}")
    validate(parent), validate(child)
    units: list[str] = []
    for path in sorted(set(parent) | set(child)):
        a, b = parent.get(path), child.get(path)
        if a == b:
            continue
        if a is None or b is None:
            units.append(f"{path}#file")
        else:
            units += _file_units(path, a, b, granularity)
    return units


def _rebuild(path: str, a: str, b: str, keep: set[str]) -> str:
    old, new = _lines(a), _lines(b)
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    out: list[str] = []
    k = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out += old[i1:i2]
            continue
        whole = f"{path}@{k}" in keep
        k += 1
        if whole:
            out += new[j1:j2]
            continue
        out += [old[i] for i in range(i1, i2) if f"{path}#-{i}" not in keep]
        out += [new[j] for j in range(j1, j2) if f"{path}#+{j}" in keep]
    return "".join(out)


def apply_units(parent: Tree, child: Tree, units: list[str]) -> Tree:
    """Parent with only the named units of the parent->child edit applied."""
    keep = set(units)
    out = dict(parent)
    for path in sorted(set(parent) | set(child)):
        a, b = parent.get(path), child.get(path)
        if a == b:
            continue
        if f"{path}#file" in keep or a is None or b is None:
            if f"{path}#file" in keep:
                if b is None:
                    out.pop(path, None)
                else:
                    out[path] = b
            continue
        out[path] = _rebuild(path, a, b, keep)
    return out


def unit_component(unit: str) -> str:
    """The component a unit belongs to."""
    path = unit.split("#", 1)[0].split("@", 1)[0]
    return component_of(path)


def unit_tree(parent: Tree, child: Tree) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """The edit as files, each with its hunks, each with its line units.

    A file added or removed whole has no hunks; it is attributed as one unit.
    """
    out = []
    for path in sorted(set(parent) | set(child)):
        a, b = parent.get(path), child.get(path)
        if a == b:
            continue
        if a is None or b is None:
            out.append((f"{path}#file", []))
            continue
        hunks = []
        for k, (tag, i1, i2, j1, j2) in enumerate(_ops(a, b)):
            lines = [f"{path}#-{i}" for i in range(i1, i2)] if tag != "insert" else []
            lines += [f"{path}#+{j}" for j in range(j1, j2)] if tag != "delete" else []
            hunks.append((f"{path}@{k}", lines))
        out.append((f"{path}#file", hunks))
    return out
