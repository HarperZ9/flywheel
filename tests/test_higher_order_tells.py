"""Higher-order (Articulate next-layer) report-only tells.

Six structural detectors that catch machine-shaped prose the phrase engine
passes: corrective negation, parallel enumeration, aphoristic landing, repeated
syntactic frame, specificity floor, and rhythm variance. Every one is
report-only: it must never gate and never move the headline number. Positive
fixtures fire the detector; negative fixtures (clean, varied, concrete prose)
must stay quiet. These are quality diagnostics, not a way to defeat detection.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT))

import check_writing as CW  # noqa: E402
import writing_lists as WL  # noqa: E402
import writing_profiles as WP  # noqa: E402
from harness.writing_lint import higher_order as HO  # noqa: E402
from harness.writing_lint import ho_frames as HF  # noqa: E402
from harness.writing_lint import regen_loop as RL  # noqa: E402

NEW_CATS = ("corrective_negation", "parallel_enumeration", "aphoristic_landing",
            "repeated_syntactic_frame", "specificity_floor", "rhythm_variance")


def v(text):
    return CW.check_text(text, WP.load("readme"))


# --- registration and gate invariance ---------------------------------------

def test_new_categories_are_known_and_report_only():
    for cat in NEW_CATS:
        assert cat in WL.KNOWN_CATEGORIES, cat
        assert cat in WL.REPORT_ONLY_CATEGORIES, cat


def test_new_categories_never_gate_in_any_slop_level():
    text = ("We price loans, read scans, and flag threats, not by hand. "
            "There is a check. There is a witness. There is a verdict.")
    for name in ("procedure", "readme", "narrative", "research"):
        r = CW.check_text(text, WP.load(name))
        for cat in NEW_CATS:
            assert cat not in r["hard"], (name, cat)


def test_new_categories_do_not_move_the_headline_number():
    text = ("We price loans, read scans, and flag threats, not by hand. "
            "There is a check. There is a witness. There is a verdict here.")
    r = v(text)
    gated = {k: n for k, n in r["violations"].items()
             if k not in WL.REPORT_ONLY_CATEGORIES}
    assert not (set(NEW_CATS) & set(gated))
    assert r["per100w"] == 0.0
    assert r["report_total"] >= 1


def test_higher_order_detail_is_present_and_json_serializable():
    r = v("We check the result, not the author. There is a receipt for it.")
    assert set(NEW_CATS) <= set(r["higher_order"])
    json.dumps(r["higher_order"])  # must not raise


# --- corrective negation ------------------------------------------------------

def test_corrective_negation_comma_not_fires():
    assert v("We verify the result, not assert it.")["violations"].get(
        "corrective_negation", 0) >= 1


def test_corrective_negation_rather_than_still_fires():
    assert v("We chose to check rather than trust.")["violations"].get(
        "corrective_negation", 0) >= 1


def test_corrective_negation_adjacent_sentence_mirror_fires():
    text = ("The receipt proves the check reproduces. "
            "It does not prove the answer is true of the world.")
    assert v(text)["violations"].get("corrective_negation", 0) >= 1


def test_corrective_negation_flags_paragraph_with_two():
    text = ("We aim for accountability, not capability. "
            "The tool checks the result, not the author.")
    assert v(text)["higher_order"]["corrective_negation"]["paragraphs_flagged"] >= 1


def test_corrective_negation_quiet_on_plain_prose():
    assert "corrective_negation" not in v(
        "The parser reads the file and writes a tree.")["violations"]


# --- parallel enumeration -----------------------------------------------------

def test_parallel_enumeration_verb_series_fires():
    r = v("They help price loans, read scans, and flag threats.")
    assert r["violations"].get("parallel_enumeration", 0) >= 1


def test_parallel_enumeration_noun_series_fires():
    r = v("The tool serves courts, agencies, hospitals, and elections.")
    d = r["higher_order"]["parallel_enumeration"]
    assert r["violations"].get("parallel_enumeration", 0) >= 1
    assert d["max_items"] >= 3


def test_parallel_enumeration_balanced_tricolon_subflag():
    # A verb-led opener breaks off, leaving three near-equal noun items.
    d = v("We check money, health, safety, and freedom.")["higher_order"][
        "parallel_enumeration"]
    assert d["tricolon_balanced"] >= 1


def test_parallel_enumeration_quiet_on_two_items_and_clauses():
    assert "parallel_enumeration" not in v(
        "We support arms and legs.")["violations"]
    assert "parallel_enumeration" not in v(
        "It was hollow, which is a real problem, and you cannot see it.")[
        "violations"]


# --- aphoristic landing -------------------------------------------------------

def test_aphoristic_landing_tag_closer_fires():
    text = ("We ran the check on our own machine and wrote the verdict to a "
            "receipt offline for later. The skeptic repeats it, and that is "
            "the point.")
    assert v(text)["violations"].get("aphoristic_landing", 0) >= 1


def test_aphoristic_landing_restatement_fires():
    text = ("The verifier records every branch it takes through the source "
            "file with care. The verifier stops.")
    assert v(text)["violations"].get("aphoristic_landing", 0) >= 1


def test_aphoristic_landing_quiet_when_final_is_not_short():
    text = ("The parser reads the file. It builds a tree from the tokens. "
            "The output then lands in a fresh buffer for the next stage.")
    assert "aphoristic_landing" not in v(text)["violations"]


def test_aphoristic_landing_reports_tag_hits_anywhere():
    d = v("Work you can check is work you can walk away from, and that is the "
          "point.")["higher_order"]["aphoristic_landing"]
    assert d["tag_phrase_hits"] >= 1


# --- repeated syntactic frame -------------------------------------------------

def test_repeated_frame_flags_template_used_three_times():
    text = ("There is a receipt for every result. There is a witness that "
            "re-runs it. There is a verdict at the end of the loop.")
    r = v(text)
    assert r["violations"].get("repeated_syntactic_frame", 0) >= 1
    assert "THERE-EXIST" in r["higher_order"]["repeated_syntactic_frame"][
        "cleft_frames"]


def test_repeated_frame_weights_clefts_above_plain_openers():
    text = ("It is a receipt. It is a witness. It is a verdict.")
    d = v(text)["higher_order"]["repeated_syntactic_frame"]
    assert d["weighted_score"] >= 6  # 3 cleft openers weighted >= 2 each


def test_repeated_frame_quiet_on_varied_openers():
    text = ("Marco climbed the oak. When the wind rose, we came down. "
            "It cost four hours. Rain arrives Thursday.")
    assert "repeated_syntactic_frame" not in v(text)["violations"]


# --- specificity floor --------------------------------------------------------

def test_specificity_floor_flags_anchorless_and_unsupported():
    text = ("The idea matters more than any tool. Studies show the method "
            "works, and it handles many cases.")
    d = v(text)["higher_order"]["specificity_floor"]
    assert d["anchorless_paragraphs"] >= 1
    assert d["unsourced_authority"] and d["unquantified_magnitude"]


def test_specificity_floor_flags_bare_number_claim():
    d = v("The accuracy improved by 40 last quarter.")["higher_order"][
        "specificity_floor"]
    assert d["bare_number_claims"] >= 1


def test_specificity_floor_quiet_on_concrete_anchored_prose():
    text = ("On March 3, 2026 the Kessler crane billed $380 for 3 hours at "
            "the Aldridge site.")
    d = v(text)["higher_order"]["specificity_floor"]
    assert d["anchorless_paragraphs"] == 0
    assert d["bare_number_claims"] == 0
    assert not d["unsourced_authority"] and not d["unquantified_magnitude"]


# --- rhythm variance ----------------------------------------------------------

def test_rhythm_variance_flags_metronomic_cadence():
    text = ("The system reads the file today. The system writes the result "
            "now. The system checks the hash again. The system sends the "
            "report along. The system logs the run here. The system clears "
            "the queue soon.")
    r = v(text)
    assert r["violations"].get("rhythm_variance", 0) >= 1
    d = r["higher_order"]["rhythm_variance"]
    assert d["longest_same_opening_pos_run"] >= 4


def test_rhythm_variance_quiet_on_varied_cadence():
    text = ("Stop. The crane arrived late and the operator wanted four full "
            "hours for a job that ran ninety minutes at most. I argued it. "
            "Dana cut the extra charge without any fuss the next morning. "
            "Fine.")
    assert "rhythm_variance" not in v(text)["violations"]


def test_rhythm_variance_none_metric_on_too_few_sentences():
    n, detail = HF.rhythm_variance(["Only two.", "Sentences here."])
    assert n == 0 and detail["cv"] is None


# --- shared tagger sanity -----------------------------------------------------

def test_coarse_pos_separates_function_verb_and_noun():
    from harness.writing_lint import ho_util as U
    assert U.coarse_pos("the") == "DET"
    assert U.coarse_pos("price") == "VERB"
    assert U.coarse_pos("courts") == "NOUN"
    assert U.coarse_pos("Flywheel", initial=False) == "PN"


# --- generate-score-regenerate loop scaffold ---------------------------------

FLAGGED = ("We price loans, read scans, and flag threats, not by hand. "
           "There is a check. There is a witness. There is a verdict here.")


def test_plan_targets_maps_fired_signals_to_directives():
    targets = RL.plan_targets(RL.score(FLAGGED, "chat"))
    signals = {t["signal"] for t in targets}
    assert {"parallel_enumeration", "repeated_syntactic_frame"} <= signals
    assert all(t["directive"] for t in targets)


def test_run_without_regenerate_changes_nothing_and_returns_plan():
    out = RL.run(FLAGGED, regenerate=None)
    assert out["text"] == FLAGGED           # no model wired: text is untouched
    assert out["plan"] and out["history"]
    assert out["stages"] == RL.LOOP_STAGES


def test_run_uses_injected_regenerate_seam():
    calls = []

    def fake_regen(text, targets):
        calls.append(len(targets))
        return "The parser reads a file on March 3, 2026 at the Aldridge site."

    out = RL.run(FLAGGED, regenerate=fake_regen, max_rounds=2)
    assert calls                              # the seam was invoked
    assert out["text"] != FLAGGED


def test_receipt_carries_provenance_and_does_not_target_a_low_score():
    before = RL.score(FLAGGED, "chat")
    after = RL.score("The parser reads a file on March 3, 2026.", "chat")
    rec = RL.receipt(before, after)
    assert "defeat AI detection" in rec["provenance"]
    assert "parallel_enumeration" in rec["signals_cleared"]
