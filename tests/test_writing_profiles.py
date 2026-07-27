import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import writing_profiles as WP  # noqa: E402


def test_every_profile_has_every_schema_field():
    for name, rec in WP.PROFILES.items():
        missing = [f for f in WP.SCHEMA_FIELDS if f not in rec]
        assert missing == [], f"{name} missing {missing}"


def test_slop_and_rigor_values_are_from_the_allowed_sets():
    for name, rec in WP.PROFILES.items():
        assert rec["slop"] in ("strict", "flavored", "off"), name
        assert rec["rigor"] in (
            "informal", "calibrated", "normative", "structured", "exact"), name


def test_load_returns_a_copy_not_the_original():
    a = WP.load("research")
    a["slop"] = "MUTATED"
    assert WP.load("research")["slop"] != "MUTATED"


def test_load_unknown_profile_is_a_named_error():
    with pytest.raises(WP.ProfileError):
        WP.load("no-such-profile")


def test_path_rules_map_known_extensions():
    assert WP.profile_for("paper.tex") == "proof"
    assert WP.profile_for("Paper.TEX") == "proof"
    assert WP.profile_for("x/y.lean") == "proof"
    assert WP.profile_for("CHANGELOG.md") == "changelog"
    assert WP.profile_for("docs/CHANGELOG") == "changelog"
    assert WP.profile_for("RELEASE_NOTES.md") == "release-notes"
    assert WP.profile_for("release/MODEL_CARD.md") == "model-card"
    assert WP.profile_for("src/README.md") == "readme"
    assert WP.profile_for(".git/COMMIT_EDITMSG") == "commit"
    assert WP.profile_for("project/specs/wire.md") == "normative-spec"
    assert WP.profile_for("essays/two-gates.md") == "narrative"
    assert WP.profile_for("papers/uplift.md") == "research"
    assert WP.profile_for("legal/terms.md") == "legal"
    # Boundary: a name that merely CONTAINS a keyword is not that kind of file.
    assert WP.profile_for("notCHANGELOG.md") == WP.DEFAULT
    assert WP.profile_for("unreleased_notes.md") == WP.DEFAULT
    assert WP.profile_for("anything-unmapped.md") == WP.DEFAULT


def test_the_starter_library_covers_the_spec_profiles():
    for name in ("procedure", "error-message", "commit", "changelog",
                 "release-notes", "api-docs", "normative-spec", "research",
                 "proof", "model-card", "readme", "legal", "social", "chat",
                 "narrative"):
        assert name in WP.PROFILES, name


def test_only_narrative_turns_the_linter_off():
    off = [n for n, r in WP.PROFILES.items() if r["slop"] == "off"]
    assert off == ["narrative"], off


def test_the_default_profile_exists_and_loads():
    # profile_for falls back to DEFAULT, and the CLI then calls load(DEFAULT).
    # If DEFAULT names no record, every unmapped file crashes the linter.
    assert WP.DEFAULT in WP.PROFILES
    assert WP.load(WP.DEFAULT)["slop"] == "flavored"


def test_every_profile_carries_register_provenance():
    # The Halliday grounding the module docstring invokes, as data.
    assert "register" in WP.SCHEMA_FIELDS
    for name, rec in WP.PROFILES.items():
        reg = rec["register"]
        assert set(reg) == {"field", "tenor", "mode"}, name
        assert all(isinstance(v, str) and v for v in reg.values()), name


def test_backslash_paths_resolve_like_forward_ones():
    assert WP.profile_for("docs\\CHANGELOG.md") == "changelog"
    assert WP.profile_for("papers\\uplift.md") == "research"
