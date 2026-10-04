"""A PySyft job result receipt holds on a real run and fails on each tamper.

The fixture in tests/fixtures/pysyft_receipt is the bundle written by
scripts/pysyft_receipt_demo.py after a real syft-job run (PySyft commit
36e65162, PR #9536) on Linux: a data owner approved a job, PySyft ran the copy
that matched the approved hash, and the receipt was signed with a throwaway key
whose private half was never written.

Every tamper test is paired: the same verifier call on the untouched bundle must
give MATCH, and the one mutation must give DRIFT naming the expected check. A
mutation that needs a new signature is signed with a fixed test key (not a
secret), and the verifier pins that key, so the check under test is the one that
catches it rather than the signature.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from harness import job_result_receipt as jr
from harness.job_result_verify import DRIFT, MATCH, UNVERIFIABLE, verify
from harness.pysyft_job_hash import JobHashError, code_hash, digest_files, submission_hash

FIX = Path(__file__).resolve().parent / "fixtures" / "pysyft_receipt"
NONCE = "openmined-bridge-demo-20261003"
REVIEWER = "do@example.org"
TEST_SEED = hashlib.sha256(b"flywheel test attacker key, not a secret").digest()


def _env():
    return json.loads((FIX / "receipt.json").read_text(encoding="utf-8"))


def _pub():
    return (FIX / "public_key.hex").read_text(encoding="utf-8").strip()


def _answers():
    return json.loads((FIX / "reveal_answers.json").read_text(encoding="utf-8"))


def _attacker():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        k = Ed25519PrivateKey.from_private_bytes(TEST_SEED)
        return k.sign, k.public_key().public_bytes_raw()
    except ImportError:
        signing = pytest.importorskip("nacl.signing")
        k = signing.SigningKey(TEST_SEED)
        return (lambda m: k.sign(m).signature), bytes(k.verify_key)


def _resign(body):
    sign, pub = _attacker()
    return jr.attach(body, sign(jr.claim_sha256(body).encode("ascii")), pub, "test-attacker"), pub.hex()


@pytest.fixture
def case(tmp_path):
    job = tmp_path / "job"
    shutil.copytree(FIX / "job", job)
    return {"env": _env(), "kw": dict(public_key_hex=_pub(), job_dir=job,
                                      results=(FIX / "results.jsonl").read_bytes(), nonce=NONCE,
                                      reviewers=[REVIEWER], revealed_answers=_answers())}


def test_the_fixture_is_the_real_run_and_its_hash_is_pysyfts():
    run = json.loads((FIX / "run.json").read_text(encoding="utf-8"))
    assert run["versions"]["syft-job"] == "0.1.41"
    body = _env()["body"]
    assert submission_hash(FIX / "job") == body["job"]["approved_hash"] == body["job"]["received_hash"]
    assert body["result"]["correct"] == 40 and body["result"]["total"] == 50


def test_clean_bundle_matches_and_names_the_attestation_gap(case):
    r = verify(case["env"], **case["kw"])
    assert r["verdict"] == MATCH and r["failed"] == []
    assert r["attestation"] == UNVERIFIABLE and "attestation" in r["attestation_reason"]
    assert "reveal" in r["checks_run"] and "signature" in r["checks_run"]


def _swap_job(c):
    (c["kw"]["job_dir"] / "code" / "main.py").write_text("print('other code')\n")


def _swap_job_and_resign(c):
    """The swapper rewrites the hashes and signs with its own key; the verifier
    still pins the data owner's key."""
    _swap_job(c)
    body = c["env"]["body"]
    body["job"]["approved_hash"] = body["job"]["received_hash"] = submission_hash(c["kw"]["job_dir"])
    c["env"] = _resign(body)[0]


def _swap_job_signer_pinned_too(c):
    """Even with the swapper's key pinned, the superstack scene still names the
    approved hash, so the half-rebuilt receipt does not hold together."""
    _swap_job_and_resign(c)
    c["kw"]["public_key_hex"] = _attacker()[1].hex()


def _edit_score(c):
    c["env"]["body"]["result"]["correct"] += 1


def _edit_score_and_resign(c):
    _edit_score(c)
    c["env"], c["kw"]["public_key_hex"] = _resign(c["env"]["body"])


def _forge_approver(c):
    c["env"]["body"]["approval"]["approved_by"] = "mallory@example.org"


def _forge_approver_and_resign(c):
    _forge_approver(c)
    c["env"], c["kw"]["public_key_hex"] = _resign(c["env"]["body"])


def _approval_of_other_job(c):
    c["env"]["body"]["job"]["received_hash"] = "0" * 64
    c["env"], c["kw"]["public_key_hex"] = _resign(c["env"]["body"])


def _replay_new_nonce(c):
    c["kw"]["nonce"] = "a-later-challenge"


def _replay_seen(c):
    c["kw"]["seen_receipt_ids"] = [c["env"]["body"]["receipt_id"]]


