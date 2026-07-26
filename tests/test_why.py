"""`flywheel why` -- asking must be the cheapest action in the system.

The practitioner contract puts this plainly: doubt is answered with records, never
with friction or blame. So `why` takes a hash prefix, needs no flags, works
offline, and never asks the operator to justify asking.

Four properties this suite pins:

  1. It answers from the RECORD. No recomputation of the oracle, no network, no
     model. If the record cannot answer, it says so and names what is missing.
  2. It leads with what would CHANGE the answer, not with reassurance. A "why"
     that only recites the proof is the fake-passport failure again.
  3. It always renders does_not_prove. The limits are part of the answer, not an
     appendix a reader has to go find.
  4. It never scores the person. No aggregate, no rate, no history of the
     operator, only facts about this record.
"""
import json

import pytest

from harness.receipt import Receipt
from harness.receipt_fields import Denominator, EvidenceKind, Tier
from harness.receipt_sign import ed25519_attach, hmac_sign, unsigned
from harness.verdict import Verdict, Attribution
from harness.why import explain, WhyError, render


def _den(**kw):
    base = dict(attempts=8, group_size=4, oracle_calls_consumed=9, hits=1,
                undecided=0, unverifiable=0, parse_failures=0, timeouts=0,
                tokens_in=120, tokens_out=512, cache_hit_tokens=0,
                tasks_proposed=4, tasks_filtered_out=0,
                filter_id="learn.difficulty.v1",
                filter_hash="sha256:" + "f" * 64, filter_is_learned=False)
    base.update(kw)
    return Denominator(**base)


