import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest


def test_apparatus_imports():
    from apparatus import Apparatus, ApparatusStatus, BootResult, boot, boot_status
    assert Apparatus is not None
    assert callable(boot)
    assert callable(boot_status)


def test_substrate_canonical_record():
    from apparatus.substrate import CanonicalRecord, ACTIVE
    assert ACTIVE == CanonicalRecord.UAISRE
    assert isinstance(CanonicalRecord.UAISRE, CanonicalRecord)


def test_target_input_channel():
    from apparatus.target import InputChannel
    ch = InputChannel(
        name="test", channel_type="http",
        address="http://localhost", fmt="json"
    )
    assert ch.name == "test"
    assert ch.governed is False


def test_target_output_channel():
    from apparatus.target import OutputChannel
    ch = OutputChannel(
        name="out", channel_type="http",
        address="http://localhost"
    )
    assert ch.monitored is False


def test_target_dataclass():
    from apparatus.target import Target
    t = Target(name="test", target_type="generic")
    assert t.name == "test"
    assert t.input_channels == []


def test_target_llm_factory():
    from apparatus.target import Target
    t = Target.llm()
    assert t.target_type == "llm"
    assert len(t.input_channels) >= 2


def test_target_all_channels_governed():
    from apparatus.target import Target, InputChannel
    t = Target(
        name="test", target_type="generic",
        input_channels=[
            InputChannel("a", "http", "addr", governed=True),
            InputChannel("b", "http", "addr", governed=True),
        ]
    )
    assert t.all_channels_governed is True


def test_target_ungoverned_channels():
    from apparatus.target import Target, InputChannel
    t = Target(
        name="test", target_type="generic",
        input_channels=[
            InputChannel("a", "http", "addr", governed=True),
            InputChannel("b", "http", "addr", governed=False),
        ]
    )
    ungoverned = t.ungoverned_channels
    assert len(ungoverned) == 1
    assert ungoverned[0] == "b"


def test_target_to_dict():
    from apparatus.target import Target
    t = Target.llm()
    d = t.to_dict()
    assert isinstance(d, dict)
    assert d["target_type"] == "llm"


def test_target_save_load(tmp_path):
    from apparatus.target import Target
    t = Target.llm(name="test-target")
    path = tmp_path / "target.json"
    t.save(path)
    loaded = Target.load(path)
    assert loaded.name == "test-target"
    assert loaded.target_type == "llm"


def test_state_projection_full():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(text="hello world")
    assert proj.carrier_text != "hello world"
    assert len(proj.symbols) == 1


def test_state_projection_sensitive_clean():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="sensitive")
    proj = sp.project(text="clean text no sensitive data")
    assert proj.carrier_text == "clean text no sensitive data"
    assert len(proj.symbols) == 0


def test_state_projection_sensitive_with_key():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="sensitive")
    proj = sp.project(text="key is sk-abcdefgh12345678")
    assert "sk-abcdefgh12345678" not in proj.carrier_text
    assert len(proj.symbols) > 0


def test_state_projection_reconstitute():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(text="secret data")
    result = sp.reconstitute_text(proj.carrier_text, proj.symbols)
    assert result == "secret data"


def test_state_projection_reconstitute_dict():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(payload={"key": "value"})
    result = sp.reconstitute(proj.carrier_payload, proj.symbols)
    assert result == {"key": "value"}


def test_state_projection_reconstitute_list():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(payload=["a", "b"])
    result = sp.reconstitute(proj.carrier_payload, proj.symbols)
    assert result == ["a", "b"]


def test_state_projection_to_dict():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(text="test")
    d = proj.to_dict()
    assert d["projection_mode"] == "carrier_state"
    assert d["symbol_scope"] == "sealed_local"
    assert "symbols" not in d


def test_state_projection_to_dict_with_symbols():
    from apparatus.state_projection import StateProjector
    sp = StateProjector(default_level="full")
    proj = sp.project(text="test")
    d = proj.to_dict(include_symbols=True)
    assert "symbols" in d


def test_projection_level_validation():
    from apparatus.state_projection import projection_level
    assert projection_level("full") == "full"
    assert projection_level("sensitive") == "sensitive"
    with pytest.raises(ValueError):
        projection_level("invalid")


def test_hash_json_deterministic():
    from apparatus.state_projection import hash_json
    h1 = hash_json({"a": 1, "b": 2})
    h2 = hash_json({"b": 2, "a": 1})
    assert h1 == h2


def test_conditioning_config():
    from apparatus.conditioning import ConditioningConfig
    cfg = ConditioningConfig()
    assert cfg.enabled is True
    assert isinstance(cfg.prefill, str)


def test_conditioning_config_save_load(tmp_path):
    from apparatus.conditioning import ConditioningConfig
    cfg = ConditioningConfig()
    path = tmp_path / "conditioning.json"
    cfg.save(path)
    loaded = ConditioningConfig.load(path)
    assert loaded.enabled == cfg.enabled


def test_witness_membrane_sha():
    from apparatus.witness.membrane import _sha
    h = _sha(b"test data")
    assert isinstance(h, str)
    assert len(h) == 64


def test_witness_membrane_sha_deterministic():
    from apparatus.witness.membrane import _sha
    assert _sha(b"same") == _sha(b"same")
    assert _sha(b"diff1") != _sha(b"diff2")


def test_witness_membrane_authority_patterns():
    from apparatus.witness.membrane import _AUTHORITY_RE
    assert _AUTHORITY_RE.search(b"clean text") is None


def test_witness_monitor_sha():
    from apparatus.witness.monitor import _sha
    h = _sha(b"test")
    assert len(h) == 64


def test_witness_monitor_marker_count_clean():
    from apparatus.witness.monitor import _marker_count
    assert _marker_count(b"clean text with no markers") == 0


def test_witness_organs_imports():
    from apparatus.witness.organs import watch, observe, confirm
    assert callable(watch)
    assert callable(observe)
    assert confirm is observe


def test_witness_exports():
    from apparatus.witness import (
        anchor, verify, coherence, refuse, corroborate,
        audit, selftest, witness_status,
        watch, observe, confirm,
        report, reanchor,
    )
    assert callable(anchor)
    assert callable(verify)
    assert callable(watch)
    assert callable(report)


def test_boot_result():
    from apparatus.boot import BootResult
    r = BootResult(errors=["something broke"])
    assert r.fully_activated is False
    r2 = BootResult()
    assert r2.fully_activated is True


def test_boot_result_summary():
    from apparatus.boot import BootResult
    r = BootResult(proxy_started=True, proxy_port=7319)
    s = r.summary()
    assert isinstance(s, str)
    assert "proxy" in s


def test_boot_result_to_dict():
    from apparatus.boot import BootResult
    r = BootResult(proxy_started=True, targets_inoculated=2)
    d = r.to_dict()
    assert d["proxy_started"] is True
    assert d["targets_inoculated"] == 2
    assert d["fully_activated"] is True
