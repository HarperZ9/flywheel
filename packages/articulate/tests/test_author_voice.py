"""The author-voice profile: literary devices judged by function, the register
measured and protected, and the factual rules still in force.

Author-written samples come only from the published essays in
tests/fixtures/author_voice/published.md and from the phrases in the author's
own description of their process. The other sentences are synthetic and say so.
"""
import pathlib

import pytest

from articulate import (checkext, device_function, domains, host_edit, voice_intent,
                        voice_register)

FIX = pathlib.Path(__file__).parent / "fixtures" / "author_voice" / "published.md"
PUBLISHED = FIX.read_text(encoding="utf-8").split("-->", 1)[1].strip()
FIRST, SECOND = PUBLISHED.split("\n\n")
# From the author's own description of their process.
PROCESS = ("Ideas keep coming, constantly flowing through me like waves in the ocean. "
           "Putting them down is turning potential into kinetic energy. "
           "I lay down the path as I walk.")


def _empty(text):
    r = checkext.check_text(text, profile=domains.load_profile("author-voice"))
    return r, [f for f in r["low"] if f["category"] == "device-empty"]


# Same device, meaningful against empty (synthetic sentences).
PAIRS = [
    ("anaphora",
     "I watched the gauge, I watched the clock, I watched the needle climb past red.",
     "We need clarity, we need focus, we need vision."),
    ("tricolon",
     "We tied the rope to the mast, checked the knot at dawn and watched the tide.",
     "It is about innovation, transformation and excellence."),
    ("metaphor", "The tooling is the rope.", "Innovation is a journey."),
]


@pytest.mark.parametrize("device,meaningful,empty", PAIRS)
def test_the_same_device_reads_by_what_it_carries(device, meaningful, empty):
    good = [d for d in device_function.analyze(meaningful)["devices"] if d["device"] == device]
    bad = [d for d in device_function.analyze(empty)["devices"] if d["device"] == device]
    assert good and all(d["verdict"] == "carries" for d in good)
    assert bad and all(d["verdict"] == "empty" for d in bad)
    assert not _empty(meaningful)[1]
    assert _empty(empty)[1]


def test_a_stock_vehicle_is_named_in_the_finding():
    _r, found = _empty("Our platform is a beacon of excellence.")
    assert found and "beacon" in found[0]["label"]


def test_the_authors_simile_carries_an_image_and_is_never_flagged():
    sims = [d for d in device_function.analyze(PROCESS)["devices"] if d["device"] == "simile"]
    assert sims and sims[0]["verdict"] == "carries" and "image" in sims[0]["carries"]
    assert not _empty(PROCESS)[1]


def test_like_as_a_verb_is_not_a_simile():
    assert not [d for d in device_function.analyze("I like coffee a lot.")["devices"]
                if d["device"] == "simile"]


def test_a_motif_needs_three_paragraphs():
    three = "The rope was wet.\n\nI held the rope.\n\nThe rope held."
    two = "The rope was wet.\n\nI held the rope."
    assert [d for d in device_function.analyze(three)["devices"] if d["device"] == "motif"]
    assert not [d for d in device_function.analyze(two)["devices"] if d["device"] == "motif"]


def test_no_device_gates_under_author_voice_and_the_report_names_what_it_cannot_read():
    r, _ = _empty("We need clarity, we need focus, we need vision. It is not a tool. It is a way.")
    assert r["gate"] == "ok"
    assert device_function.analyze("x")["unread"] == ["irony", "synecdoche"]


def test_factual_rules_still_apply_under_author_voice():
    prof = domains.load_profile("author-voice")
    r = checkext.check_text("Look, this checker is 10x faster than anything else. Sure.",
                            profile=prof)
    assert "claim-without-evidence" in [f["category"] for f in r["low"]]
    r = checkext.check_text("I watched the gauge climb — nobody looked up.", profile=prof)
    assert "em-dash" in [f["category"] for f in r["high"]]
    assert prof["no_em_dash"] is True


# The register, measured on published text.

def test_published_excerpts_carry_the_register_features():
    first = voice_register.measure(FIRST)["counts"]
    assert first["first-person"] >= 2 and first["questions"] == 1
    assert first["forward-motion"] >= 1
    process = voice_register.measure(PROCESS)["counts"]
    assert process["imagery"] >= 2 and process["forward-motion"] >= 1


def test_register_readers_skip_a_neutral_sentence():
    counts = voice_register.measure("The system stores records in a table.")["counts"]
    assert counts["first-person"] == counts["questions"] == counts["observer"] == 0
    assert counts["jaded"] == counts["contrarian"] == counts["wonder"] == 0


