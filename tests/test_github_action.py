"""Falsifiers for the repository's GitHub Action (action.yml).

The file is read as text: the runtime has no YAML parser and the checks are
about what the step scripts contain. The end-to-end run lives in
.github/workflows/action-smoke.yml against a scripted model.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = (ROOT / "action.yml").read_text(encoding="utf-8")


def _run_blocks():
    return re.findall(r"run: \|\n((?:        .*\n|\n)+)", ACTION)


def test_inputs_are_declared():
    for name in ("prompt", "mode", "version", "package", "python-version",
                 "working-directory", "backend", "max-steps", "test-cmd", "allow-unsandboxed"):
        assert re.search(rf"^  {re.escape(name)}:", ACTION, re.M), name


def test_no_input_is_spliced_into_a_shell_script():
    # Inputs reach the scripts through env only; `${{ inputs.x }}` inside a run
    # block would let a prompt carrying shell syntax run as code.
    blocks = _run_blocks()
    assert blocks
    assert not any("${{" in block for block in blocks)


def test_third_party_actions_are_pinned_by_commit():
    for ref in re.findall(r"uses: ([^\s#]+)", ACTION):
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_the_ledger_is_kept_even_when_the_run_fails():
    keep = ACTION.split("- name: Keep the ledger", 1)[1]
    assert "if: always()" in keep and "flywheel-home/sessions" in keep


def test_the_run_uses_print_mode_with_json():
    assert 'flywheel code -p "$FW_PROMPT"' in ACTION and "--output-format json" in ACTION


def test_the_smoke_workflow_runs_this_action_against_a_stub():
    smoke = (ROOT / ".github" / "workflows" / "action-smoke.yml").read_text(encoding="utf-8")
    assert "uses: ./" in smoke and "ci_stub_model.py" in smoke and "package: ." in smoke
