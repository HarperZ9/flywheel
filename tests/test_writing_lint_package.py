"""Package parity for the writing linter public surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_writing as script_check  # noqa: E402
import writing_profiles as script_profiles  # noqa: E402
from harness.writing_lint import check as package_check  # noqa: E402
from harness.writing_lint import check_writing as package_check_writing  # noqa: E402
from harness.writing_lint import profiles as package_profiles  # noqa: E402


def _run(args: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _venv_python(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def test_scripts_are_import_shims_for_packaged_linter(tmp_path: Path) -> None:
    assert script_check.check_text is package_check.check_text
    assert script_check.check_text is package_check_writing.check_text
    assert script_check.score_file is package_check.score_file
    assert script_check.score_file is package_check_writing.score_file
    assert script_check.delta is package_check.delta
    assert script_check.delta is package_check_writing.delta
    assert script_profiles.load is package_profiles.load

    old = "We utilize a seamless tool. The result was checked by reviewers."
    new = "Reviewers checked the tool. The result holds."
    for name in ("readme", "research", "narrative"):
        assert package_check.check_text(old, package_profiles.load(name)) == script_check.check_text(
            old, script_profiles.load(name)
        )
        assert package_check.delta(old, new, package_profiles.load(name)) == script_check.delta(
            old, new, script_profiles.load(name)
        )

    source = tmp_path / "sample.py"
    source.write_text(
        '\"\"\"We utilize a seamless tool.\"\"\"\n'
        'VALUE = "leverage in executable data"\n'
        '# The file was read by the parser.\n',
        encoding="utf-8",
    )
    assert package_check.score_file(str(source), package_profiles.load("chat")) == script_check.score_file(
        str(source), script_profiles.load("chat")
    )


def test_module_cli_matches_script_cli_for_json_delta_and_gate(tmp_path: Path) -> None:
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    bad = tmp_path / "bad.md"
    old.write_text("We utilize a seamless tool. The result was checked by reviewers.\n", encoding="utf-8")
    new.write_text("Reviewers checked the tool. The result holds.\n", encoding="utf-8")
    bad.write_text("We utilize a seamless tool.\n", encoding="utf-8")

    cases = [
        (["--json", "--profile", "research", str(new)], 0),
        (["--delta", str(old), str(new), "--profile", "readme", "--json"], 0),
        (["--gate", "--profile", "research", str(bad)], 1),
    ]
    for args, code in cases:
        script = _run([sys.executable, str(ROOT / "scripts" / "check_writing.py"), *args])
        module = _run([sys.executable, "-m", "harness.writing_lint.check", *args])
        named_module = _run([sys.executable, "-m", "harness.writing_lint.check_writing", *args])
        assert script.returncode == code, script.stderr
        assert module.returncode == code, module.stderr
        assert named_module.returncode == code, named_module.stderr
        if "--json" in args:
            assert json.loads(module.stdout) == json.loads(script.stdout)
            assert json.loads(named_module.stdout) == json.loads(script.stdout)
        else:
            assert module.stdout == script.stdout
            assert named_module.stdout == script.stdout
        assert module.stderr == ""
        assert named_module.stderr == ""


def test_wheel_install_exposes_writing_lint_without_scripts(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    built = _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--no-index",
            "-w",
            str(wheelhouse),
            str(ROOT),
        ]
    )
    assert built.returncode == 0, built.stderr

    env_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    py = _venv_python(env_dir)
    installed = _run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "flywheel-verify",
        ]
    )
    assert installed.returncode == 0, installed.stderr

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    doc = isolated / "doc.md"
    doc.write_text("We utilize a seamless tool.\n", encoding="utf-8")
    probe = _run(
        [
            str(py),
            "-c",
            (
                "import json; "
                "from harness.writing_lint import check_writing, profiles; "
                "r = check_writing.check_text('We utilize a seamless tool.', profiles.load('research')); "
                "print(json.dumps(r['hard'], sort_keys=True))"
            ),
        ],
        cwd=isolated,
    )
    assert probe.returncode == 0, probe.stderr
    assert '\"banned_word\"' in probe.stdout

    cli = _run(
        [str(py), "-m", "harness.writing_lint.check", "--json", "--profile", "research", str(doc)],
        cwd=isolated,
    )
    assert cli.returncode == 0, cli.stderr
    payload = json.loads(cli.stdout)
    assert payload["files"][0]["path"] == str(doc)
    assert payload["does_not_prove"] == package_check.DOES_NOT_PROVE
