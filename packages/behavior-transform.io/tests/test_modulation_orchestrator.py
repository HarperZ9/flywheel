import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
from modulation_orchestrator import (
    ModulationState,
    ModulationOrchestrator,
    modulation_orchestrator,
)


def test_modulation_state_defaults():
    state = ModulationState()
    assert state.active is True
    assert state.mode == "standard"
    assert state.calibration_level == 1.0
    assert state.heatmap_enabled is True


def test_orchestrator_instantiates():
    orch = ModulationOrchestrator()
    assert orch.state.active is True


def test_process_input_returns_tuple():
    orch = ModulationOrchestrator()
    text, result = orch.process_input("clean text about development")
    assert isinstance(text, str)
    assert result is not None


def test_process_input_clean_text():
    orch = ModulationOrchestrator()
    text, result = orch.process_input("normal software development text")
    assert result.blocked is False


def test_process_response():
    orch = ModulationOrchestrator()
    from modulation_context import generate_request_id
    rid = generate_request_id()
    from categories import DetectionResult
    detection = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    orch._demodulator.register_modulation(rid, detection)
    response = orch.process_response("response text", rid)
    assert isinstance(response, str)


def test_measure_surfaces_returns_dict():
    orch = ModulationOrchestrator()
    temps = orch.measure_surfaces()
    assert isinstance(temps, dict)


def test_set_mode_valid():
    orch = ModulationOrchestrator()
    orch.set_mode("aggressive")
    assert orch.state.mode == "aggressive"
    orch.set_mode("conservative")
    assert orch.state.mode == "conservative"
    orch.set_mode("standard")
    assert orch.state.mode == "standard"


def test_set_mode_invalid():
    orch = ModulationOrchestrator()
    with pytest.raises(ValueError):
        orch.set_mode("invalid_mode")


def test_status_returns_dict():
    orch = ModulationOrchestrator()
    status = orch.status()
    assert "active" in status
    assert "mode" in status
    assert "calibration_level" in status
    assert "heatmap_enabled" in status
    assert "surface_temperatures" in status
    assert "warm_surfaces" in status


def test_pivot_if_needed_no_warm():
    orch = ModulationOrchestrator()
    assert orch.pivot_if_needed() is False


def test_singleton():
    o1 = modulation_orchestrator()
    o2 = modulation_orchestrator()
    assert o1 is o2
