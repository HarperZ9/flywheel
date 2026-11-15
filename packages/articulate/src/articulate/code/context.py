"""articulate.code.context -- what the whole change set says about each test edit.

A test file is never read alone. The change set tells the analyzer three things
a single file cannot:

- where checks went: every check text and every new test across all changed test
  files, so a test moved to another file in the same change is a move, not a
  deletion;
- whether the change also edits non-test Python source, which is the most common
  visible reason a test's expectations shrink (the behavior changed with them);
- which symbols the source edit removed, so a test deleted with its feature is
  declared rather than reported.

Standard library only. Nothing is imported or run.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field

from .pytests import inventory


def is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    if not name.endswith(".py"):
        return False
    return (name.startswith("test_") or name.endswith("_test.py")
            or any(p in ("tests", "test", "testing") for p in parts[:-1]))


def defined_symbols(source) -> set:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def bare(name: str) -> str:
    return name.rsplit("::", 1)[-1]


@dataclass
class World:
    before: Counter = field(default_factory=Counter)   # check text -> count, all files
    after: Counter = field(default_factory=Counter)
    new_names: Counter = field(default_factory=Counter)  # bare names new to their file
    new_bodies: set = field(default_factory=set)
    tests_added: int = 0
    source_changed: bool = False
    removed_symbols: frozenset = frozenset()


def _texts(inv) -> Counter:
    out = Counter()
    if inv is not None:
        for facts in inv.functions.values():
            out.update(c.text for c in facts.checks)
    return out


def _add_file(world, before, after) -> None:
    inv0, inv1 = inventory(before or ""), inventory(after or "")
    world.before.update(_texts(inv0))
    world.after.update(_texts(inv1))
    if inv0 is None or inv1 is None:
        return
    old = inv0.tests()
    for name, facts in inv1.tests().items():
        if name not in old:
            world.new_names[bare(name)] += 1
            world.new_bodies.add(facts.body_dump)
            world.tests_added += 1


def build_world(changes) -> World:
    """One pass over the change set: check texts, new tests, source edits."""
    world, removed = World(), set()
    for change in changes:
        if not change.path.endswith(".py"):
            continue
        if is_test_path(change.path):
            _add_file(world, change.before, change.after)
        elif change.before != change.after:
            world.source_changed = True
            removed |= defined_symbols(change.before or "") - defined_symbols(change.after or "")
    world.removed_symbols = frozenset(removed)
    return world


def world_for_file(path, before, after, removed_symbols=frozenset()) -> World:
    """The world of a change set holding only this one test file."""
    world = World(removed_symbols=frozenset(removed_symbols))
    _add_file(world, before, after)
    return world


@dataclass
class FileContext:
    world: World
    lines0: list
    lines1: list
