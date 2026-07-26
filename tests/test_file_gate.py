import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_file_gate import over_gate, load_grandfathered  # noqa: E402


def test_over_gate_finds_a_long_file(tmp_path):
    (tmp_path / "long.py").write_text("x = 1\n" * 400, encoding="utf-8")
    (tmp_path / "short.py").write_text("x = 1\n", encoding="utf-8")
    found = dict(over_gate(tmp_path, limit=300))
    assert "long.py" in found
    assert found["long.py"] == 400
    assert "short.py" not in found


def test_over_gate_ignores_bytecode_caches(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.py").write_text("x = 1\n" * 500, encoding="utf-8")
    assert over_gate(tmp_path, limit=300) == []


def test_grandfather_list_parses(tmp_path):
    p = tmp_path / "burndown.md"
    p.write_text(
        "# burn-down\n\n"
        "| file | lines |\n"
        "|---|---|\n"
        "| harness/gateway.py | 2391 |\n"
        "| harness/serve.py | 420 |\n",
        encoding="utf-8")
    g = load_grandfathered(p)
    assert g["harness/gateway.py"] == 2391
    assert g["harness/serve.py"] == 420


def test_missing_burndown_is_an_empty_list_not_a_crash(tmp_path):
    assert load_grandfathered(tmp_path / "nope.md") == {}


def test_the_real_repo_has_a_burndown_covering_every_current_violation():
    root = Path(__file__).resolve().parent.parent
    listed = load_grandfathered(
        root / "project-docs" / "records" / "2026-07-25-file-gate-burndown.md")
    actual = dict(over_gate(root / "harness", limit=300))
    unlisted = [f for f in actual if f"harness/{f}" not in listed]
    assert unlisted == [], f"unlisted violations: {unlisted}"


def test_no_grandfathered_file_has_grown_past_its_frozen_size():
    root = Path(__file__).resolve().parent.parent
    listed = load_grandfathered(
        root / "project-docs" / "records" / "2026-07-25-file-gate-burndown.md")
    actual = dict(over_gate(root / "harness", limit=300))
    grown = {f: (n, listed[f"harness/{f}"]) for f, n in actual.items()
             if f"harness/{f}" in listed and n > listed[f"harness/{f}"]}
    assert grown == {}, f"grew past frozen size: {grown}"


def test_every_file_created_in_phase_0_is_under_the_gate():
    # The new modules must not need grandfathering. If one does, split it.
    root = Path(__file__).resolve().parent.parent
    new = ["verdict.py", "advantages.py", "gateway_auth.py", "gate.py"]
    over = dict(over_gate(root / "harness", limit=300))
    assert [f for f in new if f in over] == []
