"""C2 for the spine: no learned model can reach the spine verifier.

The spine verifier is on the accept path for any receipt written in spine
form, so it is listed in the verifier entry points, and the import closure
walk that holds the rest of the verifier path holds it too.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_verifier_stdlib import VERIFIER_ENTRY_POINTS, closure  # noqa: E402

SPINE = ["spine", "spine.vocab", "spine.record", "spine.cause",
         "spine.natives", "spine.verify"]


def test_every_spine_module_is_a_verifier_entry_point():
    assert set(SPINE) <= set(VERIFIER_ENTRY_POINTS)


def test_the_spine_closure_reaches_no_third_party_package_or_model_runtime():
    reached, third_party_hits = closure(SPINE)
    assert third_party_hits == []
    for model_runtime in ("serve", "proposer_local", "quant_dither", "endpoint",
                          "endpoints", "local_model"):
        assert model_runtime not in reached, f"{model_runtime} reaches the spine"