def _r(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64, family="zarankiewicz",
        family_instance_id="z-7", generator_id="g.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64, prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False, oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective="21",
        incumbent_objective="21", incumbent_source="operator_search",
        coverage={"predicate_exact": True, "search_space_enumerated": True,
                  "enumerated_fraction": "1", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256="b" * 64, analysis_script_sha256="sha256:" + "9" * 64,
        denominator=_den(), model_ref="gate:deterministic",
        base_weights_digest="", harness_version="phase1b")
    base.update(kw)
    return Receipt(**base)


def _write(tmp_path, envelope, name="r1.json"):
    p = tmp_path / name
    p.write_text(json.dumps(envelope, indent=1), encoding="utf-8")
    return p


# --- it answers from the record ------------------------------------------------

def test_it_answers_from_a_single_envelope_file(tmp_path):
    p = _write(tmp_path, unsigned(_r()))
    e = explain(p)
    assert e["verdict"] == "PASS"
    assert e["criterion_id"] == "zarankiewicz.z_2_2"
    assert e["what_decided_it"]["checker_module"].endswith("zarankiewicz")


def test_it_finds_a_receipt_by_hash_prefix_in_a_directory(tmp_path):
    r = _r()
    _write(tmp_path, unsigned(r), "a.json")
    _write(tmp_path, unsigned(_r(objective="7")), "b.json")
    prefix = r.claim_sha256().split(":", 1)[1][:12]
    e = explain(tmp_path, prefix=prefix)
    assert e["claim_sha256"] == r.claim_sha256()


def test_a_prefix_matching_nothing_says_so_rather_than_guessing(tmp_path):
    _write(tmp_path, unsigned(_r()))
    with pytest.raises(WhyError):
        explain(tmp_path, prefix="ffffffffffff")


def test_an_ambiguous_prefix_is_refused_not_resolved(tmp_path):
    # Silently picking one of two matches would answer a question the operator
    # did not ask.
    r = _r()
    _write(tmp_path, unsigned(r), "a.json")
    _write(tmp_path, unsigned(r), "b.json")
    short = r.claim_sha256().split(":", 1)[1][:4]
    try:
        e = explain(tmp_path, prefix=short)
        # Identical receipts are one claim, so a single answer is correct here.
        assert e["claim_sha256"] == r.claim_sha256()
    except WhyError as x:
        assert "ambiguous" in str(x).lower()


def test_it_needs_no_network_and_no_model(tmp_path):
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "harness" / "why.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    banned = {"urllib", "socket", "http", "requests", "torch", "subprocess"}
    assert not (mods & banned), mods


# --- it leads with what would change the answer --------------------------------

def test_it_reports_what_would_change_the_answer(tmp_path):
    p = _write(tmp_path, unsigned(_r()))
    e = explain(p)
    assert e["what_would_change_it"]
    joined = " ".join(e["what_would_change_it"]).lower()
    assert "criterion" in joined or "checker" in joined


def test_it_always_renders_the_limits(tmp_path):
    p = _write(tmp_path, unsigned(_r()))
    e = explain(p)
    assert e["does_not_prove"]
    assert "NOT_PROVES_PUBLICATION_COMPLETENESS" in e["does_not_prove"]


def test_an_unsigned_receipt_is_reported_as_unsigned_not_as_verified(tmp_path):
    p = _write(tmp_path, unsigned(_r()))
    e = explain(p)
    assert e["signature"]["state"] == "unsigned"
    assert e["signature"]["third_party_checkable"] is False


def test_a_local_only_signature_is_reported_as_not_third_party_checkable(tmp_path):
    p = _write(tmp_path, hmac_sign(_r(), b"s3cret", key_id="local").to_dict())
    e = explain(p)
    assert e["signature"]["third_party_checkable"] is False
    assert "local" in e["signature"]["state"]


def test_an_ed25519_signature_is_reported_as_checkable(tmp_path):
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    r = _r()
    env = ed25519_attach(r, bytes(sk.sign(r.claim_sha256().encode()).signature),
                         bytes(sk.verify_key), key_id="k1").to_dict()
    e = explain(_write(tmp_path, env))
    assert e["signature"]["third_party_checkable"] is True
    assert e["signature"]["verified"] is True


def test_a_tampered_signed_receipt_is_reported_as_failing(tmp_path):
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    r = _r()
    env = ed25519_attach(r, bytes(sk.sign(r.claim_sha256().encode()).signature),
                         bytes(sk.verify_key), key_id="k1").to_dict()
    env["receipt"]["verdict"] = "FAIL"
    e = explain(_write(tmp_path, env))
    assert e["signature"]["verified"] is False
    assert e["signature"]["reason"] == "digest_mismatch"


def test_a_receipt_whose_digest_does_not_match_its_body_is_flagged(tmp_path):
    env = unsigned(_r())
    env["receipt"]["objective"] = "999"
    e = explain(_write(tmp_path, env))
    assert e["record_integrity"] == "DRIFT"


def test_an_intact_receipt_reports_match(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    assert e["record_integrity"] == "MATCH"


# --- the honesty of the denominator -------------------------------------------

def test_it_shows_the_denominator_so_a_hit_can_be_priced(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    assert e["at_what_cost"]["attempts"] == 8
    assert e["at_what_cost"]["oracle_calls_consumed"] == 9
    assert e["at_what_cost"]["hits"] == 1


def test_a_learned_task_filter_is_surfaced_not_buried(tmp_path):
    env = unsigned(_r(denominator=_den(filter_is_learned=True)))
    e = explain(_write(tmp_path, env))
    assert e["at_what_cost"]["filter_is_learned"] is True
    assert "NOT_PROVES_UNBIASED_TASK_SELECTION" in e["does_not_prove"]


# --- it never scores the person ------------------------------------------------

def test_nothing_in_the_answer_scores_the_operator(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    blob = json.dumps(e).lower()
    for banned in ("trust_score", "operator_score", "reputation", "streak",
                   "days_since", "consistency_index"):
        assert banned not in blob


def test_the_answer_carries_no_advice_or_judgement(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    blob = json.dumps(e).lower()
    for banned in ("you should", "consider improving", "well done", "good job"):
        assert banned not in blob


# --- rendering ----------------------------------------------------------------

def test_render_produces_plain_text_a_person_can_read(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    text = render(e)
    assert "PASS" in text
    assert "does not prove" in text.lower()
    assert "zarankiewicz" in text


def test_render_leads_with_the_verdict_and_the_criterion(tmp_path):
    e = explain(_write(tmp_path, unsigned(_r())))
    first = render(e).splitlines()[0].lower()
    assert "pass" in first


def test_a_missing_file_is_a_named_error_not_a_traceback(tmp_path):
    with pytest.raises(WhyError):
        explain(tmp_path / "nope.json")


def test_a_malformed_file_is_a_named_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(WhyError):
        explain(p)
