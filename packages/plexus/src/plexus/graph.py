"""graph.py — render the mesh as a diagram (Mermaid / Graphviz DOT).

Discovery is only useful if you can see it. This turns the mesh into a picture:
organs as nodes, capability-labeled edges as producer -> consumer arrows, with
self-loops and the cross-tool wiring visible at a glance. Mermaid renders in any
Markdown viewer; DOT feeds Graphviz. Pure string output, zero deps.
"""
from __future__ import annotations

from .mesh import Mesh


def _san(node: str) -> str:
    """A Mermaid/DOT-safe node id (organs are simple slugs already, but be safe)."""
    return "".join(c if c.isalnum() else "_" for c in node)


def to_mermaid(mesh: Mesh, *, direction: str = "LR") -> str:
    """A Mermaid flowchart. Cross-tool edges are solid; self-loops dotted."""
    lines = [f"flowchart {direction}"]
    for organ in mesh.organs:
        lines.append(f'  {_san(organ)}["{organ}"]')
    for e in mesh.edges:
        arrow = "-.->" if e.self_loop else "-->"
        lines.append(f'  {_san(e.producer)} {arrow}|"{e.capability}"| {_san(e.consumer)}')
    return "\n".join(lines)


def to_dot(mesh: Mesh) -> str:
    """A Graphviz DOT digraph."""
    lines = ["digraph plexus {", '  rankdir=LR;', '  node [shape=box];']
    for organ in mesh.organs:
        lines.append(f'  "{organ}";')
    for e in mesh.edges:
        attrs = f'label="{e.capability}"' + (", style=dotted" if e.self_loop else "")
        lines.append(f'  "{e.producer}" -> "{e.consumer}" [{attrs}];')
    lines.append("}")
    return "\n".join(lines)
