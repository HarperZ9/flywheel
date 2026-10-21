"""self_improve_tree.py -- a harness as a reviewable tree of text files.

A harness here is everything around a model that the self-improving loop may
edit: the system prompt, guardrails, memory, tool guidance, skills, scripts and
plugin files. It is held as a mapping from a relative POSIX path to file text,
so an edit is a plain diff a reviewer can read and a digest a stranger can
recompute.

The editable surface is explicit. A path outside it is refused rather than
silently dropped, because a loop that quietly ignores part of a proposal reports
a different edit from the one it ran.

Standard library only.
"""
from __future__ import annotations

import difflib
from pathlib import Path, PurePosixPath

from .evidence_json import canonical_sha256

Tree = dict[str, str]

# The components Harness-squared exposes, plus the self-check slot. Every
# component is a top-level file or directory name.
COMPONENTS = (
    "systemprompt.md", "guardrails.md", "memory.md", "tool_guidance.md",
    "skills", "scripts", "sub_agents", "plugins", "checks",
)
# Paths whose edit changes how the harness judges its own output. An edit here
# can raise a contrast score without changing the work, so the gate attributes
# it separately and never lets it ride along with another component.
VERIFICATION_SURFACE = ("checks",)


class TreeError(ValueError):
    """A tree or a path is outside the editable surface."""


def component_of(path: str) -> str:
    """Return the component a relative path belongs to, or raise TreeError.

    A top-level file is its own component. Inside a directory the component is
    the first entry, so `scripts/check.py` and `scripts/summarize.py` are
    separate components and `skills/review/SKILL.md` belongs to `skills/review`.
    That granularity lets the gate measure a self-check edit apart from the
    script it checks.
    """
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or ".." in parts or "\\" in path:
        raise TreeError(f"not a safe relative path: {path!r}")
    head = parts[0]
    if head not in COMPONENTS:
        raise TreeError(f"{path!r} is off the editable surface {COMPONENTS}")
    if head.endswith(".md"):
        if len(parts) != 1:
            raise TreeError(f"{path!r}: a file component cannot hold children")
        return head
    if len(parts) < 2:
        raise TreeError(f"{path!r}: a directory component needs an entry")
    return f"{head}/{parts[1]}"


def validate(tree: Tree) -> Tree:
    """Check every path and value; return the tree unchanged."""
    if not isinstance(tree, dict):
        raise TreeError("a harness tree is a dict of path -> text")
    for path, text in tree.items():
        component_of(path)
        if not isinstance(text, str):
            raise TreeError(f"{path!r} must map to text")
    return tree


def digest(tree: Tree) -> str:
    """sha256 over the canonical JSON of the validated tree."""
    return canonical_sha256(validate(dict(tree)))


def unified_diff(parent: Tree, child: Tree) -> str:
    """A deterministic unified diff from parent to child, path-sorted."""
    out: list[str] = []
    for path in sorted(set(parent) | set(child)):
        a, b = parent.get(path), child.get(path)
        if a == b:
            continue
        out.extend(difflib.unified_diff(
            (a or "").splitlines(keepends=True), (b or "").splitlines(keepends=True),
            fromfile=f"a/{path}" if a is not None else "/dev/null",
            tofile=f"b/{path}" if b is not None else "/dev/null", n=2))
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
    return "".join(out)


def changed_components(parent: Tree, child: Tree) -> list[str]:
    """The sorted components whose files differ between parent and child."""
    changed = {component_of(p) for p in set(parent) | set(child)
               if parent.get(p) != child.get(p)}
    return sorted(changed)


def restrict(parent: Tree, child: Tree, components: list[str]) -> Tree:
    """Apply only the named components of the parent->child edit to parent."""
    keep = set(components)
    out = {p: t for p, t in parent.items() if component_of(p) not in keep}
    out.update({p: t for p, t in child.items() if component_of(p) in keep})
    return out


def touches_verification(components: list[str]) -> bool:
    return any(c.split("/")[0] in VERIFICATION_SURFACE for c in components)


def write_tree(tree: Tree, root: Path) -> Path:
    """Materialize a tree under root; refuses unsafe paths."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for path, text in validate(dict(tree)).items():
        dest = root / PurePosixPath(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return root


def read_tree(root: Path) -> Tree:
    """Read every file under root that sits on the editable surface.

    Files off the surface raise, so a harvested edit cannot smuggle a file the
    loop would never review.
    """
    root = Path(root)
    tree: Tree = {}
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = f.relative_to(root).as_posix()
        component_of(rel)
        tree[rel] = f.read_text(encoding="utf-8")
    return tree
