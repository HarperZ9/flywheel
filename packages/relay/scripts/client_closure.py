"""The modules the plugin's server can load, found by reading their imports.

The walk starts at the client entry point (client-plugin/server/serve.py) and
follows every import of the package, at module level and inside functions,
relative or absolute. An import on a line ending in SKIP_MARK is not followed:
it sits on a branch the plugin launch profile never takes. The isolated launch
tests start the server from the plugin folder alone to prove the closure is
complete.
"""
import ast
from pathlib import Path

SKIP_MARK = '# not in the plugin profile'


def _module_file(src, dotted):
    """The file for a dotted module under src, or None outside the tree."""
    base = Path(src, *dotted.split('.'))
    for path in (base / '__init__.py', base.with_suffix('.py')):
        if path.is_file():
            return path
    return None


def _imports(path, dotted, package):
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    parent = dotted if path.name == '__init__.py' else dotted.rpartition('.')[0]
    for node in ast.walk(ast.parse('\n'.join(lines))):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if lines[node.lineno - 1].rstrip().endswith(SKIP_MARK):
            continue
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names if a.name.split('.')[0] == package)
            continue
        if node.level:
            anchor = parent.split('.')[:len(parent.split('.')) - node.level + 1]
            base = '.'.join(anchor + ([node.module] if node.module else []))
        else:
            base = node.module or ''
        if base.split('.')[0] != package:
            continue
        yield base
        yield from (f'{base}.{a.name}' for a in node.names)


def closure(src, package, entry):
    """Relative file names under src/<package> reachable from the entry script."""
    seen, files = set(), set()
    todo = [m for m in _imports(Path(entry), '__entry__', package)]
    while todo:
        dotted = todo.pop()
        parts = dotted.split('.')
        for i in range(1, len(parts) + 1):  # a module loads its packages first
            name = '.'.join(parts[:i])
            if name in seen:
                continue
            seen.add(name)
            path = _module_file(src, name)
            if path is None:
                continue
            files.add(path.relative_to(Path(src, package)).as_posix())
            todo.extend(_imports(path, name, package))
    return files
