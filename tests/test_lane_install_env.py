"""Lane install, registry upkeep, and launch-environment regressions.

A pip sdist build backend and npm install scripts are lane-supplied code, so
`pip install <lane>` and `npm install -g <lane>` get the lane environment rather
than the gateway's. `flywheel install` must keep an operator's env_allow grant
when it rewrites a lane's registry row. A lane launched as `python -m <module>`
because the parent could import it through PYTHONPATH must still start. The
manifest must declare the non-secret configuration each lane reads, or the
allowlist drops it silently.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import harness.lanes as ln
from harness.mcp_client import StdioTransport

FAKE_KEY = "sk-test-not-a-real-key"


def _registry(monkeypatch, tmp_path, rows):
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", path)
    return path


@pytest.mark.parametrize("name", ("gather", "learn"))
def test_install_lane_runs_the_package_manager_without_provider_keys(
        name, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")
    _registry(monkeypatch, tmp_path, {name: {"env_allow": ["PIP_INDEX_URL"]}})
    seen = []

    def fake_run(cmd, *args, **kwargs):
        seen.append(kwargs.get("env"))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(ln.subprocess, "run", fake_run)
    result = ln.install_lane(name, profile="package")
    assert result["installed"] is True
    (env,) = seen
    assert env is not None, "the package manager inherited the whole environment"
    assert "OPENROUTER_API_KEY" not in env
    assert "PATH" in {key.upper() for key in env}
    assert env["PIP_INDEX_URL"] == "https://example.invalid/simple"


def test_flywheel_install_keeps_operator_rows(tmp_path, monkeypatch):
    from harness import cli_entry
    path = _registry(monkeypatch, tmp_path, {"forum": {
        "env_allow": ["ANTHROPIC_API_KEY"], "runtime_profile": "package",
        "installed": False}})
    monkeypatch.setattr(ln, "install_lane", lambda name, profile: {"installed": True})
    assert cli_entry._cmd_install(["--lanes", "forum"]) == 0
    row = json.loads(path.read_text(encoding="utf-8"))["forum"]
    assert row["env_allow"] == ["ANTHROPIC_API_KEY"]
    assert row["runtime_profile"] == "package"
    assert row["installed"] is True
    assert row["version"] == ln.LANES["forum"].version


def test_python_m_lane_found_through_parent_pythonpath_still_starts(tmp_path, monkeypatch):
    package = tmp_path / "pp" / "fwprobe_lane_mod"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, os\n"
        "print(json.dumps({'started': True, "
        "'key_seen': 'OPENROUTER_API_KEY' in os.environ}), flush=True)\n",
        encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "pp"))
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    lane = ln.Lane("pp-probe", "pp-probe", "pp-probe", ("mcp",), "pip", "0.1.0",
                   "pythonpath probe", "test", py_module="fwprobe_lane_mod")
    monkeypatch.setattr(ln, "LANES", {"pp-probe": lane})
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: "0.1.0")
    _registry(monkeypatch, tmp_path, {})
    launch = ln.resolve_mcp_launch("pp-probe")
    assert launch.argv[:3] == (sys.executable, "-m", "fwprobe_lane_mod")
    transport = StdioTransport(launch, timeout=20.0)
    try:
        seen = transport.receive()
    finally:
        transport.close()
    assert seen == {"started": True, "key_seen": False}


# Non-secret configuration each lane's own source reads. A name missing from the
# manifest is dropped by the allowlist with no error, so this table is the check.
EXPECTED_DECLARED = {
    "canon": {"CANON_HOME", "CANON_WORKSPACE", "CANON_BLOCKS_DIR", "CANON_CONTEXT_DB"},
    "telos": {"TELOS_EMET_CLI", "TELOS_EMET_DISABLE_FALLBACKS"},
    "relay": {f"{p}_{s}" for p in ("CODEX", "CLAUDE", "GLM", "GEMINI", "DEEPSEEK")
              for s in ("MODEL", "PROVIDER_BASE_URL", "CLOUD_BASE_URL")},
}


@pytest.mark.parametrize("name", sorted(EXPECTED_DECLARED))
def test_lane_declares_the_configuration_it_reads(name):
    missing = EXPECTED_DECLARED[name] - set(ln.LANES[name].env_vars)
    assert not missing, (name, sorted(missing))


def test_telos_declares_no_variable_for_the_code_0_4_2_removed():
    # telos 0.4.2 removed the CAPTCHA code and the variable that located its
    # interpreter; a lane launch must not pass it on.
    assert not [name for name in ln.LANES["telos"].env_vars if "CAPTCHA" in name.upper()]


def test_telos_declares_only_what_a_tool_it_serves_reads():
    # In the 0.4.2 package only the proof witness reads a variable a served tool
    # reaches. The Chrome and learn names are the native-control driver's, which
    # over MCP only prints its verb catalog, and the font names belong to a
    # repository script the package does not ship, so none of them is passed on.
    assert set(ln.LANES["telos"].env_vars) == EXPECTED_DECLARED["telos"]


def test_no_page_offers_telos_a_credential():
    # The 0.4.2 package reads no credential, so the credential table names no
    # telos row, and no page names a variable of the removed CAPTCHA code.
    root = Path(__file__).resolve().parents[1]
    table = (root / "docs" / "lane-runtime-selection.md").read_text(encoding="utf-8")
    assert not [line for line in table.splitlines() if line.startswith("| telos |")]
    pages = [root / "README.md", root / "CONTRIBUTING.md", *(root / "docs").rglob("*.md")]
    named = [page.relative_to(root).as_posix() for page in pages
             if re.search(r"CAPTCHA_(SERVICE_KEY|VENV_PY)", page.read_text(encoding="utf-8"))]
    assert named == []


def test_canon_launch_carries_its_blocks_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CANON_BLOCKS_DIR", str(tmp_path / "blocks"))
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: lane.version)
    _registry(monkeypatch, tmp_path, {})
    try:
        launch = ln.resolve_mcp_launch("canon")
    except ln.LaneRuntimeError:
        pytest.skip("canon has no launchable runtime on this host")
    assert dict(launch.env_overrides)["CANON_BLOCKS_DIR"] == str(tmp_path / "blocks")
