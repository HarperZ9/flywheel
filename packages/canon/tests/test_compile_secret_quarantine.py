from __future__ import annotations

import io
import json
from pathlib import Path

from canon.canonical_json import canonical_json_text
from canon.exit_codes import EX_SECURITY


FIXTURES = Path(__file__).parent / "fixtures" / "bootstrap"


def _canary() -> str:
    return "sk-" + "compileCanary123456789012345"


def _write_inputs(workspace: Path) -> None:
    workspace.mkdir()
    (workspace / "records.jsonl").write_bytes((FIXTURES / "records.jsonl").read_bytes())
    atom = json.loads((FIXTURES / "atoms.jsonl").read_text(encoding="utf-8").splitlines()[0])
    atom["id"] = "goal-compile-secret-canary"
    atom["value"] = {"summary": _canary()}
    (workspace / "atoms.jsonl").write_text(
        json.dumps(atom, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _base_args(workspace: Path) -> list[str]:
    return [
        "--workspace",
        str(workspace),
        "--records",
        "records.jsonl",
        "--atoms",
        "atoms.jsonl",
        "--target",
        "codex-cli",
    ]


def _run(argv: list[str]) -> tuple[int, str, str]:
    from canon.cli import run_cli

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def _json(stdout: str) -> dict[str, object]:
    payload = json.loads(stdout)
    assert stdout == canonical_json_text(payload)
    return payload


def test_compile_markdown_stdout_refuses_planted_secret_before_emitting_canary(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)

    code, stdout, stderr = _run(["compile", *_base_args(workspace)])

    assert code == EX_SECURITY
    assert stdout == ""
    assert _canary() not in stdout + stderr


def test_compile_json_stdout_refuses_planted_secret_with_secret_quarantine(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)

    code, stdout, stderr = _run(["--json", "compile", *_base_args(workspace)])

    assert code == EX_SECURITY
    assert stderr == ""
    assert _json(stdout)["failure_code"] == "secret_quarantine"
    assert _canary() not in stdout


def test_compile_out_refuses_planted_secret_before_writing_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)

    code, stdout, stderr = _run(["--json", "compile", *_base_args(workspace), "--out", "bundle"])

    assert code == EX_SECURITY
    assert stderr == ""
    assert _json(stdout)["failure_code"] == "secret_quarantine"
    assert _canary() not in stdout
    assert not (workspace / "bundle").exists()
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())
