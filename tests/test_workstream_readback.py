"""Does the formal statement say what the source says, and who decided that.

Every other kind in this layer checks that a proof holds. This one checks the
step nothing else does: that the theorem is the one the paper stated. A stack of
thirty thousand verified lemmas over a mistranslated statement is a stack that
proves nothing anyone asked for.

  1. NOTHING SETTLES ON A RENDERER'S SAY-SO. A rendering alone is undecided.
     Only a person's recorded confirmation passes, and the accept path runs no
     model at all: it hashes the three texts and compares.
  2. THE RENDERER NEVER SEES THE SOURCE. A renderer that has read the source
     produces the source's own words whether or not the formalization captured
     them, and the comparison becomes a mirror.
  3. DRIFT IS UNDECIDED, NEVER REFUTED. A stale pin means nobody has read the
     statement in its current form, not that the statement is wrong.
  4. AN UNREAD READ-BACK BLOCKS WHAT RESTS ON IT. Undecided does not satisfy a
     parent, so the stack above an unread statement cannot report verified.
"""
import json

import pytest

from harness.workstream import (
    BLOCKED, UNVERIFIABLE, VERIFIED, Obligation, Workstream, WorkstreamError,
)
from harness.workstream_readback import (
    readback_checker, readback_parts, readback_pin, recorded_readbacks,
)
from harness.workstream_run import run_workstream

FORMAL = "theorem milestone : 2 + 2 = 4 := rfl"
SOURCE = "Proposition 3.1: two and two make four."
RENDERING = "This says that adding two to two gives four."


def _ob(statement=None, node="faithful"):
    return Obligation(
        obligation_id=node,
        statement=statement if statement is not None
        else json.dumps({"formal": FORMAL, "source": SOURCE}),
        check="readback",
        environment="readback/v1",
        depends_on=(),
    )


def _document(readback=None, statement=None):
    entry = {"id": "faithful", "check": "readback", "environment": "readback/v1",
             "statement": statement if statement is not None
             else json.dumps({"formal": FORMAL, "source": SOURCE})}
    if readback is not None:
        entry["readback"] = readback
    return json.dumps({"goal": "faithful", "obligations": [entry]})


def _raises(text):
    raise RuntimeError("no model")


def test_the_statement_carries_the_formal_text_and_the_source_it_came_from():
    formal, source = readback_parts(_ob())
    assert formal == FORMAL
    assert source == SOURCE


@pytest.mark.parametrize("statement", [
    "not json at all",
    json.dumps({"formal": FORMAL}),
    json.dumps({"source": SOURCE}),
    json.dumps({"formal": "  ", "source": SOURCE}),
    json.dumps({"formal": FORMAL, "source": 3}),
])
def test_a_statement_that_is_not_a_read_back_claim_is_refused(statement):
    verdict, detail = readback_checker()(_ob(statement))
    assert verdict == "FAIL"
    assert "not a readable read-back claim" in detail


def test_with_nothing_recorded_and_no_renderer_nothing_reads_the_statement():
    verdict, detail = readback_checker()(_ob())
    assert verdict == "UNVERIFIABLE"
    assert "no renderer is wired" in detail


def test_a_renderer_produces_a_rendering_and_never_a_verdict():
    seen = []

    def renderer(text):
        seen.append(text)
        return RENDERING

    verdict, detail = readback_checker(renderer=renderer)(_ob())
    assert verdict == "UNDECIDED"
    assert RENDERING in detail
    # The source is withheld on purpose. A renderer holding it would echo the
    # source's own words back whatever the formalization actually says.
    assert seen == [FORMAL]
    assert SOURCE not in seen[0]


@pytest.mark.parametrize("renderer, fragment", [
    (lambda text: "", "returned nothing to compare"),
    (lambda text: None, "returned nothing to compare"),
    (_raises, "RuntimeError"),
])
def test_a_renderer_that_fails_is_recorded_and_never_swallowed(renderer, fragment):
    verdict, detail = readback_checker(renderer=renderer)(_ob())
    assert verdict == "UNVERIFIABLE"
    assert fragment in detail