FLAT = ("Products designed for retention can embed that pattern. Whether the relationship "
        "allows completion is an open question.")


def test_a_neutral_rewrite_of_published_text_is_named_as_flattening():
    report = voice_register.flattening(FIRST, FLAT)
    assert report["flattened"]
    assert {"first-person", "questions", "forward-motion"} <= set(report["lost"])


def test_a_faithful_edit_of_published_text_is_not_flattening():
    edited = FIRST.replace("That recognition matters", "That recognition counts")
    assert not voice_register.flattening(FIRST, edited)["flattened"]


def test_turning_a_run_of_ideas_into_a_list_is_flattening():
    run = ("I walked the yard and counted the trucks and watched the gate swing and then the "
           "rain came in off the harbor and nobody moved, so I kept counting until the light "
           "went.")  # synthetic
    listed = ("- I walked the yard.\n- I counted the trucks.\n- I watched the gate.\n"
              "- The rain came off the harbor.\n- I kept counting until the light went.")
    report = voice_register.flattening(run, listed)
    assert "runs-to-list" in report["lost"]


def test_edits_under_author_voice_keep_the_original_when_the_register_is_lost():
    plan = host_edit.edit_plan(FIRST, profile="author-voice")
    out = host_edit.edit_submit(FIRST, FLAT, plan["plan_id"])
    assert out["text"] == FIRST
    assert out["register"]["flattened"]
    assert any("flattened the author's register" in r for ref in out["refused"]
               for r in ref["reasons"])


def test_a_faithful_edit_under_author_voice_is_accepted():
    plan = host_edit.edit_plan(FIRST, profile="author-voice")
    edited = FIRST.replace("That recognition matters", "That recognition counts")
    out = host_edit.edit_submit(FIRST, edited, plan["plan_id"])
    assert out["text"] == edited and not out["register"]["flattened"]


def test_author_voice_plans_freeze_the_authors_terms():
    text = "I keep the boundary between signal and noise where I can see it."
    plan = host_edit.edit_plan(text, profile="author-voice")
    kinds = {s.get("kind") for s in plan["protected_spans"]}
    assert "term" in kinds


# The intent spec.

def test_the_author_voice_spec_wants_the_register_and_sets_no_device_limit():
    spec = voice_intent.load_spec("author-voice")
    for key in ("imagery", "observer", "forward-motion", "counter-view", "reader-question"):
        assert spec["wants"][key] == 1
    for device in ("anaphora-run", "tricolon", "split-antithesis", "closing-maxim"):
        assert device not in spec["limits"]
    assert spec["limits"]["hedge"] == 0
    assert set(spec["protects"]) == set(voice_register.FEATURES)


def test_a_polemic_draft_scores_above_a_flat_one_on_the_author_spec():
    spec = voice_intent.load_spec("author-voice")
    polemic = ("Everyone says the dashboard is the truth. Sure. I watched the gauge climb past "
               "red, and I already knew what the next ten seconds would look like, and nobody "
               "looked up from the screen, so I waited. I think the panel lies by omission. "
               "Funny how that works, right?")  # synthetic
    flat = "This tool is useful. It helps teams. It improves outcomes."
    assert voice_intent.check(polemic, spec)["score"] > voice_intent.check(flat, spec)["score"]


# Voice apply: the author's own draft.

@pytest.fixture
def store(tmp_path, monkeypatch):
    from articulate import voice, voice_identity, voice_store
    from voice_fixtures import VARIED
    folder = tmp_path / "store"
    voice_identity.ensure_identity(folder)
    profile = voice_identity.bind(voice.build_profile([t for _, _, t in VARIED]), folder)
    voice_store.save(profile, "mine", folder)
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(folder))
    return folder


def test_voice_apply_keeps_the_draft_when_the_rewrite_flattens_it(store):
    from articulate import voice_apply
    plan = voice_apply.plan(FIRST, "mine", authored_by_user=True, directory=store)
    out = voice_apply.submit(FIRST, FLAT, plan["plan_id"], directory=store)
    assert out["text"] == FIRST and out["register"]["flattened"]
    assert "voice" in out


def test_voice_apply_takes_the_change_when_the_author_accepts_it(store):
    from articulate import voice_apply
    plan = voice_apply.plan(FIRST, "mine", authored_by_user=True, directory=store)
    out = voice_apply.submit(FIRST, FLAT, plan["plan_id"], directory=store,
                             accept_register_change=True)
    assert out["text"] != FIRST and out["register"]["flattened"]


# Analogy, symbol and confrontation (all sentences below are synthetic).

