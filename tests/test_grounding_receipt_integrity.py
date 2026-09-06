"""The receipt integrity check, and the boundary it does not reach.

Rebuilding an ancestor's oracle environment out of its own receipt is what
gives the fresh-environment fallback reach on real tasks. It is also what
opened a false-accept path: rewrite the fixture set and the candidate together,
keep the test ids, and the canonical hash reproduces against a broken
candidate. Receipts are filed under their own content hash, so an in-place edit
moves the hash off the name and is refused before any oracle runs.

That refusal is worth exactly what it covers. An editor who renames the file
too hands the store a self-consistent receipt and the swap lands. The last test
asserts that instead of leaving it implied, because a gap nobody wrote down
reads like a gap somebody closed.

It is now also the cost of citing without a pin. A citation that names the
ancestor digest it read resolves to that one filename, so the refiled rewrite
is absent rather than substituted, and `test_citation_pin.py` holds that arm.
Everything here cites by task id alone, which is the state every receipt sealed
before pins existed is in, so the outcome below is still the live one.
"""
import json
from pathlib import Path

from harness.envelope import load_envelope
from harness.grounding import _rewitness_in_fresh_env, resolve_ancestors
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import Retrieved, load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
BROKEN = "def add(a, b):\n    return a * b\n"


def _gut(text):
    """Same test ids, every assertion replaced by one that cannot fail.

    Keeping the ids is the attack. The canonical hash folds test ids and
    outcomes, so a file that still declares them reproduces the stored hash
    whatever the candidate does. This is derived from the real fixture rather
    than hardcoded, so it stays an id-preserving swap if the task changes.
    """
    out = []
    for line in text.splitlines():
        indent = line[:len(line) - len(line.lstrip())]
        out.append(indent + "assert True"
                   if line.strip().startswith("assert ") else line)
    return "\n".join(out) + "\n"


def _seal_ancestor(tmp_path, task_id):
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = task_id
    assert run_loop(a, StubProposer(CORRECT), PytestOracle(),
                    envelopes_dir=tmp_path / "env").accepted
    (path,) = (tmp_path / "env").glob(task_id + "-*.json")
    return path


def _swap_in_a_weaker_oracle(env_path):
    """The false MATCH, staged: a broken candidate, plus a fixture set that
    still declares the same tests and asserts nothing."""
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d["candidate"] = BROKEN
    d["oracle_inputs"]["tests/test_solution.py"] = _gut(
        d["oracle_inputs"]["tests/test_solution.py"])
    env_path.write_text(json.dumps(d), encoding="utf-8")


def _refile(env_path):
    refiled = env_path.with_name("%s-%s.json" % (
        env_path.name.rsplit("-", 1)[0], load_envelope(env_path).content_hash()))
    env_path.rename(refiled)
    return refiled


def _cite(tmp_path, source):
    b = load_task(TASK_DIR, workdir=tmp_path / "ws_b")
    b.task_id = "dep_b"
    b.retrieved = [Retrieved(source=source, receipt="envelope")]
    return run_loop(b, StubProposer(CORRECT), PytestOracle(),
                    envelopes_dir=tmp_path / "env", grounding_recheck=True)


def test_a_gutted_fixture_set_reproduces_the_stored_hash(tmp_path):
    """Why the check exists, measured rather than argued. Aimed straight at the
    re-witness with the store's guard out of the way, the swap earns MATCH on a
    candidate that computes the wrong answer."""
    path = _seal_ancestor(tmp_path, "anc_raw")
    assert _rewitness_in_fresh_env(load_envelope(path))[0] == "MATCH"
    _swap_in_a_weaker_oracle(path)
    assert _rewitness_in_fresh_env(load_envelope(path))[0] == "MATCH"


def test_an_in_place_swap_is_refused_before_the_oracle_runs(tmp_path):
    path = _seal_ancestor(tmp_path, "anc_swap")
    _swap_in_a_weaker_oracle(path)
    r = _cite(tmp_path, "anc_swap")
    assert r.grounding["verdicts"]["anc_swap"] == "UNVERIFIABLE"
    assert not r.accepted
    assert "edited after sealing" in r.grounding["reasons"]["anc_swap"]


def test_resolve_separates_an_absent_receipt_from_an_edited_one(tmp_path):
    """Both fail closed. They are reported apart because they ask different
    things of whoever reads the run."""
    path = _seal_ancestor(tmp_path, "anc_swap")
    _swap_in_a_weaker_oracle(path)
    envs, problems = resolve_ancestors(tmp_path / "env", ["anc_swap", "ghost"])
    assert envs["anc_swap"] is None
    assert envs["ghost"] is None
    assert "edited after sealing" in problems["anc_swap"]
    assert "no stored envelope" in problems["ghost"]


def test_an_edited_receipt_cannot_steer_the_citation_walk(tmp_path):
    """A receipt that fails the check is dropped whole. Its retrieved[] is
    attacker-controlled text, so it never adds nodes to the closure."""
    path = _seal_ancestor(tmp_path, "anc_swap")
    d = json.loads(path.read_text(encoding="utf-8"))
    d["retrieved"] = [{"source": "planted_by_the_editor", "receipt": "envelope"}]
    path.write_text(json.dumps(d), encoding="utf-8")
    envs, _ = resolve_ancestors(tmp_path / "env", ["anc_swap"])
    assert "planted_by_the_editor" not in envs


def test_a_refiled_receipt_is_not_stopped_by_this_check(tmp_path):
    """The boundary, asserted so it cannot be mistaken for covered. Renaming
    the file to its new content hash makes the receipt self-consistent, and the
    swap lands: the ancestor reads MATCH and the citing task is accepted.

    The citation here names a task id and nothing more, so the store answers
    with its newest sealing of that id. A citation that pins the digest it read
    refuses the same rewrite; see test_citation_pin.py. Signature verification
    on this path stays open and is recorded that way in PROJECT.md.
    """
    path = _seal_ancestor(tmp_path, "anc_refiled")
    _swap_in_a_weaker_oracle(path)
    _refile(path)
    r = _cite(tmp_path, "anc_refiled")
    assert r.grounding["verdicts"]["anc_refiled"] == "MATCH"
    assert r.accepted
