"""Every path the gateway dispatches on, read out of the gateway's own source.

A hand-written API document drifts. It drifts silently, because nothing fails
when a route is added and the document is not touched, and the first person to
find out is a caller who trusted it. So nothing here is typed by hand: the
dispatchers in `harness/gateway.py` are parsed, and the paths they compare
against are the inventory.

What this gives up is honest. A path assembled at runtime, or compared through
a helper, is invisible to a parse and will be missing. The inventory is a
lower bound on what the gateway serves, never an upper one, and the
`/openapi.json` built on it says so in its own description. What it buys is
that the document cannot claim a route the code does not dispatch, and a route
added without a description fails a test instead of shipping undocumented.

    from harness.route_inventory import gateway_routes
    for route in gateway_routes():
        print(route.methods, route.path, route.match)
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

GATEWAY = Path(__file__).resolve().parent / "gateway.py"

#: Which dispatcher serves which methods, and what it calls the path. Read
#: off `_gateway_method`: PUT, DELETE and HEAD reach `_route_operation` and
#: then 501, so only the operation routes answer them.
DISPATCHERS = (
    ("_get", "p", ("GET",)),
    ("_post", "p", ("POST",)),
    ("_route_operation", "path", ("GET", "POST", "PUT", "DELETE", "HEAD")),
)

EXACT = "exact"
PREFIX = "prefix"


@dataclass(frozen=True)
class Route:
    """One dispatch target. `match` is exact or prefix, never a template."""

    path: str
    match: str
    methods: tuple[str, ...]
    description: str = ""

    @property
    def key(self) -> str:
        return f"{'|'.join(self.methods)} {self.path}"


def _literals(node: ast.AST, var: str) -> list[tuple[str, str, int]]:
    """Path literals this node compares `var` against, with kind and line."""
    found: list[tuple[str, str, int]] = []
    for inner in ast.walk(node):
        named = (isinstance(inner, ast.Compare)
                 and isinstance(inner.left, ast.Name)
                 and inner.left.id == var)
        if named:
            for op, right in zip(inner.ops, inner.comparators):
                if isinstance(op, (ast.Eq, ast.In)):
                    found += [(EXACT, c.value, c.lineno)
                              for c in ast.walk(right)
                              if isinstance(c, ast.Constant)
                              and isinstance(c.value, str)]
        starts = (isinstance(inner, ast.Call)
                  and isinstance(inner.func, ast.Attribute)
                  and inner.func.attr == "startswith"
                  and isinstance(inner.func.value, ast.Name)
                  and inner.func.value.id == var)
        if starts:
            found += [(PREFIX, c.value, c.lineno) for c in ast.walk(inner)
                      if isinstance(c, ast.Constant)
                      and isinstance(c.value, str)]
    return found


def _comments(source: str) -> dict[int, str]:
    """Trailing `#` text by line number, for lines that hold code as well.

    A comment on its own line describes the block under it, which is not the
    same thing as describing one route, so only trailing comments count. This
    is where route descriptions come from: the author already wrote them
    beside the dispatch, and a description that lives on the dispatch line
    moves when the route moves and dies when the route dies.
    """
    out: dict[int, str] = {}
    code_lines: set[int] = set()
    reader = io.StringIO(source).readline
    for token in tokenize.generate_tokens(reader):
        row = token.start[0]
        if token.type == tokenize.COMMENT:
            if row in code_lines:
                out[row] = token.string.lstrip("#").strip()
        elif token.type not in (tokenize.NL, tokenize.NEWLINE,
                                tokenize.INDENT, tokenize.DEDENT):
            code_lines.add(row)
    return out


def routes_in(source: str) -> list[Route]:
    """Parse one gateway source and return its routes, deduplicated by path.

    A path reached by more than one dispatcher answers to the union of their
    methods, which is why the methods are merged rather than the second entry
    dropped. The description is whatever the author wrote after `#` on the
    dispatch line, and stays empty when nobody wrote one.
    """
    tree = ast.parse(source)
    notes = _comments(source)
    functions = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    merged: dict[str, tuple[str, set[str], str]] = {}
    for name, var, methods in DISPATCHERS:
        fn = functions.get(name)
        if fn is None:
            continue
        for kind, path, line in _literals(fn, var):
            if not path.startswith("/"):
                continue
            match, seen, note = merged.get(path, (kind, set(), ""))
            merged[path] = (match, seen | set(methods),
                            note or notes.get(line, ""))
    return sorted((Route(path, match, tuple(sorted(methods)), note)
                   for path, (match, methods, note) in merged.items()),
                  key=lambda r: r.path)


def undescribed(routes: list[Route] | None = None) -> list[str]:
    """Paths the gateway dispatches on that nobody has described.

    Named rather than counted, because a count is not closable and a list is.
    """
    return [r.path for r in (routes or gateway_routes()) if not r.description]


def gateway_routes() -> list[Route]:
    """The live inventory, parsed from `harness/gateway.py` on every call."""
    return routes_in(GATEWAY.read_text(encoding="utf-8", errors="replace"))
