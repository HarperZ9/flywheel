"""The 2.0 schema page is generated, and the migration note names what exists.

docs/MIGRATING-2.0-SCHEMAS.md is written by scripts/gen_migration_tables.py.
A hand edit, or a change to its sources with no regeneration, fails here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gen_migration_tables as G  # noqa: E402


def _receipt(**kw):
    from tests.test_receipt_v2 import _r
    return _r(**kw)


def test_the_schema_page_matches_its_sources():
    assert G.PAGE.read_text(encoding="utf-8").replace("\r\n", "\n") == G.render()
    assert G.main(["--check"]) == 0


def test_a_stale_page_fails_the_check(tmp_path, monkeypatch, capsys):
    stale = tmp_path / "page.md"
    stale.write_text(G.render().replace("PREDICATE_EXACT", "PREDICATE_EXACTLY"), encoding="utf-8")
    monkeypatch.setattr(G, "PAGE", stale)
    monkeypatch.setattr(G, "ROOT", tmp_path)
    assert G.main(["--check"]) == 1
    assert "stale" in capsys.readouterr().out


def test_the_code_pairs_are_the_codes_the_receipt_emits():
    from harness.receipt import V4_SCHEMA
    from harness.receipt_scope import derived_scope, legacy_limits
    pairs = G.code_pairs()
    assert len(pairs) == 15
    assert ("NOT_PROVES_EXACTNESS", "PREDICATE_EXACT") in pairs
    old_codes, new_codes = {a for a, _ in pairs}, {b for _, b in pairs}
    for receipt in (_receipt(), _receipt(base_weights_digest="sha256:" + "1" * 64),
                    _receipt(executes_candidate_code=True)):
        assert set(derived_scope(receipt)) <= new_codes
        assert set(legacy_limits(_receipt(schema=V4_SCHEMA))) <= old_codes


def test_a_conditional_pair_is_present_on_opposite_sides():
    """NOT_PROVES_WHICH_WEIGHTS was present when no weights digest was pinned;
    WEIGHTS_PINNED is present when one is. The table pairs them by position,
    so this checks the position rule on a pair with a known meaning."""
    from harness.receipt_scope import derived_scope, legacy_limits
    bare, pinned = _receipt(), _receipt(base_weights_digest="sha256:" + "1" * 64)
    assert "NOT_PROVES_WHICH_WEIGHTS" in legacy_limits(bare)
    assert "WEIGHTS_PINNED" not in derived_scope(bare)
    assert "NOT_PROVES_WHICH_WEIGHTS" not in legacy_limits(pinned)
    assert "WEIGHTS_PINNED" in derived_scope(pinned)


def test_every_version_move_in_the_checklist_is_on_the_page():
    rows = G.schema_rows()
    moved, bare, same = G.sort_rows(rows)
    assert len(moved) == 158 and len(bare) == 32 and len(same) == 3
    page = G.render()
    assert all(f"| {name} | {change} |" in page for _g, name, change in moved)
    assert "| flywheel.receipt | v4 to v5 |" in page


def test_the_note_names_schemas_and_settings_the_code_has():
    from harness import oracle_qa, receipt, receipt_operations, receipt_route, token_usage
    note = (ROOT / "docs" / "MIGRATING-2.0.md").read_text(encoding="utf-8")
    for name in (receipt.SCHEMA, receipt.V4_SCHEMA, receipt_route.ROUTED_SCHEMA,
                 oracle_qa.SCHEMA, receipt_operations.SCHEMA, token_usage.ESTIMATE_FIELD,
                 "schema_or_scope", "BOUND_FROM_SUBMITTED_OBJECT",
                 "FLYWHEEL_WORKSPACE_WRITES=0", "FLYWHEEL_STREAM=0",
                 "FLYWHEEL_NATIVE_TOOLS=0", "FLYWHEEL_PROMPT_CACHE=0"):
        assert name in note, name
    assert "## What you need to do" in note and "Draft." not in note
    assert note.index("## What you need to do") < note.index("## Records:")
