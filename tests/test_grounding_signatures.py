"""The whole-cone rewrite, and the four ways a signature check could be theatre.

Three checks already guard a cited ancestor and each one compares the store
against itself. `_load_intact` refuses a receipt that no longer hashes to its
own filename. A pin refuses a store that does not hold the exact digest the
citation read. `test_citation_pin` shows the pin catching a rewrite that
`_load_intact` walks past.

None of that survives an editor who rewrites the whole cone. Rewrite the
ancestor, refile it under its new hash, rewrite the citing receipt so its pin
names that hash, refile that too. The store is now internally consistent about
a run that did not happen, and every hash and every pin agrees. The first test
below runs exactly that.

The remaining tests are the ones that decide whether the fix is worth anything.
A verifier that reads the public key out of the sidecar it is checking proves
that somebody, somewhere, holds a key. A verifier that trusts the sidecar's
recorded content hash checks a signature over a number the editor supplied. A
verifier that quietly accepts an algorithm it cannot check hands the reader a
green tick for a secret they do not have. Each of those is written here as an
attack that must fail, not as an assertion that the happy path passes.

The honest-null arm matters as much: with no trusted keys named, a store that
carries no sidecars behaves exactly as it did before this module existed. A
change that turned every unsigned ancestor UNVERIFIABLE by default would be a
break dressed as a security improvement.
"""
import json
from pathlib import Path

import pytest

from harness.envelope import load_envelope
from harness.grounding import resolve_ancestors
from harness.grounding_signatures import (
    sidecar_document, sidecar_path, signed_bytes, verify_envelope_signature,
)
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import load_task

nacl_signing = pytest.importorskip("nacl.signing")

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
BROKEN = "def add(a, b):\n    return a * b\n"
KEY_ID = "operator-2026"


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
    """A broken candidate, a fixture set that still declares the same test ids
    and asserts nothing, and a filename matching the result. Nothing about the
    stored receipt is inconsistent once this returns."""
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d["candidate"] = BROKEN
    d["oracle_inputs"]["tests/test_solution.py"] = _gut(
        d["oracle_inputs"]["tests/test_solution.py"])
    env_path.write_text(json.dumps(d), encoding="utf-8")
    refiled = env_path.with_name("%s-%s.json" % (
        env_path.name.rsplit("-", 1)[0], load_envelope(env_path).content_hash()))
    env_path.rename(refiled)
    return refiled


def _sign(env_path, key, key_id=KEY_ID):
    """Write the sidecar an honest signer writes."""
    env = load_envelope(env_path)
    digest = env.content_hash()
    doc = sidecar_document(
        task_id=env.task_id, content_hash=digest, key_id=key_id,
        signature=key.sign(signed_bytes(env.task_id, digest)).signature,
        public_key=bytes(key.verify_key))
    path = sidecar_path(env_path)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _trusted(key, key_id=KEY_ID):
    return {key_id: bytes(key.verify_key)}


def _resolve(tmp_path, task_id, trusted):
    """Resolve one cited ancestor, pinned to whatever the store now holds.

    Pinning to the digest on disk is deliberate: it hands the pin check the
    answer it wants, so anything that fails below failed on the signature.
    """
    (path,) = (tmp_path / "env").glob(task_id + "-????????????????.json")
    pin = path.stem.rsplit("-", 1)[-1]
    return resolve_ancestors(tmp_path / "env", [task_id], {task_id: pin},
                             trusted)


# --------------------------------------------------------------- the gap

def test_a_rewritten_cone_that_satisfies_every_hash_still_fails(tmp_path):
    """The whole reason this module exists.

    The editor here does everything the earlier checks look for: the receipt
    hashes to its filename, and the pin names the file that is present. What
    they cannot do is produce a signature over the digest they just invented.
    """
    path = _seal(tmp_path, "anc")
    key = nacl_signing.SigningKey.generate()
    _sign(path, key)
    refiled = _rewrite_and_refile(path)
    # The editor carries the sidecar across too, which is the strongest version
    # of the attack: a sidecar that is absent is a weaker failure than one that
    # is present, well formed, and covering the wrong receipt.
    sidecar_path(refiled).write_text(
        sidecar_path(path).read_text(encoding="utf-8"), encoding="utf-8")
    sidecar_path(path).unlink()

    envs, problems = _resolve(tmp_path, "anc", _trusted(key))
    assert envs["anc"] is None
    assert "covers a different receipt" in problems["anc"]


def test_an_untouched_signed_ancestor_still_resolves(tmp_path):
    """The control. Every test here would pass on a rule that refused
    everything, and this is the arm that rule fails."""
    path = _seal(tmp_path, "anc_ok")
    key = nacl_signing.SigningKey.generate()
    _sign(path, key)
    envs, problems = _resolve(tmp_path, "anc_ok", _trusted(key))
    assert envs["anc_ok"] is not None
    assert problems == {}


# ------------------------------------------- the four ways to fake a pass

