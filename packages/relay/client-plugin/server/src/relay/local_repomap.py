"""local_repomap.py — a compact code map so a small local model finds the right file.

aider's signature feature is a repo map: instead of dumping whole files, give the
model a ranked outline of the codebase (files, classes, functions) so it can ask
for exactly what it needs. This is the zero-dep version: Python symbols via the
stdlib `ast`, other files listed by path. Bounded output so it never blows the
context of a 7B model.
"""
from __future__ import annotations

import ast
import os
import re

_IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist",
           "build", ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "target"}
DEFAULT_MAX_BYTES = 4096

# Regex symbol patterns per extension (crude vs tree-sitter, but zero-dep and
# enough to navigate). Each pattern's group(1) is the symbol name. Patterns are
# line-anchored and kept conservative to avoid false positives (a noisy map is
# worse than a sparse one). Python is NOT here — it uses the exact ast path.
_LANG = {
    (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"): [
        (re.compile(r"\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"), "fn"),
        (re.compile(r"\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>"), "fn"),
        (re.compile(r"\s*(?:export\s+)?interface\s+(\w+)"), "iface"),
        (re.compile(r"\s*(?:export\s+)?type\s+(\w+)\s*[=<]"), "type"),
        (re.compile(r"\s*(?:export\s+)?(?:const\s+)?enum\s+(\w+)"), "enum"),
    ],
    (".go",): [
        (re.compile(r"\s*func\s+(?:\([^)]*\)\s*)?(\w+)"), "fn"),
        (re.compile(r"\s*type\s+(\w+)\s+(?:struct|interface)"), "type"),
    ],
    (".rs",): [
        (re.compile(r"\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"), "fn"),
        (re.compile(r"\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|union)\s+(\w+)"), "type"),
        (re.compile(r"\s*impl(?:<[^>]*>)?\s+(?:\w+\s+for\s+)?(\w+)"), "impl"),
        (re.compile(r"\s*(?:pub\s+)?mod\s+(\w+)"), "mod"),
        (re.compile(r"\s*macro_rules!\s+(\w+)"), "macro"),
    ],
    (".java", ".kt", ".cs", ".scala"): [
        (re.compile(r"\s*(?:public|private|protected|internal|open|final|abstract|sealed|data|static|partial)?\s*"
                    r"(?:class|interface|enum|record|object)\s+(\w+)"), "type"),
    ],
    (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"): [
        (re.compile(r"\s*(?:class|struct|enum|union)\s+(\w+)"), "type"),
    ],
    (".swift",): [
        (re.compile(r"\s*(?:public|private|internal|open|final|fileprivate)?\s*"
                    r"(?:class|struct|enum|protocol|extension|actor)\s+(\w+)"), "type"),
        (re.compile(r"\s*(?:public|private|internal|open|static)?\s*func\s+(\w+)"), "fn"),
    ],
    (".php",): [
        (re.compile(r"\s*(?:abstract\s+|final\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"\s*(?:interface|trait)\s+(\w+)"), "iface"),
        (re.compile(r"\s*(?:public|private|protected|static|\s)*function\s+(\w+)"), "fn"),
    ],
    (".rb",): [
        (re.compile(r"\s*(?:class|module)\s+(\w+)"), "class"),
        (re.compile(r"\s*def\s+(\w+)"), "fn"),
    ],
}


def _lang_for(name: str):
    ext = os.path.splitext(name)[1].lower()
    for exts, pats in _LANG.items():
        if ext in exts:
            return pats
    return None


def _regex_symbols(path: str, pats, max_symbols: int) -> list:
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                for pat, kind in pats:
                    m = pat.match(line)
                    if m:
                        out.append(f"  {kind} {m.group(1)} (L{i})")
                        break
                if len(out) >= max_symbols:
                    out.append("  ...")
                    return out
    except OSError:
        return []
    return out


def _symbols(path: str, max_symbols: int) -> list:
    """Top-level and one-level-nested def/class names with line numbers."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, ValueError, OSError):
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"  def {node.name} (L{node.lineno})")
        elif isinstance(node, ast.ClassDef):
            out.append(f"  class {node.name} (L{node.lineno})")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(f"    def {sub.name} (L{sub.lineno})")
        if len(out) >= max_symbols:
            out.append("  ...")
            break
    return out


def _cap_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    marker = f"\n[map truncated at {max_bytes} bytes]"
    marker_raw = marker.encode("utf-8")
    if len(marker_raw) >= max_bytes:
        return marker_raw[:max_bytes].decode("utf-8", errors="ignore")
    keep = max_bytes - len(marker_raw)
    return raw[:keep].decode("utf-8", errors="ignore") + marker


DEFAULT_SCAN_CAP = 2000


def _scan(root: str, base: str, scan_cap: int) -> "tuple[list, bool]":
    """Walk `root` (ignoring noise dirs) and return up to `scan_cap` (rel, full,
    name) triples plus whether the cap was hit. Deterministic (sorted dirs + files);
    the cap bounds the walk on a huge repo instead of stopping at the display limit."""
    files, hit = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE)
        for name in sorted(filenames):
            if len(files) >= scan_cap:
                return files, True
            full = os.path.join(dirpath, name)
            files.append((os.path.relpath(full, base).replace(os.sep, "/"), full, name))
    return files, hit


def _imported_modules(full: str) -> set:
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, ValueError, OSError):
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.update(node.module.split("."))
            for alias in node.names:
                mods.add(alias.name)
    return mods


def _import_indegree(scanned: list) -> dict:
    """How many scanned Python files import each file, keyed by its module basename.
    A stdlib approximation of aider's PageRank: the most-imported files rank first."""
    by_module: dict = {}
    for rel, _, name in scanned:
        if name.endswith(".py"):
            by_module.setdefault(name[:-3], []).append(rel)
    deg = {rel: 0 for rel, _, _ in scanned}
    for rel, full, name in scanned:
        if not name.endswith(".py"):
            continue
        for mod in _imported_modules(full):
            for target in by_module.get(mod, ()):
                if target != rel:
                    deg[target] += 1
    return deg


def _rank(scanned: list) -> list:
    """Most-imported first, then code before data, then path (all deterministic)."""
    deg = _import_indegree(scanned)
    return sorted(scanned, key=lambda t: (-deg[t[0]], not t[2].endswith(".py"), t[0]))


def build_repo_map(root: str, *, max_files: int = 40, max_symbols: int = 40,
                   rel_to: "str | None" = None, max_bytes: int = DEFAULT_MAX_BYTES,
                   scan_cap: int = DEFAULT_SCAN_CAP) -> str:
    """A compact, deterministic outline of `root`, RANKED so the most-referenced
    files appear first (not the alphabetically-first, which on a repo past the cap
    could omit the file the model needs). Python files carry their symbols, other
    files are listed by path. The walk is bounded by `scan_cap`, every truncation is
    reported, never silent, and the returned UTF-8 text is capped at `max_bytes`."""
    base = rel_to or root
    scanned, scan_hit = _scan(root, base, scan_cap)
    ranked = _rank(scanned)
    kept = ranked[:max_files]
    py_blocks, other = [], []
    for rel, full, name in kept:
        if name.endswith(".py"):
            syms = _symbols(full, max_symbols)
            py_blocks.append(rel + ("\n" + "\n".join(syms) if syms else ""))
        elif (pats := _lang_for(name)) is not None:
            syms = _regex_symbols(full, pats, max_symbols)
            py_blocks.append(rel + ("\n" + "\n".join(syms) if syms else ""))
        else:
            other.append(rel)
    parts = []
    if py_blocks:
        parts.append("\n".join(py_blocks))
    if other:
        parts.append("other files:\n  " + "\n  ".join(other))
    if len(kept) < len(ranked):
        parts.append(f"[map truncated at {max_files} files; showing the most-referenced]")
    if scan_hit:
        parts.append(f"[repo scan bounded at {scan_cap} files]")
    return _cap_bytes("\n\n".join(parts) if parts else "(empty)", max_bytes)
