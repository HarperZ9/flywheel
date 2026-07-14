"""Release readiness is a measurement, not a mood: each tool in the family
is checked mechanically (repo present, credo placed, belief in the README,
tests present), gaps are named per tool, and the summary counts ready over
total so 'every tool is release capable' is a receipt, not a claim."""

from harness.release_readiness import SCHEMA, readiness_report


def _tool(tmp_path, name, *, credo=True, believes=True, tests=True):
    p = tmp_path / name
    p.mkdir()
    if credo:
        (p / "CREDO.md").write_text("belief", encoding="utf-8")
    (p / "README.md").write_text(
        "# t\n" + ("## What this believes\n" if believes else ""),
        encoding="utf-8")
    if tests:
        (p / "tests").mkdir()
        (p / "tests" / "test_x.py").write_text("def test_a(): pass",
                                               encoding="utf-8")
    return str(p)


def test_a_complete_tool_is_ready(tmp_path):
    doc = readiness_report({"good": _tool(tmp_path, "good")})
    assert doc["schema"] == SCHEMA
    row = doc["tools"][0]
    assert row["ready"] is True
    assert row["gaps"] == []
    assert doc["ready_count"] == 1 and doc["total"] == 1


def test_dart_style_test_names_count(tmp_path):
    p = tmp_path / "dart-tool"
    p.mkdir()
    (p / "CREDO.md").write_text("belief", encoding="utf-8")
    (p / "README.md").write_text("## What this believes\n", encoding="utf-8")
    (p / "test").mkdir()
    (p / "test" / "widget_test.dart").write_text("void main() {}",
                                                 encoding="utf-8")
    doc = readiness_report({"dart-tool": str(p)})
    assert doc["tools"][0]["ready"] is True


def test_a_conformance_runner_counts_as_a_verification_suite(tmp_path):
    p = tmp_path / "vectors-tool"
    p.mkdir()
    (p / "CREDO.md").write_text("belief", encoding="utf-8")
    (p / "README.md").write_text("## What this believes\n", encoding="utf-8")
    (p / "conformance").mkdir()
    (p / "conformance" / "run.py").write_text("# frozen vectors",
                                              encoding="utf-8")
    doc = readiness_report({"vectors-tool": str(p)})
    assert doc["tools"][0]["ready"] is True


def test_gaps_are_named_per_tool(tmp_path):
    doc = readiness_report({
        "no-credo": _tool(tmp_path, "no-credo", credo=False),
        "no-tests": _tool(tmp_path, "no-tests", tests=False),
        "missing": str(tmp_path / "not-there"),
    })
    rows = {r["name"]: r for r in doc["tools"]}
    assert rows["no-credo"]["ready"] is False
    assert "credo" in rows["no-credo"]["gaps"]
    assert "tests" in rows["no-tests"]["gaps"]
    assert rows["missing"]["gaps"] == ["repo missing"]
    assert doc["ready_count"] == 0
    assert doc["all_ready"] is False