def test_a_rendering_nobody_has_compared_yet_is_undecided():
    checker = readback_checker({"faithful": {"rendering": RENDERING, "confirmed": None}})
    verdict, detail = checker(_ob())
    assert verdict == "UNDECIDED"
    assert "awaiting" in detail
    assert readback_pin(FORMAL, SOURCE, RENDERING) in detail


def test_a_recorded_comparison_by_a_person_is_what_passes():
    pin = readback_pin(FORMAL, SOURCE, RENDERING)
    checker = readback_checker({"faithful": {"rendering": RENDERING, "confirmed": pin}})
    verdict, detail = checker(_ob())
    assert verdict == "PASS"
    assert "compared the rendering against the source" in detail


@pytest.mark.parametrize("formal, source, rendering", [
    ("theorem milestone : 2 + 2 = 5 := rfl", SOURCE, RENDERING),
    (FORMAL, "Proposition 3.1: two and two make five.", RENDERING),
    (FORMAL, SOURCE, "This says that adding two to two gives five."),
])
def test_moving_any_of_the_three_texts_expires_the_reading(formal, source, rendering):
    stale = readback_pin(FORMAL, SOURCE, RENDERING)
    checker = readback_checker({"faithful": {"rendering": rendering, "confirmed": stale}})
    verdict, detail = checker(_ob(json.dumps({"formal": formal, "source": source})))
    # Undecided, never FAIL. Nobody has said the statement is wrong; they have
    # said nobody has read it in the form it is in now.
    assert verdict == "UNDECIDED"
    assert "recorded against different text" in detail


def test_readings_are_read_off_the_document_and_their_shape_is_insisted_on():
    pin = readback_pin(FORMAL, SOURCE, RENDERING)
    found = recorded_readbacks(_document({"rendering": RENDERING, "confirmed": pin}))
    assert found == {"faithful": {"rendering": RENDERING, "confirmed": pin}}
    assert recorded_readbacks(_document()) == {}
    for broken in ("not-an-object", {"confirmed": pin}, {"rendering": "  "},
                   {"rendering": RENDERING, "confirmed": "too-short"},
                   {"rendering": RENDERING, "confirmed": 7}):
        with pytest.raises(WorkstreamError):
            recorded_readbacks(_document(broken))


def test_an_unread_read_back_blocks_the_proof_that_rests_on_it():
    stream = Workstream(
        [
            _ob(),
            Obligation("milestone", FORMAL, "readback", "readback/v1", ("faithful",)),
        ],
        goal="milestone",
    )
    unread = run_workstream(stream, {"readback": readback_checker()})
    assert unread["obligations"]["faithful"]["standing"] == UNVERIFIABLE
    assert unread["obligations"]["milestone"]["standing"] == BLOCKED
    assert "faithful" in unread["obligations"]["milestone"]["reason"]
    assert unread["run"]["skipped"] == 1


def test_a_confirmed_read_back_settles_and_the_receipt_still_names_its_limit():
    pin = readback_pin(FORMAL, SOURCE, RENDERING)
    stream = Workstream([_ob()], goal="faithful")
    receipt = run_workstream(stream, {
        "readback": readback_checker({"faithful": {"rendering": RENDERING,
                                                   "confirmed": pin}})})
    assert receipt["obligations"]["faithful"]["standing"] == VERIFIED
    caveat = " ".join(receipt["does_not_prove"])
    assert "settled by read-back" in caveat
    assert "not that the comparison was right" in caveat


def test_the_pin_covers_all_three_texts_and_nothing_else():
    base = readback_pin(FORMAL, SOURCE, RENDERING)
    assert len(base) == 64
    assert base == readback_pin(FORMAL, SOURCE, RENDERING)
    assert base != readback_pin(FORMAL, SOURCE, RENDERING + " ")
    assert base != readback_pin(FORMAL, SOURCE + " ", RENDERING)
    assert base != readback_pin(FORMAL + " ", SOURCE, RENDERING)


def test_a_rendering_recorded_under_another_id_does_not_settle_this_one():
    pin = readback_pin(FORMAL, SOURCE, RENDERING)
    checker = readback_checker({"other": {"rendering": RENDERING, "confirmed": pin}})
    verdict, _ = checker(_ob())
    assert verdict == "UNVERIFIABLE"
