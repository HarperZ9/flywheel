"""The README's diagrams are generated from a spec, so they can go stale the way any
other derived file goes stale: somebody edits a stage name, nobody re-renders, and the
picture describes a version of plexus that no longer exists. The gate re-renders from
the spec and compares bytes. This runs the gate under pytest and asserts on its receipt,
so a drifted drawing fails the suite instead of quietly shipping."""

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"

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
    "docs/art/plexus-header.svg",
    "docs/art/wiring-lane.svg",
    "docs/art/honesty-lane.svg",
    "docs/art/edge-evidence.svg",
)


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "plexus.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_mark_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/plexus.art.json"]
    drawn = {out["file"]: out for out in receipt["outputs"]}
    assert set(drawn) == set(DRAWINGS)
    for path, out in drawn.items():
        assert len(out["sha256"]) == 64, path
        assert out["bytes"] > 0, path


def test_a_gate_that_cannot_fail_is_not_a_gate(tmp_path, monkeypatch):
    """Point the outcome-box check at a note too wide for its box and it has to
    complain. Without this, a green suite proves only that the gate ran."""
    sys.path.insert(0, str(_REPO / "tools"))
    import check_repo_art as gate
    spec = json.loads((_REPO / "docs" / "art" / "plexus.art.json").read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "plexus.art.json").write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# docs/art/edge-evidence.svg draws the six keys plexus discover returns for one
# wiring edge and says, per key, whether discovery settled it or copied it. That
# is a claim about mesh.py and cli.py, not about the picture, so nothing in
# tools/ can settle it. Each row below is driven against a real mesh.
sys.path.insert(0, str(_REPO / "src"))

from plexus.cli import _mesh_json  # noqa: E402
from plexus.manifest import Manifest, Port  # noqa: E402
from plexus.mesh import Edge, discover  # noqa: E402
from plexus.registry import builtin_manifests  # noqa: E402


def _card() -> dict:
    spec = json.loads(
        (_REPO / "docs" / "art" / "plexus.art.json").read_text("utf-8"))
    return next(c for c in spec["cards"] if c["file"] == "edge-evidence.svg")


def _live() -> dict:
    return _mesh_json(discover(builtin_manifests()))


def test_the_card_draws_the_keys_an_edge_actually_comes_back_with():
    """A key drawn that discover does not return, or one returned and not
    drawn, makes the picture a description of a different tool."""
    drawn = [f["key"] for f in _card()["fields"]]
    returned = list(_live()["edges"][0])
    assert drawn == returned


def test_evidence_is_the_constant_the_card_says_it_is():
    assert {e["evidence"] for e in _live()["edges"]} == {"declared"}


def test_self_loop_is_computed_from_the_two_ends_and_kept():
    """Drawn COMPUTED, and drawn as reported rather than dropped, so both
    halves of that row need something that reaches them."""
    edges = _live()["edges"]
    assert all(e["self_loop"] == (e["producer"] == e["consumer"])
               for e in edges)
    assert any(e["self_loop"] for e in edges), "no self loop survived to check"


def test_via_is_carried_through_without_being_read():
    """Drawn COPIED. Point a producer's module at a path that is not in the
    repository at all and the edge still forms, carrying that string as it was
    written. Nothing between the manifest and the receipt opens it."""
    nowhere = "src/does_not_exist.py:never_defined"
    assert not (_REPO / "src" / "does_not_exist.py").exists()
    pair = [
        Manifest(organ="a", emits=[Port(capability="c/1", module=nowhere)]),
        Manifest(organ="b", consumes=[Port(capability="c/1", module="b.py:f")]),
    ]
    edge = _mesh_json(discover(pair))["edges"][0]
    assert edge["via"] == nowhere
    assert edge["evidence"] == "declared"


def test_the_marked_row_is_the_one_that_looks_like_a_citation():
    """The accent claims via is the field a reader would take for proof. The
    other five are drawn as settled, so the mark has to sit on via and the
    accented row has to be the one the footnote is about."""
    marked = [f["key"] for f in _card()["fields"]
              if f.get("tone", "none") != "none"]
    assert marked == ["via"]
    assert [f["value"] for f in _card()["fields"] if f["key"] == "via"] \
        == ["COPIED"]


def test_the_footnote_second_pointer_is_held_and_never_returned():
    """The footnote says the edge carries the consumer's own module too, and
    that discover holds it without serializing it. Both halves, because a field
    quietly added to the receipt would make the footnote wrong."""
    fields = {f.name for f in dataclasses.fields(Edge)}
    assert "consumer_module" in fields
    assert "consumer_module" not in _live()["edges"][0]
    pair = [
        Manifest(organ="a", emits=[Port(capability="c/1", module="a.py:g")]),
        Manifest(organ="b", consumes=[Port(capability="c/1", module="b.py:f")]),
    ]
    assert discover(pair).edges[0].consumer_module == "b.py:f"
