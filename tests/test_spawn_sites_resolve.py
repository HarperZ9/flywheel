"""Every shipped spawn site starts the program the guarded lookup names.

1.1.0 handed bare names (git, lean, node, npm, ssh-keygen, an endpoint CLI) to
subprocess, and Windows starts a copy from the working folder before PATH; on
POSIX a relative PATH entry does the same. Here each program exists twice:
planted in the working folder and in an absolute PATH folder. subprocess is
replaced by a recorder, so nothing starts, and every recorded argv must begin
with the PATH copy. A site that recorded nothing fails too, so a pass cannot
come from a call that never reached subprocess.
"""
from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path

import pytest

WINDOWS = os.name == "nt"
NAMES = ("git", "lean", "node", "npm", "ssh-keygen", "buildc", "cp", "fwprog", "codex",
         "manimgl")


def _exe(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (f"{name}.exe" if WINDOWS else name)
    path.write_bytes(b"MZ" if WINDOWS else b"#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def same(a, b) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


@pytest.fixture
def world(tmp_path, monkeypatch):
    work, bin_ = tmp_path / "work", tmp_path / "bin"
    for name in NAMES:
        _exe(work, name)
        _exe(bin_, name)
    monkeypatch.chdir(work)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join(([] if WINDOWS else ["."]) + [str(bin_)]))
    seen: list = []

    def _text(kwargs) -> bool:
        return bool(kwargs.get("text") or kwargs.get("encoding")
                    or kwargs.get("universal_newlines"))

    class FakeProc:
        def __init__(self, args, *rest, **kwargs):
            seen.append(args)
            text = _text(kwargs)
            self.args, self.pid, self.returncode = args, 0, 0
            self.stdin = io.StringIO() if text else io.BytesIO()
            self.stdout = io.StringIO("") if text else io.BytesIO(b"")
            self.stderr = io.StringIO("") if text else io.BytesIO(b"")

        def communicate(self, input=None, timeout=None):
            return self.stdout.read(), self.stderr.read()

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

        terminate = kill

    def fake_run(args, *rest, **kwargs):
        seen.append(args)
        out = "" if _text(kwargs) else b""
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr=out)

    def fake_check_output(args, *rest, **kwargs):
        seen.append(args)
        return "" if _text(kwargs) else b""

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    return work, bin_, seen


def _telos(root: Path):
    from harness import telos_kernels
    real = telos_kernels._module_path
    telos_kernels._module_path = lambda: root / "kernels.mjs"
    try:
        return telos_kernels.run_kernel(next(iter(telos_kernels.KERNELS)))
    finally:
        telos_kernels._module_path = real


def _lean_probe(root: Path):
    from harness.infra import lean_adapter
    lean_adapter.reset_lean_probe()
    try:
        return lean_adapter._probe_lean()
    finally:
        lean_adapter.reset_lean_probe()


def _npm_root(root: Path):
    from harness import lane_runtime_support as support
    support._npm_global_root.cache_clear()
    try:
        return support._npm_global_root()
    finally:
        support._npm_global_root.cache_clear()


def _mcp_launch(root: Path):
    from harness.mcp_client import LaunchSpec, StdioTransport
    return StdioTransport(LaunchSpec(("fwprog", "serve"), cwd=str(root)))


def _mcp_list(root: Path):
    from harness.mcp_client import StdioTransport
    return StdioTransport(["fwprog", "serve"])


def _endpoint(root: Path):
    from harness.endpoints import CliBackend
    return CliBackend("probe", ["fwprog", "{prompt}"]).chat(
        [{"role": "user", "content": "hi"}], system="", max_tokens=1, temperature=0.0, seed=0)


def _authority(root: Path):
    from harness.authority_registry import _command_resolver
    return _command_resolver({"argv": ["fwprog"]}, root, True, 5.0, None)("answer")


