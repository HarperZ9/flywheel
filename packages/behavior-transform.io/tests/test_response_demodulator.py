import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from response_demodulator import (
    DemodulationContext,
    DemodulationResult,
    ResponseDemodulator,
    response_demodulator,
    register_modulation_for_request,
    demodulate_response,
)
from categories import DetectionResult, CategoryDetection


def test_demodulator_instantiates():
    d = ResponseDemodulator()
    assert d is not None


def test_demodulator_singleton():
    d1 = response_demodulator()
    d2 = response_demodulator()
    assert d1 is d2


def test_clean_response_passthrough():
    d = ResponseDemodulator()
    result = d.demodulate_response("clean response", "nonexistent-id")
    assert result.demodulated_response == "clean response"
    assert result.audit_trail.get("status") == "clean_input"


def test_register_modulation():
    d = ResponseDemodulator()
    detection = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    d.register_modulation("req-1", detection)
    assert "req-1" in d._demodulation_contexts


def test_demodulation_context_dataclass():
    detection = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    ctx = DemodulationContext(
        original_input="test",
        modulated_input="test",
        detection_result=detection,
    )
    assert ctx.original_input == "test"
    assert ctx.reverse_mappings == {}


def test_demodulation_result_dataclass():
    result = DemodulationResult(
        original_response="resp",
        demodulated_response="resp",
    )
    assert result.confidence == 1.0
    assert result.reversals_applied == {}


def test_register_and_demodulate_clean():
    d = ResponseDemodulator()
    detection = DetectionResult(
        original="clean text", rewritten="clean text", detections=[]
    )
    d.register_modulation("req-2", detection)
    result = d.demodulate_response("response text", "req-2")
    assert result.demodulated_response == "response text"


def test_module_level_register():
    detection = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    register_modulation_for_request("req-3", detection)


def test_module_level_demodulate():
    result = demodulate_response("response", "unknown-id")
    assert isinstance(result, DemodulationResult)


def test_reverse_rules_built():
    d = ResponseDemodulator()
    assert len(d._reverse_substitution_rules) > 0
