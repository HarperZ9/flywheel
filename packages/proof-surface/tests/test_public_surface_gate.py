from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import check_public_surface as gate


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_discovery_is_tracked_only_and_excludes_build_and_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    (repo / "USAGE.md").write_text("C:/Users/private/leak\n", encoding="utf-8")
    (repo / "dist").mkdir()
    (repo / "dist" / "leak.md").write_text(
        "C:/Users/private/build-leak\n", encoding="utf-8"
    )
    _git(repo, "add", "README.md", "dist/leak.md")

    assert gate.discover_public_surfaces(repo) == [repo / "README.md"]


def test_credential_suffixes_and_unknown_text_are_always_scanned(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    token = "ghp_" + "a" * 30
    private_key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    paths = [
        repo / ".env.local",
        repo / "operator.pem",
        repo / "operator.key",
        repo / "app.properties",
        repo / "runtime.conf",
        repo / "unknown.payload",
    ]
    for path in paths:
        path.write_text(token + "\n" + private_key + "\n", encoding="utf-8")
    _git(repo, "add", *[path.name for path in paths])

    surfaces, findings = gate.scan_repository(repo)

    assert surfaces == sorted(paths)
    assert {finding.path for finding in findings} == {path.name for path in paths}
    assert {finding.code for finding in findings} == {
        "private-key-material",
        "secret-material",
    }


def test_known_binary_is_exempt_but_unknown_binary_fails_closed(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    (repo / "unknown.blob").write_bytes(b"\xff\xfe\x00\x01")
    _git(repo, "add", "image.png", "unknown.blob")

    surfaces, findings = gate.scan_repository(repo)

    assert surfaces == [repo / "image.png", repo / "unknown.blob"]
    assert [(finding.path, finding.code) for finding in findings] == [
        ("unknown.blob", "unreadable-unclassified")
    ]


def test_oversized_unclassified_file_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    path = repo / "large.unknown"
    path.write_text("x" * 65, encoding="utf-8")
    _git(repo, "add", path.name)
    monkeypatch.setattr(gate, "MAX_SCAN_BYTES", 64)

    _, findings = gate.scan_repository(repo)

    assert [(finding.path, finding.code) for finding in findings] == [
        ("large.unknown", "oversized-unclassified")
    ]


def test_scan_reports_each_high_signal_public_leak() -> None:
    token = "ghp_" + "a" * 30
    private_key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    text = "\n".join(
        [
            "C:/Users/alice/private.json",
            "/home/alice/private.json",
            "api_token = " + token,
            private_key,
            "This uses an em dash \u2014 here.",
            "Mojibake \u00e2\u20ac\u201d remains.",
            "TODO: replace this.",
            "Read protected/operator.json.",
        ]
    )

    findings = gate.scan_text(Path("README.md"), text, public_prose=True)

    assert {finding.code for finding in findings} == {
        "machine-path",
        "secret-material",
        "private-key-material",
        "em-dash",
        "mojibake",
        "unresolved-placeholder",
        "private-reference",
    }
    assert findings == sorted(findings)


def test_source_code_is_scanned_for_secret_material_not_prose_style() -> None:
    text = 'TOKEN = "' + "sk-" + "a" * 30 + '"\n# TODO \u2014 prose\n'

    findings = gate.scan_text(Path("src/module.py"), text, public_prose=False)

    assert [finding.code for finding in findings] == ["secret-material"]


def test_known_byte_frozen_v0_1_path_debt_is_count_bounded() -> None:
    relative = Path(
        "conformance/authorization-receipt/v0.1/valid/minimal.receipt.json"
    )
    legacy = "C:/dev/public/proof-surface/conformance/"

    assert gate.scan_text(relative, legacy, public_prose=True) == []
    findings = gate.scan_text(relative, legacy + "\n" + legacy, public_prose=True)
    assert [finding.code for finding in findings] == ["machine-path"]


def test_known_public_readme_em_dash_debt_is_count_bounded() -> None:
    relative = Path("src/proof_surface/visual_measurement/README.md")

    assert gate.scan_text(relative, "one \u2014 dash", public_prose=True) == []
    findings = gate.scan_text(
        relative, "one \u2014 dash\ntwo \u2014 dashes", public_prose=True
    )
    assert [finding.code for finding in findings] == ["em-dash"]


def test_cli_is_deterministic_and_nonzero_on_findings(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "README.md").write_text(
        "TBD\nC:/Users/alice/leak\n", encoding="utf-8"
    )
    _git(repo, "add", "README.md")

    assert gate.main([str(repo)]) == 1
    first = capsys.readouterr().out
    assert gate.main([str(repo)]) == 1
    second = capsys.readouterr().out

    assert first == second
    assert "README.md:1:1 [unresolved-placeholder]" in first
    assert "README.md:2:1 [machine-path]" in first
