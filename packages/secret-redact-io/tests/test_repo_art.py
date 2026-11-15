"""The README's diagrams are generated from a spec, so they can go stale the way any
other derived file goes stale: somebody edits a stage name, nobody re-renders, and the
picture describes a version of secret-redact-io that no longer exists. The gate
re-renders from the spec and compares bytes. This runs the gate under pytest and asserts
on its receipt, so a drifted drawing fails the suite instead of quietly shipping."""

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"
_SPEC = _REPO / "docs" / "art" / "secret-redact-io.art.json"

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
    "docs/art/secret-redact-io-header.svg",
    "docs/art/guarded-lane.svg",
    "docs/art/blind-spots-lane.svg",
    "docs/art/receipt-fields.svg",
)


def _receipt() -> dict:
    out = subprocess.run([sys.executable, str(_GATE), "--json"],
                         cwd=_REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "secret-redact-io.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_mark_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/secret-redact-io.art.json"]
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
    spec = json.loads(_SPEC.read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "secret-redact-io.art.json").write_text(json.dumps(spec),
                                                        encoding="utf-8")
    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1


# docs/art/receipt-fields.svg draws the nine keys a receipt comes back with and
# says, per key, whether it holds a hash, a count, a name, a clock stamp, or
# whatever the caller handed over. That is a claim about receipts.py and the
# four call sites, not about the picture, so nothing under tools/ can settle it.
# Each row below is driven against a real receipt.

from secret_redact_io.exec_io import run_guarded  # noqa: E402
from secret_redact_io.fetch_io import fetch_guarded  # noqa: E402
from secret_redact_io.file_io import (  # noqa: E402
    read_text_guarded,
    write_text_guarded,
)
from secret_redact_io.receipts import GuardrailReceipt  # noqa: E402
from secret_redact_io.redaction import GuardrailPolicy  # noqa: E402

LEAK = "sk-" + "a1b2c3d4" * 5


def _card() -> dict:
    spec = json.loads(_SPEC.read_text("utf-8"))
    return next(c for c in spec["cards"] if c["file"] == "receipt-fields.svg")


def _seeded(tmp_path: Path) -> Path:
    """A file holding one secret, written byte for byte so the length a receipt
    reports can be checked against the source rather than against the
    platform's idea of a line ending."""
    source = tmp_path / "seeded.txt"
    source.write_text(f"token={LEAK}\n", encoding="utf-8", newline="")
    return source


def _live(tmp_path: Path) -> dict:
    return read_text_guarded(_seeded(tmp_path)).receipt.to_dict()


def test_the_card_draws_the_keys_a_receipt_actually_comes_back_with(tmp_path):
    """A key drawn that a receipt does not carry, or one carried and not drawn,
    makes the picture a description of a different tool."""
    drawn = [f["key"] for f in _card()["fields"]]
    assert drawn == list(_live(tmp_path))


def test_no_part_of_the_secret_survives_into_the_receipt(tmp_path):
    """The whole claim of the drawing is that a receipt is hashes, counts and
    names. Serialize one built over a real secret and look for the secret."""
    receipt = read_text_guarded(_seeded(tmp_path)).receipt
    assert LEAK not in receipt.to_json()
    assert receipt.redactions == {"openai_api_key": 1}


def test_the_two_digest_rows_are_over_the_bytes_on_either_side(tmp_path):
    """Drawn DIGEST, one before any rule ran and one after. Re-running the same
    policy over the same input has to reproduce the second, or the row is
    claiming a reproducibility the tool does not have."""
    source = _seeded(tmp_path)
    first = read_text_guarded(source).receipt
    second = read_text_guarded(source).receipt
    assert first.input_sha256 == second.input_sha256
    assert first.redacted_sha256 == second.redacted_sha256
    assert first.input_sha256 != first.redacted_sha256


def test_the_count_rows_are_lengths_and_a_tally_of_rule_names(tmp_path):
    """Drawn COUNT. raw_bytes and redacted_bytes are lengths of the two texts,
    and they part company once a replacement is a different size than what it
    replaced. redactions names rules, never what they matched."""
    result = read_text_guarded(_seeded(tmp_path))
    receipt = result.receipt
    assert receipt.raw_bytes == len(f"token={LEAK}\n".encode("utf-8"))
    assert receipt.redacted_bytes == len(result.text.encode("utf-8"))
    assert receipt.raw_bytes != receipt.redacted_bytes
    assert set(receipt.redactions) <= {
        rule.name for rule in GuardrailPolicy.default().rules}


