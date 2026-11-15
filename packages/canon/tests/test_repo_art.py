"""The drawings in the README, held against the code they describe.

The art gate settles whether a drawing fits its columns and matches the spec it
was rendered from. Both sides of that check read the same JSON, so it cannot
settle whether a drawing is TRUE. That is what this file is for: every count the
three drawings put on the page is asserted here against the module that defines
it, so a claim that stops holding fails the suite instead of staying on the page.

One number is self-referential. The card says how many cases the suite carries,
and that total includes the cases below, so the assertion collects the same
directory the claim describes.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from importlib import import_module
from pathlib import Path

from ._helpers import RECORD_FILES, load_dict

# import_module rather than `from canon import canon_check`: the package
# re-exports a function of that same name, so the plain import binds the
# function and every attribute lookup below would fail.
backend_base = import_module("canon.backends.base")
backends = import_module("canon.backends")
canon_check = import_module("canon.canon_check")
drift = import_module("canon.drift")
layering = import_module("canon.layering")
reconcile_run = import_module("canon.reconcile_run")
region = import_module("canon.region")
registry = import_module("canon.registry")
schema = import_module("canon.schema")
vault_reader = import_module("canon.vault_reader")
versions = import_module("canon.versions")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_repo_art as GATE  # noqa: E402

SPEC = json.loads((ROOT / "docs" / "art" / "canon.art.json").read_text(encoding="utf-8"))
CARD = {field["key"]: field for field in SPEC["cards"][0]["fields"]}
SURFACE = next(f for f in SPEC["flows"] if f["file"] == "surface-lane.svg")
VERDICT = next(f for f in SPEC["flows"] if f["file"] == "verdict-lane.svg")
# Collapsed, so a claim is held against the words rather than the line wrap.
README = re.sub(r"\s+", " ", (ROOT / "README.md").read_text(encoding="utf-8"))


def _block(rec_id: str, scope: str, ordinal: int, text: str) -> schema.Record:
    payload = load_dict(RECORD_FILES["personality-block"])
    payload["id"] = rec_id
    payload["scope"] = scope
    payload["data"]["text"] = text
    payload["provenance"]["create_ord"] = ordinal
    payload["provenance"]["native_id"] = f"test:{rec_id}:{scope}"
    return schema.Record.from_dict(payload)


def test_the_art_gate_passes_every_check():
    """The gate runs under pytest too, so the front page is covered by CI."""
    result = GATE.receipt()
    assert [check for check in result["checks"] if not check["passed"]] == []
    assert result["passed"] is True


def test_one_envelope_carries_eight_kinds_under_two_tags():
    assert CARD["record kinds"]["value"] == "eight of them"
    assert len(schema.KINDS) == 5
    assert len(schema.WORKSPACE_KINDS) == 3
    assert schema.ALL_KINDS == schema.KINDS + schema.WORKSPACE_KINDS
    named = CARD["record kinds"]["note"].split(":", 1)[1].split(".")[0]
    assert [word.strip() for word in named.split(",")] == list(schema.KINDS)
    assert "WORKSPACE_KINDS adds three on their own tag" in CARD["record kinds"]["note"]
    tags = {schema.schema_tag_for(kind) for kind in schema.WORKSPACE_KINDS}
    assert tags == {"canon.workspace-state/v1"}
    assert {schema.schema_tag_for(kind) for kind in schema.KINDS} == {"canon.record/v1"}


def test_two_scopes_layer_workspace_over_global():
    assert CARD["scopes"]["value"] == "two, layered"
    assert schema.SCOPES == ("global", "workspace")
    pool = [
        _block("voice", "global", 10, "The global default."),
        _block("voice", "workspace", 20, "The workspace override."),
    ]
    resolved = layering.resolve_blocks(pool, "workspace")
    assert [rec.scope for rec in resolved] == ["workspace"]
    assert resolved[0].data["text"] == "The workspace override."
    assert layering.resolve_blocks(pool, "global")[0].scope == "global"


def test_the_resolve_order_reads_no_clock():
    """The ordinal decides, so a rebuild from the same records is byte-stable."""
    late = _block("a", "global", 90, "Written second.")
    early = _block("b", "global", 10, "Written first.")
    resolved = layering.resolve_blocks([late, early], "global")
    assert [rec.id for rec in resolved] == ["b", "a"]
    stages = {stage["title"]: stage["note"] for stage in SURFACE["stages"]}
    assert stages["Resolve"] == "Current entries, clock-free order."


def test_seven_surfaces_sit_on_the_write_allow_list():
    assert CARD["rendered surfaces"]["value"] == "seven files"
    catalog = registry.SURFACE_CATALOG
    assert len(catalog) == 7
    assert [(s.harness, s.scope, s.relative_path) for s in catalog] == [
        ("claude-code", "global", ".claude/CLAUDE.md"),
        ("claude-code", "workspace", "CLAUDE.md"),
        ("codex", "workspace", "AGENTS.md"),
        ("hermes", "workspace", "SOUL.md"),
        ("gemini-cli", "workspace", "GEMINI.md"),
        ("copilot", "workspace", ".github/copilot-instructions.md"),
        ("cursor", "workspace", ".cursor/rules/canon.mdc"),
    ]


def test_a_path_outside_the_allow_list_is_refused(tmp_path):
    """Without this, "four surfaces" would be a count rather than a boundary."""
    home = str(tmp_path / "home")
    workspace = str(tmp_path / "workspace")
    allowed = registry.allowed_paths(home=home, workspace=workspace)
    assert len(allowed) == 7
    for path in allowed:
        assert registry.is_write_allowed(path, home=home, workspace=workspace)
    stranger = str(tmp_path / "workspace" / "NOTES.md")
    assert not registry.is_write_allowed(stranger, home=home, workspace=workspace)
    other_rule = str(tmp_path / "workspace" / ".cursor" / "rules" / "team.mdc")
    assert not registry.is_write_allowed(other_rule, home=home, workspace=workspace)
    outcomes = {o["label"]: o["note"] for o in SURFACE["outcomes"]}
    assert outcomes["NOT WRITTEN"] == "no region, or not allow-listed"


def test_only_the_span_between_the_markers_is_canon_to_rewrite():
    header = "# Your file\n\nProse you wrote.\n"
    body = "<!-- canon:begin scope=workspace -->\nold\n"
    footer = "<!-- canon:end -->\n\nMore prose you wrote.\n"
    text = header + body + footer
    sliced = region.extract_region(text)
    assert sliced.present is True
    assert sliced.scope == "workspace"
    rewritten = region.splice_region(text, "new\n")
    assert rewritten.startswith(header)
    assert rewritten.endswith("More prose you wrote.\n")
    assert "old" not in rewritten
    assert "new" in rewritten


def test_a_file_with_no_region_is_off_limits_rather_than_an_error():
    sliced = region.extract_region("# Just your file\n")
    assert sliced.present is False
    assert sliced.inner == ""
    assert sliced.prefix == "# Just your file\n"
    labels = [edge["label"] for edge in SURFACE["returns"]]
    assert "NO CANON REGION, NO WRITE" in labels


def test_four_storage_adapters_behind_one_protocol():
    assert CARD["storage adapters"]["value"] == "four of them"
    directory = Path(backends.__file__).parent
    adapters = sorted(
        path.stem
        for path in directory.glob("*.py")
        if path.stem not in {"__init__", "base"}
    )
    assert adapters == ["files", "flywheel", "mneme", "sqlite"]


def test_five_capability_tokens_declare_what_an_adapter_carries():
    assert CARD["capabilities"]["value"] == "five tokens"
    assert sorted(backend_base.CAPABILITIES) == [
        "arbitrary-kind",
        "audit-chain",
        "foreign-provenance",
        "relations",
        "temporal",
    ]
    assert len(backend_base.CAPABILITIES) == 5
    named = CARD["capabilities"]["note"].split(".")[0]
    for token in backend_base.CAPABILITIES:
        assert token in named


def test_twenty_two_seams_each_carry_a_version_pin():
    assert CARD["schema pins"]["value"] == "twenty-two seams"
    assert len(versions.SEAM_PINS) == 22
    assert len(versions.PIN_REGISTRY) == 22
    assert set(versions.PIN_REGISTRY) == set(versions.SEAM_PINS)


def test_the_aggregate_check_folds_four_legs():
    assert CARD["check legs"]["value"] == "four of them"
    report = canon_check.canon_check([])
    assert [
        name
        for name in ("drift", "vault", "vault_symmetric", "persona")
        if hasattr(report, name)
    ] == ["drift", "vault", "vault_symmetric", "persona"]
    named = CARD["check legs"]["note"]
    for word in ("surface drift", "vault round-trip", "read symmetry", "persona"):
        assert word in named


def test_a_leg_with_no_seam_wired_does_not_vote():
    """The drawing says an unwired leg reports nothing; here it is doing that."""
    report = canon_check.canon_check([])
    assert report.drift is None
    assert report.persona is None
    assert report.vault is not None
    assert report.ok is True
    assert canon_check.canon_check_exit_code(report) == 0
    labels = [edge["label"] for edge in VERDICT["returns"]]
    assert "A LEG WITH NO SEAM DOES NOT VOTE" in labels


def test_four_gate_functions_share_one_exit_code():
    assert CARD["gate exit codes"]["value"] == "four functions"
    gates = (
        drift.drift_exit_code,
        reconcile_run.reconcile_exit_code,
        vault_reader.read_exit_code,
        canon_check.canon_check_exit_code,
    )
    assert len(gates) == 4
    assert len({gate.__module__ for gate in gates}) == 4
    stages = {stage["title"]: stage["note"] for stage in VERDICT["stages"]}
    assert stages["Verdict"] == "One exit code, zero or one."


def _source_module_stats() -> tuple[int, int]:
    modules = sorted((ROOT / "src" / "canon").rglob("*.py"))
    lines = sum(
        len(path.read_text(encoding="utf-8").splitlines()) for path in modules
    )
    return len(modules), lines


def test_the_source_tree_is_the_size_the_card_claims():
    modules, lines = _source_module_stats()
    assert CARD["source modules"]["value"] == f"{modules} files"
    assert CARD["source lines"]["value"] == f"{lines:,} lines"


def test_the_roadmap_names_two_surfaces_the_catalog_does_not_carry():
    """The honest null on the card, held against both the README and the code."""
    assert CARD["surfaces not rendered"]["value"] == "two named"
    assert CARD["surfaces not rendered"]["tone"] == "drift"
    assert "the global SOUL.md and the global GEMINI.md surfaces are later phases" in README
    pairs = {(surface.harness, surface.scope) for surface in registry.SURFACE_CATALOG}
    assert ("hermes", "global") not in pairs
    assert ("gemini-cli", "global") not in pairs
    assert ("gemini-cli", "workspace") in pairs


def test_the_suite_carries_the_number_of_tests_the_card_claims():
    """Self-referential on purpose: the count includes the cases in this file.

    Collection, not a run, so this does not recurse into itself. It also has to
    be collection: a parametrized function is one function and many cases, and
    the word on the card is cases.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout[-2000:]
    per_file = re.findall(r"^tests/\S+\.py: (\d+)$", proc.stdout, re.MULTILINE)
    test_files = sorted((ROOT / "tests").glob("test_*.py"))
    assert len(per_file) == len(test_files)
    assert CARD["python tests"]["value"] == f"{sum(int(n) for n in per_file)} cases"


def test_the_note_counts_the_functions_behind_those_cases():
    """The gap between the two numbers is parametrization, so the note says so."""
    found = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += len(
            [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            ]
        )
    test_file_count = len(sorted((ROOT / "tests").glob("test_*.py")))
    assert f"pytest over {test_file_count} files" in CARD["python tests"]["note"]
    assert f"{found} test functions" in CARD["python tests"]["note"]
