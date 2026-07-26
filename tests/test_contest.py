"""The contest channel: the refuted party does not decide what gets recorded.

Every other trust mechanism in this design protects a reader from the author. This
one protects a reader from the author's DISCRETION. A refutation the author can
quietly decline to record is worthless, and a grievance channel where the
complainant is handed the criterion as well as the voice just rebuilds the cage on
the other side of the bench.

So a contest:

  - is signed with the CONTESTER's key, not the author's. The author cannot mint
    one, and cannot forge agreement with one either.
  - names the exact claim digest it disputes, so it cannot be vaguely about
    everything.
  - enters the same append-only ledger as any other record, at which point
    declining to publish it is a rollback and detectable rather than a decision.
  - stays OPEN until resolved, and the open count is a published series rather
    than a queue the author drains.

What a contest is NOT: it is not a verdict. Two parties disagreeing is a recorded
fact, not a resolution, and this module refuses to adjudicate.
"""
import json

import pytest

from harness.contest import (
    Contest, ContestError, ContestReason, open_contest, contest_series,
    resolve, RESOLUTIONS,
)
from harness.ledger import Ledger
from harness.receipt import Receipt
from harness.receipt_fields import Denominator, EvidenceKind, Tier
from harness.receipt_sign import unsigned
from harness.verdict import Verdict, Attribution


def _den():
    return Denominator(
        attempts=8, group_size=4, oracle_calls_consumed=9, hits=1, undecided=0,
        unverifiable=0, parse_failures=0, timeouts=0, tokens_in=120,
        tokens_out=512, cache_hit_tokens=0, tasks_proposed=4,
        tasks_filtered_out=0, filter_id="f.v1",
        filter_hash="sha256:" + "f" * 64, filter_is_learned=False)


