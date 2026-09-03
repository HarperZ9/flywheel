"""Attempt receipts carry CLI identity: version, resolved path, effort."""
import hashlib, json, pathlib
import harness.cross_harness_cli_identity as identity_module
from harness.cross_harness_adapters import DirectCodexAdapter, FlywheelRouterAdapter, ProcessOutcome
from harness.cross_harness_adapters import _resolve_codex
from harness.cross_harness_cli_identity import (REASONING_EFFORT_UNSPECIFIED, cli_identity_fields,
    codex_cli_version, resolve_binary, validate_executable_path)
from harness.cross_harness_peer_adapters import _resolve_claude, _resolve_cursor
from harness.cross_harness_executor import execute_cross_harness_manifest

ENVELOPE = json.dumps({"artifacts": {"result.json": {}}})


def _outcome():
    stdout = "\n".join((json.dumps({"type": "turn.completed", "model": "served-spark"}),
                        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": ENVELOPE}})))
    return ProcessOutcome(0, stdout, "", 5, False)


def _run_pair(tmp_path, adapters):
    source = tmp_path / "source"; source.mkdir(); prompt = "prompt"
    task = {"task_id": "agt-001-task", "raw_prompt": prompt, "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_sha256s": {}, "required_inputs": [], "expected_artifacts": ["result.json"],
            "oracle": {"expected_artifacts": ["result.json"]}}
    roles = list(adapters)
    manifest = {"task_set_id": "set", "task_rows": [task], "provider_specs": [{"provider_role": role,
        "harness_id": role.split("_")[0], "adapter_id": "codex_cli_json/v1" if role == "codex_harness" else "flywheel_router/v1",
        "model_id": "gpt-5.3-codex-spark", "model_display_name": "GPT-5.3-Codex-Spark", "requested_model_reference": "gpt-5.3-codex-spark"} for role in roles]}
    runtime = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []} for role in roles]}
    return execute_cross_harness_manifest(manifest, runtime, adapters, artifact_root=tmp_path / "artifacts", source_root=source,
        run_id="run", phase="spark", selectors=["agt-001"], roles=roles, repetitions=1)["rows"]


def test_codex_cli_version_probes_once_and_memoizes(tmp_path, monkeypatch):
    monkeypatch.setattr(identity_module, "_version_cache", {})
    exe = tmp_path / "codex.cmd"; exe.write_text("stub")
    calls = []
    def probe(argv, *, cwd, stdin_text, timeout_seconds):
        calls.append(argv); return ProcessOutcome(0, "codex-cli 0.45.0\nextra line", "", 3, False)
    assert codex_cli_version(str(exe), runner=probe) == "codex-cli 0.45.0"
    assert calls == [[str(exe), "--version"]]
    def forbidden(*args, **kwargs): raise AssertionError("memoized path must not respawn")
    assert codex_cli_version(str(exe), runner=forbidden) == "codex-cli 0.45.0"


def test_codex_cli_version_never_spawns_for_missing_or_empty_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(identity_module, "_version_cache", {})
    def forbidden(*args, **kwargs): raise AssertionError("no subprocess for an absent executable")
    assert codex_cli_version("", runner=forbidden) == ""
    assert codex_cli_version(str(tmp_path / "missing" / "codex.cmd"), runner=forbidden) == ""
    assert codex_cli_version("codex.cmd", runner=forbidden) == ""


def test_codex_cli_version_records_empty_on_failed_probes(tmp_path, monkeypatch):
    monkeypatch.setattr(identity_module, "_version_cache", {})
    outcomes = {"rc.cmd": ProcessOutcome(1, "codex-cli 0.45.0", "boom", 3, False),
                "timeout.cmd": ProcessOutcome(0, "codex-cli 0.45.0", "", 3, True),
                "silent.cmd": ProcessOutcome(0, "   \n", "", 3, False)}
    for name, outcome in outcomes.items():
        exe = tmp_path / name; exe.write_text("stub")
        assert codex_cli_version(str(exe), runner=lambda *a, **k: outcome) == ""
    raising = tmp_path / "raising.cmd"; raising.write_text("stub")
    def broken(*args, **kwargs): raise OSError("spawn refused")
    assert codex_cli_version(str(raising), runner=broken) == ""