SITES = {
    "boot git head": ("git", lambda r: __import__("harness.boot", fromlist=["x"])._git_head(r)),
    "continuation preview git": ("git", lambda r: __import__(
        "harness.continuation_preview", fromlist=["x"])._run_git(r, "status")),
    "local_git": ("git", lambda r: __import__(
        "harness.local_git", fromlist=["x"]).GitRepo(str(r))._run("status")),
    "routing collection git head": ("git", lambda r: __import__(
        "harness.routing_collection", fromlist=["x"])._git_head(r)),
    "session summary git": ("git", lambda r: __import__(
        "harness.session_summary", fromlist=["x"])._git(r, "status")),
    "studio engine git head": ("git", lambda r: __import__(
        "harness.studio_body_engine_render", fromlist=["x"])._git_head(r)),
    "workspace git identity": ("git", lambda r: __import__(
        "harness.workspace_git_identity", fromlist=["x"]).git(r, "status", check=False)),
    "worktree preflight": ("git", lambda r: __import__(
        "harness.worktree_preflight", fromlist=["x"])._gather_and_assess(str(r))),
    "trace bench replay git": ("git", lambda r: __import__(
        "harness.trace_bench_replay", fromlist=["x"])._git(r, "status")),
    "receipt signing key": ("ssh-keygen", lambda r: __import__(
        "harness.receipt_signer", fromlist=["x"]).generate_signing_key(
            r / "keys" / "id", comment="probe")),
    "telos kernel": ("node", _telos),
    "lean adapter probe": ("lean", _lean_probe),
    "lean export": ("lean", lambda r: __import__(
        "harness.lean_export", fromlist=["x"]).lean_axioms("theorem t : True := trivial")),
    "proof run": ("lean", lambda r: __import__(
        "harness.proof_run", fromlist=["x"]).run_proof(r / "a.lean")),
    "npm global root": ("npm", _npm_root),
    "mcp launch spec": ("fwprog", _mcp_launch),
    "mcp argv": ("fwprog", _mcp_list),
    "stdio protocol server": ("fwprog", lambda r: __import__(
        "harness.child_stdio", fromlist=["x"]).spawn(["fwprog"], r)),
    "debug adapter launch": ("fwprog", lambda r: __import__(
        "harness.dap_policy", fromlist=["x"])._spawn_detached(["fwprog"], r, None)),
    "codex app server": ("codex", lambda r: __import__(
        "harness.codex_app_server_client", fromlist=["x"]).CodexAppServerStdioTransport()),
    "cli endpoint": ("fwprog", _endpoint),
    "accountable hook": ("fwprog", lambda r: __import__(
        "harness.accountable_hooks", fromlist=["x"]).subprocess_runner()(["fwprog"])),
    "command authority": ("fwprog", _authority),
    "verified bench gate": ("fwprog", lambda r: __import__(
        "harness.verified_bench", fromlist=["x"]).subprocess_gate(
            "fwprog --check", "proposal", workspace=r)),
    "buildc receipt verify": ("buildc", lambda r: __import__(
        "harness.buildc_receipt_bridge", fromlist=["x"]).run_buildc_verify(r / "r.json")),
    "workspace clone copy": ("cp", lambda r: __import__(
        "harness.workspace_clone", fromlist=["x"])._sh(["cp", "a", "b"])),
    "lane cli": ("fwprog", lambda r: __import__(
        "harness.lane_cli", fromlist=["x"]).run_lane_cli("gather", ["--version"],
                                                         prefix=["fwprog"], timeout=5)),
    "keychain tool": ("fwprog", lambda r: __import__(
        "harness.trace_enc_aead", fromlist=["x"])._run_status(["fwprog"])),
    "manim render": ("manimgl", lambda r: __import__(
        "harness.manim_lesson", fromlist=["x"]).render_lesson("src", "Scene", str(r))),
    "lean replay": ("fwprog", lambda r: __import__(
        "harness.lean_replay", fromlist=["x"]).run_killable(["fwprog"])),
}


@pytest.mark.parametrize("site", sorted(SITES))
def test_the_site_starts_the_path_copy_never_the_working_folder_copy(site, world, monkeypatch):
    work, bin_, seen = world
    name, call = SITES[site]
    try:
        call(work)
    except Exception:
        pass  # the recorded argv is the evidence; what the site does next is not
    assert seen, f"{site} never reached subprocess"
    expected = bin_ / (f"{name}.exe" if WINDOWS else name)
    for argv in seen:
        assert not isinstance(argv, str), f"{site} ran a shell string: {argv!r}"
        assert same(argv[0], expected), f"{site} started {argv[0]!r}"