def _r(objective="21"):
    return Receipt(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64, family="zarankiewicz",
        family_instance_id="z-7", generator_id="g.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64, prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False, oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective=objective,
        incumbent_objective="21", incumbent_source="operator_search",
        coverage={"predicate_exact": True, "search_space_enumerated": True,
                  "enumerated_fraction": "1", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256="b" * 64, analysis_script_sha256="sha256:" + "9" * 64,
        denominator=_den(), model_ref="gate:deterministic",
        base_weights_digest="", harness_version="phase1c")


def _keypair():
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    return sk, bytes(sk.verify_key)


def _signed_contest(disputed_claim, *, reason=ContestReason.CHECKER_IS_WRONG,
                    statement="the predicate admits a false accept at n=33"):
    sk, pub = _keypair()
    draft = Contest(disputed_claim_sha256=disputed_claim, reason=reason,
                    statement=statement, contester_key_id="stranger-1",
                    contester_public_key=pub.hex())
    sig = bytes(sk.sign(draft.signing_payload().encode()).signature)
    return draft.attach_signature(sig), pub


# --- a contest is signed by the contester -------------------------------------

def test_a_signed_contest_verifies():
    c, pub = _signed_contest("sha256:" + "1" * 64)
    ok, reason = c.verify()
    assert ok is True
    assert reason == "ok"


def test_the_signature_covers_the_statement():
    c, pub = _signed_contest("sha256:" + "1" * 64)
    d = c.to_dict()
    d["statement"] = "actually I withdraw this"
    ok, reason = Contest.from_dict(d).verify()
    assert ok is False
    assert reason == "bad_signature"


def test_the_signature_covers_the_disputed_claim():
    c, _ = _signed_contest("sha256:" + "1" * 64)
    d = c.to_dict()
    d["disputed_claim_sha256"] = "sha256:" + "2" * 64
    assert Contest.from_dict(d).verify()[0] is False


def test_the_signature_covers_the_reason():
    c, _ = _signed_contest("sha256:" + "1" * 64)
    d = c.to_dict()
    d["reason"] = ContestReason.NOVELTY_DISPUTED.value
    assert Contest.from_dict(d).verify()[0] is False


def test_the_author_cannot_mint_a_contest_in_someone_elses_name():
    # An author holding the contester's PUBLIC key still cannot sign as them.
    _, pub = _keypair()
    other_sk, _ = _keypair()
    draft = Contest(disputed_claim_sha256="sha256:" + "1" * 64,
                    reason=ContestReason.CHECKER_IS_WRONG,
                    statement="fabricated", contester_key_id="stranger-1",
                    contester_public_key=pub.hex())
    forged = draft.attach_signature(
        bytes(other_sk.sign(draft.signing_payload().encode()).signature))
    assert forged.verify()[0] is False


def test_an_unsigned_contest_does_not_verify():
    c = Contest(disputed_claim_sha256="sha256:" + "1" * 64,
                reason=ContestReason.CHECKER_IS_WRONG, statement="x",
                contester_key_id="k", contester_public_key="00" * 32)
    ok, reason = c.verify()
    assert ok is False
    assert reason == "unsigned"


# --- a contest must be specific ------------------------------------------------

def test_a_contest_needs_a_disputed_claim_digest():
    with pytest.raises(ContestError):
        Contest(disputed_claim_sha256="", reason=ContestReason.CHECKER_IS_WRONG,
                statement="everything is wrong", contester_key_id="k",
                contester_public_key="00" * 32)


def test_a_contest_needs_a_substantive_statement():
    with pytest.raises(ContestError):
        Contest(disputed_claim_sha256="sha256:" + "1" * 64,
                reason=ContestReason.CHECKER_IS_WRONG, statement="  ",
                contester_key_id="k", contester_public_key="00" * 32)


def test_a_contest_needs_a_typed_reason():
    with pytest.raises(ContestError):
        Contest(disputed_claim_sha256="sha256:" + "1" * 64,
                reason="because I feel like it", statement="x",
                contester_key_id="k", contester_public_key="00" * 32)


def test_a_contest_needs_an_identified_key():
    with pytest.raises(ContestError):
        Contest(disputed_claim_sha256="sha256:" + "1" * 64,
                reason=ContestReason.CHECKER_IS_WRONG, statement="x",
                contester_key_id="", contester_public_key="00" * 32)


# --- it enters the same append-only log -----------------------------------------

def test_opening_a_contest_appends_it_to_the_ledger(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    c, _ = _signed_contest(claim)
    entry = open_contest(led, c)
    assert entry["kind"] == "contest"
    assert led.size() == 2


def test_a_contest_is_chained_like_any_other_entry(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    first = led.append(unsigned(_r()))
    c, _ = _signed_contest(first["claim_sha256"])
    entry = open_contest(led, c)
    assert entry["prev_hash"] == first["entry_hash"]
    assert led.verify()["verdict"] == "MATCH"


def test_declining_to_publish_a_contest_becomes_a_detectable_rollback(tmp_path):
    """The point. Once a contest is in the log, removing it is a rollback that
    consistency catches, so silence stops being a decision the author gets to
    make privately."""
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    c, _ = _signed_contest(claim)
    open_contest(led, c)
    head = led.head()

    rows = (tmp_path / "l.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "l.jsonl").write_text(rows[0] + "\n", encoding="utf-8")
    scrubbed = Ledger(tmp_path / "l.jsonl")
    scrubbed.append(unsigned(_r("99")))
    scrubbed.append(unsigned(_r("98")))
    assert scrubbed.size() > head["size"] - 1
    ok, reason = Ledger.check_consistency(scrubbed.consistency_since(head))
    assert ok is False


def test_an_unverifiable_contest_is_refused_at_the_door(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    c, _ = _signed_contest(claim)
    d = c.to_dict()
    d["statement"] = "tampered after signing"
    with pytest.raises(ContestError):
        open_contest(led, Contest.from_dict(d))


def test_a_contest_against_an_absent_claim_is_refused(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append(unsigned(_r()))
    c, _ = _signed_contest("sha256:" + "0" * 64)
    with pytest.raises(ContestError):
        open_contest(led, c)


def test_the_same_contest_twice_is_idempotent(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    c, _ = _signed_contest(claim)
    open_contest(led, c)
    open_contest(led, c)
    assert led.size() == 2


# --- open contests are a published series --------------------------------------

def test_the_series_counts_open_contests(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a = led.append(unsigned(_r("1")))["claim_sha256"]
    b = led.append(unsigned(_r("2")))["claim_sha256"]
    open_contest(led, _signed_contest(a)[0])
    open_contest(led, _signed_contest(b)[0])
    s = contest_series(led)
    assert s["open"] == 2
    assert s["resolved"] == 0
    assert s["total"] == 2


def test_resolving_a_contest_appends_rather_than_closing_it(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    c, _ = _signed_contest(claim)
    entry = open_contest(led, c)
    before = led.size()
    resolve(led, entry["key"], RESOLUTIONS.UPHELD,
            "the checker did admit a false accept at n=33; criterion amended")
    assert led.size() == before + 1          # appended, not edited
    s = contest_series(led)
    assert s["open"] == 0
    assert s["resolved"] == 1


def test_a_resolution_records_which_way_it_went(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    resolve(led, entry["key"], RESOLUTIONS.REJECTED, "n=33 is out of scope")
    s = contest_series(led)
    assert s["by_resolution"]["REJECTED"] == 1


def test_an_untyped_resolution_is_refused(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    with pytest.raises(ContestError):
        resolve(led, entry["key"], "sort of upheld", "vague")


def test_a_resolution_needs_a_reason(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    with pytest.raises(ContestError):
        resolve(led, entry["key"], RESOLUTIONS.REJECTED, "   ")


def test_resolving_an_unknown_contest_is_refused(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    with pytest.raises(ContestError):
        resolve(led, "nope", RESOLUTIONS.UPHELD, "x")


def test_resolving_twice_is_refused_rather_than_overwriting(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    resolve(led, entry["key"], RESOLUTIONS.UPHELD, "first")
    with pytest.raises(ContestError):
        resolve(led, entry["key"], RESOLUTIONS.REJECTED, "second")


# --- it refuses to adjudicate ---------------------------------------------------

def test_a_contest_is_not_a_verdict(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    blob = json.dumps(entry).lower()
    # Two parties disagreeing is a recorded fact, not a resolution.
    assert "pass" not in blob.replace("passed", "")
    assert entry.get("verdict") is None


def test_the_series_states_what_it_does_not_prove(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append(unsigned(_r()))
    s = contest_series(led)
    joined = " ".join(s["does_not_prove"])
    assert "COMPLETENESS" in joined or "UNCONTESTED" in joined


def test_no_field_scores_the_contester(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    claim = led.append(unsigned(_r()))["claim_sha256"]
    entry = open_contest(led, _signed_contest(claim)[0])
    blob = json.dumps(entry).lower()
    for banned in ("trust_score", "reputation", "credibility", "contester_score"):
        assert banned not in blob
