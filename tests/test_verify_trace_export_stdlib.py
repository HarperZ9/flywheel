"""EN-C1: the export verifier imports only the standard library, and the copy
an export carries runs on a bare interpreter with site-packages disabled."""
import ast
from pathlib import Path
import subprocess
import sys

VERIFIER = Path(__file__).resolve().parents[1] / "harness" / "trace_export_verify.py"


def test_the_verifier_imports_only_the_standard_library():
    tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative import: the copy runs alone"
            names.add(node.module.split(".")[0])
    assert names and names <= set(sys.stdlib_module_names) | {"__future__"}, names


def test_the_verifier_is_on_the_stdlib_gate_entry_points():
    gate = (VERIFIER.parents[1] / "scripts" / "check_verifier_stdlib.py").read_text()
    assert '"trace_export_verify"' in gate


def test_the_copied_verifier_runs_isolated(tmp_path):
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "verify.py").write_bytes(VERIFIER.read_bytes())
    done = subprocess.run([sys.executable, "-I", "-S", str(folder / "verify.py"), str(folder)],
                          capture_output=True, text=True, cwd=tmp_path)
    assert done.returncode == 2 and done.stdout.startswith("UNVERIFIABLE")
    assert "manifest" in done.stdout
