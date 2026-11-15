"""The front-page artwork, checked rather than eyeballed.

The drawings under docs/art/ are generated from docs/art/relay.art.json. These
tests run the gates in tools/check_repo_art.py and assert on the receipt they
emit, so a spec edited without re-rendering, a card note the wrapper silently
truncates, or an outcome label wider than its box is a red test rather than a
crooked picture nobody looked at.

The clause-ladder card gets a second layer below that. Those gates settle
whether the drawing fits its columns; whether the drawing is TRUE of the
contract module and of the verifier that ships inside a certificate is settled
against those two directly.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from relay import contract

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
    "docs/art/relay-header.svg",
    "docs/art/accountability-lane.svg",
    "docs/art/endpoint-ladder.svg",
    "docs/art/clause-ladder.svg",
)


def _receipt():
    done = subprocess.run([sys.executable, str(_GATE), "--json"],
                          cwd=str(_REPO), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr or done.stdout
    return json.loads(done.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "relay.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_header_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/relay.art.json"]
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

    spec = json.loads((_REPO / "docs" / "art" / "relay.art.json").read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "relay.art.json").write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# docs/art/clause-ladder.svg names every clause a contract may carry and says,
# for each one, whether the zero-dependency verifier vendored into a .rvc
# re-derives it. Both halves are claims about the code rather than about the
# picture, so nothing in tools/ can settle them.
IN_TREE = "in-tree verifier only"


def _card():
    spec = json.loads(
        (_REPO / "docs" / "art" / "relay.art.json").read_text("utf-8"))
    return next(c for c in spec["cards"] if c["file"] == "clause-ladder.svg")


def _vendored():
    """The standalone verifier, loaded from the file that ships in the .rvc.

    Loaded by path rather than imported, because the point of that file is
    that it runs with no relay on the machine at all.
    """
    spec = importlib.util.spec_from_file_location(
        "vendored_verify_cert", _REPO / "verify_cert.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chain(verifier, rows=3):
    """A short, well-formed hash chain the verifier accepts."""
    out, prev = [], verifier.GENESIS
    for seq in range(rows):
        row = {"seq": seq, "kind": "note", "content": f"step {seq}",
               "meta": {}, "prev_hash": prev}
        row["entry_hash"] = verifier._entry_hash(row)
        prev = row["entry_hash"]
        out.append(row)
    return out


def _cert(rows, clauses):
    return {"ledger_jsonl": "\n".join(json.dumps(r) for r in rows),
            "contract": {"clauses": clauses}}


def test_the_card_draws_every_clause_type_and_no_others():
    """A clause added to contract.py and not to the drawing fails here.

    Compared as a set, because the drawing groups the clauses that travel with
    the file ahead of the ones that do not, and CLAUSE_TYPES is in the order
    the module happens to declare them.
    """
    drawn = [f["key"] for f in _card()["fields"]]
    assert sorted(drawn) == sorted(contract.CLAUSE_TYPES)
    assert len(drawn) == len(set(drawn)), "a clause is drawn twice"


def test_each_row_says_what_the_vendored_verifier_actually_returns():
    verifier = _vendored()
    facts = {"check_trusted": True, "intent_critical": 0, "edited_paths": [],
             "approval_verdict": "GATED"}
    for field in _card()["fields"]:
        held, _why = verifier._clause_ok({"type": field["key"], "arg": []},
                                         facts)
        drawn_as_offline = field["value"] != IN_TREE
        assert (held is not None) == drawn_as_offline, field["key"]


def test_the_marked_row_is_the_clause_that_runs_before_the_contract():
    """The card accents one row, and the accent is a claim: chain_intact is
    re-derived whether or not a contract asks for it. Hand the verifier a
    certificate whose clause list is empty. An intact chain reaches ALLOW; the
    same certificate with one byte of content changed is REFUTED anyway."""
    assert [f["key"] for f in _card()["fields"]
            if f.get("tone", "none") != "none"] == ["chain_intact"]

    verifier = _vendored()
    rows = _chain(verifier)
    assert verifier.verify_cert(_cert(rows, []))[0] == "ALLOW"

    rows[1]["content"] = "step 1 as rewritten later"
    label, why = verifier.verify_cert(_cert(rows, []))
    assert label == "REFUTED", why
