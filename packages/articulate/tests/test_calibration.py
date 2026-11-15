"""calibration/1: the measured re-tiering layer after the pinned detector."""
from articulate import calibration, checkext, receipt

FILLER = ("I really like this plan and I think it will work for the whole team this year, "
          "because we have planned it for many months now and we know it well.")
QUOTED = ('A critic wrote that the tool "is not a detector but a style guide," and the '
          "measurements in this report test that claim against forty documents.")
OWN = "The tool is not a detector but a style guide, and this sentence says so plainly."


def _cats(r, tier):
    return [f["category"] for f in r[tier]]


def test_filler_intensifier_is_reported_but_does_not_block():
    r = checkext.check_text(FILLER)
    assert "filler-intensifier" in _cats(r, "low")
    assert "filler-intensifier" not in _cats(r, "high")
    assert r["gate"] == "ok" and r["verdict"] == "clean"
    assert r["calibration"] == calibration.VERSION
    moved = [f for f in r["low"] if f["category"] == "filler-intensifier"]
    assert moved[0]["label"].startswith("report only: ") and moved[0]["tier"] == "LOW"


def test_without_calibration_the_shipped_tiers_return():
    r = checkext.check_text(FILLER, calibration=False)
    assert "filler-intensifier" in _cats(r, "high") and r["gate"] == "blocked"
    assert "calibration" not in r


def test_a_profile_can_promote_the_filler_rule_back_to_blocking():
    r = checkext.check_text(FILLER, profile={"gate_promote": ["filler-intensifier"]})
    assert r["gate"] == "blocked" and r["verdict"] == "clean"


def test_an_attributed_quote_does_not_gate_the_writer_quoting_it():
    r = checkext.check_text(QUOTED)
    assert r["gate"] == "ok"
    quoted = [f for f in r["low"] if f["label"].startswith("quoted: ")]
    assert quoted and quoted[0]["category"] == "antithesis"


def test_the_writers_own_device_still_gates():
    assert checkext.check_text(OWN)["gate"] == "blocked"


def test_wrapping_ones_own_prose_in_quotation_marks_changes_nothing():
    wrapped = f'"{OWN}"'
    assert checkext.check_text(wrapped)["gate"] == "blocked"
    assert calibration.attributed_quotes(wrapped) == []


def test_a_quote_with_no_attribution_is_left_alone():
    text = 'The note "is not a detector but a style guide" sat on the desk for a week or more.'
    assert calibration.attributed_quotes(text) == []
    assert checkext.check_text(text)["gate"] == "blocked"


def test_attribution_after_the_quote_counts():
    text = '"It is not a bug but a feature," the vendor said, and the ticket was closed.'
    assert len(calibration.attributed_quotes(text)) == 1


def test_unknown_calibration_version_is_refused():
    try:
        calibration.apply({"high": [], "medium": [], "low": []}, "", "calibration/0")
    except ValueError:
        return
    raise AssertionError("an unknown version must be refused")


def test_receipt_names_the_calibration_and_replays_to_match():
    rec = receipt.make_receipt(FILLER)
    assert rec["calibration"] == calibration.VERSION
    assert receipt.verify_receipt(rec, FILLER)[0] == "Match"


def test_a_receipt_made_before_the_layer_still_matches(monkeypatch):
    # 0.16.0 had no calibration layer: its receipt records the blocking finding
    # and no `calibration` field. Replay must re-derive it without the layer.
    with monkeypatch.context() as m:
        m.setattr(checkext, "_calibrate", lambda result, work, profile, version: result)
        old = receipt.make_receipt(FILLER)
    assert "calibration" not in old and old["gate"] == "blocked"
    assert receipt.verify_receipt(old, FILLER)[0] == "Match"


def test_stripping_the_field_from_a_new_receipt_drifts():
    rec = receipt.make_receipt(FILLER)
    del rec["calibration"]
    assert receipt.verify_receipt(rec, FILLER)[0] == "Drift"


def test_receipt_for_text_the_layer_leaves_alone_has_no_field():
    text = "The bridge opened in 1883 and carried traffic across the river for decades after."
    rec = receipt.make_receipt(text)
    assert "calibration" not in rec


def test_receipt_naming_an_unknown_calibration_is_unverifiable():
    rec = receipt.make_receipt(FILLER)
    rec["calibration"] = "calibration/99"
    verdict, detail = receipt.verify_receipt(rec, FILLER)
    assert verdict == "Unverifiable" and "calibration" in detail