def test_the_operation_row_names_the_path_that_built_the_receipt(tmp_path):
    """Drawn NAME, and drawn as one of five. A sixth operation reaching a
    receipt would make the row an incomplete list rather than a wrong one, so
    it is worth failing on."""
    seen = {
        read_text_guarded(_seeded(tmp_path)).receipt.operation,
        write_text_guarded(tmp_path / "out.txt", "hello").receipt.operation,
        write_text_guarded(tmp_path / "dry.txt", "hello",
                           dry_run=True).receipt.operation,
        run_guarded([sys.executable, "-c", "print('hello')"]).receipt.operation,
    }
    assert seen == {"read", "write", "write.dry_run", "exec"}


def test_the_target_row_is_trimmed_before_it_is_written(tmp_path):
    """Drawn NAME, with the claim that arguments and query strings are dropped
    before the field is set. An exec keeps the program's base name only, so the
    secret passed as an argument cannot reach the receipt through target."""
    receipt = run_guarded([sys.executable, "-c", f"print({LEAK!r})"]).receipt
    assert receipt.target == Path(sys.executable).name
    assert LEAK not in receipt.target


def test_a_query_string_never_reaches_the_target_field():
    """The other half of the target row, and the reason fetch is drawn beside
    exec. The field is built from the scheme, host and path, so a token carried
    in a query string is gone before the receipt exists."""
    source = Path(_module_of(fetch_guarded)).read_text(encoding="utf-8")
    assert 'target=f"{parsed.scheme}://{parsed.netloc}{parsed.path}"' in source
    assert "parsed.query" not in source


def _module_of(function) -> str:
    return sys.modules[function.__module__].__file__


def test_the_marked_row_is_the_one_nothing_redacts():
    """The accent claims metadata is the one field a secret can be written
    into. Nothing between create and the serialized receipt touches it, and no
    other row is marked, so the mark has to sit there and nowhere else."""
    marked = [f["key"] for f in _card()["fields"]
              if f.get("tone", "none") != "none"]
    assert marked == ["metadata"]
    receipt = GuardrailReceipt.create(
        operation="read", target="notes.txt", raw_bytes=b"",
        redacted_text="", redactions={}, metadata={"note": LEAK})
    assert receipt.metadata == {"note": LEAK}
    assert LEAK in receipt.to_json()


def test_the_four_shipped_call_sites_keep_metadata_to_counts_and_status(tmp_path):
    """The mark is on what the field allows, not on what this package does with
    it. Every path that ships puts a count, a flag or a status there, and the
    footnote would be alarmist if one of them started passing content."""
    metadata = [
        read_text_guarded(_seeded(tmp_path)).receipt.metadata,
        write_text_guarded(tmp_path / "out.txt", "hello").receipt.metadata,
        run_guarded([sys.executable, "-c", "print(1)"]).receipt.metadata,
    ]
    assert metadata == [
        {"exists": True},
        {"written": True},
        {"argv_count": 3, "returncode": 0},
    ]
    for entry in metadata:
        assert all(isinstance(value, (bool, int)) for value in entry.values())


def test_a_guarded_write_persists_the_text_the_caller_was_handed(tmp_path):
    """The return edge in guarded-lane.svg says the write path puts the
    redacted text on disk. That is the one stage in the drawing that changes
    something outside the process, so it is worth reading back."""
    target = tmp_path / "written.txt"
    result = write_text_guarded(target, f"token={LEAK}\n")
    assert target.read_text(encoding="utf-8") == result.text
    assert LEAK not in target.read_text(encoding="utf-8")


def test_a_dry_run_writes_nothing_at_all(tmp_path):
    """The other half of that stage. A dry run reports what it would have
    written and leaves the path alone."""
    target = tmp_path / "absent.txt"
    receipt = write_text_guarded(target, f"token={LEAK}\n",
                                 dry_run=True).receipt
    assert not target.exists()
    assert receipt.metadata == {"written": False}


def test_the_rule_list_the_drawing_counts_is_the_rule_list_that_ships():
    """Both flows say seven, in a stage title and in a footnote. Adding an
    eighth rule is a good change that makes the pictures wrong, and this is
    what says so."""
    assert len(GuardrailPolicy.default().rules) == 7


def test_a_secret_shaped_like_prose_passes_through_untouched():
    """The honest edge blind-spots-lane.svg draws, and the outcome it labels
    unmatched. A credential with no shape to match survives the pass, and the
    receipt says only that no rule fired."""
    plain = "the door code is banana forty two"
    redacted = GuardrailPolicy.default().redact_text(plain)
    assert redacted.text == plain
    assert redacted.counts == {}
