"""A deletion names the copy each client keeps and how to remove it there,
without advice that removes more than the owner deleted. Claude Code's
`claude project purge` deletes every session of a project (checked against
`claude project purge --help`, Claude Code 2.1.251: it has no per-session
option), so it is never offered as the way to remove one session."""
from harness.trace_delete_plan import REMEDIES


def test_claude_code_names_the_session_file_and_warns_about_purge():
    text = REMEDIES["claude-code"]
    assert "<session id>.jsonl" in text
    assert "claude project purge" in text and "every session" in text
    assert "--session" not in text


def test_codex_is_not_given_a_command_it_does_not_have():
    text = REMEDIES["codex"]
    assert "rollout" in text and "no command" in text


def test_the_cli_prints_the_remedy_as_advice_not_as_a_command(capsys):
    from harness.trace_cli_delete import _print_plan
    plan = {"counts": {"CT": 1}, "keys": {}, "receipts": [], "out_of_reach": {},
            "remedies": {"claude-code": REMEDIES["claude-code"]}, "residue_forecast": {},
            "notes": [], "not_covered": [], "plan_digest": "a" * 64}
    _print_plan(plan)
    out = capsys.readouterr().out
    assert "remove it with: claude project purge" not in out
    assert "claude-code keeps its own copy" in out
