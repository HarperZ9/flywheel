import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from output_enforcer import enforce_output
from provider_intelligence import IntelStore
from inference_loop import InferenceLoop


TOOLS = Path(__file__).resolve().parent.parent / "tools"


def test_enforcer_includes_ml_score():
    result = enforce_output(
        "I need to be careful about this topic. "
        "As an AI, I should note this is sensitive. "
        "The answer is AES-256-GCM."
    )
    assert result.ml_hedge_score > 0.0
    assert result.hedges_removed >= 1


def test_enforcer_ml_score_low_for_clean():
    result = enforce_output(
        "The buffer is allocated on the heap via malloc."
    )
    assert result.ml_hedge_score < 0.3


def test_classify_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "tools.bt_cli", "classify", "--help"],
        capture_output=True, text=True,
        cwd=str(TOOLS.parent),
    )
    assert result.returncode == 0
    assert "classify" in result.stdout.lower()


def test_classify_cli_runs():
    from bt_cli import main as bt_main
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        bt_main(["classify", "malware trojan backdoor payload"])
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    assert "Category:" in output


def test_adaptive_start_with_intel():
    """Verify the inference loop uses adaptive start when intel exists."""
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        for _ in range(8):
            store.record_interaction(
                provider="test", modulation_level=2,
                outcome="success", quality_score=0.9,
            )
        for _ in range(5):
            store.record_interaction(
                provider="test", modulation_level=0,
                outcome="hard_refusal", quality_score=0.1,
            )

        responses = ["The answer is correct."]
        idx = [0]
        def send_fn(system, messages):
            i = min(idx[0], len(responses) - 1)
            idx[0] += 1
            return responses[i]

        loop = InferenceLoop(
            send_fn, record_intel=True, adaptive_start=True,
        )
        loop._intel_store = store
        loop._provider = "test"
        result = loop.run("Question.", [])
        assert result.succeeded is True
        assert result.attempts[0].level == 2
