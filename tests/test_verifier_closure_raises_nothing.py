"""Every offline verifier must return a verdict on hostile bytes, never raise.

A stranger runs these verifiers on ATTACKER-SUPPLIED JSON they `json.loads` into
Python objects (dict / list / str / int / float / bool / None only). Each verifier
already promises, in its docstring, that it "never raises on hostile input" or
returns a named (ok, reason). The recurring defect this file pins down is a single
class: an unguarded TYPE or SHAPE assumption on an attacker field lets a
non-ValueError escape (AttributeError from `.get`/`.split` on a non-dict/non-str;
TypeError from `bytes.fromhex`/`list()`/`asdict()` on the wrong type, or from
`x in frozenset` when `x` is unhashable; KeyError from a missing field) past an
`except` clause that only catches the ValueError family.

`json.loads` never yields set / bytes / tuple / custom objects, so those TypeError
shapes are out of reach for this adversary. The reachable ones are exercised below,
one module per section, closing the whole class rather than one case at a time.
"""
import hashlib
import json
from pathlib import Path

import pytest

import receipt_factories as factories
from harness.bundle import pack_bundle, verify_bundle, MANIFEST_NAME
from harness.receipt_sign import unsigned, ed25519_attach, verify_signed
from harness.ledger import Ledger
from harness.envelope import verify_citations
from harness.chain import validate_chain
from harness.contest import Contest, ContestReason
from harness.why import explain, WhyError


def _r(objective="21"):
    return factories.receipt(objective=objective)


# --- bundle.verify_bundle ---------------------------------------------------

def _pack_one(tmp_path):
    return pack_bundle(
        tmp_path / "b.frb",
        envelopes=[unsigned(_r())],
        criterion={"criterion_id": "zarankiewicz.z_2_2", "version": 1},
        checker_sources={"zarankiewicz.py": "def k22_free(g):\n    return True\n"},
        qa_card={"schema": "flywheel.oracle-qa-card/v2", "passed": True},
        tree_head={"schema": "flywheel.tree-head/v1", "size": 1,
                   "root": "sha256:" + "1" * 64})


def _reseat_signature(bundle_dir, new_signature):
    """Hand a stranger a self-consistent bundle whose one receipt carries an
    attacker-chosen `signature`: swap the field and re-seat the manifest hash so
    the byte-level gate still passes, leaving the signature the only anomaly."""
    d = Path(bundle_dir)
    rp = sorted((d / "receipts").glob("*.json"))[0]
    env = json.loads(rp.read_text(encoding="utf-8"))
    env["signature"] = new_signature
    raw = json.dumps(env, indent=1, sort_keys=True).encode("utf-8")
    rp.write_bytes(raw)
    rel = rp.relative_to(d).as_posix()
    mp = d / MANIFEST_NAME
    m = json.loads(mp.read_text(encoding="utf-8"))
    for f in m["files"]:
        if f["path"] == rel:
            f["sha256"] = hashlib.sha256(raw).hexdigest()
            f["bytes"] = len(raw)
    mp.write_text(json.dumps(m, indent=1, sort_keys=True), encoding="utf-8")
    return d


@pytest.mark.parametrize("hostile_sig", [[], "x", 5, True])
def test_bundle_names_a_non_object_signature_instead_of_crashing(tmp_path,
                                                                 hostile_sig):
    # `sig.get("sig_alg")` on a non-dict signature raises AttributeError, escaping
    # the "never raises on hostile input" the docstring promises.
    d = _reseat_signature(_pack_one(tmp_path), hostile_sig)
    v = verify_bundle(d)                              # must not raise
    assert v["verdict"] == "MATCH"                    # integrity intact; sig is off
    assert "malformed" in v["receipts"][0]["signature"].lower()


def test_bundle_handles_an_unhashable_sig_alg_instead_of_crashing(tmp_path):
    # `sig_alg in LOCAL_ONLY_ALGS` against a frozenset raises TypeError on an
    # unhashable sig_alg (a list), escaping the verifier.
    d = _reseat_signature(_pack_one(tmp_path), {"sig_alg": ["ed25519"]})
    v = verify_bundle(d)                              # must not raise
    assert v["verdict"] == "MATCH"
    assert v["receipts"][0]["signature"]             # a named state, no crash


@pytest.mark.parametrize("bad_pub", [123, ["ab"], {"x": 1}, True])
def test_bundle_names_a_non_string_public_key_instead_of_crashing(tmp_path,
                                                                  bad_pub):
    # `bytes.fromhex(public_key)` on a truthy non-string raises TypeError, a sibling
    # of the ValueError the `except` catches, so it escapes.
    d = _reseat_signature(_pack_one(tmp_path),
                          {"sig_alg": "ed25519", "public_key": bad_pub,
                           "key_id": "k"})
    v = verify_bundle(d)                              # must not raise
    assert v["verdict"] == "MATCH"
    assert "malformed_public_key" in v["receipts"][0]["signature"]


