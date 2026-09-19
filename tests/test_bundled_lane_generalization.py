"""Generalized bundled-lane staging, admission, and dispatch (any manifest lane).

These lock in that the relay-only special case now covers any lane in the
python-lane-payloads manifest, without weakening the controls: the staged source
is still hash-checked against the descriptor (fail-closed on mismatch), admission
still cross-checks the descriptor against a trusted expectation, and the admitted
launch still exposes only the lane's declared health tools.
"""
import hashlib
import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from harness.evidence_json import canonical_sha256


def _load_stage_module():
    spec = importlib.util.spec_from_file_location(
        "stage_python_lane_sources", Path("scripts/stage_python_lane_sources.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _source_repo(tmp_path: Path, lane: str) -> tuple[Path, str, bytes]:
    repo = tmp_path / f"{lane}-src"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / ".gitattributes").write_text("*.py text eol=lf\n", encoding="utf-8")
    data = b"def serve():\n    return 0\n"
    path = repo / "src" / lane / "mcp.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    (repo / "LICENSE").write_text("MIT\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, commit, data


def _manifest(tmp_path: Path, lane: str, commit: str, repo: Path, data: bytes,
              *, sha_override: str | None = None) -> Path:
    row = {
        "lane": lane,
        "owner_tag": "v1.0.0",
        "owner_commit": commit,
        "registry_source_repo": f"public/{lane}",
        "component_descriptor": {"source": {
            "repo": str(repo),
            "files": [{"path": f"src/{lane}/mcp.py",
                       "bytes": len(data),
                       "sha256": sha_override or (
                           "sha256:" + hashlib.sha256(data).hexdigest())}]}},
    }
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_stage_generalizes_beyond_canon_to_any_manifest_lane(tmp_path):
    """A non-canon manifest lane materializes at its pin and hash-verifies."""
    module = _load_stage_module()
    repo, commit, data = _source_repo(tmp_path, "widget")
    manifest = _manifest(tmp_path, "widget", commit, repo, data)

    receipt = module.stage_sources(Namespace(
        manifest=str(manifest), source_root=str(tmp_path / "sources"),
        lane=["widget"], source_repo=[], receipt=None, bounded_receipt=None))

    staged = Path(receipt["lanes"][0]["path"])
    assert receipt["verdict"] == "PASS"
    assert receipt["lanes"][0]["lane"] == "widget"
    assert (staged / "src" / "widget" / "mcp.py").is_file()


def test_stage_rejects_source_hash_mismatch(tmp_path):
    """The source manifest hash check still fails closed for any lane."""
    module = _load_stage_module()
    repo, commit, data = _source_repo(tmp_path, "widget")
    manifest = _manifest(tmp_path, "widget", commit, repo, data,
                         sha_override="sha256:" + "9" * 64)

    try:
        module.stage_sources(Namespace(
            manifest=str(manifest), source_root=str(tmp_path / "sources"),
            lane=["widget"], source_repo=[], receipt=None, bounded_receipt=None))
    except module.StageError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("a source hash mismatch was accepted")


def test_stage_peels_annotated_tag_pin_to_its_commit(tmp_path):
    """A pin that names an annotated tag object stages the tagged commit."""
    module = _load_stage_module()
    repo, commit, data = _source_repo(tmp_path, "widget")
    _git(repo, "tag", "-a", "v1.0.0", "-m", "release")
    tag_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "v1.0.0"], text=True).strip()
    assert tag_sha != commit
    manifest = _manifest(tmp_path, "widget", tag_sha, repo, data)

    receipt = module.stage_sources(Namespace(
        manifest=str(manifest), source_root=str(tmp_path / "sources"),
        lane=["widget"], source_repo=[], receipt=None, bounded_receipt=None))

    staged = Path(receipt["lanes"][0]["path"])
    assert receipt["verdict"] == "PASS"
    assert subprocess.check_output(
        ["git", "-C", str(staged), "rev-parse", "HEAD"], text=True).strip() == commit


def _descriptor(lane: str, *, version: str = "1.0.0") -> dict:
    body = b"def serve():\n    return 0\n"
    files = [{"path": f"src/{lane}/mcp.py", "bytes": len(body),
              "sha256": "sha256:" + hashlib.sha256(body).hexdigest()}]
    return {
        "schema": "flywheel.bundled-lane-component/v1",
        "name": lane, "version": version,
        "source": {
            "repo": f"https://github.com/HarperZ9/{lane}.git",
            "commit": "a" * 40, "path": f"src/{lane}",
            "algorithm": "sha256-canonical-source-manifest/v1",
            "file_count": len(files),
            "bytes": sum(f["bytes"] for f in files),
            "files": files,
            "manifest_sha256": "sha256:" + canonical_sha256(files),
        },
        "entrypoint": {"argv": ["--bundled-lane-mcp", lane],
                       "module": f"{lane}.mcp", "callable": "serve",
                       "health_tool": f"{lane}.status"},
        "allowed_tools": [f"{lane}.status", f"{lane}.doctor"],
        "does_not_prove": ["NOT_PROVES_FULL_LANE_WORKFLOW: status/doctor only."],
    }


