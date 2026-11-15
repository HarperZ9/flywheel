from __future__ import annotations

import io
import json
import ctypes
import os
from pathlib import Path


RECORDS_JSONL = (
    '{"canon_schema":"canon.record/v1","data":{"body":"Keep facts bounded.","title":"Voice"},'
    '"id":"voice-canon","kind":"personality-block","provenance":{"create_ord":1,'
    '"create_time":null,"harness":"synthetic","model_slug":"none",'
    '"native_id":"block:voice-canon","session_id":null,'
    '"source_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
    '"scope":"workspace","temporal":{"supersedes":null,"valid_until":null}}\n'
)

ATOMS_JSONL = "\n".join(
    [
        (
            '{"atom_schema":"canon.atom/v1","classification":"normative","critical":true,'
            '"disclosure":{"profile":"project-only"},"freshness":{"state":"current"},'
            '"hashes":{},"id":"goal-migrate","layer":"session","precedence_rank":0,'
            '"scope_key":"workspace:canon","source_refs":[{"ref":"record:voice-canon"}],'
            '"source_span_refs":[],"status":"active","trust":{"label":"trusted-local"},'
            '"type":"active-goal","value":{"summary":"Move a provider-neutral handoff into Canon."}}'
        ),
        (
            '{"atom_schema":"canon.atom/v1","classification":"normative","critical":true,'
            '"disclosure":{"profile":"project-only"},"freshness":{"state":"current"},'
            '"hashes":{},"id":"omit-private-db","layer":"session","precedence_rank":1,'
            '"scope_key":"workspace:canon","source_refs":[],"source_span_refs":[],'
            '"status":"active","trust":{"label":"trusted-local"},"type":"omission",'
            '"value":{"reason":"real provider histories are excluded from this fixture"}}'
        ),
        "",
    ]
)


def _write_inputs(workspace: Path) -> None:
    workspace.mkdir()
    (workspace / "records.jsonl").write_text(RECORDS_JSONL, encoding="utf-8")
    (workspace / "atoms.jsonl").write_text(ATOMS_JSONL, encoding="utf-8")


def _run(argv: list[str]) -> tuple[int, str, str]:
    from canon.cli import run_cli

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def _base_args(workspace: Path) -> list[str]:
    return [
        "--workspace",
        str(workspace),
        "--records",
        "records.jsonl",
        "--atoms",
        "atoms.jsonl",
        "--target",
        "codex-cli",
    ]


def test_current_readonly_mcp_surface_survives_continuity_cli_import() -> None:
    from canon.local_mcp import handle

    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "canon.status",
        "canon.doctor",
        "canon.blocks",
        "canon.render",
        "canon.validate",
        "canon.check",
    }


def test_preview_reports_provider_neutral_bundle_and_does_not_mutate(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)
    before = _tree(workspace)

    code, stdout, stderr = _run(["--json", "preview", *_base_args(workspace)])

    assert code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["command"] == "preview"
    data = payload["data"]
    assert data["mode"] == "preview"
    assert data["target"]["adapter"] == "codex-cli"
    assert data["target"]["host_enforcement_observed"] is False
    assert data["source_state"]["records_digest"].startswith("sha256:")
    assert data["source_inputs"] == ["records.jsonl", "atoms.jsonl"]
    assert set(data["artifacts"]) == {"canon.capsule.json", "CANON.md", "readiness-probe.json"}
    assert _tree(workspace) == before


def test_export_canon_markdown_stdout_carries_source_hashes_without_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)
    before = _tree(workspace)

    code, stdout, stderr = _run(["export", *_base_args(workspace), "--format", "canon-md"])

    assert code == 0
    assert stderr == ""
    assert stdout.startswith("# CANON\n<!-- canon:capsule/v1 digest=sha256:")
    assert "Source state `records_digest`" in stdout
    assert "sha256:" in stdout
    assert "omit-private-db" in stdout
    assert _tree(workspace) == before

    code, stdout, stderr = _run(["export", *_base_args(workspace), "--format", "capsule-json"])
    assert code == 0
    assert stderr == ""
    capsule = json.loads(stdout)
    assert capsule["source_state"]["records_digest"].startswith("sha256:")
    assert capsule["receipts"][0]["records_sha256"].startswith("sha256:")
    assert capsule["receipts"][0]["atoms_sha256"].startswith("sha256:")
    assert any(atom["id"] == "omit-private-db" and atom["type"] == "omission" for atom in capsule["atoms"])
    assert capsule["omissions"] == []


def test_out_bundle_write_creates_expected_artifacts_and_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)
    before = _tree(workspace)

    code, stdout, stderr = _run(["--json", "export", *_base_args(workspace), "--format", "bundle", "--out", "bundle"])

    if os.name != "nt":
        assert code == 4
        assert stderr == ""
        assert json.loads(stdout)["failure_code"] == "unsafe_path"
        assert _tree(workspace) == before
        return
    assert code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["data"]["write_status"] == "created"
    assert sorted(path.name for path in (workspace / "bundle").iterdir()) == [
        "CANON.md",
        "canon.capsule.json",
        "readiness-probe.json",
    ]
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())

    code, stdout, stderr = _run(["--json", "export", *_base_args(workspace), "--format", "bundle", "--out", "bundle"])

    assert code == 0
    assert stderr == ""
    assert json.loads(stdout)["data"]["write_status"] == "idempotent"
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())