@pytest.mark.parametrize("bad_files", [5, True, 1.5, None])
def test_bundle_survives_a_non_list_files_manifest(tmp_path, bad_files):
    # `manifest["files"]` binds inside the try, but `for f in listed` iterates it
    # outside; a non-iterable scalar raises TypeError there, past the except.
    d = _pack_one(tmp_path)
    mp = d / MANIFEST_NAME
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["files"] = bad_files
    mp.write_text(json.dumps(m, indent=1, sort_keys=True), encoding="utf-8")
    v = verify_bundle(d)                              # must not raise
    assert v["verdict"] == "UNVERIFIABLE"


# --- ledger.check_consistency -----------------------------------------------

def _proof(**over):
    base = {"old_size": 1, "new_size": 2,
            "old_root": "sha256:" + "ab" * 32, "new_root": "sha256:" + "cd" * 32,
            "path": []}
    base.update(over)
    return base


@pytest.mark.parametrize("field", ["old_root", "new_root"])
def test_check_consistency_names_a_non_string_root_instead_of_crashing(field):
    # A non-string root makes `root.split(":", 1)` raise AttributeError, a sibling of
    # the (KeyError, ValueError, IndexError) the except catches, so it escapes.
    ok, reason = Ledger.check_consistency(_proof(**{field: 123}))
    assert ok is False
    assert "malformed_proof" in reason


@pytest.mark.parametrize("path", [[0], [None], 5, [["ab"]]])
def test_check_consistency_names_a_non_string_path_instead_of_crashing(path):
    # A non-string path element makes bytes.fromhex raise TypeError, and a
    # non-iterable path makes the comprehension raise TypeError -- both escape.
    ok, reason = Ledger.check_consistency(_proof(path=path))
    assert ok is False
    assert "malformed_proof" in reason


# --- receipt_sign.verify_signed ---------------------------------------------

@pytest.mark.parametrize("bad_alg", [["ed25519"], {"a": 1}])
def test_verify_signed_names_an_unhashable_algorithm_instead_of_crashing(bad_alg):
    # `alg not in KNOWN_ALGS` against a frozenset raises TypeError on an unhashable
    # sig_alg, escaping the "never raises on hostile input" contract.
    env = {"receipt": {"x": 1}, "signature": {"sig_alg": bad_alg}}
    assert verify_signed(env, b"\x11" * 32) == (False, "unknown_algorithm")


@pytest.mark.parametrize("bad_so", [5, None, True])
def test_verify_signed_names_a_non_iterable_signed_over_instead_of_crashing(bad_so):
    # `list(signed_over)` raises TypeError on a non-iterable signed_over, escaping.
    env = {"receipt": {"x": 1},
           "signature": {"sig_alg": "ed25519", "signed_over": bad_so}}
    assert verify_signed(env, b"\x11" * 32) == (False, "signed_over_mismatch")


@pytest.mark.parametrize("bad_sig", [123, [1, 2], {"x": 1}, True])
def test_verify_signed_names_a_non_string_sig_instead_of_crashing(bad_sig):
    # `bytes.fromhex(sig["sig"])` raises TypeError on a non-string sig, past the
    # `except (Ed25519Error, ValueError)` that guards it.
    env = ed25519_attach(_r(), b"\x00" * 64, b"\x11" * 32, key_id="k1").to_dict()
    env["signature"]["sig"] = bad_sig
    assert verify_signed(env, b"\x11" * 32) == (False, "bad_signature")


def test_verify_signed_names_a_missing_sig_instead_of_crashing():
    # `sig["sig"]` raises KeyError when the field is absent, past the same except.
    env = ed25519_attach(_r(), b"\x00" * 64, b"\x11" * 32, key_id="k1").to_dict()
    del env["signature"]["sig"]
    assert verify_signed(env, b"\x11" * 32) == (False, "bad_signature")


# --- envelope.verify_citations ----------------------------------------------

@pytest.mark.parametrize("bad_citation", [1, "abc", [1, 2], True])
def test_verify_citations_names_a_non_object_citation_instead_of_crashing(
        bad_citation):
    # `c.get(...)` on a non-dict citation element raises AttributeError, escaping.
    result = verify_citations([bad_citation], lambda s: None)
    assert result["all_verified"] is False
    assert result["verdicts"][0]["verdict"] == "drift"