def test_cli_identity_fields_default_effort_is_never_fabricated():
    assert REASONING_EFFORT_UNSPECIFIED == "unspecified"
    assert cli_identity_fields("codex-cli 0.45.0", "C:/bin/codex.cmd") == {
        "cli_version": "codex-cli 0.45.0", "resolved_binary_path": "C:/bin/codex.cmd", "reasoning_effort": "unspecified"}
    assert cli_identity_fields("", "", "high")["reasoning_effort"] == "high"


def test_validate_executable_path_rejects_non_exe_fixture(tmp_path):
    shim = tmp_path / "claude.cmd"; shim.write_text("@echo off\r\npython shim.py %*\r\n")
    assert validate_executable_path(str(shim)).startswith("EXECUTABLE_PATH_NOT_BINARY")
    script = tmp_path / "claude"; script.write_text("#!/bin/sh\nexec node wrapper.js \"$@\"\n")
    assert validate_executable_path(str(script)).startswith("EXECUTABLE_PATH_NOT_BINARY")
    pe = tmp_path / "real.exe"; pe.write_bytes(b"MZ\x90\x00" + b"\x00" * 16)
    assert validate_executable_path(str(pe)) == ""
    elf = tmp_path / "real-elf"; elf.write_bytes(b"\x7fELF" + b"\x00" * 16)
    assert validate_executable_path(str(elf)) == ""
    assert validate_executable_path("").startswith("EXECUTABLE_PATH_EMPTY")
    assert validate_executable_path("codex.cmd").startswith("EXECUTABLE_PATH_NOT_ABSOLUTE")
    assert validate_executable_path(str(tmp_path / "missing.exe")).startswith("EXECUTABLE_PATH_MISSING")


def test_resolve_binary_takes_the_binary_out_of_the_npm_shim_layout(monkeypatch):
    """The layout that shipped a blocked codex arm, reproduced.

    An npm install puts codex.cmd, codex.ps1, and an extensionless shell script
    on PATH, and hides the real codex.exe in a vendor directory. Resolving the
    first PATH hit picks a wrapper, which validate_executable_path then refuses,
    so the arm records unavailable while the harness is installed and working.
    """
    on_path = {"codex.cmd": "C:/npm/codex.cmd", "codex.ps1": "C:/npm/codex.ps1",
               "codex": "C:/npm/codex", "codex.exe": "C:/npm/vendor/codex.exe"}
    monkeypatch.setattr("shutil.which", on_path.get)
    assert resolve_binary(("codex.exe", "codex")) == "C:/npm/vendor/codex.exe"
    assert resolve_binary(("codex.cmd", "codex.ps1")) == ""
    assert resolve_binary(("absent",)) == ""


def test_no_cli_resolver_returns_a_wrapper_when_that_is_all_it_finds(monkeypatch):
    """Every adapter resolves through one rule, so one test covers all of them."""
    resolvers = (_resolve_codex, _resolve_claude, _resolve_cursor)
    monkeypatch.setattr("shutil.which", lambda name: f"C:/npm/{name}.cmd")
    for resolve in resolvers:
        assert resolve() == "", f"{resolve.__name__} accepted a wrapper"
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/local/bin/{name}")
    for resolve in resolvers:
        assert resolve().startswith("/usr/local/bin/"), resolve.__name__


def test_fixture_receipts_from_both_codex_adapters_carry_cli_identity(tmp_path):
    probe = lambda exe: "codex-cli 0.45.0-fixture"
    adapters = {"codex_harness": DirectCodexAdapter(runner=lambda *a, **k: _outcome(),
                    executable_resolver=lambda: "C:/bin/codex.cmd", version_probe=probe),
                "flywheel_harness": FlywheelRouterAdapter(runner=lambda *a, **k: _outcome(),
                    executable_resolver=lambda: "C:/bin/codex.cmd", version_probe=probe)}
    rows = _run_pair(tmp_path, adapters)
    assert {row["provider_role"] for row in rows} == {"codex_harness", "flywheel_harness"}
    expected = {"cli_version": "codex-cli 0.45.0-fixture", "resolved_binary_path": "C:/bin/codex.cmd",
                "reasoning_effort": "unspecified"}
    for row in rows:
        assert (row["execution_state"], row["receipt_state"]) == ("returned", "verified")
        observed = row["metrics"]["resource_observation"]
        assert {key: observed[key] for key in expected} == expected
        receipt = json.loads(pathlib.Path(row["receipt_path"]).read_text())
        sealed = receipt["receipt_subject"]["final_row"]["metrics"]["resource_observation"]
        assert {key: sealed[key] for key in expected} == expected
