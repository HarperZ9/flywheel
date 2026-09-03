"""check_ui_coverage.py -- which engine routes the native client can reach.

The desktop app renders the engine. A route with no client reference is a
capability the operator cannot get to, so the gap is worth measuring rather
than assuming, and worth freezing so it only shrinks.

Reachability, not grep. `_route_operation` claims `/api/agent` and
`/api/operations/` and returns True before `_gateway_method` calls its
fallback, so the `/api/agent` branch inside `_post` is dead code. Counting it
as a live route inflates the denominator and hides the real gap; an earlier
hand audit did exactly that. The dispatch model is read from the source here
rather than hardcoded.

Run: python scripts/check_ui_coverage.py [--list]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATEWAY = ROOT / "harness" / "gateway.py"
DART = ROOT / "desktop" / "lib"

# Frozen at the current gap. This may only shrink: a route that gains a native
# surface leaves the list and cannot come back, and a new unreferenced route
# fails the gate.
BASELINE = 21


def _api_strings(node: ast.AST) -> set:
    """Every /api literal this function dispatches on."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare):
            for side in [sub.left, *sub.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    if side.value.startswith("/api"):
                        found.add(side.value)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == "startswith":
                for arg in sub.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.startswith("/api"):
                            found.add(arg.value)
    return found


def live_routes() -> tuple[set, set]:
    """(reachable, dead) route literals, per the handler's own dispatch."""
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8", errors="replace"))
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef) and n.name == "_Handler")
    methods = {n.name: n for n in handler.body if isinstance(n, ast.FunctionDef)}
    claim = _api_strings(methods["_route_operation"]) if "_route_operation" in methods else set()
    exact = {c for c in claim if not c.endswith("/")}
    prefix = {c for c in claim if c.endswith("/")}

    def claimed(route: str) -> bool:
        return route in exact or any(route.startswith(p) for p in prefix)

    live, dead = set(), set()
    for name, fn in methods.items():
        if name == "_route_operation":
            continue
        for route in _api_strings(fn):
            if name in ("_get", "_post") and claimed(route):
                dead.add(route)
            else:
                live.add(route)
    # The operation route serves what it claims.
    live |= {c.rstrip("/") for c in claim if c.rstrip("/")}
    return {r.rstrip("/") for r in live if r.rstrip("/") != "/api"}, dead


def client_routes() -> set:
    """Every /api path the Flutter client names. A bare /api is a base-URL
    fragment, never a capability reference, and prefix-matches everything."""
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in DART.rglob("*.dart"))
    found = {m.rstrip("/") for m in re.findall(r"(/api/[A-Za-z0-9_\-/]*)", text)}
    return {f for f in found if f and f != "/api"}


def main() -> int:
    live, dead = live_routes()
    ui = client_routes()
    # Only a client path strictly BELOW a route reaches it; the reverse would
    # let one broad reference claim a whole family.
    covered = {r for r in live
               if r in ui or any(u.startswith(r + "/") for u in ui)}
    missing = sorted(live - covered)

    print(f"engine routes reachable : {len(live)}")
    print(f"dead (never dispatched) : {len(dead)}"
          + (f"  {sorted(dead)}" if dead else ""))
    print(f"surfaced in the client  : {len(covered)}")
    print(f"not surfaced            : {len(missing)}  (frozen at {BASELINE})")
    pct = 100.0 * len(covered) / len(live) if live else 0.0
    print(f"coverage                : {pct:.1f}%")

    if "--list" in sys.argv:
        for route in missing:
            print(f"  {route}")

    if len(missing) > BASELINE:
        new = set(missing)
        print(f"\nFAIL: {len(missing) - BASELINE} route(s) lost their native "
              f"surface, or a new unreferenced route landed.")
        print("The list only shrinks. Surface it, or explain the regression.")
        for route in sorted(new):
            print(f"  {route}")
        return 1
    if len(missing) < BASELINE:
        print(f"\nBASELINE STALE: {BASELINE - len(missing)} route(s) gained a "
              f"surface. Lower BASELINE to {len(missing)} to lock the gain in.")
        return 1
    print("\nui coverage gate clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
