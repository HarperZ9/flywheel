import json, os, pathlib, shutil, subprocess, sys, tempfile, time
import pytest
from harness.cross_harness_adapters import LocalRouterAdapter, _local_http
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_process import run_process
from harness.cross_harness_types import AttemptRequest


def _profile(url):
    row = {"profile_id": "local", "backend": "serve", "model": "14B", "model_ref": "local:14b", "endpoint_url": url,
           "supports_agentic_workflow": True, "root_exists": True}
    return {**row, "profile_sha256": canonical_sha256(row)}


def _request(tmp_path):
    return AttemptRequest("run", "local", "set", "agt-001-task", "prompt", "a" * 64, "local_14b", "local", "openai_compatible_local/v1",
        "14B", tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 2, tmp_path)


@pytest.mark.parametrize("payload", [
    b'', b'{"text":"ok","text":"forged"}', b'{"text":NaN}', b'[]', b'{"text":"' + b'x' * 20000 + b'"}',
    b'{"text":' + b'[' * 5000 + b'0' + b']' * 5000 + b'}', b'x' * ((1 << 20) + 1),
], ids=["empty", "duplicate", "nonfinite", "type", "field", "depth", "total"])
def test_local_http_uses_the_provider_json_boundary(payload, monkeypatch, tmp_path):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count): return payload[:count]
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr("harness.cross_harness_adapters.urllib.request.build_opener", lambda *a: Opener())
    adapter = LocalRouterAdapter("local_14b", _profile("http://127.0.0.1:8765"))
    result = adapter.execute(_request(tmp_path))
    assert result.execution_state == "malformed" and result.failure_class == "malformed_provider_output"


