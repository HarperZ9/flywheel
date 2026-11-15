"""The three new surfaces (GEMINI.md, the Copilot instructions file, one Cursor
rule), the block scope that none of them can enforce, and the verdict that
holds each target to the downgrades it declared."""
from __future__ import annotations

import pytest

from canon.fidelity import roundtrip_report
from canon.region import extract_region
from canon.schema import Provenance, Record
from canon.textblock import IngestRefused, RenderRefused, ingest_region, render_region
from canon.textblock import recompute_source_hash
from canon.validator import validate_record
from canon.workspace.hosts import cursor_frontmatter_problem, new_host_text
from canon.workspace.identity import derive_identity
from canon.workspace.pool import project_pool
from canon.workspace.store import ProjectStore
from canon.workspace.switch import commit_switch, plan_switch
from canon.workspace.target_fidelity import AT_IMPORT, GLOB, target_roundtrip
from canon.workspace.targets import target_for

from ._workspace_helpers import block, init_repo

SURFACE_TARGETS = ["claude-code", "codex", "gemini-cli", "copilot", "cursor"]


def scoped(rid="react", globs=("src/**/*.tsx", "src/**/*.ts"), body="Use hooks."):
    rec = block(rid, body, 1)
    return Record(rec.kind, rec.id, rec.scope,
                  {**rec.data, "applies_to": list(globs)}, rec.provenance)


def test_a_scoped_block_round_trips_with_a_visible_scope_line():
    text = render_region([scoped()], "workspace")
    assert 'applies="src/**/*.tsx|src/**/*.ts"' in text
    assert "\nApplies to: src/**/*.tsx, src/**/*.ts\nUse hooks.\n" in text
    host = f"<!-- canon:begin scope=workspace -->\n{text}<!-- canon:end -->\n"
    [back] = ingest_region(host)
    assert back.data == {"title": "React", "body": "Use hooks.",
                         "applies_to": ["src/**/*.tsx", "src/**/*.ts"]}
    assert roundtrip_report([scoped()], "workspace").ok


def test_an_unscoped_block_renders_exactly_as_before():
    text = render_region([block("voice", "Plain English.", 3)], "workspace")
    assert text == '<!-- canon:block id="voice" ord="3" -->\n## Voice\nPlain English.\n'
    assert recompute_source_hash("Voice", "Plain English.") == \
        recompute_source_hash("Voice", "Plain English.", None)
    assert recompute_source_hash("Voice", "x") != recompute_source_hash("Voice", "x", ["a"])


def test_an_edited_scope_line_is_refused_not_absorbed():
    text = render_region([scoped()], "workspace").replace(
        "Applies to: src/**/*.tsx, src/**/*.ts", "Applies to: everything")
    with pytest.raises(IngestRefused, match="Applies to"):
        ingest_region(f"<!-- canon:begin scope=workspace -->\n{text}<!-- canon:end -->\n")


@pytest.mark.parametrize("globs", [[], ["a|b"], ['x"y'], [""]])
def test_an_unusable_scope_is_refused_by_the_validator_and_the_renderer(globs):
    rec = scoped(globs=globs)
    assert any("applies_to" in p for p in validate_record(rec))
    with pytest.raises(RenderRefused):
        render_region([rec], "workspace")


@pytest.mark.parametrize("target", SURFACE_TARGETS)
def test_every_target_declares_the_glob_downgrade_and_passes(target):
    verdict = target_roundtrip([scoped(), block("plain", "No scope.", 2)], target)
    assert verdict.ok, verdict
    assert [(d.record_id, d.feature, d.declared) for d in verdict.downgrades] == [
        ("react", GLOB, True)]


@pytest.mark.parametrize("target", SURFACE_TARGETS)
def test_an_undeclared_downgrade_fails_the_verdict(target):
    verdict = target_roundtrip([scoped()], target, declared={})
    assert not verdict.ok
    assert [d.declared for d in verdict.downgrades] == [False]


def test_an_at_path_line_is_an_import_on_claude_code_gemini_and_cursor_only():
    rec = block("setup", "Read @docs/setup.md before a release.", 1)
    for target in ("claude-code", "gemini-cli", "cursor"):
        assert [d.feature for d in target_roundtrip([rec], target).downgrades] == [AT_IMPORT]
    for target in ("codex", "copilot"):
        assert target_roundtrip([rec], target).downgrades == ()
    mail = block("mail", "Mail release@example.com first.", 1)
    assert target_roundtrip([mail], "claude-code").downgrades == ()


def test_the_cursor_rule_needs_always_apply_frontmatter():
    assert cursor_frontmatter_problem(new_host_text("cursor")) is None
    region = "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"
    assert "frontmatter" in cursor_frontmatter_problem(region)
    manual = "---\ndescription: x\nalwaysApply: false\n---\n" + region
    assert "alwaysApply" in cursor_frontmatter_problem(manual)


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    store.put(scoped())
    return repo, ident, store, str(tmp_path / "home")


@pytest.mark.parametrize("target, rel", [
    ("gemini-cli", "GEMINI.md"),
    ("copilot", ".github/copilot-instructions.md"),
    ("cursor", ".cursor/rules/canon.mdc"),
])
def test_switch_creates_each_new_surface_where_its_host_reads_it(project, target, rel):
    repo, ident, store, home = project
    files: dict = {}
    plan = plan_switch(ident, project_pool(store), target_for(target), home=home,
                       read_text=files.get, create=True)
    commit_switch(plan, files.__setitem__)
    [(path, text)] = files.items()
    assert path.replace("\\", "/").endswith("/" + rel)
    assert extract_region(text).present
    assert [r.id for r in ingest_region(text)] == ["react", "canon-workspace-brief"]
    assert any("activation.glob (declared)" in w for w in plan.warnings)
    if target == "cursor":
        assert text.startswith("---\ndescription:") and cursor_frontmatter_problem(text) is None


def test_switch_warns_when_an_existing_cursor_rule_would_not_load(project):
    repo, ident, store, home = project
    path = str((repo / ".cursor" / "rules" / "canon.mdc").resolve())
    files = {path: "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"}
    plan = plan_switch(ident, project_pool(store), target_for("cursor"), home=home,
                       read_text=files.get)
    assert any("frontmatter" in w for w in plan.warnings)
