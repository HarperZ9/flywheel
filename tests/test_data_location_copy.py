"""I11: copy says exactly where data goes (design 7.13, FW-14).

A surface may not say "your data stays on your machine" without saying that
request content goes to the provider the owner picks, and may not call a
deletion "GDPR-style" or "GDPR erasure". The check normalizes whitespace, so
a phrase wrapped across a line break is found. A shipped sentence may stay
when a dated `Correction, <date>:` line follows it within ten lines.
"""
from pathlib import Path
import importlib.util
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_data_location_copy", ROOT / "scripts" / "check_data_location_copy.py")
copy = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = copy  # dataclasses resolve their module by name
_SPEC.loader.exec_module(copy)

# The opening shipped in the 1.0.4 notes, wrapped where the file wraps it.
SHIPPED_104 = ("A self-hostable, model-agnostic AI workstation and coding harness. "
               "Flywheel runs a task\nwith any model, frontier or local, behind one "
               "OpenAI-compatible surface, and your keys and\ndata stay on your "
               "machine. An answer is accepted only when a real check passes.\n")
SHIPPED_README = ("Flywheel runs any model, frontier or local, behind a single "
                  "OpenAI-compatible\nsurface, and your keys and data stay on your "
                  "machine. Its desktop assistant,\n")


def _violations(text, name="README.md"):
    return copy.violations_in(text, name)


def test_the_shipped_openings_are_flagged_including_the_wrapped_one():
    assert [v.rule for v in _violations(SHIPPED_104)] == ["data_location"]
    assert [v.rule for v in _violations(SHIPPED_README)] == ["data_location"]
    assert _violations(SHIPPED_104)[0].line == 3


def test_gdpr_wording_for_a_deletion_is_flagged():
    for phrase in ("forget erases the text for GDPR-style deletion",
                   "a GDPR erasure of the row", "GDPR style deletion"):
        assert [v.rule for v in _violations(phrase + "\n")] == ["gdpr"], phrase


def test_other_unqualified_forms_are_flagged():
    for phrase in ("Your data stays on your computer.",
                   "your prompts never leave your machine",
                   "Your data stays local."):
        assert _violations(phrase + "\n"), phrase


def test_a_dated_correction_within_ten_lines_lets_the_shipped_text_stay():
    corrected = SHIPPED_104 + "\n" * 3 + (
        "Correction, 2026-09-26: keys and Flywheel's records stay on your machine. "
        "The content of each request goes to the hosted provider you route it to.\n")
    assert _violations(corrected) == []
    too_far = SHIPPED_104 + "\n" * 11 + "Correction, 2026-09-26: see above.\n"
    assert [v.rule for v in _violations(too_far)] == ["data_location"]
    undated = SHIPPED_104 + "Correction: keys stay local.\n"
    assert [v.rule for v in _violations(undated)] == ["data_location"]


def test_the_qualified_sentence_passes():
    qualified = ("Your provider keys and Flywheel's records stay on your machine. The "
                 "content of each request, including files and tool output the agent "
                 "reads, goes to the model provider you pick, under that provider's "
                 "terms. With a local model it stays on your machine.\n")
    assert _violations(qualified) == []


def test_an_allowlisted_local_model_sentence_passes_only_where_it_is_listed():
    path, sentence = next(iter(copy.ALLOWED))
    assert _violations(sentence + "\n", path) == []
    assert _violations(sentence + "\n", "README.md") != []


def test_the_repository_surfaces_pass_and_keep_the_shipped_sentences():
    found = copy.scan(ROOT)
    assert found == [], "\n".join(v.render() for v in found)
    for notes in ("RELEASE-NOTES-1.0.3.md", "RELEASE-NOTES-1.0.4.md"):
        text = " ".join((ROOT / notes).read_text(encoding="utf-8").split())
        assert "your keys and data stay on your machine" in text, notes
        assert "Correction, 2026-09-26:" in text, notes


def test_the_scan_covers_every_surface_the_design_names():
    names = {p.relative_to(ROOT).as_posix() for p in copy.surfaces(ROOT)}
    assert "README.md" in names and "RELEASE-NOTES-1.0.4.md" in names
    assert "docs/features/flywheel-lane-mneme.md" in names
    assert any(n.startswith("harness/") and n.endswith(".py") for n in names)
    assert any(n.startswith("desktop/lib/") and n.endswith(".dart") for n in names)
    assert "site/index.html" in names


def test_the_script_exits_nonzero_on_a_violation(tmp_path):
    (tmp_path / "README.md").write_text(SHIPPED_README, encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" /
                             "check_data_location_copy.py"), "--root", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "README.md:2" in result.stdout


QUALIFIED_README = ("Flywheel runs any model, frontier or local, behind a single "
                    "OpenAI-compatible\nsurface. Flywheel's records stay on your machine, "
                    "and your provider keys are\nstored only there and sent only to their "
                    "own provider. The content of each\nrequest goes to the model provider "
                    "you pick, under that provider's terms.\n")


def test_a_local_claim_passes_only_with_the_provider_qualifier_nearby():
    """Red test for the qualifier: the README opening passes with its
    provider sentence and fails once that sentence is deleted."""
    assert _violations(QUALIFIED_README) == []
    stripped = QUALIFIED_README.split(" The content of each")[0] + "\n"
    assert [v.rule for v in _violations(stripped)] == ["unqualified_local"]
    for phrase in ("Records stay on your machine.", "Nothing leaves your machine.",
                   "Your history never leaves your computer."):
        assert [v.rule for v in _violations(phrase + "\n")] == ["unqualified_local"], phrase


def test_a_local_model_sentence_is_not_a_claim_about_hosted_providers():
    assert _violations("With a local model, the request content stays on your machine.\n") \
        == []


def test_a_correction_must_name_where_content_goes():
    unrelated = SHIPPED_104 + "Correction, 2026-09-26: a typo in the install line.\n"
    assert [v.rule for v in _violations(unrelated)] == ["data_location"]


def test_the_desktop_docs_are_surfaces_too():
    names = {p.relative_to(ROOT).as_posix() for p in copy.surfaces(ROOT)}
    assert "desktop/docs/MOBILE-SETUP.md" in names
