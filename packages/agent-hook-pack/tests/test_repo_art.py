"""The README's diagrams are generated from a spec, so they can go stale the way any
other derived file goes stale: somebody adds a pattern, nobody re-renders, and the
picture describes a version of agent-hook-pack that no longer exists. The gate
re-renders from the spec and compares bytes. This runs the gate under pytest and asserts
on its receipt, so a drifted drawing fails the suite instead of quietly shipping."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "agent-hook-pack.art.json"

GATES = (
    "spec.present", "art.matches_spec", "art.render_is_deterministic",
    "art.identity_per_repository", "art.seed_is_recorded",
    "art.no_local_paths_or_em_dashes", "art.spec_words_reach_the_drawing",
    "art.note_survives_the_wrapper", "art.return_edge_stays_on_its_row",
    "art.every_illustration_is_shown", "art.tagline_stays_inside_its_rule",
    "art.outcome_fits_its_box", "art.card_draws_shapes_not_digits",
    "art.card_text_fits_its_column", "art.card_widths_bound_every_face",
    "art.card_draws_measured_characters", "art.card_carries_one_mark",
    "art.card_alt_reaches_the_readme", "art.the_gate_can_fail",
)

DRAWINGS = ("docs/art/agent-hook-pack-header.svg", "docs/art/proposal-lane.svg",
            "docs/art/staged-sweep-lane.svg", "docs/art/audit-findings.svg")


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "agent-hook-pack.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_card_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/agent-hook-pack.art.json"]
    drawn = {out["file"]: out for out in receipt["outputs"]}
    assert set(drawn) == set(DRAWINGS)
    for path, out in drawn.items():
        assert len(out["sha256"]) == 64, path
        assert out["bytes"] > 0, path


def test_a_gate_that_cannot_fail_is_not_a_gate(tmp_path, monkeypatch):
    """Point the outcome-box check at a note too wide for its box and it has to
    complain. Without this, a green suite proves only that the gate ran."""
    sys.path.insert(0, str(_REPO / "tools"))
    import check_repo_art as gate
    spec = json.loads(_SPEC.read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "agent-hook-pack.art.json").write_text(json.dumps(spec),
                                                       encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# audit-findings.svg lists the nine findings an audit can return, proposal-lane.svg
# says what block-secrets.py does with a proposed call, and staged-sweep-lane.svg
# says what verify-no-secrets.sh reads. Those are claims about the package and the
# shipped hooks, so nothing under tools/ can settle them. Every row and every stage
# below is driven against the code that ships.

from agent_hook_pack import hook_pack  # noqa: E402

HOOKS = _REPO / "src" / "agent_hook_pack" / "hooks"

# Assembled here rather than committed whole, which is the rule this package sets
# for its own fixtures. Each one is the shape a rule matches, not a live value.
SHAPES = {"secret_pattern_0": "ghp_" + "A" * 24, "secret_pattern_1": "sk-" + "b" * 24,
          "secret_pattern_2": "AKIA" + "ABCDEFGHIJKLMNOP",
          "secret_pattern_3": "-----BEGIN RSA PRIVATE KEY-----"}


def _card() -> dict:
    spec = json.loads(_SPEC.read_text("utf-8"))
    return next(c for c in spec["cards"] if c["file"] == "audit-findings.svg")


def _hook(root: Path, name: str, body: str = "echo ok\n") -> Path:
    line = "#!/usr/bin/env python\n" if name.endswith(".py") else "#!/usr/bin/env bash\n"
    path = root / name
    path.write_text(line + body, encoding="utf-8")
    return path


def _five(root: Path) -> None:
    for name in hook_pack.EXPECTED_HOOKS:
        _hook(root, name)


def _codes(root: Path) -> set:
    return {code for _, code in hook_pack.audit_hooks(root)}


BROKEN = {
    "hook_empty": ("block-secrets.py", "   \n"),
    "shebang_missing": ("lint-on-save.sh", "echo ok\n"),
    "shebang_unexpected": ("block-secrets.py", "#!/bin/sh\necho ok\n"),
    **{c: ("check-branch.sh", '#!/usr/bin/env bash\nTOKEN="' + v + '"\n')
       for c, v in SHAPES.items()},
}


def _scenarios(tmp_path: Path) -> dict:
    """One directory per finding, each built to raise exactly that one."""
    made = {"hook_dir_missing": tmp_path / "absent"}
    short = tmp_path / "short"
    short.mkdir()
    for name in sorted(hook_pack.EXPECTED_HOOKS)[1:]:
        _hook(short, name)
    made["required_hook_missing"] = short
    for code, (name, body) in BROKEN.items():
        root = tmp_path / code
        root.mkdir()
        _five(root)
        (root / name).write_text(body, encoding="utf-8")
        made[code] = root
    return made


def test_the_card_draws_every_finding_the_audit_can_raise(tmp_path):
    """A row drawn for a code the audit never emits, or a code emitted and not
    drawn, makes the table a description of a different tool."""
    scenarios = _scenarios(tmp_path)
    drawn = [f["key"] for f in _card()["fields"]]
    assert set(drawn) == set(scenarios)
    assert len(drawn) == 9
    for code, root in scenarios.items():
        assert code in _codes(root), code


def test_each_row_is_raised_on_its_own(tmp_path):
    """Every scenario is otherwise a clean directory, so a row that only ever
    appears alongside another row would be misdrawn as a separate finding."""
    for code, root in _scenarios(tmp_path).items():
        assert _codes(root) == {code}, code


def test_the_packaged_hooks_raise_nothing():
    """The five hooks that ship are the directory the audit runs against by
    default, and they have to be clean for any of the above to mean anything."""
    assert hook_pack.audit_hooks(hook_pack.HOOK_DIR) == []
    assert len(hook_pack.EXPECTED_HOOKS) == 5
    assert len(hook_pack.SENSITIVE_PATTERNS) == 4


def test_a_missing_directory_is_reported_on_its_own(tmp_path):
    """Drawn as the one finding that arrives alone, because there is nothing
    left to inspect once the source path is gone."""
    absent = tmp_path / "absent"
    assert hook_pack.audit_hooks(absent) == [(str(absent), "hook_dir_missing")]


def test_the_marked_row_is_the_one_that_stops_its_own_inspection(tmp_path):
    """The accent claims an empty hook is never checked for a shebang or for a
    token. Give one an empty body and both later checks have to stay quiet."""
    marked = [f["key"] for f in _card()["fields"] if f.get("tone", "none") != "none"]
    assert marked == ["hook_empty"]
    root = tmp_path / "hooks"
    root.mkdir()
    _five(root)
    (root / "check-branch.sh").write_text("", encoding="utf-8")
    for _, code in hook_pack.audit_hooks(root):
        assert code == "hook_empty"


def _propose(payload) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOKS / "block-secrets.py")],
                          input=text, capture_output=True, text=True)


def test_an_ordinary_path_is_allowed_through():
    """The allowed outcome. Nothing about the call matches a name or a part, so
    the hook exits zero and says nothing."""
    out = _propose({"tool_name": "Read", "tool_input": {"file_path": "src/main.py"}})
    assert out.returncode == 0
    assert out.stderr == ""


def test_a_sensitive_name_is_blocked_and_the_reason_names_the_path():
    """The blocked outcome, and the reason stage. Exit two is what stops the
    call, and the path has to appear in what the calling tool shows."""
    out = _propose({"tool_name": "Read", "tool_input": {"file_path": "app/.env"}})
    assert out.returncode == 2
    assert "app/.env" in out.stderr


def test_a_write_to_a_template_is_scaffolding_and_passes():
    """The scaffold stage. Creating a .env is not the same as reading one, so
    only Read and Edit are stopped."""
    for tool, code in (("Write", 0), ("Read", 2), ("Edit", 2)):
        out = _propose({"tool_name": tool, "tool_input": {"file_path": ".env.local"}})
        assert out.returncode == code, tool


def test_a_credential_directory_is_matched_as_a_whole_part():
    """The components stage, and the reason it is drawn as parts rather than as
    a substring. A real key directory is blocked and a module that merely reads
    like one is not."""
    blocked = _propose({"tool_name": "Read",
                        "tool_input": {"file_path": "/home/a/.ssh/config"}})
    assert blocked.returncode == 2
    assert ".ssh" in blocked.stderr
    allowed = _propose({"tool_name": "Read",
                        "tool_input": {"file_path": "src/private_key_utils.py"}})
    assert allowed.returncode == 0


def test_a_call_with_no_file_path_has_nothing_to_judge():
    """The payload stage. A tool call that names no file is let through rather
    than guessed about."""
    assert _propose({"tool_name": "Bash", "tool_input": {"command": "ls"}}).returncode == 0


def test_a_hook_that_cannot_read_its_input_exits_one():
    """The return edge, drawn from error back to the exit code. One and two are
    both non-zero, and only one of them means the check actually ran."""
    out = _propose("this is not json")
    assert out.returncode == 1
    assert "Hook error" in out.stderr


def _bash(script: Path, cwd: Path) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not on PATH")
    return subprocess.run([bash, str(script)], cwd=cwd, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
    return root


def test_outside_a_working_tree_the_sweep_does_nothing(tmp_path):
    """The not-a-repository outcome. There is no index to read, so the hook
    exits zero rather than reporting a clean sweep it never ran."""
    out = _bash(HOOKS / "verify-no-secrets.sh", tmp_path)
    assert out.returncode == 0
    assert out.stderr == ""


def test_a_staged_secret_is_named_and_the_turn_is_stopped(tmp_path):
    """The blocked outcome. A credential shape assembled at runtime is staged,
    and the sweep has to find it while it is still only staged."""
    root = _repo(tmp_path)
    (root / "deploy.sh").write_text(f'AWS_KEY={SHAPES["secret_pattern_2"]}\n',
                                    encoding="utf-8")
    subprocess.run(["git", "add", "deploy.sh"], cwd=root, check=True,
                   capture_output=True)
    out = _bash(HOOKS / "verify-no-secrets.sh", root)
    assert out.returncode == 2
    assert "deploy.sh" in out.stderr
    assert SHAPES["secret_pattern_2"] not in out.stderr


def test_a_staged_env_file_is_refused_by_name(tmp_path):
    """The base-names stage. The file's contents are never the question here,
    because the name alone is enough."""
    root = _repo(tmp_path)
    (root / ".env").write_text("PORT=8080\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env"], cwd=root, check=True,
                   capture_output=True)
    out = _bash(HOOKS / "verify-no-secrets.sh", root)
    assert out.returncode == 2
    assert "SENSITIVE FILE STAGED" in out.stderr


def test_a_clean_index_and_an_empty_index_both_pass(tmp_path):
    """The clean outcome, and the stage that exits before it. Staging ordinary
    work has to stay silent, or the hook is noise people turn off."""
    root = _repo(tmp_path)
    assert _bash(HOOKS / "verify-no-secrets.sh", root).returncode == 0
    (root / "notes.md").write_text("nothing to see\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=root, check=True,
                   capture_output=True)
    out = _bash(HOOKS / "verify-no-secrets.sh", root)
    assert out.returncode == 0
    assert out.stderr == ""
