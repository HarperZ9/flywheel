from __future__ import annotations

import io
import json
import os
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from canon.canonical_json import canonical_json_text, sha256_bytes
from canon.exit_codes import EX_GATE, EX_OK, EX_SECURITY, EX_UNAVAILABLE, EX_UNSUPPORTED, EX_USAGE


FIXTURES = Path(__file__).parent / "fixtures" / "bootstrap"


def _copy_inputs(workspace: Path) -> tuple[Path, Path]:
    records = workspace / "records.jsonl"
    atoms = workspace / "atoms.jsonl"
    records.write_bytes((FIXTURES / "records.jsonl").read_bytes())
    atoms.write_bytes((FIXTURES / "atoms.jsonl").read_bytes())
    return records, atoms


def _run(argv: list[str], *, stdin: io.StringIO | None = None) -> tuple[int, str, str]:
    from canon.cli import run_cli

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(argv, stdin=stdin, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def _json(stdout: str) -> dict[str, object]:
    payload = json.loads(stdout)
    assert stdout == canonical_json_text(payload)
    return payload


def _doctor_args(workspace: Path) -> list[str]:
    return [
        "doctor",
        "--workspace",
        str(workspace),
        "--target",
        "codex-cli",
        "--records",
        "records.jsonl",
        "--atoms",
        "atoms.jsonl",
    ]


def _source_state_digest(workspace: Path, *names: str) -> str:
    import hashlib

    items = []
    for name in names:
        raw = (workspace / name).read_bytes()
        items.append({"path": name, "sha256": sha256_bytes(raw), "size": len(raw)})
    text = json.dumps(sorted(items, key=lambda item: item["path"]), sort_keys=True, separators=(",", ":")) + "\n"
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def _canary() -> str:
    return json.loads((FIXTURES / "secret_atoms.jsonl").read_text(encoding="utf-8"))["value"]["summary"]


class _HostileMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        del key
        raise RuntimeError("sk-doctorCanary123456789012345")

    def __iter__(self):
        raise RuntimeError("sk-doctorCanary123456789012345")

    def __len__(self) -> int:
        raise RuntimeError("sk-doctorCanary123456789012345")

    def __repr__(self) -> str:
        return "sk-doctorCanary123456789012345"


class _HostileStr(str):
    def __repr__(self) -> str:
        return "sk-doctorCanary123456789012345"


def _clean_finding():
    import canon.doctor as doctor

    return doctor.DoctorFinding("adapter_descriptor_valid", "info", "ok", "adapter descriptor valid")


def test_clean_doctor_reports_descriptor_sources_and_exact_source_state(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)

    code, stdout, stderr = _run(["--json", *_doctor_args(workspace)])

    assert code == EX_OK
    assert stderr == ""
    payload = _json(stdout)
    data = payload["data"]
    assert payload["message"] == "doctor diagnostics complete"
    assert data["source_state_sha256"] == _source_state_digest(workspace, "records.jsonl", "atoms.jsonl")
    assert data["source_inputs"] == ["records.jsonl", "atoms.jsonl"]
    assert data["target"]["adapter_id"] == "codex-cli"
    assert data["target"]["integration_tier"] == "native-advisory"
    assert [finding["code"] for finding in data["findings"]] == [
        "adapter_descriptor_valid",
        "source_state_bound",
        "records_valid",
        "atoms_valid",
    ]


def test_doctor_supports_omitted_sources_and_human_output(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()

    code, stdout, stderr = _run(["doctor", "--target", "chatgpt-app", "--workspace", str(workspace)])

    assert code == EX_OK
    assert stdout == "PASS doctor: doctor diagnostics complete\n"
    assert stderr == ""


def test_secret_quarantine_scans_before_parse_and_never_leaks_canary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import canon.doctor as doctor

    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    (workspace / "atoms.jsonl").write_bytes((FIXTURES / "secret_atoms.jsonl").read_bytes())

    def forbidden_parse(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("secret-bearing sources must not be parsed")

    monkeypatch.setattr(doctor.Record, "from_dict", forbidden_parse)
    monkeypatch.setattr(doctor.CanonAtom, "from_dict", forbidden_parse)

    code, stdout, stderr = _run(["--json", *_doctor_args(workspace), "--expected-source-state", "sha256:" + "0" * 64])

    report = doctor.run_doctor(doctor.DoctorConfig(workspace=str(workspace), target="codex-cli", records="records.jsonl", atoms="atoms.jsonl"))
    rendered = stdout + stderr + repr(report) + str(report.to_dict()) + str(report.to_result_data())
    assert code == EX_SECURITY
    assert _json(stdout)["failure_code"] == "secret_quarantine"
    assert _canary() not in rendered


def test_offline_unknown_is_explicit_and_performs_no_external_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("doctor must not perform external work")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)

    code, stdout, stderr = _run(["--json", "doctor", "--target", "chatgpt-app", "--workspace", str(tmp_path), "--offline"])

    finding = _json(stdout)["data"]["findings"][-1]
    assert code == EX_OK
    assert stderr == ""
    assert finding["code"] == "remote_reachability_unknown"
    assert finding["evidence"]["status"] == "unknown"
    assert "does_not_prove" in finding["evidence"]


def test_authoritative_descriptor_tier_and_unsupported_lifecycle_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    import canon.doctor as doctor
    from canon.adapter import AdapterDescriptor

    descriptor = AdapterDescriptor(
        adapter_id="retired-target",
        display_name="Retired Target",
        version="1",
        integration_tier="unsupported",
        target_surfaces=("CANON.md",),
        import_modes=("file",),
        export_modes=("stdout",),
        bootstrap={"can_block_before_work": False},
    )
    monkeypatch.setattr(doctor, "descriptor_for", lambda target: descriptor)

    report = doctor.run_doctor(doctor.DoctorConfig(workspace=".", target="retired-target"))

    assert report.exit_code == EX_UNSUPPORTED
    assert report.failure_code == "unsupported_lifecycle"
    assert report.to_result_data()["target"]["integration_tier"] == "unsupported"


def test_strict_source_validation_reports_line_and_source_without_raw_input(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    (workspace / "records.jsonl").write_bytes(b'{"canon_schema":"canon.record/v1","canon_schema":"canon.record/v1"}\n')

    code, stdout, stderr = _run(["--json", *_doctor_args(workspace)])

    finding = _json(stdout)["data"]["findings"][0]
    assert code == EX_USAGE
    assert stderr == ""
    assert finding["failure_code"] == "invalid_args"
    assert finding["evidence"] == {"line": 1, "source": "records"}
    assert "canon.record" not in stdout


def test_expected_source_state_uses_authoritative_drift_gate(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    good = _source_state_digest(workspace, "records.jsonl", "atoms.jsonl")

    assert _run(["--json", *_doctor_args(workspace), "--expected-source-state", good])[0] == EX_OK
    code, stdout, stderr = _run(["--json", *_doctor_args(workspace), "--expected-source-state", "sha256:" + "0" * 64])

    payload = _json(stdout)
    assert code == EX_GATE
    assert stderr == ""
    assert payload["failure_code"] == "source_changed"
    assert payload["data"]["source_state_sha256"] == good


def test_stdin_may_be_consumed_once_and_only_from_injected_stream(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    text = (FIXTURES / "records.jsonl").read_text(encoding="utf-8")

    ok = _run(["--json", *_doctor_args(workspace), "--records", "-"], stdin=io.StringIO(text))
    both = _run(["--json", *_doctor_args(workspace), "--records", "-", "--atoms", "-"], stdin=io.StringIO(text))
    missing = _run(["--json", *_doctor_args(workspace), "--records", "-"])

    assert ok[0] == EX_OK
    assert both[0] == EX_USAGE
    assert missing[0] == EX_USAGE
    assert _canary() not in ok[1] + ok[2] + both[1] + both[2] + missing[1] + missing[2]


def test_source_path_failures_are_sanitized_and_classified(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    outside = tmp_path / "outside-records.jsonl"
    outside.write_text("[]\n", encoding="utf-8")

    missing = _run(["--json", *_doctor_args(workspace), "--records", "missing.jsonl"])
    outside_result = _run(["--json", *_doctor_args(workspace), "--records", str(outside)])

    assert missing[0] == EX_UNAVAILABLE
    assert _json(missing[1])["failure_code"] == "source_unreachable"
    assert outside_result[0] == EX_SECURITY
    assert _json(outside_result[1])["failure_code"] == "unsafe_path"
    assert _canary() not in outside_result[1] + outside_result[2]


def test_symlink_and_workspace_swap_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import canon.cli_artifacts as cli_artifacts

    workspace = tmp_path / "work"
    workspace.mkdir()
    records, _atoms = _copy_inputs(workspace)
    link = workspace / "records-link.jsonl"
    try:
        link.symlink_to(records)
    except OSError:
        pytest.skip("current platform or privileges do not allow file symlinks")
    assert _run(["--json", *_doctor_args(workspace), "--records", "records-link.jsonl"])[0] == EX_SECURITY

    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced"
    outside.mkdir()
    _copy_inputs(outside)
    real_resolve = cli_artifacts.resolve_under_root

    def swap_once(path: object, **kwargs: object) -> Path:
        workspace.rename(displaced)
        outside.rename(workspace)
        monkeypatch.setattr(cli_artifacts, "resolve_under_root", real_resolve)
        return real_resolve(path, **kwargs)

    monkeypatch.setattr(cli_artifacts, "resolve_under_root", swap_once)
    assert _run(["--json", *_doctor_args(workspace)])[0] == EX_SECURITY


def test_doctor_performs_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    before = _tree(workspace)

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("doctor must not write")

    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "touch", forbidden)

    assert _run(["--json", *_doctor_args(workspace)])[0] == EX_OK
    assert _tree(workspace) == before


def test_public_types_are_immutable_and_revalidate_tampering_without_hostile_repr(tmp_path: Path) -> None:
    import canon.doctor as doctor

    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    report = doctor.run_doctor(doctor.DoctorConfig(workspace=str(workspace), target="codex-cli", records="records.jsonl"))

    with pytest.raises(AttributeError):
        report.findings = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.findings[0].evidence["source"] = "changed"  # type: ignore[index]
    object.__setattr__(report.findings[0], "severity", "bad")
    with pytest.raises(TypeError) as tampered:
        report.to_dict()

    with pytest.raises(doctor.DoctorConfigError) as hostile:
        doctor.DoctorConfig(workspace=".", target=_HostileStr("codex-cli"))
    object.__setattr__(report.findings[0], "evidence", _HostileMapping())
    with pytest.raises(TypeError) as hostile_report:
        report.to_dict()

    assert _canary() not in str(tampered.value) + str(hostile.value) + str(hostile_report.value)


def test_doctor_config_repr_hides_paths_and_rejects_stdin_secret_metadata() -> None:
    import canon.doctor as doctor
    from canon.cli_artifacts import SourceBytes

    config = doctor.DoctorConfig(
        workspace="C:/private/canon",
        target="codex-cli",
        records="records.jsonl",
        atoms="atoms.jsonl",
    )
    assert "C:/private/canon" not in repr(config)
    assert "records.jsonl" not in repr(config)

    with pytest.raises(doctor.DoctorConfigError) as excinfo:
        doctor.DoctorConfig(
            workspace=".",
            target="codex-cli",
            records="-",
            stdin_source=SourceBytes(f"stdin-{_canary()}", b""),
        )
    assert _canary() not in str(excinfo.value)


@pytest.mark.parametrize("field", ("workspace", "records", "atoms"))
def test_doctor_config_secret_text_is_rejected_before_snapshot_or_json(field: str) -> None:
    import canon.doctor as doctor

    canary = _canary()
    clean = {"workspace": ".", "target": "codex-cli", "records": "records.jsonl", "atoms": "atoms.jsonl"}
    config = doctor.DoctorConfig(**clean)
    assert doctor.snapshot_doctor_config(config)[field] == clean[field]

    dirty = dict(clean)
    dirty[field] = f"safe-prefix-{canary}"
    with pytest.raises(doctor.DoctorConfigError) as constructed:
        doctor.DoctorConfig(**dirty)
    assert str(constructed.value) == "invalid doctor config"
    assert canary not in str(constructed.value) + repr(constructed.value)

    object.__setattr__(config, field, f"tampered-{canary}")
    with pytest.raises(doctor.DoctorConfigError) as snapshotted:
        doctor.snapshot_doctor_config(config)
    assert str(snapshotted.value) == "invalid doctor config"
    assert canary not in str(snapshotted.value) + repr(snapshotted.value)

    argv = ["--json", "doctor", "--target", "codex-cli", "--workspace", "."]
    if field == "workspace":
        argv[5] = f"cli-{canary}"
    else:
        argv.extend([f"--{field}", f"cli-{canary}"])
    code, stdout, stderr = _run(argv)

    assert code == EX_USAGE
    assert _json(stdout)["message"] == "invalid doctor config"
    assert canary not in stdout + stderr


def test_doctor_public_types_reject_secret_leaves_without_json_or_exception_leak() -> None:
    import canon.doctor as doctor

    for build in (
        lambda: doctor.DoctorFinding("adapter_descriptor_valid", "info", "ok", _canary()),
        lambda: doctor.DoctorFinding("adapter_descriptor_valid", "info", "ok", "ready", {"nested": [_canary()]}),
        lambda: doctor.DoctorReport(True, "ok", "ready", (_clean_finding(),), {"nested": {"token": _canary()}}),
    ):
        with pytest.raises((TypeError, doctor.DoctorConfigError)) as excinfo:
            build()
        assert _canary() not in str(excinfo.value)

    report = doctor.DoctorReport(True, "ok", "ready", (_clean_finding(),), {"safe": True})
    object.__setattr__(report.findings[0], "message", _canary())
    object.__setattr__(report, "data", {"nested": [_canary()]})
    assert _canary() not in repr(report.findings[0]) + repr(report)
    for serialize in (report.to_dict, report.to_result_data):
        with pytest.raises(TypeError) as excinfo:
            serialize()
        assert _canary() not in str(excinfo.value)

    finding = _clean_finding()
    object.__setattr__(finding, "evidence", {"nested": [_canary()]})
    assert _canary() not in repr(finding)
    with pytest.raises(TypeError) as excinfo:
        finding.to_dict()
    assert _canary() not in str(excinfo.value)


def test_doctor_report_rejects_unknown_codes_and_noncanonical_priority() -> None:
    import canon.doctor as doctor

    with pytest.raises(TypeError):
        doctor.DoctorFinding("future", "blocker", "future-code", "future failure")

    secret = doctor.DoctorFinding("secret_quarantine", "blocker", "secret_quarantine", "source quarantined")
    drift = doctor.DoctorFinding("source_changed", "blocker", "source_changed", "source state changed")
    with pytest.raises(TypeError):
        doctor.DoctorReport(False, "source_changed", "doctor diagnostics complete", (drift, secret))

    report = doctor.DoctorReport(False, "secret_quarantine", "doctor diagnostics complete", (secret, drift))
    object.__setattr__(report, "findings", (drift, secret))
    object.__setattr__(report, "failure_code", "source_changed")
    object.__setattr__(report, "exit_code", EX_GATE)
    with pytest.raises(TypeError):
        report.to_dict()


def test_direct_stdin_source_respects_exact_max_source_bytes() -> None:
    import canon.doctor as doctor
    from canon.cli_artifacts import MAX_SOURCE_BYTES, SourceBytes

    exact = SourceBytes("stdin-records", b"\n" * MAX_SOURCE_BYTES)
    assert doctor.DoctorConfig(workspace=".", target="codex-cli", records="-", stdin_source=exact).stdin_source == exact

    over = SourceBytes("stdin-records", b"\n" * (MAX_SOURCE_BYTES + 1))
    with pytest.raises(doctor.DoctorConfigError) as excinfo:
        doctor.DoctorConfig(workspace=".", target="codex-cli", records="-", stdin_source=over)
    assert _canary() not in str(excinfo.value)


def test_option_ordering_is_canonical_and_secret_has_failure_priority(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    _copy_inputs(workspace)
    (workspace / "atoms.jsonl").write_bytes((FIXTURES / "secret_atoms.jsonl").read_bytes())

    first = _run(["--json", *_doctor_args(workspace), "--expected-source-state", "sha256:" + "0" * 64])
    second = _run([*_doctor_args(workspace), "--expected-source-state", "sha256:" + "0" * 64, "--json"])

    assert first[0] == second[0] == EX_SECURITY
    assert first[1] == second[1]
    payload = _json(first[1])
    assert payload["failure_code"] == "secret_quarantine"
    assert payload["data"]["findings"][0]["failure_code"] == "secret_quarantine"
    assert "source_changed" not in first[1]