def test_bundle_write_rejects_stage_drift_without_false_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import canon.cli_publish as cli_publish

    workspace = tmp_path / "work"
    _write_inputs(workspace)
    before = _tree(workspace)
    real_rename = cli_publish._rename_stage
    attempted: dict[str, bool] = {}

    def mutate_stage_before_rename(parent, stage, target_name: str) -> None:
        attempted["ran"] = True
        (stage.path / "CANON.md").write_text("tampered\n", encoding="utf-8")
        (stage.path / "extra.txt").write_text("extra\n", encoding="utf-8")
        real_rename(parent, stage, target_name)

    monkeypatch.setattr(cli_publish, "_rename_stage", mutate_stage_before_rename)

    code, stdout, stderr = _run(["--json", "export", *_base_args(workspace), "--format", "bundle", "--out", "bundle"])

    if os.name != "nt":
        assert attempted == {}
        assert code == 4
        assert stderr == ""
        assert json.loads(stdout)["failure_code"] == "unsafe_path"
        assert _tree(workspace) == before
        return
    assert attempted == {"ran": True}
    assert code == 4
    assert stderr == ""
    assert json.loads(stdout)["failure_code"] == "unsafe_path"
    assert not (workspace / "bundle").exists()
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())


def test_bundle_outside_root_is_rejected_before_stage_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    _write_inputs(workspace)

    code, stdout, stderr = _run([
        "--json",
        "export",
        *_base_args(workspace),
        "--format",
        "bundle",
        "--out",
        "../outside/bundle",
    ])

    assert code == 4
    assert stderr == ""
    assert json.loads(stdout)["failure_code"] == "unsafe_path"
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())
    assert not (tmp_path / "outside").exists()


def test_bundle_rename_failure_cleans_stage_without_false_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import canon.cli_publish as cli_publish

    workspace = tmp_path / "work"
    _write_inputs(workspace)
    before = _tree(workspace)

    def fail_rename(_parent, _stage, _target_name: str) -> None:
        raise OSError(5, "synthetic rename failure")

    monkeypatch.setattr(cli_publish, "_rename_stage", fail_rename)

    code, stdout, stderr = _run(["--json", "export", *_base_args(workspace), "--format", "bundle", "--out", "bundle"])

    if os.name != "nt":
        assert code == 4
        assert stderr == ""
        assert json.loads(stdout)["failure_code"] == "unsafe_path"
        assert _tree(workspace) == before
        return
    assert code == 8
    assert stderr == ""
    assert json.loads(stdout)["failure_code"] == "io_error"
    assert not (workspace / "bundle").exists()
    assert not any(path.name.startswith(".canon-compile-") for path in workspace.iterdir())


def test_bundle_rename_uses_parent_handle_relative_leaf(tmp_path: Path, monkeypatch) -> None:
    import canon.cli_publish as cli_publish

    parent = cli_publish._DirCap(tmp_path / "work", 101, (1, 1))
    stage = cli_publish._DirCap(tmp_path / "work" / ".canon-compile-stage.tmp", 202, (1, 2))
    calls: list[tuple[int, int, str]] = []

    def rename_by_parent(stage_ref: int, parent_ref: int, target_name: str) -> None:
        calls.append((stage_ref, parent_ref, target_name))

    monkeypatch.setattr(cli_publish, "_win_rename_by_handle", rename_by_parent)

    cli_publish._rename_stage(parent, stage, "bundle")

    assert calls == [(202, 101, "bundle")]


def test_windows_rename_primitive_uses_rootdirectory_and_leaf(monkeypatch) -> None:
    import canon.cli_publish as cli_publish

    captured: dict[str, object] = {}

    def fake_nt_set_information_file(handle, _ios, buffer, size, info_class):
        info = cli_publish._RenameInfo.from_buffer(buffer)
        name_bytes = ctypes.string_at(
            ctypes.addressof(buffer) + cli_publish._RenameInfo.FileName.offset,
            info.FileNameLength,
        )
        captured.update({
            "stage_ref": int(handle.value),
            "root_ref": int(info.RootDirectory),
            "name": name_bytes.decode("utf-16-le"),
            "size": int(size),
            "info_class": int(info_class),
        })
        return 0

    monkeypatch.setattr(cli_publish, "_load_win_rename_api", lambda: None)
    monkeypatch.setattr(cli_publish, "_NtSetInformationFile", fake_nt_set_information_file, raising=False)
    monkeypatch.setattr(cli_publish, "_RtlNtStatusToDosError", lambda _status: 999, raising=False)

    cli_publish._win_rename_by_handle(202, 101, "bundle")

    assert captured == {
        "stage_ref": 202,
        "root_ref": 101,
        "name": "bundle",
        "size": cli_publish._RenameInfo.FileName.offset + len("bundle".encode("utf-16-le")),
        "info_class": 10,
    }
