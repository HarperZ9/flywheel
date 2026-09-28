import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_gateway_effect_offline_import_stays_out_of_live_gateway_runtime():
    script = """
import importlib
import json
import sys
importlib.import_module('harness.gateway_effect_offline')
watched = [
    'harness.gateway_secret_boundary',
    'harness.gateway_operation',
    'harness.gateway_operation_recovery',
    'harness.gateway_operation_process',
    'harness.output_check_worker',
    'harness.gateway_agent_native_runtime',
    'harness.gateway_agent_native_tools',
    'harness.output_check_service',
    'harness.output_check_sources',
    'harness.domain_packs',
]
print(json.dumps({name: name in sys.modules for name in watched}, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    loaded = json.loads(result.stdout)

    assert loaded == {name: False for name in loaded}


def test_gateway_effect_offline_keeps_live_workers_out_of_verifier_closure():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from check_verifier_stdlib import VERIFIER_ENTRY_POINTS, closure
    finally:
        sys.path.pop(0)

    reached, _ = closure(VERIFIER_ENTRY_POINTS)
    assert "gateway_effect_offline" in reached
    live_runtime = {
        "gateway_secret_boundary",
        "gateway_operation",
        "gateway_operation_shape",
        "gateway_operation_recovery",
        "gateway_operation_process",
        "output_check_worker",
        "gateway_agent_binding",
        "gateway_agent_native_tools",
        "gateway_agent_native_runtime",
        "output_check_service",
        "output_check_sources",
        "domain_packs",
    }

    assert reached.isdisjoint(live_runtime)
