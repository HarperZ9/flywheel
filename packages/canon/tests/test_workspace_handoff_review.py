"""The brief and its receipt as they land: `@path` tokens a host would import,
the drift check and reconcile after a switch, the receipt a switch keeps, the
budget measured on the rendered block, handoff's two files, budget flags,
secrets in a left-out label, the markdown target, and `pull`'s messages."""
from __future__ import annotations

import hashlib
import io
import json

import pytest

from canon.cli import run_cli
from canon.drift import drift_report
from canon.exit_codes import EX_BUDGET, EX_CONFLICT, EX_IO, EX_OK, EX_USAGE
from canon.registry import write_surfaces
from canon.textblock import ingest_region
from canon.workspace import authoring
from canon.workspace.brief import SecretInRender, make_brief
from canon.workspace.identity import derive_identity
from canon.workspace.pool import TaggedRecord, block_pool, project_pool
from canon.workspace.store import ProjectStore
from canon.workspace.target_fidelity import AT_IMPORT, OMITTED, target_roundtrip
from canon.workspace.targets import target_for

from ._workspace_helpers import block, init_repo


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    store.put(block("voice", "Plain technical English.", 1))
    args = ["--workspace", str(repo), "--store", str(store.root), "--home", str(tmp_path / "h")]
    return tmp_path, repo, ident, store, args


def _files(repo):
    def read(path):
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                return handle.read()
        except FileNotFoundError:
            return None

    def write(path, text):
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    return read, write


@pytest.mark.parametrize("target, rel", [("claude-code", "CLAUDE.md"),
                                         ("gemini-cli", "GEMINI.md"),
                                         ("cursor", ".cursor/rules/canon.mdc")])
def test_an_at_path_in_the_brief_stays_text_on_an_import_host(project, target, rel):
    _, repo, _, store, args = project
    store.put(authoring.focus(store, goal="Ship", notes="Read @docs/release.md before tagging"))
    store.put(authoring.work_item(store, title="Check @README against staging"))
    code, out, _ = _run(["--json", "switch", "--to", target, "--create", *args])
    assert code == EX_OK and json.loads(out)["data"]["warnings"] == []
    text = (repo / rel).read_text(encoding="utf-8")
    assert "`@docs/release.md`" in text and "`@README`" in text
    assert " @docs/" not in text and " @README" not in text


def test_bare_name_imports_are_detected_and_code_spans_are_not():
    rec = block("setup", "See @README.md and @package.json for the steps.", 1)
    quoted = block("quoted", "See `@README.md` for the steps.", 1)
    for target in ("claude-code", "gemini-cli", "cursor"):
        assert [d.feature for d in target_roundtrip([rec], target).downgrades] == [AT_IMPORT]
        assert target_roundtrip([quoted], target).downgrades == ()


def test_a_switched_surface_is_a_match_and_reconcile_keeps_the_brief(project):
    _, repo, _, store, args = project
    store.put(authoring.work_item(store, title="Write the tests"))
    assert _run(["switch", "--to", "gemini-cli", "--create", *args])[0] == EX_OK
    blocks = block_pool(project_pool(store))
    read, write = _files(repo)
    report = drift_report(blocks, home=args[5], workspace=str(repo), read_text=read)
    gemini = next(s for s in report.surfaces if s.surface.relative_path == "GEMINI.md")
    assert gemini.verdict == "match" and report.ok
    surfaces = tuple(s.surface for s in report.surfaces if s.surface.relative_path == "GEMINI.md")
    write_surfaces(blocks, home=args[5], workspace=str(repo), read_text=read,
                   write_text=write, surfaces=surfaces)
    ids = [r.id for r in ingest_region((repo / "GEMINI.md").read_text(encoding="utf-8"))]
    assert ids == ["voice", "canon-workspace-brief"]


def _many(store, n):
    for i in range(n):
        store.put(authoring.work_item(store, title=f"Task number {i} of the backlog"))


