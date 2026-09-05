"""What a lean environment string binds, and what it only claims.

`lean4:v4.9.0+mathlib:2026-08-01` makes two claims. The version half was always
compared against the toolchain that answered. The library half was carried into
the workstream identity and believed, which is the more expensive half to get
wrong: two proofs of one statement under different Mathlib revisions are two
different results.

  1. BOTH HALVES BIND BY ONE RULE. Named and confirmed passes, named and
     unreported is unverifiable, named and contradicted is unverifiable.
  2. AN UNBOUND LIBRARY IS NEVER A REFUTATION. Nothing about the statement is
     settled by a manifest we could not read.
  3. THE MANIFEST PATH COMES FROM THE ENVIRONMENT, NEVER THE DECLARATION. A
     path read out of a document a stranger wrote is a file-read surface.
  4. A MANIFEST WE CANNOT PARSE IS NO MANIFEST. It tells us nothing about what
     was on the library path, so it cannot confirm a pin.
"""
import json

import pytest

from harness.workstream_lean import (
    _lean_environment, _one_library, _pinned_libraries, manifest_path,
    manifest_revisions,
)

MATHLIB_SHA = "b5eba595428809e96f3ed113bc7ba776c5f801ac"


def _manifest(tmp_path, packages):
    path = tmp_path / "lake-manifest.json"
    path.write_text(json.dumps({"version": "1.1.0", "packages": packages}),
                    encoding="utf-8")
    return path


def test_a_library_pin_is_read_out_of_the_environment_and_lean_is_not_one():
    assert _pinned_libraries("lean4:v4.9.0+mathlib:2026-08-01") == [
        ("mathlib", "2026-08-01")]
    assert _pinned_libraries("lean4:v4.9.0+mathlib:a+batteries:b") == [
        ("mathlib", "a"), ("batteries", "b")]
    assert _pinned_libraries("lean4:v4.9.0") == []
    assert _pinned_libraries("lean:4.9.0") == []
    assert _pinned_libraries("") == []


@pytest.mark.parametrize("environment", [
    "prove2me:mission-7",
    "cfr:2026-title21",
    "mhs:plate-reader-3/driver-2.1.0",
    "assay:hplc-2/cal-2026-08-30",
])
def test_an_environment_that_does_not_compose_pins_no_library(environment):
    # Only a +-joined environment declares parts. Reading every colon anywhere
    # as a revision claim would turn most of this repository's environments
    # unverifiable for saying nothing about Lean in the first place.
    assert _pinned_libraries(environment) == []
    matched, _ = _lean_environment(environment, "Lean (version 4.33.1)", None)
    assert matched is True


def test_a_manifest_lists_every_revision_a_library_answers_to(tmp_path):
    path = _manifest(tmp_path, [
        {"name": "mathlib", "rev": MATHLIB_SHA, "inputRev": "v4.9.0"},
        {"name": "batteries", "rev": "aaaa1111bbbb2222"},
    ])
    revisions = manifest_revisions(path)
    assert revisions == {
        "mathlib": (MATHLIB_SHA, "v4.9.0"),
        "batteries": ("aaaa1111bbbb2222",),
    }


def test_no_manifest_and_an_unreadable_manifest_read_the_same_way(tmp_path):
    # None means nothing to read against. It is deliberately not {}, which would
    # say the path was read and carried no such library.
    assert manifest_revisions(tmp_path / "absent.json") is None
    broken = tmp_path / "lake-manifest.json"
    broken.write_text("{not json", encoding="utf-8")
    assert manifest_revisions(broken) is None
    shapeless = tmp_path / "shapeless.json"
    shapeless.write_text(json.dumps({"packages": "mathlib"}), encoding="utf-8")
    assert manifest_revisions(shapeless) is None
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"version": "1.1.0"}), encoding="utf-8")
    assert manifest_revisions(empty) is None


def test_the_manifest_is_found_by_the_environment_or_the_working_directory(
        tmp_path, monkeypatch):
    named = _manifest(tmp_path, [{"name": "mathlib", "rev": MATHLIB_SHA}])
    monkeypatch.setenv("FLYWHEEL_LEAN_MANIFEST", str(named))
    assert manifest_path() == named
    monkeypatch.setenv("FLYWHEEL_LEAN_MANIFEST", str(tmp_path / "gone.json"))
    assert manifest_path() is None
    monkeypatch.delenv("FLYWHEEL_LEAN_MANIFEST")
    monkeypatch.chdir(tmp_path)
    assert manifest_path() == tmp_path / "lake-manifest.json"


@pytest.mark.parametrize("pinned, bound, fragment", [
    (MATHLIB_SHA, True, "mathlib"),
    ("v4.9.0", True, "mathlib v4.9.0"),
    (MATHLIB_SHA[:7], True, "mathlib"),
    (MATHLIB_SHA[:12], True, "mathlib"),
    ("b5eba", False, "the manifest has"),
    ("2026-08-01", False, "the manifest has"),
])
def test_a_pin_matches_a_revision_a_full_sha_or_a_short_sha(pinned, bound, fragment):
    revisions = {"mathlib": (MATHLIB_SHA, "v4.9.0")}
    got, note = _one_library("mathlib", pinned, revisions)
    assert got is bound
    assert fragment in note


def test_a_library_the_manifest_does_not_list_is_told_apart_from_no_manifest():
    absent, note = _one_library("mathlib", "v4.9.0", {"batteries": ("x",)})
    assert absent is False
    assert "lists no such library" in note
    nothing, note = _one_library("mathlib", "v4.9.0", None)
    assert nothing is False
    assert "no lake manifest was discoverable" in note


def test_the_note_carries_both_halves_when_both_bind():
    matched, note = _lean_environment(
        "lean4:v4.9.0+mathlib:v4.9.0", "Lean (version 4.9.0)",
        {"mathlib": (MATHLIB_SHA, "v4.9.0")})
    assert matched is True
    assert "lean 4.9.0" in note
    assert "mathlib v4.9.0" in note


def test_a_library_that_does_not_bind_fails_the_whole_environment():
    # The version half matched. A note reading "matching the pinned environment"
    # on its own would be a receipt saying more than was checked.
    matched, note = _lean_environment(
        "lean4:v4.9.0+mathlib:2026-08-01", "Lean (version 4.9.0)", None)
    assert matched is False
    assert "matching the pinned" not in note
    assert "mathlib" in note


def test_the_version_half_is_decided_before_any_library_is_read():
    matched, note = _lean_environment(
        "lean4:v4.9.0+mathlib:v4.9.0", "Lean (version 4.33.1)",
        {"mathlib": ("v4.9.0",)})
    assert matched is False
    assert "ran on 4.33.1" in note


def test_an_environment_naming_no_library_binds_on_the_version_alone():
    matched, note = _lean_environment("lean4:v4.9.0", "Lean (version 4.9.0)", None)
    assert matched is True
    assert "matching the pinned" in note


def test_every_pinned_library_must_bind_not_just_the_first():
    revisions = {"mathlib": ("v4.9.0",)}
    matched, note = _lean_environment(
        "lean4:v4.9.0+mathlib:v4.9.0+batteries:v0.0.1",
        "Lean (version 4.9.0)", revisions)
    assert matched is False
    assert "batteries" in note
