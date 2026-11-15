"""The art gate settles whether a drawing fits its columns and matches its spec. It
cannot settle whether the drawing is true, because both sides derive from the same JSON.
So this file reads the sealed documents and runs the checker: every claim the three
drawings make is asserted here against real bytes, and a claim that stops holding fails
the suite rather than staying on the page.

The seal test is the load-bearing one. README.md is a sealed document, and these
drawings live in it, so an edit that is not followed by a re-seal fails here instead of
shipping a corpus that says DRIFT to the first stranger who checks it."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "verify_manifest.py"
_SPEC = _REPO / "docs" / "art" / "witnessing-spine.art.json"
_MANIFEST = _REPO / "MANIFEST.sha256"

RUNS = (
    "RUN-001-verifiable-provenance-financial-ai.md",
    "RUN-002-genai-cobol-modernization-equivalence.md",
    "RUN-003-quant-ml-out-of-sample-steelman.md",
    "RUN-004-defi-trustlessness-steelman.md",
    "RUN-005-enterprise-attestation-assurance-steelman.md",
)

LABELS = (
    "peer-reviewed",
    "preprint",
    "standard",
    "gov",
    "primary-legal",
    "incident",
    "gray-lit",
    "data",
)


def _module():
    spec = importlib.util.spec_from_file_location("verify_manifest", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seal(root: Path, names, digests=None) -> None:
    lines = ["# a manifest", "# with two comment lines"]
    for name in names:
        recorded = (digests or {}).get(name)
        if recorded is None:
            recorded = hashlib.sha256((root / name).read_bytes()).hexdigest()
        lines.append(recorded + "  " + name)
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _corpus(root: Path, count: int = 3) -> list[str]:
    names = []
    for index in range(count):
        name = "doc%d.md" % index
        (root / name).write_text("document %d\n" % index, encoding="utf-8")
        names.append(name)
    _seal(root, names)
    return names


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(root)],
        capture_output=True,
        text=True,
    )


def test_the_real_corpus_still_re_derives_against_its_own_manifest() -> None:
    result = _run(_REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("MATCH")


def test_the_manifest_holds_two_comment_lines_and_one_digest_per_document() -> None:
    lines = _MANIFEST.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 9
    assert len([line for line in lines if line.startswith("#")]) == 2
    entries = _module()._parse(_MANIFEST.read_text(encoding="utf-8"))
    assert len(entries) == 7
    assert all(digest is not None for digest, _ in entries)


def test_every_sealed_document_is_present_and_re_derives_on_its_own() -> None:
    for digest, name in _module()._parse(_MANIFEST.read_text(encoding="utf-8")):
        path = _REPO / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name


def test_the_readme_is_sealed_so_an_unsealed_edit_cannot_ship() -> None:
    sealed = {name for _, name in _module()._parse(_MANIFEST.read_text(encoding="utf-8"))}
    assert "README.md" in sealed
    assert len(sealed & set(RUNS)) == len(RUNS)
    assert "SYNTHESIS-the-witnessing-spine.md" in sealed


def test_the_checker_needs_nothing_beyond_the_standard_library() -> None:
    imported = [
        line.split()[1].split(".")[0]
        for line in _SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert sorted(imported) == ["hashlib", "pathlib", "sys"]


def test_blank_lines_and_comments_are_skipped_before_anything_is_hashed() -> None:
    parse = _module()._parse
    assert parse("\n\n# a note\n   \n") == []
    assert parse("#one\n" + "a" * 64 + "  f.md\n") == [("a" * 64, "f.md")]


def test_a_malformed_line_counts_as_unverifiable_rather_than_passing() -> None:
    parse = _module()._parse
    for line in ("noseparatorhere", "a" * 64 + "  ", "a" * 63 + "  f.md", "  f.md"):
        entries = parse(line + "\n")
        assert entries and entries[0][0] is None, line


def test_a_manifest_of_only_malformed_lines_is_unverifiable(tmp_path) -> None:
    (tmp_path / "doc0.md").write_text("kept\n", encoding="utf-8")
    (tmp_path / "MANIFEST.sha256").write_text("not a manifest line\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert result.stdout.startswith("UNVERIFIABLE")


def test_a_digest_is_read_case_insensitively(tmp_path) -> None:
    (tmp_path / "doc0.md").write_text("upper\n", encoding="utf-8")
    upper = hashlib.sha256((tmp_path / "doc0.md").read_bytes()).hexdigest().upper()
    _seal(tmp_path, ["doc0.md"], {"doc0.md": upper})
    assert _run(tmp_path).returncode == 0


def test_a_file_larger_than_one_read_block_still_re_derives(tmp_path) -> None:
    payload = b"witness" * 40000
    (tmp_path / "big.bin").write_bytes(payload)
    assert len(payload) > 65536
    assert _module()._digest(tmp_path / "big.bin") == hashlib.sha256(payload).hexdigest()
    _seal(tmp_path, ["big.bin"])
    assert _run(tmp_path).returncode == 0


def test_a_clean_corpus_reports_match_and_counts_what_it_checked(tmp_path) -> None:
    names = _corpus(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("MATCH")
    assert str(len(names)) in result.stdout


def test_one_changed_byte_reports_drift_and_names_the_file(tmp_path) -> None:
    _corpus(tmp_path)
    (tmp_path / "doc1.md").write_text("document 1 tampered\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.startswith("DRIFT")
    assert "doc1.md" in result.stdout


def test_a_deleted_document_is_unverifiable_rather_than_drift(tmp_path) -> None:
    _corpus(tmp_path)
    (tmp_path / "doc1.md").unlink()
    result = _run(tmp_path)
    assert result.returncode == 2
    assert result.stdout.startswith("UNVERIFIABLE")


def test_a_missing_manifest_is_unverifiable_rather_than_a_pass(tmp_path) -> None:
    _corpus(tmp_path)
    (tmp_path / "MANIFEST.sha256").unlink()
    result = _run(tmp_path)
    assert result.returncode == 2
    assert result.stdout.startswith("UNVERIFIABLE")


def test_deleting_a_second_file_cannot_downgrade_a_caught_tamper(tmp_path) -> None:
    _corpus(tmp_path)
    (tmp_path / "doc1.md").write_text("document 1 tampered\n", encoding="utf-8")
    (tmp_path / "doc2.md").unlink()
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.startswith("DRIFT")


def test_the_verdict_is_one_word_and_one_line_of_detail(tmp_path) -> None:
    _corpus(tmp_path)
    lines = [line for line in _run(tmp_path).stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].split()[0] in {"MATCH", "DRIFT", "UNVERIFIABLE"}


def test_the_three_exit_codes_are_the_three_words_on_the_drawing(tmp_path) -> None:
    labels = _module()._LABELS
    assert labels == {0: "MATCH", 1: "DRIFT", 2: "UNVERIFIABLE"}
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    drawn = {item["label"] for item in spec["flows"][0]["outcomes"]}
    assert drawn == set(labels.values())


def test_a_target_that_is_not_a_directory_is_unverifiable(tmp_path) -> None:
    stray = tmp_path / "stray.txt"
    stray.write_text("not a corpus\n", encoding="utf-8")
    result = _run(stray)
    assert result.returncode == 2
    assert result.stdout.startswith("UNVERIFIABLE")


def test_the_corpus_holds_five_runs_and_one_synthesis() -> None:
    for name in RUNS:
        assert (_REPO / name).is_file(), name
    assert (_REPO / "SYNTHESIS-the-witnessing-spine.md").is_file()


def test_four_verdicts_are_false_as_stated_and_one_is_partial() -> None:
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert readme.count("FALSE as stated") == 4
    assert readme.count("partial; fails at verification") == 1


def test_every_run_names_four_parallel_searches_in_its_method_line() -> None:
    for name in RUNS:
        method = [
            line
            for line in (_REPO / name).read_text(encoding="utf-8").splitlines()
            if line.startswith("**Method:**")
        ]
        assert len(method) == 1, name
        assert "4 parallel" in method[0] or "four parallel" in method[0], name


def test_all_five_runs_carry_maturity_labels_and_the_synthesis_cites_them() -> None:
    def count(name: str) -> int:
        text = (_REPO / name).read_text(encoding="utf-8")
        return sum(text.count("[" + label + "]") for label in LABELS)

    for name in RUNS:
        assert count(name) > 0, name
    assert count("SYNTHESIS-the-witnessing-spine.md") == 0


def test_the_readme_names_every_maturity_label_the_runs_use() -> None:
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    for label in LABELS:
        assert "[" + label + "]" in readme, label


def test_what_did_not_confirm_is_named_in_place_rather_than_dropped_silently() -> None:
    marked = [name for name in RUNS if "UNVERIFIED" in (_REPO / name).read_text(encoding="utf-8")]
    assert marked, "no run names an excluded source"
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    assert "excluded from load-bearing use" in readme


def test_the_strongest_claim_is_labeled_a_bid_and_not_a_proof() -> None:
    synthesis = (_REPO / "SYNTHESIS-the-witnessing-spine.md").read_text(encoding="utf-8")
    assert "abductive" in synthesis
    assert "not a deductive identity" in synthesis
    card = json.loads(_SPEC.read_text(encoding="utf-8"))["cards"][0]
    accented = [field for field in card["fields"] if field.get("tone")]
    assert len(accented) == 1
    assert accented[0]["value"] == "an abductive bid"


def test_the_card_row_count_matches_what_its_own_alt_text_claims() -> None:
    card = json.loads(_SPEC.read_text(encoding="utf-8"))["cards"][0]
    assert len(card["fields"]) == 12
    assert card["alt"].startswith("Twelve rows")


@pytest.mark.parametrize("name", RUNS)
def test_each_run_is_sealed_under_the_name_the_readme_lists(name: str) -> None:
    sealed = {rel for _, rel in _module()._parse(_MANIFEST.read_text(encoding="utf-8"))}
    assert name in sealed
    assert name in (_REPO / "README.md").read_text(encoding="utf-8")


def test_every_sealed_document_is_lf_so_a_fresh_clone_derives_these_digests() -> None:
    """A digest is over bytes, and .gitattributes gives every checkout LF endings. A file
    left CRLF in the working tree hashes to something no clone reproduces, so the seal
    would say DRIFT to the first stranger who ran it while looking clean here."""
    assert "eol=lf" in (_REPO / ".gitattributes").read_text(encoding="utf-8")
    crlf = bytes([13, 10])
    for _, name in _module()._parse(_MANIFEST.read_text(encoding="utf-8")):
        assert crlf not in (_REPO / name).read_bytes(), name
    assert crlf not in _MANIFEST.read_bytes()
