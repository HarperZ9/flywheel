"""The README's drawings are rendered from a spec, so they rot like any other derived
file: a rule moves, nobody re-renders, and the picture describes something that stopped
being true. The art gate re-renders every drawing and compares bytes. This runs it under
pytest, so a stale drawing fails the suite rather than waiting for somebody to look.

Whether a drawing is TRUE of the corpus is a different question, and the file next door
answers it by reading the sealed documents and running the checker."""

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "witnessing-spine.art.json"

GATES = (
    "spec.present",
    "art.matches_spec",
    "art.render_is_deterministic",
    "art.identity_per_repository",
    "art.seed_is_recorded",
    "art.no_local_paths_or_em_dashes",
    "art.spec_words_reach_the_drawing",
    "art.note_survives_the_wrapper",
    "art.return_edge_stays_on_its_row",
    "art.every_illustration_is_shown",
    "art.tagline_stays_inside_its_rule",
    "art.outcome_fits_its_box",
    "art.card_draws_shapes_not_digits",
    "art.card_text_fits_its_column",
    "art.card_widths_bound_every_face",
    "art.card_draws_measured_characters",
    "art.card_carries_one_mark",
    "art.card_alt_reaches_the_readme",
    "art.the_gate_can_fail",
)

DRAWINGS = (
    "docs/art/witnessing-spine-header.svg",
    "docs/art/seal-lane.svg",
    "docs/art/steelman-lane.svg",
    "docs/art/corpus-table.svg",
)


def _receipt() -> dict:
    result = subprocess.run(
        [sys.executable, str(_GATE), "--json"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_the_art_gate_passes_every_check_it_names() -> None:
    receipt = _receipt()
    assert receipt["schema"] == "witnessing-spine.repo-art/v1"
    assert tuple(check["name"] for check in receipt["checks"]) == GATES
    assert [check["name"] for check in receipt["checks"] if not check["passed"]] == []


def test_every_drawing_is_committed_and_reaches_the_page() -> None:
    receipt = _receipt()
    assert {output["file"] for output in receipt["outputs"]} == set(DRAWINGS)
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    front = readme
    # The previous header left the README on 4 October 2026 and is recorded in the brand notes;
    # a page here is the README or a doc under docs/, the same set tools/check_repo_art.py uses.
    readme += "".join(q.read_text(encoding="utf-8") for q in sorted((_REPO / "docs").rglob("*.md")))
    for drawing in DRAWINGS:
        assert (_REPO / drawing).is_file(), drawing
        assert drawing in readme, drawing
    for hero in ("docs/art/hero-dark.svg", "docs/art/hero-light.svg"):
        assert (_REPO / hero).is_file() and hero in front, hero


def test_the_alt_text_in_the_readme_is_the_alt_text_in_the_spec() -> None:
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    for item in spec["flows"] + spec["cards"]:
        assert "![" + item["alt"] + "](docs/art/" + item["file"] + ")" in readme
