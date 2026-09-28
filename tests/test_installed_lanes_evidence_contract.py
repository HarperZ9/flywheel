"""Reject incomplete launch evidence and artifacts from unrelated workflows."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from test_make_installed_lanes_evidence import (
    COMMIT, _fake_gh, _launch, _others, _problems, _repo, _write, _zip,
    gh, launch_contract, mk,
)


@pytest.mark.parametrize("mode", ["full", "inspect"])
@pytest.mark.parametrize("optional_state", ["SKIP", "UNSUPPORTED"])
def test_complete_launch_receipts_allow_optional_unavailable_checks(tmp_path, mode, optional_state):
    receipt = _launch(mode)
    for row in receipt["assertions"]:
        if row["severity"] == "info":
            row["state"] = optional_state
    assert launch_contract.validate_receipt_semantics(receipt) == []
    others = _others()
    others[f"{mk.RECEIPTS}/installed-launch-{mode}.json"] = receipt
    assert _problems(_write(tmp_path, others=others)) == []


def _break_launch(receipt, defect):
    if defect == "empty_assertions":
        receipt["assertions"] = []
    elif defect == "missing_assertions":
        del receipt["assertions"]
    elif defect == "missing_required":
        receipt["assertions"].pop(0)
    elif defect == "duplicate_required":
        receipt["assertions"].append(dict(receipt["assertions"][0]))
    elif defect == "critical_not_checked":
        receipt["assertions"][0]["state"] = "NOT_CHECKED"
    elif defect == "missing_phases":
        del receipt["phase_results"]
    elif defect == "missing_phase":
        receipt["phase_results"].pop()


@pytest.mark.parametrize("mode", ["full", "inspect"])
@pytest.mark.parametrize("defect", [
    "empty_assertions", "missing_assertions", "missing_required", "duplicate_required",
    "critical_not_checked", "missing_phases", "missing_phase",
])
def test_invalid_launch_receipt_is_refused_without_writing_evidence(tmp_path, mode, defect, capsys):
    others = _others()
    name = f"installed-launch-{mode}.json"
    receipt = others[f"{mk.RECEIPTS}/{name}"]
    _break_launch(receipt, defect)
    assert launch_contract.validate_receipt_semantics(receipt) != []
    artifact = _write(tmp_path / "artifact", others=others)
    repo = _repo(tmp_path / "repo")
    result = mk.main([
        "--run-id", "5", "--commit", COMMIT, "--job-id", "7", "--date", "2026-09-28",
        "--artifact-zip-sha256", "ef" * 32, "--root", str(repo), "--artifact", str(artifact),
    ])
    assert result == 1
    assert name in capsys.readouterr().out
    assert list((repo / mk.EVIDENCE_DIR).iterdir()) == []


def test_launch_receipts_cannot_be_swapped_between_full_and_inspect(tmp_path):
    others = _others()
    full, inspect = [f"{mk.RECEIPTS}/{name}" for name in mk.LAUNCH]
    others[full], others[inspect] = others[inspect], others[full]
    assert all(launch_contract.validate_receipt_semantics(others[path]) == []
               for path in (full, inspect))
    problems = _problems(_write(tmp_path, others=others))
    assert all(any(name in problem for problem in problems) for name in mk.LAUNCH), problems


def _metadata():
    return {"path": ".github/workflows/windows-installed-acceptance.yml",
            "repository": {"full_name": "o/r"}, "head_branch": "main", "head_sha": COMMIT}


def _successful_run(metadata, commit=COMMIT):
    view = {"status": "completed", "conclusion": "success", "headSha": commit,
            "jobs": [{"databaseId": 7, "startedAt": "2026-09-28T09:01:00Z",
                      "conclusion": "success"}]}
    artifacts = [{"id": 9, "name": "windows-installed-acceptance-5", "expired": False,
                  "digest": "sha256:" + "ab" * 32}]
    return _fake_gh(view, artifacts, metadata)


@pytest.mark.parametrize("change", [
    {"path": ".github/workflows/ci.yml"}, {"path": None},
    {"repository": {"full_name": "unrelated/project"}}, {"repository": None},
    {"head_sha": "f" * 40}, {"head_sha": None}, {"head_branch": ""},
])
def test_unrelated_or_unidentified_workflow_is_refused(change):
    with pytest.raises(SystemExit):
        gh.run_meta("o/r", 5, _successful_run({**_metadata(), **change}))


@pytest.mark.parametrize("field", ["path", "repository", "head_sha", "head_branch"])
def test_absent_workflow_identity_fields_are_refused(field):
    metadata = _metadata()
    del metadata[field]
    with pytest.raises(SystemExit):
        gh.run_meta("o/r", 5, _successful_run(metadata))


def test_run_metadata_records_the_workflow_repository_ref_and_sha():
    meta = gh.run_meta("o/r", 5, _successful_run(_metadata()))
    assert meta["workflow_source"] == {"repository": "o/r", "ref": "refs/heads/main",
                                       "sha": COMMIT}


def test_mismatched_build_commit_is_refused_before_zip_download(tmp_path):
    calls = []
    responder = _successful_run(_metadata())

    def run(cmd, **kwargs):
        calls.append(cmd)
        return responder(cmd, **kwargs)

    with pytest.raises(SystemExit):
        gh.fetch_and_verify("o/r", 5, tmp_path, run, expected_commit="e" * 40)
    assert not any(cmd[-1].endswith("/zip") for cmd in calls)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", [
    {"repository": "unrelated/project"}, {"ref": "refs/heads/unreviewed"},
    {"sha": "e" * 40}, None, {},
])
def test_verified_zip_requires_workflow_source_to_match_run_metadata(tmp_path, change):
    artifact = _write(tmp_path / "fixture")
    summary_path = artifact / mk.RUN_SUMMARY
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if change is not None:
        summary["workflow_source"] = {
            "repository": "o/r", "ref": "refs/heads/main", "sha": COMMIT, **change}
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    data = _zip({p.relative_to(artifact).as_posix(): p.read_bytes()
                 for p in artifact.rglob("*") if p.is_file()})
    responder = _successful_run(_metadata())

    def run(cmd, **kwargs):
        if cmd[1:] == ["api", "repos/o/r/actions/artifacts/9/zip"]:
            return SimpleNamespace(returncode=0, stdout=data, stderr=b"")
        response = responder(cmd, **kwargs)
        if cmd[-1].endswith("/artifacts"):
            body = json.loads(response.stdout)
            body["artifacts"][0]["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
            response.stdout = json.dumps(body).encode()
        return response

    download = tmp_path / "download"
    if change != {}:
        with pytest.raises(SystemExit, match="workflow_source"):
            gh.fetch_and_verify("o/r", 5, download, run, expected_commit=COMMIT)
    else:
        meta = gh.fetch_and_verify("o/r", 5, download, run, expected_commit=COMMIT)
        assert meta == {"run_id": 5, "job_id": 7, "date": "2026-09-28",
                        "artifact_zip_sha256": hashlib.sha256(data).hexdigest()}
        extracted = download / "windows-installed-acceptance-5" / mk.RUN_SUMMARY
        assert extracted.is_file()
        receipt = json.loads(extracted.read_text(encoding="utf-8-sig"))
        assert receipt["source_commit"] == COMMIT
        assert receipt["workflow_source"] == {
            "repository": "o/r", "ref": "refs/heads/main", "sha": COMMIT}


def test_bad_metadata_through_main_writes_no_evidence(tmp_path, monkeypatch):
    fetch = gh.fetch_and_verify
    runner = _successful_run({**_metadata(), "repository": {"full_name": "wrong/project"}})

    def fetch_with_bad_metadata(repo, run_id, artifact, *, expected_commit):
        return fetch(repo, run_id, artifact, runner, expected_commit=expected_commit)

    monkeypatch.setattr(gh, "fetch_and_verify", fetch_with_bad_metadata)
    repo = _repo(tmp_path / "repo")
    artifact = tmp_path / "download"
    with pytest.raises(SystemExit):
        mk.main(["--run-id", "5", "--commit", COMMIT, "--from-gh", "--repo", "o/r",
                 "--root", str(repo), "--artifact", str(artifact)])
    assert list((repo / mk.EVIDENCE_DIR).iterdir()) == []
    assert not artifact.exists()


def test_evidence_writer_passes_build_commit_to_github_verification(tmp_path, monkeypatch):
    received = []

    def fetch(repo, run_id, artifact, *, expected_commit):
        received.append((repo, run_id, expected_commit))
        return {"run_id": 5, "job_id": 7, "date": "2026-09-28",
                "artifact_zip_sha256": "ab" * 32}

    monkeypatch.setattr(gh, "fetch_and_verify", fetch)
    artifact = _write(tmp_path / "artifact")
    repo = _repo(tmp_path / "repo")
    assert mk.main(["--run-id", "5", "--commit", COMMIT, "--from-gh",
                    "--root", str(repo), "--artifact", str(artifact)]) == 0
    evidence = json.loads((repo / mk.EVIDENCE_DIR / "installed-lanes-ci-5.json").read_text())
    assert evidence["source_commit"] == COMMIT
    assert evidence["run"]["run_id"] == 5 and evidence["run"]["job_id"] == 7
    assert received == [("HarperZ9/flywheel", 5, COMMIT)]
