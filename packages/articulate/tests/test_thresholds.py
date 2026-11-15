"""P0-c: below a word floor a device-clean text has too few tokens to be called
clean human writing, so it degrades to "unverifiable" and the receipt abstains.
A banned device is unambiguous at any length, so it still reads "flagged".
"""
import articulate
from articulate import profiles, receipt

SHORT_CLEAN = "Thanks for the update. I will review it and reply tomorrow.\n"
SHORT_DEVICE = "We leverage synergy to unlock value.\n"
SHORT_LOW_ONLY = "Great work today \U0001F389\n"
LONG_CLEAN = (
    "The team met on Tuesday to plan the next release. They agreed on the dates, "
    "assigned each task to a named owner, and set a short check-in for Friday "
    "morning to confirm the work had landed before the weekend arrived.\n"
)


def _v(text, prof="flavored"):
    return articulate.check_text(text, profile=profiles.load(prof))


def test_short_clean_text_is_unverifiable():
    r = _v(SHORT_CLEAN)
    assert r["verdict"] == "unverifiable"
    assert r["sufficient"] is False
    assert r["clean"] is True          # device-clean stays a fact; the verdict abstains
    assert r["gate"] == "ok"


def test_short_device_text_is_flagged_at_any_length():
    r = _v(SHORT_DEVICE)
    assert r["verdict"] == "flagged"
    assert r["gate"] == "blocked"      # leverage is a HIGH device


def test_short_text_with_only_an_advisory_is_not_unverifiable():
    r = _v(SHORT_LOW_ONLY)
    assert r["verdict"] != "unverifiable"   # an emoji is a real signal to report
    assert r["low"]


def test_long_clean_text_is_a_confident_clean():
    r = _v(LONG_CLEAN)
    assert r["verdict"] == "clean"
    assert r["sufficient"] is True


# --- the receipt abstains too ---------------------------------------------- #

def test_short_clean_receipt_verifies_unverifiable():
    rec = receipt.make_receipt(SHORT_CLEAN, "flavored")
    assert rec["verdict"] == "unverifiable"
    verdict, _ = receipt.verify_receipt(rec, SHORT_CLEAN)
    assert verdict == "Unverifiable"


def test_short_device_receipt_still_matches():
    rec = receipt.make_receipt(SHORT_DEVICE, "flavored")
    verdict, _ = receipt.verify_receipt(rec, SHORT_DEVICE)
    assert verdict == "Match"          # device evidence is re-derivable and valid


def test_long_clean_receipt_matches():
    rec = receipt.make_receipt(LONG_CLEAN, "flavored")
    verdict, _ = receipt.verify_receipt(rec, LONG_CLEAN)
    assert verdict == "Match"
