"""The restricted source companion never reaches the pre-action monitor.

harness/local_tools.py is in the reviewed companion closure because the
gateway import chain loads it. ToolExecutor.execute now imports
harness.preaction (whose judge layer is an HTTP model client) and
harness.local_tools_receipt. Both imports sit inside method bodies, and the
companion (model-free, no network, no exec, no write) never builds a
ToolExecutor. These tests pin that boundary: the closure excludes the monitor,
no reviewed module imports an unreviewed local module at import time, and the
extracted companion answers every request with the monitor absent.
"""
import ast
import json
import os
from pathlib import Path
import sys
import tomllib
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
MONITOR = ('harness/preaction/', 'harness/local_tools_receipt.py')


def _closure():
    return json.loads((ROOT / 'scripts/source_tool_closure.json').read_text(encoding='utf-8'))


def _resolve(module, level, package):
    """Map an import to a repo-relative harness path, or None for stdlib/third party."""
    if level:
        base = package.split('.')[: len(package.split('.')) - level + 1]
        dotted = '.'.join(base + ([module] if module else []))
    else:
        dotted = module or ''
    if dotted != 'harness' and not dotted.startswith('harness.'):
        return None
    stem = dotted.replace('.', '/')
    for candidate in (stem + '.py', stem + '/__init__.py'):
        if (ROOT / candidate).is_file():
            return candidate
    return None


def _import_time_targets(path):
    """Local modules imported at module or class scope; function bodies are lazy."""
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    package = path[:-3].replace('/', '.')
    if not path.endswith('__init__.py'):
        package = package.rsplit('.', 1)[0]
    else:
        package = package[: -len('.__init__')]
    found = set()

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Import):
                found.update(filter(None, (_resolve(a.name, 0, package) for a in child.names)))
            elif isinstance(child, ast.ImportFrom):
                target = _resolve(child.module, child.level, package)
                if target:
                    found.add(target)
                for alias in child.names:  # "from . import x" names a submodule
                    sub = _resolve(f'{child.module + "." if child.module else ""}{alias.name}',
                                   child.level, package)
                    if sub:
                        found.add(sub)
            visit(child)
    visit(tree)
    return found


def test_closure_excludes_the_preaction_monitor():
    names = _closure()
    assert len(names) == 82
    assert not [name for name in names if name.startswith(MONITOR)]
    assert 'harness/local_tools.py' in names and 'harness/tool_mcp.py' in names


def test_no_reviewed_module_imports_an_unreviewed_local_module_at_import_time():
    names = _closure()
    escapes = {path: sorted(t for t in _import_time_targets(path) if t not in names)
               for path in names if path.endswith('.py')}
    assert {path: hits for path, hits in escapes.items() if hits} == {}


def test_monitor_imports_in_local_tools_stay_inside_method_bodies():
    # A future edit that hoists either import to module scope fails here, and
    # the closure check above fails with it.
    targets = _import_time_targets('harness/local_tools.py')
    assert not [t for t in targets if t.startswith(MONITOR)]
    text = (ROOT / 'harness/local_tools.py').read_text(encoding='utf-8')
    assert 'from .preaction.executor_bridge import' in text
    assert 'from .local_tools_receipt import' in text


def test_extracted_companion_runs_every_request_without_the_monitor(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    from scripts.check_source_tool_plugin import check
    if os.name != 'nt':
        pytest.skip('existing bounded MCP process runner is Windows-specific')
    archive = bundle(tmp_path / 'build', dev=True)
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
    assert 'server/harness/local_tools.py' in names
    assert not [n for n in names if n.startswith(tuple('server/' + m for m in MONITOR))]
    # check() runs the extracted server isolated (-I -S -B) through initialize,
    # status, receipt proofs, resources and seven denied tools with every allow
    # flag set. A path into the monitor would raise ImportError and fail it.
    receipt = check(archive, tmp_path / 'acceptance', VERSION, python=sys.executable, dev=True)
    assert receipt['status'] == 'PASS'