def _rows(lane: str, **kw) -> dict:
    cd = _descriptor(lane, **kw)
    return {lane: {"lane": lane, "component_descriptor": cd,
                   "component_descriptor_sha256": "sha256:" + canonical_sha256(cd)}}


def test_admit_non_relay_manifest_lane_exposes_only_declared_health_tools():
    """A manifest lane admits from its row and admits status+doctor only."""
    from harness.bundled_lane_admission import admit_bundled_lane

    rows = _rows("widget")
    result = admit_bundled_lane(
        "widget", executable="D:/app/flywheel-gateway.exe", environ={},
        importable_fn=lambda name: name == "widget.mcp", manifest_rows=rows)

    assert result.blocking_codes == ()
    assert result.launch.argv == (
        "D:/app/flywheel-gateway.exe", "--bundled-lane-mcp", "widget")
    assert result.launch.allowed_tools == ("widget.status", "widget.doctor")
    assert result.launch.inherit_env is False
    assert result.launch.hide_window is True
    assert result.component["allowed_tools"] == ["widget.status", "widget.doctor"]
    assert result.component["descriptor_sha256"] == (
        rows["widget"]["component_descriptor_sha256"])


def test_admit_non_relay_rejects_descriptor_digest_mismatch():
    """A tampered descriptor digest is refused for a manifest lane too."""
    from harness.bundled_lane_admission import admit_bundled_lane

    rows = _rows("widget")
    result = admit_bundled_lane(
        "widget", executable="gateway.exe", environ={},
        importable_fn=lambda _name: True, manifest_rows=rows,
        expected={"descriptor_sha256": "sha256:" + "0" * 64})

    assert result.launch is None
    assert "bundled_descriptor_digest_mismatch" in result.blocking_codes


def test_admit_unknown_lane_is_not_supported():
    from harness.bundled_lane_admission import admit_bundled_lane

    result = admit_bundled_lane(
        "ghost", executable="gateway.exe", environ={}, manifest_rows={})

    assert result.launch is None
    assert result.blocking_codes == ("bundled_lane_not_supported",)


def test_dispatch_serves_any_admitted_manifest_lane(monkeypatch):
    """Dispatch admits and serves a sync manifest lane by name."""
    from harness import bundled_lane_admission, bundled_lane_descriptor

    monkeypatch.setattr(bundled_lane_descriptor, "module_importable",
                        lambda _name: True)
    served = []
    module = SimpleNamespace(serve=lambda: served.append(True) or 0)

    code = bundled_lane_admission.dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "widget"],
        import_module_fn=lambda name: module,
        executable="gateway.exe", environ={}, manifest_rows=_rows("widget"))

    assert code == 0
    assert served == [True]


def test_dispatch_runs_async_coroutine_serve(monkeypatch):
    """An async coroutine serve callable runs to completion under asyncio.run.

    forum's declared callable is ``async def serve_stdio``, so the child mode has
    to run a coroutine, not refuse it."""
    from harness import bundled_lane_admission, bundled_lane_descriptor

    monkeypatch.setattr(bundled_lane_descriptor, "module_importable",
                        lambda _name: True)
    calls = []

    async def _aserve():
        calls.append(True)
        return 0

    code = bundled_lane_admission.dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "widget"],
        import_module_fn=lambda name: SimpleNamespace(serve=_aserve),
        executable="gateway.exe", environ={}, manifest_rows=_rows("widget"))

    assert code == 0
    assert calls == [True]


def test_dispatch_refuses_non_coroutine_awaitable(monkeypatch):
    """A non-coroutine awaitable has no run contract here, so it is closed and refused."""
    from harness import bundled_lane_admission, bundled_lane_descriptor

    monkeypatch.setattr(bundled_lane_descriptor, "module_importable",
                        lambda _name: True)

    class _Awaitable:
        def __init__(self):
            self.closed = False

        def __await__(self):  # pragma: no cover - never awaited
            yield

        def close(self):
            self.closed = True

    obj = _Awaitable()
    code = bundled_lane_admission.dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "widget"],
        import_module_fn=lambda name: SimpleNamespace(serve=lambda: obj),
        executable="gateway.exe", environ={}, manifest_rows=_rows("widget"))

    assert code == 2
    assert obj.closed is True


def test_dispatch_rejects_unknown_lane_and_extra_args():
    from harness.bundled_lane_admission import dispatch_bundled_lane_mcp

    assert dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "ghost"], manifest_rows={}) == 2
    assert dispatch_bundled_lane_mcp(
        ["--bundled-lane-mcp", "widget", "extra"], manifest_rows=_rows("widget")) == 2
    assert dispatch_bundled_lane_mcp(["--not-bundled"]) is None