def test_a_switch_receipt_names_every_left_out_record_and_the_brief_says_how(project):
    tmp_path, repo, _, store, args = project
    _many(store, 40)
    receipt = tmp_path / "r.json"
    code, out, _ = _run(["switch", "--to", "claude-code", "--create", "--budget-bytes", "900",
                         "--receipt", str(receipt), *args])
    assert code == EX_OK
    data = json.loads(receipt.read_text(encoding="utf-8"))
    text = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "The receipt lists every one." not in text
    assert "canon switch --to claude-code --dry-run --receipt FILE lists every one." in text
    assert len(data["left_out"]) > 20 and "- and " in text
    ledger = json.loads((store.project_dir() / "renders.json").read_text(encoding="utf-8"))
    [entry] = ledger["surfaces"].values()
    assert entry["receipt"]["left_out"] == data["left_out"]


def test_the_brief_block_that_lands_fits_the_budget_and_matches_the_receipt(project):
    _, repo, _, store, args = project
    _many(store, 60)
    code, out, _ = _run(["--json", "switch", "--to", "codex", "--create",
                         "--budget-bytes", "1500", *args])
    assert code == EX_OK
    receipt = json.loads(out)["data"]["receipt"]
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    block_text = text[text.index('<!-- canon:block id="canon-workspace-brief"'):
                      text.index("<!-- canon:end -->")]
    assert len(block_text.encode("utf-8")) <= 1500
    assert receipt["rendered_block"]["sha256"] == hashlib.sha256(block_text.encode()).hexdigest()


def test_handoff_checks_both_files_before_writing_either(project):
    tmp_path, _, _, _, args = project
    existing = tmp_path / "brief.md"
    existing.write_text("mine\n", encoding="utf-8")
    receipt = tmp_path / "r.json"
    base = ["handoff", "--to", "codex", *args[:4]]
    code, out, _ = _run(["--json", *base, "--out", str(existing), "--receipt", str(receipt)])
    assert code == EX_CONFLICT and not receipt.exists()
    existing.unlink()
    assert _run([*base, "--out", str(existing), "--receipt", str(receipt)])[0] == EX_OK
    missing = tmp_path / "nodir" / "b.md"
    other = tmp_path / "r2.json"
    code, out, _ = _run(["--json", *base, "--out", str(missing), "--receipt", str(other)])
    assert code == EX_IO and json.loads(out)["failure_code"] == "io_error"
    assert not other.exists()


@pytest.mark.parametrize("flag", ["--budget-bytes", "--budget-lines"])
def test_a_zero_budget_is_a_usage_error(project, flag):
    _, _, _, _, args = project
    assert _run(["handoff", "--to", "codex", flag, "0", *args[:4]])[0] == EX_USAGE


def test_a_secret_in_a_left_out_label_is_refused(project):
    _, _, ident, store, _ = project
    canary = "ghp_" + "z" * 36
    _many(store, 40)
    pool = project_pool(store)
    leak = authoring.build("work-item", "task-99", {"title": "rotate " + canary,
                                                    "status": "open"}, 99)
    with pytest.raises(SecretInRender, match="receipt"):
        make_brief(ident, pool + [TaggedRecord(store.project_id, leak)],
                   target_for("codex"), budget_bytes=1200)


def test_the_markdown_target_names_the_blocks_it_cannot_carry(project):
    _, _, ident, store, _ = project
    brief = make_brief(ident, project_pool(store), target_for("markdown"))
    [excluded] = brief.receipt["excluded"]
    assert excluded["reason"] == "instruction block: the markdown target has no instruction file"
    verdict = target_roundtrip([block("voice", "Plain.", 1)], "markdown")
    assert verdict.ok and [(d.feature, d.declared) for d in verdict.downgrades] == [(OMITTED, True)]


def test_pull_says_what_is_missing_without_suggesting_a_flag_it_lacks(project):
    _, _, _, _, args = project
    code, out, _ = _run(["--json", "workspace", "pull", "--from", "claude-code", *args])
    message = json.loads(out)["message"]
    assert code == EX_USAGE and "nothing to read back" in message and "--create" not in message
    code, out, _ = _run(["--json", "workspace", "pull", "--from", "markdown", *args])
    assert code == EX_USAGE and "no instruction file" in json.loads(out)["message"]


def test_a_budget_too_small_for_the_header_is_still_a_budget_failure(project):
    _, _, _, _, args = project
    assert _run(["handoff", "--to", "codex", "--budget-bytes", "10", *args[:4]])[0] == EX_BUDGET
