"""No harness module goes back to starting or finding a program the unguarded way.

The per-site tests drive the sites that exist today. This one reads every harness
module, so a site added later fails here before anyone writes its test:

- no ``shutil.which``: the guarded lookup is ``safe_program.which``;
- no subprocess call whose argv literal starts with a program name, such as
  ``subprocess.run(["git", ...])``;
- no direct ``safe_program.argv`` outside the helper and the install module:
  ``safe_program.launch`` returns the environment a batch-file child needs too;
- every ``shell=True`` start takes its environment from ``run_env`` or
  ``shell_env``.

Each rule is shown to fire on a small sample first, so a pass is not a rule that
never matches.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent / "harness"
SPAWNS = {"run", "Popen", "check_output", "check_call", "call"}
ARGV_ALLOWED = {"safe_program.py", "lane_install.py"}


def _problems(source: str, name: str) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        owner = func.value.id if (isinstance(func, ast.Attribute)
                                  and isinstance(func.value, ast.Name)) else ""
        attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        where = f"{name}:{node.lineno}"
        if owner == "shutil" and attr == "which":
            out.append(f"{where} shutil.which")
        if owner == "subprocess" and attr in SPAWNS and node.args:
            first = node.args[0]
            if isinstance(first, (ast.List, ast.Tuple)) and first.elts and isinstance(
                    first.elts[0], ast.Constant) and isinstance(first.elts[0].value, str):
                out.append(f"{where} bare program {first.elts[0].value!r}")
        if owner == "safe_program" and attr == "argv" and name not in ARGV_ALLOWED:
            out.append(f"{where} safe_program.argv without launch")
        shell = any(k.arg == "shell" and not (isinstance(k.value, ast.Constant)
                                              and k.value.value is False)
                    for k in node.keywords)
        if shell and (attr in SPAWNS or attr == "spawn_killable"):
            env = next((ast.unparse(k.value) for k in node.keywords if k.arg == "env"), "")
            if "run_env(" not in env and "shell_env(" not in env:
                out.append(f"{where} shell without a guarded env")
    return out


@pytest.mark.parametrize(("sample", "rule"), [
    ("import shutil\nshutil.which('git')\n", "shutil.which"),
    ("import subprocess\nsubprocess.run(['git', 'status'])\n", "bare program"),
    ("from harness import safe_program\nsafe_program.argv(['git'])\n", "without launch"),
    ("import subprocess\nsubprocess.run('pytest', shell=True)\n", "guarded env"),
    ("spawn_killable('pytest', shell=True, env={})\n", "guarded env"),
])
def test_control_each_rule_fires_on_a_sample(sample, rule):
    assert any(rule in problem for problem in _problems(sample, "sample.py"))


def test_control_the_guarded_forms_pass():
    ok = ("import subprocess\nfrom harness import safe_program\n"
          "cmd, env = safe_program.launch(['git', 'status'])\n"
          "subprocess.run(cmd, env=env)\n"
          "subprocess.run('pytest', shell=True, env=run_env())\n")
    assert _problems(ok, "sample.py") == []


def test_no_harness_module_starts_or_finds_a_program_the_unguarded_way():
    found = []
    for path in sorted(HARNESS.rglob("*.py")):
        if "_vendor" in path.parts:
            continue
        found += _problems(path.read_text(encoding="utf-8"), path.name)
    assert found == []
