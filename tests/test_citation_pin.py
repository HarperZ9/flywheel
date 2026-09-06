"""A citation that names the digest it read, and what that buys.

The receipt integrity check refuses a receipt that no longer hashes to its own
filename. An editor who renames the file to the new hash walks straight past
it, and `test_grounding_receipt_integrity` asserts that outcome rather than
leaving it implied. The gap is that a citation names a task id, so the store is
free to answer with whichever sealing of that id is newest.

A pin closes it by naming one receipt. The store either holds that exact file
or it holds nothing, and a rewrite filed under its own new hash is nothing.

Two arms below are controls rather than demonstrations. An honest pinned cone
still reaches MATCH, without which every test here would pass on a rule that
simply refuses everything. And an unpinned citation hashes exactly as it did
before pins existed, so turning this on does not orphan a sealed receipt.
"""
import json
from pathlib import Path

from harness.envelope import ProofEnvelope, load_envelope
from harness.evolutionary_flywheel import VerifiedPool
from harness.grounding import resolve_ancestors
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import Retrieved, cite, load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
BROKEN = "def add(a, b):\n    return a * b\n"
BASE = dict(task_id="t", candidate="x", oracle="pytest", oracle_cmd="c",
            oracle_output_hash="h", verdict="PASS", model_ref="stub", seed=0,
            prompt_hash="p", budget_spent={})


def _gut(text):
    """Same test ids, every assertion replaced by one that cannot fail."""
    out = []
    for line in text.splitlines():
        indent = line[:len(line) - len(line.lstrip())]
        out.append(indent + "assert True"
                   if line.strip().startswith("assert ") else line)
    return "\n".join(out) + "\n"


def _seal(tmp_path, task_id, ws="ws_a"):
    a = load_task(TASK_DIR, workdir=tmp_path / ws)
    a.task_id = task_id
    assert run_loop(a, StubProposer(CORRECT), PytestOracle(),
                    envelopes_dir=tmp_path / "env").accepted
    (path,) = (tmp_path / "env").glob(task_id + "-*.json")
    return path


def _rewrite_and_refile(env_path):
    """The whole attack in one step: a broken candidate, a fixture set that
    still declares the same test ids and asserts nothing, and a filename that
    matches the result. Nothing about the stored receipt is inconsistent."""
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d["candidate"] = BROKEN
    d["oracle_inputs"]["tests/test_solution.py"] = _gut(
        d["oracle_inputs"]["tests/test_solution.py"])
    env_path.write_text(json.dumps(d), encoding="utf-8")
    refiled = env_path.with_name("%s-%s.json" % (
        env_path.name.rsplit("-", 1)[0], load_envelope(env_path).content_hash()))
    env_path.rename(refiled)
    return refiled


def _cite(tmp_path, retrieved):
    b = load_task(TASK_DIR, workdir=tmp_path / "ws_b")
    b.task_id = "dep_b"
    b.retrieved = retrieved
    return run_loop(b, StubProposer(CORRECT), PytestOracle(),
                    envelopes_dir=tmp_path / "env", grounding_recheck=True)


def test_a_pinned_citation_refuses_the_refiled_rewrite(tmp_path):
    """The gap, closed. Same attack the integrity check lets through: the
    citing task read one receipt, and the store no longer holds it."""
    path = _seal(tmp_path, "anc_pin")
    pin = cite(load_envelope(path))
    _rewrite_and_refile(path)
    r = _cite(tmp_path, [pin])
    assert r.grounding["verdicts"]["anc_pin"] == "UNVERIFIABLE"
    assert not r.accepted
    assert "digest this citation names" in r.grounding["reasons"]["anc_pin"]


def test_an_untouched_pinned_ancestor_still_verifies(tmp_path):
    """The control. A rule that refused every pinned citation would pass the
    arm above and be worth nothing."""
    path = _seal(tmp_path, "anc_ok")
    r = _cite(tmp_path, [cite(load_envelope(path))])
    assert r.grounding["verdicts"]["anc_ok"] == "MATCH"
    assert r.accepted


def test_the_same_receipt_unpinned_is_still_swappable(tmp_path):
    """The cost of not pinning, stated where the fix is. This is the outcome
    `test_grounding_receipt_integrity` records, run against the new code so it
    stays a measured limit rather than a remembered one."""
    path = _seal(tmp_path, "anc_bare")
    _rewrite_and_refile(path)
    r = _cite(tmp_path, [Retrieved(source="anc_bare", receipt="envelope")])
    assert r.grounding["verdicts"]["anc_bare"] == "MATCH"
    assert r.accepted