def _wrong_signer(c):
    c["kw"]["public_key_hex"] = _attacker()[1].hex()


def _drop_a_row(c):
    c["kw"]["results"] = b"\n".join(c["kw"]["results"].splitlines()[1:]) + b"\n"


def _lie_in_rows(c):
    """A consistent lie: flip a wrong row to correct and rebuild every digest."""
    lines = c["kw"]["results"].decode().splitlines()
    i = next(n for n, ln in enumerate(lines) if '"correct": false' in ln)
    lines[i] = lines[i].replace('"correct": false', '"correct": true')
    results = ("\n".join(lines) + "\n").encode()
    old = c["env"]["body"]
    rows = jr.parse_rows(results)
    body = copy.deepcopy(old)
    body["result"].update(correct=old["result"]["correct"] + 1, items_root=jr.items_root(rows),
                          results_sha256=hashlib.sha256(results).hexdigest())
    body["superstack"] = jr.superstack_receipt(body["job"], results, rows,
                                               body["result"]["correct"], len(rows))
    c["kw"]["results"] = results
    c["env"], c["kw"]["public_key_hex"] = _resign(body)


def _drop_a_limit(c):
    c["env"]["body"]["does_not_prove"].pop(0)
    c["env"], c["kw"]["public_key_hex"] = _resign(c["env"]["body"])


def _break_superstack_seal(c):
    c["env"]["body"]["superstack"]["backend"] = "something-else"
    c["env"], c["kw"]["public_key_hex"] = _resign(c["env"]["body"])


MUTATIONS = [
    (_swap_job, "job_hash"), (_swap_job_and_resign, "wrong_signer"),
    (_swap_job_signer_pinned_too, "superstack_scene"),
    (_edit_score, "signature"), (_edit_score, "claim_digest"),
    (_edit_score_and_resign, "score"),
    (_forge_approver, "signature"), (_forge_approver_and_resign, "approver"),
    (_approval_of_other_job, "approval_covers_other_job"),
    (_replay_new_nonce, "replay_nonce"), (_replay_seen, "replay_seen"),
    (_wrong_signer, "wrong_signer"), (_drop_a_row, "results_bytes"),
    (_lie_in_rows, "reveal"), (_drop_a_limit, "schema_or_limits"),
    (_break_superstack_seal, "superstack:seal"),
]


@pytest.mark.parametrize("mutate,expected", MUTATIONS, ids=lambda v: getattr(v, "__name__", v))
def test_each_tamper_drifts_and_its_clean_pair_matches(case, mutate, expected):
    assert verify(copy.deepcopy(case["env"]), **case["kw"])["verdict"] == MATCH
    mutate(case)
    r = verify(case["env"], **case["kw"])
    assert r["verdict"] == DRIFT and expected in r["failed"], r["failed"]


def test_without_the_reveal_a_consistent_lie_passes_and_that_is_stated(case):
    """The honest null: before the answers are revealed, the receipt shows only that
    the score matches the released rows. The does_not_prove list says so."""
    _lie_in_rows(case)
    case["kw"]["revealed_answers"] = None
    assert verify(case["env"], **case["kw"])["verdict"] == MATCH
    assert any("revealed and rescored" in s for s in jr.DOES_NOT_PROVE)


def test_missing_inputs_are_unverifiable_not_match(case):
    case["kw"].update(job_dir=None)
    r = verify(case["env"], **case["kw"])
    assert r["verdict"] == UNVERIFIABLE and r["missing_inputs"] == ["job_dir"]


@pytest.mark.parametrize("hostile", [{}, {"body": None}, {"body": {}, "signature": {}}, []])
def test_hostile_envelopes_drift_without_raising(hostile):
    r = verify(hostile, public_key_hex=_pub(), job_dir=FIX / "job",
               results=(FIX / "results.jsonl").read_bytes())
    assert r["verdict"] == DRIFT and r["failed"]


def test_hash_format_by_hand(tmp_path):
    job = tmp_path / "j"
    (job / "code" / "__pycache__").mkdir(parents=True)
    (job / "code" / "a.py").write_bytes(b"x=1\n")
    (job / "code" / "__pycache__" / "a.pyc").write_bytes(b"skipped")
    (job / "run.sh").write_bytes(b"python a.py\n")
    (job / "config.yaml").write_bytes(b"name: j\n")
    (job / "SYFT.PUB.YAML").write_bytes(b"skipped, case-insensitive")
    h = hashlib.sha256()
    for rel, data in (("code/a.py", b"x=1\n"), ("config.yaml", b"name: j\n"), ("run.sh", b"python a.py\n")):
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    assert submission_hash(job) == h.hexdigest()
    assert code_hash(job) == digest_files([("code/a.py", b"x=1\n"), ("run.sh", b"python a.py\n")])


def test_a_missing_job_folder_is_a_named_error(tmp_path):
    with pytest.raises(JobHashError):
        submission_hash(tmp_path / "absent")
