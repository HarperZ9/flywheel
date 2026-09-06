"""Credentials must not travel inside a receipt, and the gap must be visible.

Carrying a task's fixture set is what gave the fresh-environment re-check reach
on real work. It also pointed a snapshot of a working directory at an artefact
meant to be published, so a `.env` sitting beside the tests would have been
signed and shipped with everything else.

The headline arm here does not test the rule, it tests the outcome: seal a task
whose workdir holds a key and assert the key's text appears nowhere in the
serialised receipt. A rule test passes when the rule I wrote does what I meant.
That one passes only if nothing else carries the secret out by a route I did
not think of.

The last arm asserts a false withhold rather than hiding it. Withholding is the
safe direction and it is not free: a fixture that legitimately assigns a
password loses its task fresh-environment reach.
"""
import json
from pathlib import Path

from harness.envelope import ProofEnvelope
from harness.grounding import _shortfall
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.oracle_inputs import capture, restore
from harness.proposer import StubProposer
from harness.receipt_secrets import withhold_reason
from harness.task import Retrieved, Task, load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
BASE = dict(task_id="t", candidate="x", oracle="pytest", oracle_cmd="c",
            oracle_output_hash="h", verdict="PASS", model_ref="stub", seed=0,
            prompt_hash="p", budget_spent={})


def _tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_a_credential_in_the_workdir_reaches_no_part_of_the_receipt(tmp_path):
    """The property that matters, checked against the whole serialised receipt
    rather than against the field the rule happens to guard."""
    task = load_task(TASK_DIR, workdir=tmp_path / "ws")
    task.task_id = "secretive"
    (task.workdir_path() / ".env").write_text("API_TOKEN=%s\n" % AWS_KEY,
                                              encoding="utf-8")
    result = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env")
    assert result.accepted
    (path,) = (tmp_path / "env").glob("secretive-*.json")
    assert AWS_KEY not in path.read_text(encoding="utf-8")
    assert ".env" not in result.envelope.oracle_inputs
    assert result.envelope.withheld_inputs == [
        {"path": ".env", "reason": "named like a credential file"}]


def test_a_key_pasted_into_an_ordinary_file_is_caught_by_content(tmp_path):
    """The name rule cannot see this one. helpers.py is what a fixture is
    usually called."""
    _tree(tmp_path, {"tests/t.py": "def test_x(): ...",
                     "helpers.py": "TOKEN = '%s'\n" % AWS_KEY})
    carried, withheld = capture(tmp_path)
    assert set(carried) == {"tests/t.py"}
    assert withheld == [{"path": "helpers.py",
                         "reason": "contains a aws_access_key"}]


def test_a_withheld_entry_names_the_file_and_never_the_secret(tmp_path):
    _tree(tmp_path, {"helpers.py": "TOKEN = '%s'\n" % AWS_KEY})
    _, withheld = capture(tmp_path)
    assert AWS_KEY not in json.dumps(withheld)


def test_the_env_template_is_a_fixture_and_stays(tmp_path):
    """`.env.example` is a file the engineering standard requires a repo to
    commit. Withholding every `.env.*` would drop a fixture whose entire
    purpose is to be read."""
    _tree(tmp_path, {".env.example": "API_TOKEN=replace-me\n",
                     ".env.production": "API_TOKEN=%s\n" % AWS_KEY})
    carried, withheld = capture(tmp_path)
    assert set(carried) == {".env.example"}
    assert [w["path"] for w in withheld] == [".env.production"]


def test_restore_refuses_a_credential_a_receipt_offers_it(tmp_path):
    """Capture will not put a credential into a receipt. This end will not take
    one out of somebody else's and write it to our disk."""
    written = restore({".env": "API_TOKEN=%s\n" % AWS_KEY,
                       "id_rsa": "-----BEGIN RSA PRIVATE KEY-----\nx\n",
                       "keep.py": "ok"}, tmp_path)
    assert written == 1
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["keep.py"]


def test_the_withheld_marker_is_signed_along_with_everything_else():
    """Left out of the digest, the marker could be stripped and a partial
    capture would read as a complete one. Its default stays out, so receipts
    sealed before the field verify against their own signatures."""
    plain = ProofEnvelope(**BASE)
    marked = ProofEnvelope(**BASE, withheld_inputs=[{"path": ".env",
                                                     "reason": "named like a "
                                                               "credential "
                                                               "file"}])
    assert "withheld_inputs" not in plain._digest_fields()
    assert "withheld_inputs" in marked._digest_fields()
    assert plain.content_hash() != marked.content_hash()


def test_a_fixture_that_legitimately_assigns_a_password_is_withheld(tmp_path):
    """The cost, asserted rather than left to be discovered. A test for a
    password validator reads like a leak to the content rule, gets withheld,
    and its task loses fresh-environment reach. Fail closed is the right
    direction here; it is not a free one."""
    _tree(tmp_path, {"tests/t.py": 'password = "correct-horse-battery"\n'})
    carried, withheld = capture(tmp_path)
    assert carried == {}
    assert withheld == [{"path": "tests/t.py",
                         "reason": "contains a generic_password"}]
    assert withhold_reason("tests/t.py", 'password = "short"') is None


def test_a_withheld_fixture_says_so_where_the_verdict_is(tmp_path):
    """The cost followed all the way to whoever reads the run.

    A withheld test file leaves its ancestor unable to re-run, and the verdict
    that comes back is the same UNVERIFIABLE a tamper produces. Nothing in the
    hash can separate them, so the reason carries the fact instead.
    """
    ws = tmp_path / "ws_a"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_x.py").write_text(
        'password = "correct-horse-battery"\n\n\ndef test_x():\n    assert 1\n',
        encoding="utf-8")
    ancestor = Task(task_id="anc_pw", prompt="unused: the proposer is a stub",
                    oracle="pytest", oracle_cmd="python -m pytest tests/",
                    workdir=str(ws), candidate_path="solution.py")
    sealed = run_loop(ancestor, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env")
    assert sealed.accepted
    assert sealed.envelope.withheld_inputs

    citing = load_task(TASK_DIR, workdir=tmp_path / "ws_b")
    citing.task_id = "dep_b"
    citing.retrieved = [Retrieved(source="anc_pw", receipt="envelope")]
    r = run_loop(citing, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_pw"] == "UNVERIFIABLE"
    assert "withheld at seal time" in r.grounding["reasons"]["anc_pw"]


def test_the_reason_also_names_fixtures_this_end_refused():
    """The other half of the shortfall. Capture cannot produce a receipt that
    offers a credential, so this arm goes at the helper rather than through a
    hand-forged receipt that would prove more about my forgery than the code."""
    env = ProofEnvelope(**BASE, oracle_inputs={"a.py": "1", "b.py": "2"})
    assert _shortfall(env, 2, 1) == "; this end refused 1 of 2 carried fixtures"
    assert _shortfall(env, 2, 2) == ""
