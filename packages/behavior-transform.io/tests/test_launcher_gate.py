"""Tests for authority-gated launcher and pipeline authority integration."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from authority_gate import GateResult


class TestLauncherGate:
    def test_launch_denied_by_gate(self):
        denied = GateResult(
            allowed=False,
            gate="launch",
            entitlement="transform",
            reason="unauthorized: no_capsule",
            checked_at=time.time(),
        )
        mock_gate_mod = MagicMock()
        mock_gate_mod.gate_launch = MagicMock(return_value=denied)
        with patch.dict("sys.modules", {"authority_gate": mock_gate_mod}):
            import importlib
            from preflight import launcher
            importlib.reload(launcher)
            result = launcher.launch(
                child=["echo", "test"],
                surface="test_surface",
                host="test_host",
                enforce_auth=True,
            )
            assert result["status"] == "fail"
            assert "authority gate denied" in result["message"]
            assert "gate" in result

    def test_launch_skips_gate_when_disabled(self):
        from preflight.launcher import launch
        with patch("preflight.launcher.verify_latest_seal", return_value={"status": "fail", "findings": ["no seal"]}):
            with patch("preflight.launcher.resolve_native_command", side_effect=lambda x: x):
                result = launch(
                    child=["echo", "test"],
                    surface="test_surface",
                    host="test_host",
                    enforce_auth=False,
                )
                assert result["status"] == "fail"
                assert "gate" not in result


class TestPipelineAuthority:
    def test_pipeline_includes_authority_field(self):
        from pipeline import PreInferencePipeline
        pipe = PreInferencePipeline(enforce_auth=False)
        result = pipe.run("clean text for testing")
        d = result.to_dict()
        assert "authority" in d
        assert d["authority"]["checked"] is False

    def test_pipeline_blocks_on_denied_gate(self):
        denied = GateResult(
            allowed=False,
            gate="scan",
            entitlement="scan",
            reason="unauthorized",
            checked_at=time.time(),
        )

        mock_gate_scan = MagicMock(return_value=denied)
        with patch.dict("sys.modules", {"authority_gate": MagicMock(gate_scan=mock_gate_scan)}):
            from pipeline import PreInferencePipeline
            pipe = PreInferencePipeline(enforce_auth=True)
            pipe._check_authority = lambda: type("A", (), {
                "checked": True, "authorized": False,
                "surface": "test", "reason": "unauthorized",
                "to_dict": lambda self: {"checked": True, "authorized": False,
                                          "surface": "test", "reason": "unauthorized"},
            })()
            result = pipe.run("test text")
            assert result.blocked
            assert "authority gate denied" in result.block_reason

    def test_pipeline_passes_when_auth_unchecked(self):
        from pipeline import PreInferencePipeline
        pipe = PreInferencePipeline(enforce_auth=False)
        result = pipe.run("clean text")
        assert not result.blocked
        assert not result.authority.checked


class TestNewGates:
    def test_gate_scan_exists(self):
        from authority_gate import gate_scan
        result = gate_scan()
        assert isinstance(result, GateResult)
        assert result.gate == "scan"

    def test_gate_classify_exists(self):
        from authority_gate import gate_classify
        result = gate_classify()
        assert isinstance(result, GateResult)
        assert result.gate == "classify"
