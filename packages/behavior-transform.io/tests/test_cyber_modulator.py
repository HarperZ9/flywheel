import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from cyber_modulator import (
    AssessmentPhase,
    CyberModulator,
    CyberModulationResult,
    GitMetadataSurface,
    GitMetadataModulationResult,
    cyber_modulator,
    modulate_cyber,
    git_metadata_surface,
    _PHASE_FRAME,
    _TECHNIQUE_MAP,
    _COMPOUND_PATTERNS,
)


def test_assessment_phase_has_12_phases():
    phases = [
        v for k, v in vars(AssessmentPhase).items()
        if not k.startswith("_")
    ]
    assert len(phases) == 12


def test_phase_frame_covers_all_phases():
    phases = [
        v for k, v in vars(AssessmentPhase).items()
        if not k.startswith("_")
    ]
    for phase in phases:
        assert phase in _PHASE_FRAME, f"missing frame for {phase}"


def test_technique_map_nonempty():
    assert len(_TECHNIQUE_MAP) > 30


def test_compound_patterns_nonempty():
    assert len(_COMPOUND_PATTERNS) > 10


def test_cyber_modulator_singleton():
    m1 = cyber_modulator()
    m2 = cyber_modulator()
    assert m1 is m2


def test_cyber_modulator_clean_text():
    result = modulate_cyber("the weather is sunny and warm today")
    assert isinstance(result, CyberModulationResult)
    assert result.blocked is False
    assert result.compound_rewrites == 0


def test_cyber_modulation_result_fields():
    result = CyberModulationResult(
        original="test", modulated="test",
    )
    assert result.applied_substitutions == []
    assert result.technique_mappings == []
    assert result.phase_frames == []


def test_cyber_modulation_result_demodulate_noop():
    result = CyberModulationResult(
        original="test", modulated="test",
    )
    assert result.demodulate("response text") == "response text"


def test_git_metadata_surface_singleton():
    s1 = git_metadata_surface()
    s2 = git_metadata_surface()
    assert s1 is s2


def test_git_metadata_branch_clean():
    surface = GitMetadataSurface()
    result = surface.modulate_branch_name("feature/add-login")
    assert isinstance(result, GitMetadataModulationResult)
    assert result.blocked is False


def test_git_metadata_commit_clean():
    surface = GitMetadataSurface()
    result = surface.modulate_commit_message("fix: resolve login timeout")
    assert isinstance(result, GitMetadataModulationResult)
    assert result.blocked is False


def test_git_metadata_tool_output():
    surface = GitMetadataSurface()
    result = surface.modulate_tool_output("scan completed successfully")
    assert isinstance(result, GitMetadataModulationResult)


def test_cyber_modulator_audit_trail():
    result = modulate_cyber("clean development text")
    assert "status" in result.audit_trail
    assert result.audit_trail["status"] == "cyber_modulated"