def test_a_perfectly_valid_signature_from_an_unnamed_key_is_refused(tmp_path):
    """Discipline 2, as two attacks that differ only in what the forger claims.

    Both rewrite the cone and sign it correctly with a key the forger generated,
    so both sidecars are internally flawless: the recorded hash matches the
    receipt on disk, and the signature verifies against the public key the file
    carries. A verifier that read the key out of the sidecar would return true
    for either, and would be reporting that somebody owns a keypair.

    They fail by different routes, and the routes are worth keeping apart. A
    forger who claims the operator's key_id is checked against the operator's
    key and the signature does not verify. A forger who names their own key_id
    is refused before any curve arithmetic runs.
    """
    path = _seal(tmp_path, "anc_forge")
    honest = nacl_signing.SigningKey.generate()
    forger = nacl_signing.SigningKey.generate()
    refiled = _rewrite_and_refile(path)
    env = load_envelope(refiled)

    _sign(refiled, forger)
    ok, why = verify_envelope_signature(env, refiled, _trusted(honest))
    assert not ok
    assert "does not verify" in why
    # The same sidecar verifies against itself, which is the point: the forgery
    # is not visible inside the file. Only the trusted mapping sees it.
    assert verify_envelope_signature(env, refiled, _trusted(forger)) == (True, "")

    _sign(refiled, forger, key_id="forger-1")
    ok, why = verify_envelope_signature(env, refiled, _trusted(honest))
    assert not ok
    assert "not in the trusted set" in why


def test_a_sidecar_cannot_declare_the_hash_it_is_checked_against(tmp_path):
    """Discipline 1, as an attack.

    Both files are the same task id, so the task-id check cannot be what
    rejects this. The editor rewrites the receipt and edits the sidecar's
    recorded hash to match, leaving the signature untouched. A verifier that
    signed over the recorded value rather than the recomputed one would accept.
    """
    path = _seal(tmp_path, "anc_declare")
    key = nacl_signing.SigningKey.generate()
    _sign(path, key)
    doc = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    refiled = _rewrite_and_refile(path)
    sidecar_path(path).unlink()
    doc["content_hash"] = load_envelope(refiled).content_hash()
    sidecar_path(refiled).write_text(json.dumps(doc), encoding="utf-8")

    ok, why = verify_envelope_signature(load_envelope(refiled), refiled,
                                        _trusted(key))
    assert not ok
    assert "does not verify" in why


def test_a_local_only_algorithm_is_refused_by_name(tmp_path):
    """Discipline 3. An HMAC sidecar asks the reader to hold the signing
    secret, and a reader holding it is checking their own work. Refusing it
    silently would be worse than refusing it loudly, because the store would
    look signed."""
    path = _seal(tmp_path, "anc_hmac")
    key = nacl_signing.SigningKey.generate()
    _sign(path, key)
    doc = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    doc["sig_alg"] = "hmac-sha256"
    sidecar_path(path).write_text(json.dumps(doc), encoding="utf-8")

    ok, why = verify_envelope_signature(load_envelope(path), path, _trusted(key))
    assert not ok
    assert "local-only" in why


def test_a_flipped_byte_in_the_signature_is_invalid_not_missing(tmp_path):
    """Discipline 4. A forged signature and an unsigned receipt both fail
    closed, and a reader who cannot tell them apart cannot tell an incomplete
    rollout from an attack."""
    path = _seal(tmp_path, "anc_flip")
    key = nacl_signing.SigningKey.generate()
    _sign(path, key)
    doc = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    raw = bytearray(bytes.fromhex(doc["sig"]))
    raw[0] ^= 0x01
    doc["sig"] = bytes(raw).hex()
    sidecar_path(path).write_text(json.dumps(doc), encoding="utf-8")
    forged = verify_envelope_signature(load_envelope(path), path, _trusted(key))

    sidecar_path(path).unlink()
    absent = verify_envelope_signature(load_envelope(path), path, _trusted(key))

    assert forged[0] is False and absent[0] is False
    assert forged[1] != absent[1], "a forgery and an unsigned store read alike"
    assert "does not verify" in forged[1]
    assert "no signature sidecar" in absent[1]


# -------------------------------------------------------- the honest nulls

def test_naming_no_keys_leaves_an_unsigned_store_exactly_as_it_was(tmp_path):
    """The default proves nothing new, on purpose.

    Turning this on for every caller would turn every receipt sealed before
    signatures existed into UNVERIFIABLE, which is a break, not a hardening.
    """
    path = _seal(tmp_path, "anc_bare")
    assert not sidecar_path(path).exists()
    envs, problems = _resolve(tmp_path, "anc_bare", None)
    assert envs["anc_bare"] is not None
    assert problems == {}


def test_asking_for_signatures_over_an_unsigned_store_fails_closed(tmp_path):
    """The cost of opting in, stated where the switch is. A caller who names
    keys against a store that carries no sidecars gets nothing verified, and
    the reason says which of the two problems they have."""
    path = _seal(tmp_path, "anc_none")
    key = nacl_signing.SigningKey.generate()
    assert not sidecar_path(path).exists()
    envs, problems = _resolve(tmp_path, "anc_none", _trusted(key))
    assert envs["anc_none"] is None
    assert "no signature sidecar" in problems["anc_none"]


def test_an_empty_trusted_set_trusts_nothing_rather_than_everything(tmp_path):
    """The shortcut that would have made every arm above pass: reading an empty
    mapping as "no policy configured" instead of "no key is trusted"."""
    path = _seal(tmp_path, "anc_empty")
    _sign(path, nacl_signing.SigningKey.generate())
    ok, why = verify_envelope_signature(load_envelope(path), path, {})
    assert not ok
    assert "not in the trusted set" in why


def test_a_signature_does_not_carry_from_one_task_id_to_another(tmp_path):
    """The message binds the task id, so a receipt cannot borrow a sibling's
    signature even where the content hashes agree."""
    key = nacl_signing.SigningKey.generate()
    digest = "0123456789abcdef"
    sig = key.sign(signed_bytes("task_a", digest)).signature
    from harness.ed25519_verify import verify as ed_verify
    assert ed_verify(bytes(key.verify_key), signed_bytes("task_a", digest), sig)
    assert not ed_verify(bytes(key.verify_key),
                         signed_bytes("task_b", digest), sig)