def test_two_citations_that_disagree_resolve_to_nothing(tmp_path):
    """A cone naming two digests for one source has no reading that satisfies
    it. Picking either one would be a guess dressed as a verdict."""
    path = _seal(tmp_path, "anc_fork")
    real = load_envelope(path).content_hash()
    envs, problems = resolve_ancestors(
        tmp_path / "env", ["anc_fork"], {"anc_fork": real})
    assert envs["anc_fork"] is not None

    forked = _seal(tmp_path, "mid_fork", ws="ws_c")
    d = json.loads(forked.read_text(encoding="utf-8"))
    d["retrieved"] = [{"source": "anc_fork", "receipt": "envelope",
                       "digest": "0" * 16}]
    forked.write_text(json.dumps(d), encoding="utf-8")
    forked.rename(forked.with_name("mid_fork-%s.json"
                                   % load_envelope(forked).content_hash()))
    envs, problems = resolve_ancestors(
        tmp_path / "env", ["anc_fork", "mid_fork"], {"anc_fork": real})
    assert envs["anc_fork"] is None
    assert "different digests" in problems["anc_fork"]


def _forked_citer(tmp_path, task_id, source, digest, ws):
    """Seal a real receipt, then make it cite `source` at `digest` and refile
    it so the result is self-consistent. The citation is what the test needs;
    everything else about the receipt stays a receipt the loop produced."""
    path = _seal(tmp_path, task_id, ws=ws)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["retrieved"] = [{"source": source, "receipt": "envelope",
                       "digest": digest}]
    path.write_text(json.dumps(d), encoding="utf-8")
    path.rename(path.with_name("%s-%s.json"
                               % (task_id, load_envelope(path).content_hash())))


def test_a_pin_that_arrives_after_the_source_was_resolved_still_lands(tmp_path):
    """The walk order the checks above never take. A source reachable by two
    paths can be loaded before the second path says which digest it meant, so
    the disagreement is caught after the walk instead of during it. Both ways
    of disagreeing are here: against another pin, and against a source that was
    resolved with no pin at all and went to the newest sealing.
    """
    real = load_envelope(_seal(tmp_path, "anc_late")).content_hash()
    _forked_citer(tmp_path, "mid_late", "anc_late", "0" * 16, "ws_c")

    # popped last-first, so the pinned source resolves before mid_late is read
    envs, problems = resolve_ancestors(tmp_path / "env",
                                       ["mid_late", "anc_late"],
                                       {"anc_late": real})
    assert envs["anc_late"] is None
    assert "different digests" in problems["anc_late"]

    envs, problems = resolve_ancestors(tmp_path / "env",
                                       ["mid_late", "anc_late"])
    assert envs["anc_late"] is None
    assert "digest this citation names" in problems["anc_late"]


def test_the_pool_pins_what_it_hands_the_next_run(tmp_path):
    """The loop's own memory-to-context edge, which is where most citations
    come from. A caller who never touches `digest` still gets a pinned cone."""
    pool = VerifiedPool()
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = "fam.one"
    sealed = run_loop(a, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env", pool=pool)
    assert pool.digests["fam.one"] == sealed.envelope.content_hash()

    b = load_task(TASK_DIR, workdir=tmp_path / "ws_b")
    b.task_id = "fam.two"
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", pool=pool,
                 grounding_recheck=True)
    assert r.envelope.retrieved == [
        {"source": "fam.one", "receipt": "envelope:%s" % pool.digests["fam.one"],
         "digest": pool.digests["fam.one"]}]
    assert r.grounding["verdicts"]["fam.one"] == "MATCH"


def test_an_unpinned_citation_hashes_as_it_did_before_pins_existed():
    """Drop-when-default, at the entry rather than the field. A receipt sealed
    from an unpinned citation carries no `digest` key at all, so its digest is
    the one it would have had, and signatures over older receipts hold."""
    old = ProofEnvelope(**BASE, retrieved=[{"source": "a", "receipt": "r"}])
    from harness.loop import _citation
    now = ProofEnvelope(**BASE, retrieved=[
        _citation(Retrieved(source="a", receipt="r"))])
    assert "digest" not in now.retrieved[0]
    assert now.content_hash() == old.content_hash()


def test_the_pin_is_signed_along_with_the_citation():
    """Left out of the digest, a pin could be stripped to turn a pinned
    citation back into a swappable one without moving the citing hash."""
    pinned = ProofEnvelope(**BASE, retrieved=[
        {"source": "a", "receipt": "r", "digest": "b" * 16}])
    stripped = ProofEnvelope(**BASE, retrieved=[{"source": "a", "receipt": "r"}])
    assert pinned.content_hash() != stripped.content_hash()
    assert pinned.claim_sha256() != stripped.claim_sha256()
