"""I2, static half: harness code writes only into registered or exempt places.

Three shapes are found by reading the AST of every harness module:
  1. path joins under `state_root`, `run_root`, `flywheel_home`, a `home`
     that its module reads from FLYWHEEL_HOME, or `run_root_default()`;
  2. `Path("...")` literals in modules that write through the pinned private
     filesystem (`write_new_or_same`, `publish_bytes`), by first segment;
  3. `mkdtemp(prefix=..., dir=...)` calls, by prefix.
What this cannot see is stated in the design: paths built from variables, and
stores other processes write. The dynamic sweep covers the second gap.
"""
import ast
from dataclasses import dataclass
from pathlib import Path

from harness import trace_inventory

HARNESS = Path(__file__).resolve().parents[1] / "harness"
_ROOTS = {"state_root": "state", "run_root": "run", "flywheel_home": "home",
          "run_root_default": "run"}
_PINNED_WRITES = ("write_new_or_same", "publish_bytes")


@dataclass(frozen=True)
class Finding:
    root: str
    segment: str
    module: str
    line: int


def _name(node):
    if isinstance(node, ast.Call):
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "home" and getattr(getattr(func, "value", None), "id", None) == "Path":
            return "os_home"  # the account's home directory, not FLYWHEEL_HOME
        if name in ("Path", "str") and node.args:
            return _name(node.args[0])
        if name == "get" and node.args and isinstance(node.args[0], ast.Constant):
            return "FLYWHEEL_HOME" if node.args[0].value == "FLYWHEEL_HOME" else None
        return name
    return getattr(node, "id", None) or getattr(node, "attr", None)


def _root(node, reads_home):
    name = _name(node)
    if name == "FLYWHEEL_HOME" or (name == "home" and reads_home):
        return "home"
    return _ROOTS.get(name)


def _flatten(node):
    segments = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = node.right
        segments.insert(0, right.value if isinstance(right, ast.Constant)
                        and isinstance(right.value, str) else None)
        node = node.left
    return node, segments


def _joins(tree, reads_home, module):
    inner = {id(n.left) for n in ast.walk(tree)
             if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)) or id(node) in inner:
            continue
        base, segments = _flatten(node)
        root = _root(base, reads_home)
        if root is None or not segments or segments[0] is None:
            continue
        head = segments[0].split("/")[0]
        if root == "home" and head == "state" and len(segments) > 1 and segments[1]:
            root, head = "state", segments[1].split("/")[0]
        yield Finding(root, head, module, node.lineno)


def _pinned_literals(tree, source, module):
    if not any(f".{m}(" in source for m in _PINNED_WRITES):
        return
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Path"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            head = node.args[0].value.split("/")[0]
            if head and not head.startswith("."):
                yield Finding("state", head, module, node.lineno)


def _mkdtemps(tree, module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _name(node) == "mkdtemp":
            words = {k.arg: k.value for k in node.keywords}
            prefix = words.get("prefix")
            if "dir" in words and isinstance(prefix, ast.Constant):
                yield Finding("any", f"{prefix.value}*", module, node.lineno)


def scan_source(source, module):
    tree = ast.parse(source)
    reads_home = "FLYWHEEL_HOME" in source
    yield from _joins(tree, reads_home, module)
    yield from _pinned_literals(tree, source, module)
    yield from _mkdtemps(tree, module)


def scan_harness():
    for path in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = path.relative_to(HARNESS.parent).as_posix()
        yield from scan_source(path.read_text(encoding="utf-8"), module)


def test_scanner_finds_each_shape_in_planted_source():
    """False-success control: the scan must see the writes it exists to see."""
    planted = (
        "import os, tempfile\nfrom pathlib import Path\n"
        "a = state_root / 'planted-store' / 'v1'\n"
        "b = Path(run_root) / 'planted.json'\n"
        "c = self.flywheel_home / 'state' / 'planted-state'\n"
        "d = Path(os.environ.get('FLYWHEEL_HOME', '')) / 'planted-home'\n"
        "fs.write_new_or_same(Path('planted-pinned/v1') / 'x', b'')\n"
        "e = tempfile.mkdtemp(prefix='planted-tmp-', dir=parent)\n")
    found = {(f.root, f.segment) for f in scan_source(planted, "planted.py")}
    assert found == {("state", "planted-store"), ("run", "planted.json"),
                     ("state", "planted-state"), ("home", "planted-home"),
                     ("state", "planted-pinned"), ("any", "planted-tmp-*")}


def test_an_unregistered_planted_join_is_reported():
    finding = next(scan_source("x = state_root / 'nobody-registered-me'\n", "p.py"))
    assert trace_inventory.explain_static(finding.root, finding.segment,
                                          finding.module) is None


def test_every_harness_write_location_is_registered_or_exempt():
    findings = list(scan_harness())
    assert len(findings) > 40, "the scan must see the real write sites"
    unexplained = sorted(
        f"{f.module}:{f.line} {f.root}/{f.segment}" for f in findings
        if trace_inventory.explain_static(f.root, f.segment, f.module) is None)
    assert unexplained == []


def test_the_known_trace_stores_are_among_the_findings():
    seen = {(f.root, f.segment) for f in scan_harness()}
    for expected in [("state", "gateway-agent-traces"), ("home", "store.db"),
                     ("run", "snapshots"), ("run", "fold_index.json"),
                     ("any", "native-cli-profile-*"), ("run", "bench")]:
        assert expected in seen
