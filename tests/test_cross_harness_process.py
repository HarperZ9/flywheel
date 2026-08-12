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
@pytest.mark.parametrize("double_fork", [False, True])
def test_wsl_normal_exit_daemons_are_contained_and_pipes_bounded(double_fork):
    root = pathlib.Path(__file__).resolve().parents[1]
    linux_root = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(root)], capture_output=True, text=True, check=True).stdout.strip()
    script = r'''
import pathlib,sys,tempfile,time
sys.path.insert(0, sys.argv[1]); from harness.cross_harness_process import run_process
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d); marker=p/'escaped'; daemon="import pathlib,sys,time;time.sleep(.5);pathlib.Path(sys.argv[1]).write_text('bad');time.sleep(8)"
 if sys.argv[2]=='1': parent="import os,subprocess,sys;pid=os.fork();os._exit(0) if pid else (os.setsid(),subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]),os._exit(0))"
 else: parent="import subprocess,sys;subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]],start_new_session=True)"
 started=time.monotonic(); out=run_process([sys.executable,'-c',parent,daemon,str(marker)],cwd=p,stdin_text='',timeout_seconds=2,output_path=p/'out',sanitizer=lambda x:x); time.sleep(.8)
 assert time.monotonic()-started < 2 and not out.timed_out and not marker.exists()
'''
    completed = subprocess.run(["wsl.exe", "-e", "python3", "-", linux_root, "1" if double_fork else "0"], input=script, text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr


def test_linux_containment_unavailable_fails_before_launch(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(process, "prepare_linux_cgroup", lambda: (_ for _ in ()).throw(OSError("no delegated cgroup")), raising=False)
    marker = tmp_path / "launched"
    with pytest.raises(OSError, match="no delegated cgroup"):
        process.run_process([sys.executable, "-c", f"open({str(marker)!r},'w').write('bad')"], cwd=tmp_path, stdin_text="", timeout_seconds=1, output_path=tmp_path / "out", sanitizer=lambda x: x)
    assert not marker.exists()


def test_linux_kill_capability_failure_blocks_launch_and_cleans_stage(tmp_path, monkeypatch):
    import harness.cross_harness_linux as linux
    group = tmp_path / "group"; group.mkdir()
    for name in ("cgroup.procs", "cgroup.kill", "cgroup.events"): (group / name).write_text("populated 0" if name == "cgroup.events" else "")
    monkeypatch.setattr(linux, "_current_cgroup_root", lambda: tmp_path)
    original = pathlib.Path.write_text
    def denied(self, *args, **kwargs):
        if self.name == "cgroup.kill": raise PermissionError("denied")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "write_text", denied)
    with pytest.raises(OSError, match="containment unavailable"):
        linux.prepare_linux_cgroup()


def test_linux_selector_setup_failure_always_kills_group_and_process(monkeypatch):
    import harness.cross_harness_linux as linux
    calls = []
    class Group:
        def kill_and_remove(self): calls.append("group")
    class Stream:
        def fileno(self): return 1
        def close(self): calls.append("stream")
    class Proc:
        stdout = stderr = stdin = Stream()
        def poll(self): return None
        def kill(self): calls.append("process")
        def wait(self, timeout): return 0
    monkeypatch.setattr(linux.os, "set_blocking", lambda *a: (_ for _ in ()).throw(OSError("setup failed")))
    with pytest.raises(OSError, match="setup failed"):
        linux.run_linux_process(Proc(), Group(), b"", time.monotonic() + 1)
    assert "group" in calls and "process" in calls and "stream" in calls


def test_linux_selector_constructor_failure_always_kills_group_and_process(monkeypatch):
    import harness.cross_harness_linux as linux
    calls = []
    class Group:
        def kill_and_remove(self): calls.append("group")
    class Stream:
        def close(self): calls.append("stream")
    class Proc:
        stdout = stderr = stdin = Stream()
        def poll(self): return None
        def kill(self): calls.append("process")
        def wait(self, timeout): return 0
    monkeypatch.setattr(linux.selectors, "DefaultSelector", lambda: (_ for _ in ()).throw(OSError("selector failed")))
    with pytest.raises(OSError, match="selector failed"):
        linux.run_linux_process(Proc(), Group(), b"", time.monotonic() + 1)
    assert "group" in calls and "process" in calls and "stream" in calls
