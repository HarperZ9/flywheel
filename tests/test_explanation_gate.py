"""The explanation gate: a diff is accepted only after the reviewer's own
explanation demonstrably engages with what changed. The check is mechanical
(named files and changed identifiers must appear in the explanation), so no
learned model sits in the accept path; what it verifies is engagement
specificity, and it says so rather than claiming to measure understanding."""

from harness.explanation_gate import SCHEMA, explanation_receipt

DIFF = """\
--- a/billing/invoice.py
+++ b/billing/invoice.py
@@ -10,7 +10,9 @@
-def total(items):
-    return sum(i.price for i in items)
+def total(items, tax_rate=0.0):
+    subtotal = sum(i.price for i in items)
+    return subtotal * (1 + tax_rate)
"""


def test_engaged_explanation_passes():
    r = explanation_receipt(
        DIFF,
        "total() in billing/invoice.py now takes a tax_rate and multiplies "
        "the subtotal by (1 + tax_rate) instead of returning the raw sum of "
        "item price values.")
    assert r["schema"] == SCHEMA
    assert r["passed"] is True
    assert r["coverage"] >= 0.6
    assert "billing/invoice.py" in r["mentioned_files"]
    assert len(r["sha256"]) == 64


def test_pasting_the_diff_back_verbatim_fails():
    """The whole premise is teach-back in the reviewer's OWN words. Pasting
    the diff back covers every term trivially; that is not comprehension
    evidence, and the gate must refuse it."""
    r = explanation_receipt(DIFF, DIFF)
    assert r["passed"] is False
    assert r["own_words_ratio"] < 0.3


def test_explanation_padded_with_the_diff_still_needs_own_words():
    padded = DIFF + "\n" + "total tax_rate subtotal"
    r = explanation_receipt(DIFF, padded)
    assert r["passed"] is False


def test_genuine_explanation_carries_words_absent_from_the_diff():
    r = explanation_receipt(
        DIFF,
        "total() in billing/invoice.py now takes a tax_rate and multiplies "
        "the subtotal by (1 + tax_rate) instead of returning the raw sum of "
        "item price values.")
    assert r["own_words_ratio"] >= 0.3


def test_vague_explanation_fails_with_the_misses_named():
    r = explanation_receipt(DIFF, "fixed the bug and cleaned things up")
    assert r["passed"] is False
    assert r["missed"], "the gate must name what the explanation never touched"
    assert "tax_rate" in r["missed"] or "subtotal" in r["missed"]


def test_the_receipt_is_honest_about_what_it_measures():
    r = explanation_receipt(DIFF, "x")
    assert "engagement" in r["note"]
    assert "understanding" in r["note"]


def test_deterministic():
    a = explanation_receipt(DIFF, "total tax_rate subtotal invoice")
    b = explanation_receipt(DIFF, "total tax_rate subtotal invoice")
    assert a["sha256"] == b["sha256"]


def test_files_keep_their_full_repo_path():
    r = explanation_receipt(
        DIFF,
        "total() in billing/invoice.py now takes a tax_rate and multiplies "
        "the subtotal by (1 + tax_rate) instead of the raw sum of price.")
    assert r["files"] == ["billing/invoice.py"]
    assert "billing/invoice.py" in r["mentioned_files"]


def test_a_basename_mention_still_counts_for_the_file():
    r = explanation_receipt(
        DIFF,
        "invoice.py: total now takes tax_rate, computes the subtotal of "
        "item price values, and scales it.")
    assert "billing/invoice.py" in r["mentioned_files"]
