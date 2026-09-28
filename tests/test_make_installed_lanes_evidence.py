"""The installed-lanes evidence writer refuses an artifact it cannot vouch for.

Each test builds a synthetic acceptance artifact from the committed lane
expectations, breaks one thing, and checks that the writer names it. A clean
artifact yields the same summary shape as the committed evidence file.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import installed_lanes_gh as gh
from scripts import make_installed_lanes_evidence as mk

REPO = Path(__file__).resolve().parents[1]
COMMIT = "0123456789abcdef0123456789abcdef01234567"
EXPECTED = json.loads((REPO / mk.EXPECTATIONS).read_text(encoding="utf-8"))["lanes"]
INSTALLER = {"name": "Flywheel-Setup-9.9.9-x64.exe", "sha256": "ab" * 32, "size": 1234}
DENY = ["runneradmin", "someone"]


def _lane(row: dict) -> dict:
    measured = "A" if row["verdict"] == "AT_CLASS" else None
    failed = [{"check": c, "code": None, "status": 200} for c in row.get("failed", [])]
    return {"class_plan": "A", "class_expected": "A", "class_measured": measured,
            "verdict": row["verdict"], "failed": failed, "untested": [], "not_measurable": []}


def _receipt(mode: str) -> dict:
    lanes = {lane: _lane(row) for lane, row in EXPECTED.items()}
    at_class = sum(1 for r in lanes.values() if r["verdict"] == "AT_CLASS")
    return {"schema": mk.RECEIPT_SCHEMA, "install_mode": mode,
            "expected": {"departures": [], "matches": True},
            "guards": {"fresh_settled": True, "token_absent_from_receipt": True},
            "host": {"model_server": False},
            "meta": {"source_commit": COMMIT, "engine_sha256": "cd" * 32},
            "summary": {"below_bar": ["index", "telos"], "by_class": {"A": at_class},
                        "guards_failed": [], "verdict": "BELOW_BAR"},
            "lanes": lanes}


def _write(root: Path, receipts: dict | None = None, run: dict | None = None,
           manifest_commit: str = COMMIT) -> Path:
    receipts = receipts or {mode: _receipt(mode) for mode in mk.LEGS}
    run = run or {"schema": mk.RUN_SCHEMA, "source_commit": COMMIT, "version": "9.9.9",
                  "installer": INSTALLER, "engine_sha256": "cd" * 32}
    (root / mk.RECEIPTS).mkdir(parents=True, exist_ok=True)
    for mode, name in mk.LEGS.items():
        (root / mk.RECEIPTS / name).write_text(json.dumps(receipts[mode]), encoding="utf-8")
    (root / mk.RUN_SUMMARY).write_text(json.dumps(run), encoding="utf-8-sig")
    (root / "SHA256SUMS.txt").write_text(f"{INSTALLER['sha256']}  {INSTALLER['name']}\n")
    (root / "installed-build-manifest.json").write_text(
        json.dumps({"source_commit": manifest_commit}), encoding="utf-8")
    return root


def _problems(root: Path) -> list[str]:
    return mk.check_artifact(root, COMMIT, EXPECTED, "9.9.9", DENY)[0]


def test_a_clean_artifact_passes_and_matches_the_committed_shape(tmp_path):
    root = _write(tmp_path)
    problems, receipts, run = mk.check_artifact(root, COMMIT, EXPECTED, "9.9.9", DENY)
    assert problems == []
    meta = {"run_id": 1, "job_id": 2, "date": "2026-01-01", "artifact_zip_sha256": "ef" * 32}
    summary = mk.build_summary(root, receipts, run, meta)
    committed = json.loads(next((REPO / mk.EVIDENCE_DIR).glob("installed-lanes-ci-*.json"))
                           .read_text(encoding="utf-8"))
    assert summary.keys() == committed.keys()
    assert summary["run"].keys() == committed["run"].keys()
    assert summary["legs"]["per-user"].keys() == committed["legs"]["per-user"].keys()
    raw = (root / mk.RECEIPTS / mk.LEGS["all-users"]).read_bytes()
    assert summary["legs"]["all-users"]["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["installer"] == {"name": INSTALLER["name"], "bytes": INSTALLER["size"]}
    assert set(summary["lanes"]) == set(EXPECTED)


@pytest.mark.parametrize("breakage, words", [
    (lambda r: r["per-user"]["expected"].update(matches=False), "expected.matches"),
    (lambda r: r["all-users"]["expected"]["departures"].append("gather"), "departures"),
    (lambda r: r["per-user"]["guards"].update(fresh_settled=False), "guard"),
    (lambda r: r["per-user"]["meta"].update(source_commit="f" * 40), "meta.source_commit"),
    (lambda r: r["all-users"]["lanes"]["gather"].update(verdict="BELOW_BAR"), "gather"),
    (lambda r: r["per-user"]["lanes"].pop("canon"), "lanes differ"),
    (lambda r: r["per-user"]["summary"]["by_class"].update(A=1), "by_class"),
    (lambda r: r["all-users"]["meta"].update(engine_sha256="0" * 64), "engine_sha256"),
    (lambda r: r["all-users"]["lanes"]["bulletin"].update(untested=["x"]), "different outcomes"),
])
def test_a_broken_receipt_is_refused(tmp_path, breakage, words):
    receipts = {mode: _receipt(mode) for mode in mk.LEGS}
    breakage(receipts)
    problems = _problems(_write(tmp_path, receipts=receipts))
    assert any(words in p for p in problems), problems


@pytest.mark.parametrize("change, words", [
    ({"source_commit": "f" * 40}, "source_commit"),
    ({"version": "1.0.4"}, "version"),
    ({"installer": dict(INSTALLER, sha256="00" * 32)}, "SHA256SUMS"),
    ({"installer": dict(INSTALLER, size=0)}, "installer.size"),
])
def test_a_run_summary_off_the_receipts_is_refused(tmp_path, change, words):
    run = {"schema": mk.RUN_SCHEMA, "source_commit": COMMIT, "version": "9.9.9",
           "installer": INSTALLER, "engine_sha256": "cd" * 32, **change}
    assert any(words in p for p in _problems(_write(tmp_path, run=run)))


def test_a_manifest_off_the_commit_or_a_missing_file_is_refused(tmp_path):
    assert any("installed-build-manifest.json" in p
               for p in _problems(_write(tmp_path / "a", manifest_commit="f" * 40)))
    root = _write(tmp_path / "b")
    (root / "installed-build-manifest.json").unlink()
    (root / "SHA256SUMS.txt").unlink()
    problems = _problems(root)
    assert any("installed-build-manifest.json: missing" in p for p in problems)
    assert any("SHA256SUMS" in p for p in problems)
    (root / mk.RECEIPTS / mk.LEGS["all-users"]).unlink()
    with pytest.raises(SystemExit, match="installed-lanes-all-users.json is missing"):
        _problems(root)


@pytest.mark.parametrize("value, rule", [
    ("C:\\build\\engine", "local path"),
    ("see D:/a/flywheel", "local path"),
    ("/home/someone/x", "user folder"),
    ("\\\\server\\share", "network path"),
    ("mail me@example.com", "e-mail address"),
    ("ghp_" + "a" * 30, "token"),
    ("user RunnerAdmin", "account name"),
    ("Someone ran it", "account name"),
])
def test_private_detail_in_any_artifact_string_is_refused(tmp_path, value, rule):
    receipts = {mode: _receipt(mode) for mode in mk.LEGS}
    receipts["per-user"]["lanes"]["gather"]["untested"] = [value]
    problems = _problems(_write(tmp_path, receipts=receipts))
    assert any(p.endswith(rule) and "installed-lanes-per-user.json" in p for p in problems)


def test_placeholders_and_names_inside_words_are_not_private(tmp_path):
    receipts = {mode: _receipt(mode) for mode in mk.LEGS}
    for mode in mk.LEGS:
        receipts[mode]["lanes"]["gather"]["untested"] = [
            "<install_root>\\engine", "https://example.org/x", "lanes/mneme", "someones"]
    assert _problems(_write(tmp_path, receipts=receipts)) == []


def test_the_writer_refuses_without_run_metadata_and_writes_nothing(tmp_path):
    with pytest.raises(SystemExit, match="--job-id"):
        mk.main(["--run-id", "1", "--commit", COMMIT, "--artifact", str(_write(tmp_path)),
                 "--date", "2026-01-01", "--artifact-zip-sha256", "0" * 64])
    with pytest.raises(SystemExit):
        mk.main(["--run-id", "1", "--commit", "abc123", "--artifact", str(tmp_path)])
    base = ["--run-id", "1", "--commit", COMMIT, "--artifact", str(tmp_path), "--job-id", "2"]
    with pytest.raises(SystemExit, match="YYYY-MM-DD"):
        mk.main(base + ["--date", "27 Sep", "--artifact-zip-sha256", "0" * 64])
    with pytest.raises(SystemExit, match="64 lowercase hex"):
        mk.main(base + ["--date", "2026-01-01", "--artifact-zip-sha256", "x"])
    assert not (REPO / mk.EVIDENCE_DIR / "installed-lanes-ci-1.json").exists()


def _repo(root: Path) -> Path:
    (root / mk.EVIDENCE_DIR).mkdir(parents=True)
    (root / mk.EXPECTATIONS).parent.mkdir(parents=True)
    (root / mk.EXPECTATIONS).write_bytes((REPO / mk.EXPECTATIONS).read_bytes())
    (root / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    return root


def test_the_writer_refuses_a_failing_artifact_and_writes_only_a_clean_one(
        tmp_path, monkeypatch):
    """End to end through main: each refusal exits 1 and leaves no file, and the
    local account name is refused like the runner's."""
    monkeypatch.setattr(mk.getpass, "getuser", lambda: "zed")
    repo = _repo(tmp_path / "repo")
    out = repo / mk.EVIDENCE_DIR / "installed-lanes-ci-5.json"
    args = ["--run-id", "5", "--commit", COMMIT, "--job-id", "7", "--date", "2026-01-01",
            "--artifact-zip-sha256", "ef" * 32, "--root", str(repo), "--artifact"]
    breakages = (
        lambda r: r["per-user"]["expected"].update(matches=False),
        lambda r: r["all-users"]["expected"]["departures"].append("gather"),
        lambda r: r["all-users"]["guards"].update(token_absent_from_receipt=False),
        lambda r: r["per-user"]["meta"].update(source_commit="f" * 40),
        lambda r: [r[m]["lanes"]["gather"].update(untested=["C:\\Users\\x"]) for m in r],
        lambda r: [r[m]["lanes"]["gather"].update(untested=["ran as Zed"]) for m in r],
    )
    for i, breakage in enumerate(breakages):
        receipts = {mode: _receipt(mode) for mode in mk.LEGS}
        breakage(receipts)
        assert mk.main([*args, str(_write(tmp_path / f"bad{i}", receipts=receipts))]) == 1
        assert not out.exists(), i
    assert mk.main([*args, str(_write(tmp_path / "good"))]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["run"] == {"workflow": mk.WORKFLOW, "run_id": 5, "job_id": 7,
                              "date": "2026-01-01", "artifact_zip_sha256": "ef" * 32}
    assert written["source_commit"] == COMMIT and written["installer"]["bytes"] == 1234


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return buf.getvalue()


def test_the_zip_must_match_its_digest_and_the_local_folder(tmp_path):
    files = {"ci-installed-acceptance-summary.json": b"{}", "installed-acceptance/a.json": b"1"}
    data = _zip(files)
    digest = hashlib.sha256(data).hexdigest()
    with pytest.raises(SystemExit, match="digest"):
        gh.match_or_extract(data, "0" * 64, tmp_path, "art")
    target = gh.match_or_extract(data, digest, tmp_path, "art")
    assert (target / "installed-acceptance" / "a.json").read_bytes() == b"1"
    assert gh.match_or_extract(data, digest, tmp_path, "art") == target
    (target / "installed-acceptance" / "a.json").write_bytes(b"2")
    with pytest.raises(SystemExit, match="differ from their zip members"):
        gh.match_or_extract(data, digest, tmp_path, "art")
    (target / "extra.txt").write_bytes(b"")
    with pytest.raises(SystemExit, match="files differ from the artifact zip"):
        gh.match_or_extract(data, digest, tmp_path, "art")
    evil = _zip({"../escape.json": b"x"})
    with pytest.raises(SystemExit, match="leaves the folder"):
        gh.match_or_extract(evil, hashlib.sha256(evil).hexdigest(), tmp_path / "e", "art")


def _fake_gh(view: dict, artifacts: list):
    def run(cmd, capture_output, check):
        body = view if cmd[1:3] == ["run", "view"] else {"artifacts": artifacts}
        return SimpleNamespace(returncode=0, stdout=json.dumps(body).encode(), stderr=b"")
    return run


def test_run_metadata_comes_from_a_successful_run_and_its_named_artifact():
    job = {"databaseId": 7, "startedAt": "2026-09-27T23:55:52Z", "conclusion": "success"}
    view = {"status": "completed", "conclusion": "success", "headSha": COMMIT, "jobs": [job]}
    art = {"id": 9, "name": "windows-installed-acceptance-5", "expired": False,
           "digest": "sha256:" + "ab" * 32}
    meta = gh.run_meta("o/r", 5, _fake_gh(view, [art]))
    assert (meta["job_id"], meta["date"], meta["artifact_id"]) == (7, "2026-09-27", 9)
    assert meta["artifact_zip_sha256"] == "ab" * 32
    with pytest.raises(SystemExit, match="completed/failure"):
        gh.run_meta("o/r", 5, _fake_gh(dict(view, conclusion="failure"), [art]))
    with pytest.raises(SystemExit, match="no unexpired artifact"):
        gh.run_meta("o/r", 5, _fake_gh(view, [dict(art, name="other")]))
    with pytest.raises(SystemExit, match="no sha256 digest"):
        gh.run_meta("o/r", 5, _fake_gh(view, [dict(art, digest=None)]))
    two = copy.deepcopy(view)
    two["jobs"].append(job)
    with pytest.raises(SystemExit, match="one successful job"):
        gh.run_meta("o/r", 5, _fake_gh(two, [art]))
