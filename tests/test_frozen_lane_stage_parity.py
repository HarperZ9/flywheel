"""Keep clean-runner source staging aligned with the frozen payload contract."""
import ast
from pathlib import Path


def test_helper_stages_all_frozen_sources_before_freeze_with_bounded_receipt():
    text = Path("desktop/tool/run_ci_installed_acceptance.ps1").read_text()

    studio = text.index("stage pinned Studio runtime")
    stage = text.index("stage Python lane sources")
    env = text.index("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT")
    freeze = text.index("freeze gateway")
    assert studio < stage < env < freeze
    assert 'Join-Path $env:RUNNER_TEMP "flywheel-python-lane-sources"' in text
    spec = ast.parse(Path("packaging/flywheel-gateway.spec").read_text())
    lanes = next(ast.literal_eval(node.value) for node in spec.body
                 if isinstance(node, ast.Assign) and any(
                     isinstance(t, ast.Name) and t.id == "PYTHON_SOURCE_LANES" for t in node.targets))
    command = next(line for line in text.splitlines() if '"scripts/stage_python_lane_sources.py"' in line)
    for lane in lanes:
        assert f'"--lane", "{lane}"' in command
    assert "--bounded-receipt\", $pythonLaneBoundedReceipt" in text
    assert 'Join-Path $installerDir "python-lane-source-stage.json"' in text