def test_malformed_local_http_attempt_still_seals_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr("harness.cross_harness_adapters._local_http", lambda *a: (_ for _ in ()).throw(__import__("harness.cross_harness_adapters", fromlist=["MalformedProviderOutput"]).MalformedProviderOutput("bad local JSON")))
    source = tmp_path / "source"; source.mkdir(); prompt = "prompt"
    task = {"task_id": "agt-001-task", "raw_prompt": prompt, "raw_prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}
    manifest = {"task_set_id": "set", "task_rows": [task], "provider_specs": [{"provider_role": "local_14b", "harness_id": "local", "adapter_id": "openai_compatible_local/v1", "target_model": "14B"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": []}]}
    adapter = LocalRouterAdapter("local_14b", _profile("http://127.0.0.1:8765"))
    run = execute_cross_harness_manifest(manifest, runtime, {"local_14b": adapter}, artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    assert (run["rows"][0]["execution_state"], run["rows"][0]["receipt_state"]) == ("malformed", "verified")


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("wsl.exe") is None, reason="WSL integration unavailable")
@pytest.mark.parametrize("mode", ["normal", "double-fork", "self-migrate"])
def test_wsl_provider_execution_fails_closed_before_launch(mode):
    root = pathlib.Path(__file__).resolve().parents[1]
    linux_root = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(root)], capture_output=True, text=True, check=True).stdout.strip()
    script = r'''
import pathlib,sys,tempfile
sys.path.insert(0, sys.argv[1]); from harness.cross_harness_process import run_process
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d); marker=p/'launched'; mode=sys.argv[2]
 code={
  'normal': "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('bad')",
  'double-fork': "import os,pathlib,sys;pathlib.Path(sys.argv[1]).write_text('bad');os.fork()",
  'self-migrate': "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('bad');open('/sys/fs/cgroup/cgroup.procs','w').write(str(__import__('os').getpid()))",
 }[mode]
 try: run_process([sys.executable,'-c',code,str(marker)],cwd=p,stdin_text='',timeout_seconds=2,output_path=p/'out',sanitizer=lambda x:x)
 except OSError as exc: assert 'Linux provider containment unavailable' in str(exc)
 else: raise AssertionError('provider launched')
 assert not marker.exists()
'''
    completed = subprocess.run(["wsl.exe", "-e", "python3", "-", linux_root, mode], input=script, text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr


def test_linux_containment_unavailable_fails_before_launch(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    monkeypatch.setattr(process.sys, "platform", "linux")
    marker = tmp_path / "launched"
    with pytest.raises(OSError, match="Linux provider containment unavailable"):
        process.run_process([sys.executable, "-c", f"open({str(marker)!r},'w').write('bad')"], cwd=tmp_path, stdin_text="", timeout_seconds=1, output_path=tmp_path / "out", sanitizer=lambda x: x)
    assert not marker.exists()


def test_owned_nonempty_stage_tree_is_scrubbed_without_following_links(tmp_path):
    import harness.cross_harness_process as process
    stage, outside = tmp_path / "out.txt", tmp_path / "outside"; outside.mkdir(); secret = outside / "secret"; secret.write_text("outside-secret")
    stage.mkdir(); (stage / "raw-secret").write_text("provider-secret")
    link = stage / "escape"
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip("directory symlink unavailable")
    assert process._scrub_owned_tree(stage) and not stage.exists() and secret.read_text() == "outside-secret"


def test_stage_cleanup_failure_is_reported_after_raw_bytes_are_zeroed(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    stage = tmp_path / "stage"; stage.mkdir(); raw = stage / "raw"; raw.write_text("provider-secret")
    original = pathlib.Path.unlink
    monkeypatch.setattr(pathlib.Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("locked")) if self == raw else original(self, *a, **k))
    assert not process._scrub_owned_tree(stage) and raw.read_bytes() == b""


def test_owned_stage_hardlink_is_unlinked_without_truncating_outside(tmp_path):
    import harness.cross_harness_process as process
    stage, outside = tmp_path / "stage", tmp_path / "outside"; stage.mkdir(); outside.write_text("DO-NOT-TRUNCATE")
    linked = stage / "linked"
    try: os.link(outside, linked)
    except OSError: pytest.skip("hard links unavailable")
    assert not process._scrub_owned_tree(stage)
    assert not stage.exists() and outside.read_text() == "DO-NOT-TRUNCATE"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows provider boundary")
@pytest.mark.parametrize("failure", ["popen", "job", "resume", "runner"])
def test_exceptional_process_paths_report_stage_cleanup_failure(tmp_path, monkeypatch, failure):
    import harness.cross_harness_process as process
    monkeypatch.setattr(process, "_scrub_owned_tree", lambda path: False)
    if failure == "popen": monkeypatch.setattr(process.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("launch")))
    elif failure == "job": monkeypatch.setattr(process, "_windows_job", lambda proc: None)
    elif failure == "resume": monkeypatch.setattr(process, "_resume_windows", lambda proc: False)
    else: monkeypatch.setattr(process, "_run_windows_process", lambda *a: (_ for _ in ()).throw(RuntimeError("runner")))
    with pytest.raises(OSError, match="provider staging cleanup failed"):
        process.run_process([sys.executable, "-c", "pass"], cwd=tmp_path, stdin_text="", timeout_seconds=1,
                            output_path=tmp_path / "out", sanitizer=lambda value: value)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
def test_owned_stage_cleanup_removes_junction_without_following_it(tmp_path):
    import harness.cross_harness_process as process
    stage, outside = tmp_path / "stage", tmp_path / "outside"; stage.mkdir(); outside.mkdir(); secret = outside / "secret"; secret.write_text("outside-secret")
    junction = stage / "escape"
    made = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
    if made.returncode: pytest.skip("junction creation unavailable")
    assert process._scrub_owned_tree(stage) and not stage.exists() and secret.read_text() == "outside-secret"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows provider boundary")
def test_stage_cleanup_failure_marks_real_process_malformed(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    original = process._scrub_owned_tree
    def scrub_and_report_failure(path):
        original(path)
        return False
    monkeypatch.setattr(process, "_scrub_owned_tree", scrub_and_report_failure)
    outcome = process.run_process([sys.executable, "-c", "pass"], cwd=tmp_path, stdin_text="", timeout_seconds=1,
                                  output_path=tmp_path / "out", sanitizer=lambda value: value)
    assert outcome.malformed_output and not list(tmp_path.glob(".cross-harness-stage-*"))