MAPPED = ("A code review is like a pre-flight check: the reviewer is the co-pilot, the diff "
          "is the checklist, and nobody takes off until both sign.")
STOCK = "A code review is like a rollercoaster."
LITERAL = "Build 2 runs in 2.1 seconds, like build 1 did on the same 75 files."


def _analogies(text):
    return [d for d in device_function.analyze(text)["devices"] if d["device"] == "analogy"]


def test_the_same_analogy_frame_reads_by_the_structure_it_carries():
    good, bad = _analogies(MAPPED), _analogies(STOCK)
    assert good and good[0]["verdict"] == "carries" and good[0]["detail"] == "2 mapped parts"
    assert bad and bad[0]["verdict"] == "empty" and bad[0]["stock"] == ["rollercoaster"]
    assert not _empty(MAPPED)[1]
    assert _empty(STOCK)[1] and "analogy" in _empty(STOCK)[1][0]["label"]


def test_a_relation_carried_across_is_an_analogy_that_carries():
    rows = _analogies("A token is to a server as a key is to a lock.")
    assert rows and rows[0]["verdict"] == "carries"


def test_a_literal_comparison_with_real_numbers_is_not_a_device():
    rows = device_function.analyze(LITERAL)["devices"]
    assert not [d for d in rows if d["device"] in ("analogy", "simile", "metaphor")]
    assert not _empty(LITERAL)[1]


def test_flattening_or_dropping_an_analogy_is_a_loss():
    assert voice_register.measure(MAPPED)["counts"]["analogy"] == 1
    assert "analogy" in voice_register.flattening(MAPPED, STOCK)["lost"]
    assert "analogy" in voice_register.flattening(
        MAPPED, "A code review needs two people to sign.")["lost"]
    plan = host_edit.edit_plan(MAPPED, profile="author-voice")
    flat = "A code review is like a rollercoaster, and nobody takes off until both sign."
    out = host_edit.edit_submit(MAPPED, flat, plan["plan_id"])
    assert out["text"] == MAPPED and "analogy" in out["register"]["lost"]


CONFRONT = ("You say you read every log, but you skip the one that names you. Ask yourself "
            "why. The scale of justice we all hold tips the same way every time.")


def test_symbol_and_confrontation_are_measured_and_protected():
    counts = voice_register.measure(CONFRONT)["counts"]
    assert counts["confrontation"] >= 2 and counts["symbol"] >= 1
    # The softened version keeps the scope words, so the meaning guard passes it
    # and the register guard is what keeps the original.
    soft = ("People read every log and skip the one that names them. We all hold opinions "
            "that tip one way every time.")
    report = voice_register.flattening(CONFRONT, soft)
    assert {"confrontation", "symbol"} <= set(report["lost"])
    plan = host_edit.edit_plan(CONFRONT, profile="author-voice")
    out = host_edit.edit_submit(CONFRONT, soft, plan["plan_id"])
    assert out["text"] == CONFRONT
    assert {"confrontation", "symbol"} <= set(out["register"]["lost"])
    assert any("flattened" in r for ref in out["refused"] for r in ref["reasons"])


def test_plain_address_and_a_literal_mirror_are_not_confrontation_or_symbol():
    counts = voice_register.measure("You said the build passed, and it did. "
                                    "I fixed the mirror in the hall.")["counts"]
    assert counts["confrontation"] == 0 and counts["symbol"] == 0


def test_a_confrontation_cannot_carry_an_unsourced_statistic():
    prof = domains.load_profile("author-voice")
    made_up = CONFRONT + " Studies show 90% of you never open it."
    r = checkext.check_text(made_up, profile=prof)
    assert "claim-without-evidence" in [f["category"] for f in r["low"]]
    r = checkext.check_text(CONFRONT, profile=prof)
    assert "claim-without-evidence" not in [f["category"] for f in r["low"]]


# Research and publication: an analogy that carries an argument points at a map.

def _pub(text):
    r = checkext.check_text(text, profile=domains.load_profile("publication"))
    return r, [f for f in r["low"] if f["category"] == "analogy-untested"]


def test_an_argument_by_analogy_with_no_map_gets_advice_not_a_block():
    r, found = _pub(MAPPED)
    assert found and r["gate"] == "ok"


def test_an_analogy_that_points_at_its_map_gets_no_advice():
    _r, found = _pub(MAPPED + " The map breaks when the diff runs past one screen.")
    assert not found


def test_a_stock_comparison_or_author_voice_gets_no_map_advice():
    assert not _pub(STOCK)[1]
    r = checkext.check_text(MAPPED, profile=domains.load_profile("author-voice"))
    assert "analogy-untested" not in [f["category"] for f in r["low"]]