@pytest.mark.parametrize("bad_block", [5, True, "abc"])
def test_verify_citations_survives_a_non_list_citations_block(bad_block):
    # `for c in citations or []` iterates a truthy scalar and raises TypeError.
    result = verify_citations(bad_block, lambda s: None)
    assert result["all_verified"] is False


@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf")])
def test_verify_citations_names_a_non_finite_offset_instead_of_crashing(
        non_finite):
    # json.loads parses a bare `Infinity` / `-Infinity` to float('inf'), so a
    # stranger can seat one in start_byte. int(float('inf')) raises OverflowError
    # -- an ArithmeticError, sibling of none of (KeyError, TypeError, ValueError)
    # the offset except catches -- so it escapes the drift verdict. (A NaN offset
    # already lands as drift: int(nan) raises the ValueError that except catches.)
    result = verify_citations(
        [{"source_sha256": "de", "start_byte": non_finite,
          "end_byte": 10, "quote_sha256": "x"}],
        lambda s: b"hello world")            # non-None src reaches the int() line
    assert result["all_verified"] is False
    assert result["verdicts"][0]["verdict"] == "drift"


# --- chain.validate_chain ---------------------------------------------------

@pytest.mark.parametrize("bad_stage", ["forged", ["forged"], 5, None])
def test_validate_chain_names_a_non_receipt_stage_instead_of_crashing(bad_stage):
    # asdict() on a stage that is neither a dict nor a dataclass raises TypeError.
    # validate_chain has no try/except, so it escapes the DRIFT/UNVERIFIABLE the
    # docstring promises.
    assert validate_chain([bad_stage]).verdict == "UNVERIFIABLE"


def test_validate_chain_names_a_stage_missing_a_field_instead_of_crashing():
    # A dict stage missing a required key raises KeyError inside StageReceipt(...).
    v = validate_chain([{"inputs_hash": "a", "outputs_hash": "b",
                         "verdict": "PASS"}])
    assert v.verdict == "UNVERIFIABLE"


# --- contest.verify ---------------------------------------------------------

@pytest.mark.parametrize("bad_pub", [123, ["ab"], {"x": 1}, True])
def test_contest_verify_names_a_non_string_public_key_instead_of_crashing(bad_pub):
    # A contest arrives from JSON; __post_init__ never checks contester_public_key.
    # verify() does bytes.fromhex(contester_public_key), raising TypeError past the
    # `except (Ed25519Error, ValueError)`.
    c = Contest("sha256:" + "ab" * 32, ContestReason.CHECKER_IS_WRONG,
                "a real statement", "key-1", bad_pub, "aa")
    assert c.verify() == (False, "bad_signature")


# --- why.explain ------------------------------------------------------------

@pytest.mark.parametrize("content", ["[]", "5", '"x"', "true", "null",
                                     '{"schema": "x"}'])
def test_explain_names_a_non_receipt_record_instead_of_crashing(tmp_path, content):
    # The single-file path in _envelopes skips the receipt-shape guard the directory
    # path applies, so env["receipt"] raises TypeError/KeyError. explain promises a
    # named WhyError, and its CLI catches only WhyError.
    p = tmp_path / "rec.json"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(WhyError):
        explain(p)


@pytest.mark.parametrize("hostile_sig", [[1, 2], "x", 5, True,
                                         {"sig_alg": ["ed25519"]},
                                         {"sig_alg": "ed25519", "public_key": 123}])
def test_explain_survives_a_hostile_signature_on_a_valid_receipt(tmp_path,
                                                                 hostile_sig):
    # A valid receipt body clears _envelopes and Receipt.from_dict, so
    # _signature_state is reached with an attacker signature: sig.get /
    # sig_alg-in-frozenset / bytes.fromhex each raise, escaping explain.
    p = tmp_path / "rec.json"
    env = {"schema": "flywheel.signed-receipt/v1",
           "receipt": _r().to_dict(), "signature": hostile_sig}
    p.write_text(json.dumps(env), encoding="utf-8")
    out = explain(p)                                  # must not raise
    assert out["signature"]["verified"] is False


def test_explain_prefix_survives_a_non_string_claim_digest(tmp_path):
    # In prefix mode, claim_sha256 is read raw before Receipt.from_dict. A
    # non-string value makes .split raise AttributeError; the search must stay a
    # named WhyError (no match), not a traceback.
    body = _r().to_dict()
    body["claim_sha256"] = 12345
    p = tmp_path / "d"
    p.mkdir()
    (p / "rec.json").write_text(
        json.dumps({"schema": "flywheel.signed-receipt/v1",
                    "receipt": body, "signature": None}), encoding="utf-8")
    with pytest.raises(WhyError):
        explain(p, prefix="abc")
